"""Coordinator mechanics with isolated fake executors; no hardware acceptance or API calls."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from pydantic import PrivateAttr
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from hardware_claw.coordinator import Coordinator, TaskStore, WorkflowError
from hardware_claw.coordinator.agent import make_coordinator_tools, build_coordinator
from hardware_claw.coordinator.store import ROOT
from hardware_claw.runtime import execute_turn
from hardware_claw import limits


class ParentModel(BaseChatModel):
    """Test double follows actual task versions returned by host tools."""
    _step: int = PrivateAttr(default=0)
    @property
    def _llm_type(self): return 'offline-coordinator-fixture'
    def bind_tools(self, tools, **kwargs):
        assert {t.name for t in tools} == {'get_task_state', 'run_stage', 'deliver_project', 'read_task_evidence'}
        return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._step += 1
        if self._step == 1:
            calls = [{'name': 'get_task_state', 'args': {}, 'id': 'state', 'type': 'tool_call'}]
        elif self._step == 2:
            result = json.loads(next(m.content for m in reversed(messages) if isinstance(m, ToolMessage)))
            calls = [{'name': 'run_stage', 'args': {'stage': 'selection', 'objective': '资料选型任务',
                'expected_task_version': result['data']['version']}, 'id': 'stage', 'type': 'tool_call'}]
        else:
            calls = []
        msg = AIMessage(content='' if calls else '阶段尚未接入，未完成选型或生成。', tool_calls=calls,
                        usage_metadata={'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15})
        return ChatResult(generations=[ChatGeneration(message=msg)])


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        root = ROOT / 'temp/coordinator-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.store = TaskStore(Path(self.tmp.name))
        self.ident = self.store.create()
        self.c = Coordinator(self.ident, store=self.store)
        self.c.begin_turn('讨论一个硬件方案')

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def invoke(self, stage='selection', **kwargs):
        return await self.c.run_stage(stage, 'fixture task', self.store.load(self.ident)['version'], **kwargs)

    def test_tool_surface_and_fixed_enum(self):
        tools = make_coordinator_tools(self.c)
        self.assertEqual([t.name for t in tools], ['get_task_state', 'run_stage', 'deliver_project', 'read_task_evidence'])
        self.assertNotIn('spawn_agent', [t.name for t in tools])
        self.assertEqual(tools[1].args['stage']['enum'], ['selection', 'generation', 'verification'])

    async def test_current_failure_is_read_and_delegated_once(self):
        from hardware_claw.projects.service import ProjectService
        project = ProjectService.create('evidence', 'evidence fixture', workspace=Path(self.tmp.name) / 'projects')
        with self.store.edit(self.ident) as (state, _):
            state['project_id'] = project.id
        self.c.project = project
        self.c.executors['selection'] = AsyncMock(return_value={
            'status': 'completed', 'summary': 'selected', 'hardware_ids': ['dht22_red_module'], 'requirements': ['input']})
        await self.invoke()
        seen = []
        async def generation(request):
            seen.append(request)
            ref = 'a'*32 if len(seen) == 1 else 'b'*32
            with self.store.connect() as con:
                self.store.save_record(con, self.ident, {'run_id': ref, 'kind': 'generation_detail',
                    'stage_run_id': request['run_id'], 'events': [{'kind': 'candidate_check', 'step': 'static',
                    'version': 0, 'report': {'verdict': 'fail', 'issues': [{'code': 'MISSING_ENTRY', 'path': 'src/main.cpp'}]}}]})
            return {'status': 'blocked', 'summary': 'failed check', 'detail_ref': ref}
        self.c.executors['generation'] = generation
        first = await self.invoke('generation', expected_project_version=0)
        tool = {t.name:t for t in make_coordinator_tools(self.c)}['read_task_evidence']
        reply = tool.invoke({'kind':'stage', 'ref':first['evidence_ref']})['data']
        self.assertEqual(reply['checks'][0]['issues'][0]['code'], 'MISSING_ENTRY')
        self.assertTrue(reply['repair_action']['available'])
        self.assertEqual(reply['repair_action']['args']['repair_from'], first['evidence_ref'])
        self.assertNotIn('next_offset', reply)
        self.assertEqual(first['diagnosis']['checks'][0]['issues'][0]['code'], 'MISSING_ENTRY')
        self.assertEqual(tool.invoke({'kind':'stage', 'ref':'0'*32})['error_code'], 'INVALID_REFERENCE')
        with self.assertRaisesRegex(WorkflowError, 'repair_from'):
            await self.invoke('generation', expected_project_version=0)
        with self.assertRaises(WorkflowError) as stale:
            await self.invoke('generation', expected_project_version=1, repair_from=first['evidence_ref'])
        self.assertEqual(stale.exception.code, 'PROJECT_VERSION_CONFLICT')
        second = await self.invoke('generation', expected_project_version=0, repair_from=first['evidence_ref'])
        self.assertEqual(seen[-1]['repair_evidence']['check']['issues'][0]['code'], 'MISSING_ENTRY')
        with self.assertRaises(WorkflowError) as exhausted:
            await self.invoke('generation', expected_project_version=0, repair_from=second['evidence_ref'])
        self.assertEqual(exhausted.exception.code, 'REPAIR_LIMIT')
        self.assertEqual(len(seen), 2)

    async def test_unavailable_persists_blocker_without_fake_handoff(self):
        result = await self.invoke()
        self.assertEqual(result['error_code'], 'STAGE_UNAVAILABLE')
        self.assertEqual(result['status'], 'blocked')
        state = Coordinator(self.ident, store=TaskStore(Path(self.tmp.name))).state()
        self.assertIsNone(state['active_run'])
        self.assertEqual(state['latest'], {})
        self.assertEqual(state['recent_runs'], [result['run_id']])
        self.assertEqual(state['latest_outcome'], 'blocked')

    async def test_successful_handoff_is_compact_and_supplied_to_next_stage(self):
        async def selected(request):
            self.assertNotIn('messages', request)
            return {'status': 'completed', 'summary': '选型fixture', 'hardware_ids': ['dht22_red_module'],
                    'requirements': ['测量温度']}
        self.c.executors['selection'] = selected
        first = await self.invoke()
        self.assertEqual(first['status'], 'completed')
        seen = []
        async def next_selection(request):
            seen.append(request)
            return {'status': 'needs_input', 'summary': '请补充需求', 'blockers': ['missing constraint']}
        self.c.executors['selection'] = next_selection
        second = await self.invoke()
        self.assertEqual(seen[0]['handoffs'][0]['run_id'], first['run_id'])
        self.assertNotIn('handoffs', second)
        self.assertEqual(second['input_refs'], [first['run_id']])
        state = self.c.state()
        self.assertEqual(state['latest']['selection'], first['run_id'])
        self.assertEqual(state['stage_progress']['selection'], {
            'accepted_ref': first['run_id'], 'accepted_project_version': None,
            'latest_status': 'needs_input', 'blockers': ['missing constraint'], 'summary': '请补充需求'})
        self.assertEqual(state['stage_progress']['generation']['latest_status'], 'not_started')
        self.assertNotIn('next_stage', state['handoffs'][0]['result'])

    async def test_legacy_stage_hint_does_not_affect_restored_task(self):
        self.c.executors['selection'] = AsyncMock(return_value={
            'status': 'completed', 'summary': 'accepted', 'hardware_ids': ['dht22_red_module'],
            'requirements': ['measurement']})
        first = await self.invoke()
        first['result']['next_stage'] = 'generation'
        with self.store.connect() as con:
            self.store.save_record(con, self.c.task_id, first)
        state = self.c.state()
        self.assertEqual(state['stage_progress']['selection']['accepted_ref'], first['run_id'])
        self.assertNotIn('next_stage', state['handoffs'][0]['result'])
        self.assertEqual(self.store.record(self.c.task_id, first['run_id'])['result']['next_stage'], 'generation')

    async def test_unknown_hardware_cannot_be_saved_as_completed(self):
        async def invalid(request):
            return {'status':'completed','summary':'fixture','hardware_ids':['invented-device']}
        self.c.executors['selection'] = invalid
        result = await self.invoke()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error_code'], 'NOT_FOUND')
        self.assertEqual(self.c.state()['latest'], {})

    async def test_historical_reference_cannot_override_current_selection(self):
        async def selected(request):
            return {'status': 'completed', 'summary': 'fixture', 'hardware_ids': ['dht22_red_module'],
                    'requirements': ['measurement']}
        self.c.executors['selection'] = selected
        first = await self.invoke()
        current = await self.invoke()
        seen = []
        async def generation(request):
            seen.append(request)
            return {'status': 'blocked', 'summary': 'fixture stops before generation'}
        self.c.executors['generation'] = generation
        with patch.object(self.c, '_check_project_version', return_value={'version': 1}):
            await self.invoke('generation', input_refs=[first['run_id']], expected_project_version=1)
        self.assertEqual(seen[0]['current_handoffs']['selection'], current['run_id'])
        self.c.executors['selection'] = AsyncMock(return_value={'status': 'needs_input', 'summary': 'unresolved revision'})
        await self.invoke()
        result = await self.invoke('generation', input_refs=[first['run_id']])
        self.assertEqual(result['error_code'], 'MISSING_HANDOFF')
        self.assertEqual(len(seen), 1)

    async def test_stale_version_and_cross_task_reference_rejected(self):
        old = self.c.state()['version']
        first = await self.invoke()
        with self.assertRaises(WorkflowError) as caught:
            await self.c.run_stage('selection', 'stale', old)
        self.assertEqual(caught.exception.code, 'TASK_VERSION_CONFLICT')
        other = Coordinator(self.store.create(), store=self.store)
        with self.assertRaises(WorkflowError) as caught:
            await other.run_stage('selection', 'foreign', 0, [first['run_id']])
        self.assertEqual(caught.exception.code, 'INVALID_REFERENCE')
        self.assertIsNone(other.state()['active_run'])

    async def test_cancel_and_concurrency_release_active_stage(self):
        entered = asyncio.Event()
        async def slow(request):
            entered.set()
            await asyncio.Event().wait()
        self.c.executors['selection'] = slow
        task = asyncio.create_task(self.invoke())
        await entered.wait()
        with self.assertRaises(WorkflowError) as caught:
            await self.invoke()
        self.assertEqual(caught.exception.code, 'TASK_BUSY')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertIsNone(self.c.state()['active_run'])
        self.assertEqual(self.c.state()['latest_outcome'], 'cancelled')

    async def test_timeout_and_invalid_output_do_not_complete(self):
        async def slow(request): await asyncio.sleep(1)
        self.c.executors['selection'] = slow
        with patch.object(limits, 'COORDINATOR_STAGE_TIMEOUT_SECONDS', 0.01):
            self.assertEqual((await self.invoke())['error_code'], 'STAGE_TIMEOUT')
        async def invalid(request): return {'status': 'completed'}
        self.c.executors['selection'] = invalid
        self.assertEqual((await self.invoke())['error_code'], 'INVALID_HANDOFF')
        self.assertIsNone(self.c.state()['active_run'])

    async def test_generation_needs_handoff_and_verification_needs_current_build(self):
        executor = AsyncMock(return_value={'status':'completed','summary':'claim','project_version':2})
        self.c.executors['generation'] = executor
        self.assertEqual((await self.invoke('generation'))['error_code'], 'MISSING_HANDOFF')
        executor.assert_not_called()
        project = Mock(id='fixture-project')
        project.get.return_value = {'version': 2, 'file_check': None, 'build': None}
        ident = self.store.create(project.id)
        c = Coordinator(ident, store=self.store, project=project, executors={'verification': executor})
        result = await c.run_stage('verification','test',0,expected_project_version=2)
        self.assertEqual(result['error_code'],'BUILD_REQUIRED')
        executor.assert_not_called()

    async def test_completion_claim_cannot_replace_host_evidence(self):
        project = Mock(id='fixture-project')
        project.get.return_value = {'version': 2, 'file_check': {'verdict':'pass'}, 'build': {'verdict':'pass'}, 'behavior':'unsupported'}
        executor = AsyncMock(return_value={'status':'completed','summary':'model says pass','project_version':2})
        c = Coordinator(self.store.create(project.id), store=self.store, project=project, executors={'verification':executor})
        result = await c.run_stage('verification','check',0,expected_project_version=2)
        self.assertEqual(result['error_code'],'UNPROVEN_COMPLETION')
        self.assertEqual(c.state()['latest'], {})

    def test_verified_delivery_cannot_export_unsupported_result(self):
        project = Mock(id='fixture-project')
        project.get.return_value = {'version': 2}
        project.delivery.return_value = {'behavior': 'unsupported'}
        c = Coordinator(self.store.create(project.id), store=self.store, project=project)
        with self.assertRaises(WorkflowError) as caught:
            c.deliver(0, 2, 'verified')
        self.assertEqual(caught.exception.code, 'NOT_VERIFIED')
        project.export.assert_not_called()
        self.assertEqual(c.state()['version'], 0)

    async def test_usage_is_persistent_without_invalidating_tool_version(self):
        version = self.c.state()['version']
        self.c.record_usage({'input_tokens':10,'output_tokens':5,'total_tokens':15})
        self.c.record_usage(None)
        state = self.c.state()
        self.assertEqual(state['version'],version)
        self.assertEqual(state['usage']['total_tokens'],15)
        self.assertFalse(state['budget']['usage_complete'])
        with patch.object(limits, 'COORDINATOR_TOTAL_TOKENS', 15):
            with self.assertRaises(WorkflowError): await self.invoke()

    async def test_real_langchain_loop_reports_blocked_not_completed(self):
        events, history = [], []
        async def emit(kind, data): events.append((kind,data))
        status = await execute_turn(ParentModel(), '请选型', history, emit, coordinator=self.c)
        self.assertEqual(status, 'blocked')
        summary = events[-1][1]
        self.assertEqual(summary['model_responses'], 3)
        self.assertEqual(summary['tool_requests'], 2)
        self.assertEqual(summary['tokens_reported'], 45)
        self.assertTrue(summary['usage_complete'])
        self.assertEqual(summary['coordinator']['usage']['total_tokens'], 45)
        self.assertEqual(len(history), 2)
        self.assertNotEqual(summary.get('log_status'), 'write_failed')

    async def test_budget_middleware_blocks_next_model_call(self):
        self.c.record_usage({'input_tokens':1,'output_tokens':1,'total_tokens':2})
        with patch.object(limits, 'COORDINATOR_TOTAL_TOKENS', 2):
            with self.assertRaises(WorkflowError):
                await build_coordinator(ParentModel(), self.c).ainvoke({'messages':[('user','hello')]})
