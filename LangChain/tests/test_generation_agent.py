"""Generation orchestration fixtures; fake build artifacts never leave root temp."""
import asyncio
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import PrivateAttr

from hardware_claw import limits
from hardware_claw.coordinator import Coordinator, TaskStore, WorkflowError
from hardware_claw.projects.service import ProjectService, ROOT, atomic_json
from hardware_claw.adapters.compiler import fingerprint
from hardware_claw.stages.generation import GenerationTrace, attach_generation
from hardware_claw.stages.selection_state import SelectionEvidence
from hardware_claw.tools.hardware_catalog import read_hardware
from hardware_claw.runtime import execute_turn

BOARD = 'esp32_s3_devkitc1_n32r16v'
DESIGN = {'goal':'software mechanism fixture','simulation_only':True,'board_id':BOARD,
          'components':[],'connections':[],'dependencies':[],'assumptions':[],'pin_defines':{}}
SOURCE = '#include <Arduino.h>\nvoid setup(){ Serial.begin(115200); Serial.println("HWCLAW_BOOT"); }\nvoid loop(){ delay(100); }\n'


class GenerationModel(BaseChatModel):
    mode: str = 'normal'
    _malformed: bool = PrivateAttr(default=False)
    @property
    def _llm_type(self): return 'generation-test-fixture'
    def bind_tools(self, tools, **kwargs): return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        child = '生成子Agent' in messages[0].content
        last = messages[-1]
        if '一次性提交最小文字补丁' in messages[0].content:
            old = 'void loop(){ delay(100); }' if self.mode == 'bad_repair' else 'void cycle(){ delay(100); }'
            edit = {'path':'src/main.cpp','old_text':old,'new_text':'void loop(){ delay(75); }'}
            msg = AIMessage(content='', tool_calls=[{'name':'GenerationRepair','args':{'edits':[edit]},'id':'repair'}],
                            usage_metadata={'input_tokens':10,'output_tokens':2,'total_tokens':12})
            return ChatResult(generations=[ChatGeneration(message=msg)])
        prior = [json.loads(m.content)['data'] for m in messages if isinstance(m,ToolMessage)
                 and m.name in {'get_project','update_project_design','scaffold_project','write_project_files'}
                 and json.loads(m.content).get('data')]
        version = prior[-1]['version'] if prior else 0
        if child:
            report = {'status':'candidate','summary':'fixture candidate','hardware_ids':[BOARD],'project_version':version}
            if self.mode == 'claim': name,args='GenerationReport',report
            elif not isinstance(last,ToolMessage) or self.mode == 'loop': name,args='get_project',{}
            elif last.name=='get_project': name,args='read_hardware',{'hardware_ids':[BOARD]}
            elif last.name=='read_hardware': name,args='update_project_design',{'expected_version':version,'design':DESIGN}
            elif last.name=='update_project_design': name,args='scaffold_project',{'expected_version':version}
            elif last.name=='scaffold_project':
                source = SOURCE.replace('void loop', 'void cycle') if self.mode in {'repair','bad_repair'} else SOURCE
                name,args='write_project_files',{'expected_version':version,'files':{'src/main.cpp':source,'README.md':'software fixture only'}}
            elif last.name=='write_project_files' and json.loads(last.content).get('error_code')=='INVALID_TOOL_JSON':
                name,args='write_project_files',{'expected_version':version,
                     'files':{'src/main.cpp':SOURCE,'README.md':'software fixture only'}}
            elif last.name=='write_project_files' and self.mode=='preempted_report': name,args='get_project',{}
            else: name,args='GenerationReport',report
            if name=='write_project_files' and self.mode in {'file_json','file_json_repeat'} and (
                    not self._malformed or self.mode=='file_json_repeat'):
                self._malformed=True
                msg=AIMessage(content='',invalid_tool_calls=[{'id':f'bad-write-{len(messages)}','name':name,
                     'args':'{"expected_version":2,"files":{','error':'JSON'}],
                    usage_metadata={'input_tokens':10,'output_tokens':2,'total_tokens':12})
                return ChatResult(generations=[ChatGeneration(message=msg)])
            if name=='GenerationReport' and self.mode=='json' and not self._malformed:
                self._malformed=True
                msg=AIMessage(content='',invalid_tool_calls=[{'id':'bad','name':name,'args':'{"summary":bad}','error':'JSON'}],
                    usage_metadata={'input_tokens':10,'output_tokens':2,'total_tokens':12})
                return ChatResult(generations=[ChatGeneration(message=msg)])
        elif not isinstance(last,ToolMessage): name,args='get_task_state',{}
        elif last.name=='get_task_state':
            d=json.loads(last.content)['data']
            name,args='run_stage',{'stage':'generation','objective':'fixture generate','expected_task_version':d['version'],
                'expected_project_version':d['project']['version'] if d['project'] else None}
        else: name,args=None,None
        msg=AIMessage(content='' if name else 'fixture result, not hardware acceptance',
            tool_calls=[{'name':name,'args':args,'id':str(len(messages))}] if name else [],
            usage_metadata={'input_tokens':10,'output_tokens':2,'total_tokens':12})
        return ChatResult(generations=[ChatGeneration(message=msg)])


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_required_progress_and_rejection_supply_executable_next_reads(self):
        await self.child()
        ids = [BOARD, 'ps2_joystick', 'st7789_240x240_simulation']
        trace = GenerationTrace(self.c, ids)
        tools = {t.name: t for t in trace.make_tools()}
        version = self.c.project.get()['version']
        first = await tools['read_hardware'].ainvoke({'hardware_ids': ids, 'max_characters': 32000})
        missing = set(first['stage_usage']['missing_required_refs'])
        self.assertTrue(missing)
        self.assertFalse(first['stage_usage']['ready'])
        bad = await tools['update_project_design'].ainvoke({'expected_version': version, 'design': DESIGN})
        self.assertEqual(bad['error_code'], 'MISSING_USAGE_SOURCE')
        self.assertEqual(set(bad['data']['missing_required_refs']), missing)
        self.assertTrue(bad['data']['next_reads'])
        # A single requested source can be complete without completing stage-wide usage.
        call = bad['data']['next_reads'][0]
        partial_args = call['args'] | {'references': call['args']['references'][:1]}
        partial = await tools['read_hardware'].ainvoke(partial_args)
        self.assertTrue(partial['data']['complete'])
        self.assertFalse(partial['stage_usage']['ready'])
        self.assertEqual(set(partial['stage_usage']['missing_required_refs']), missing - set(partial_args['references']))
        for call in partial['stage_usage']['next_reads']:
            reply = await tools[call['tool']].ainvoke(call['args'])
            self.assertTrue(reply['data']['complete'])
        self.assertTrue(trace.usage_status()['ready'])
        self.assertEqual(trace.usage_status()['next_reads'], [])
        self.assertEqual(self.c.project.get()['version'], version)

    async def asyncSetUp(self):
        base=ROOT/'temp/generation-tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base); self.root=Path(self.tmp.name)
        store=TaskStore(self.root/'tasks')
        self.c=Coordinator(store.create(),store=store)
        self.c.begin_turn('fixture generate')
        evidence=SelectionEvidence();evidence.observe(read_hardware.invoke({'hardware_ids':[BOARD],'view':'selection'})['data'])
        result={'status':'completed','summary':'fixture selection','requirements':['fixture'],'hardware_ids':[BOARD],'detail_ref':'b'*32}
        with store.edit(self.c.task_id) as (state,con):
            state['latest']['selection']='a'*32
            store.save_record(con,self.c.task_id,{'run_id':'a'*32,'stage':'selection','status':'completed','result':result})
            store.save_record(con,self.c.task_id,{'run_id':'b'*32,'kind':'selection_detail','stage_run_id':'a'*32,'result':result,'selection_snapshot':evidence.dump([BOARD])})
        real_create=ProjectService.create
        self.factory=patch.object(ProjectService,'create',side_effect=lambda title,requirement,template:real_create(title,requirement,template,workspace=self.root/'projects'))
        self.factory.start()

    async def asyncTearDown(self):
        self.factory.stop();self.tmp.cleanup()

    async def fake_compile(self, project, version):
        state=project._load(); attempt=uuid.uuid4().hex; artifacts={}
        for name in ('firmware.bin','firmware.elf'):
            path=project.meta/'builds'/attempt/name;path.parent.mkdir(parents=True,exist_ok=True)
            data=b'TEST_DOUBLE_ONLY';path.write_bytes(data)
            artifacts[name]={'sha256':hashlib.sha256(data).hexdigest(),'path':str(path)}
        report={'version':version,'source_sha256':fingerprint(state),'verdict':'pass','attempt':attempt,'artifacts':artifacts}
        atomic_json(project.meta/'build.json',report)
        return report

    async def child(self, mode='normal', expected=None):
        attach_generation(self.c,GenerationModel(mode=mode))
        with patch('hardware_claw.adapters.compiler.compile_project',side_effect=self.fake_compile):
            return await self.c.run_stage('generation','fixture',self.c.state()['version'],expected_project_version=expected)

    async def test_child_creates_binds_and_records_only_its_usage(self):
        result=await self.child()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.c.state()['project_id'],self.c.project.id)
        detail=self.c.store.record(self.c.task_id,result['result']['detail_ref'])
        self.assertEqual(detail['metrics']['model_responses'],6)
        self.assertEqual(self.c.state()['usage_by_role']['generation']['total_tokens'],72)
        self.assertEqual(self.c.project.get()['file_check']['verdict'],'pass')
        self.assertEqual(self.c.project.delivery()['behavior'],'not_run')
        self.assertNotIn('messages',detail['context'])

    async def test_parent_routes_generation_delivers_and_reports_new_binding(self):
        self.c.builtin_stages=True; events=[]
        async def emit(k,d):events.append((k,d))
        with patch('hardware_claw.adapters.compiler.compile_project',side_effect=self.fake_compile):
            status=await execute_turn(GenerationModel(),'fixture generate',[],emit,coordinator=self.c)
        self.assertEqual(status,'completed')
        summary=events[-1][1]
        self.assertEqual(summary['model_responses'],9)
        self.assertEqual(summary['tokens_reported'],108)
        self.assertEqual(summary['project']['delivery_status'],'ready_for_vscode')
        self.assertEqual(summary['project']['behavior'],'not_run')

    async def test_followup_reuses_same_project_and_versions(self):
        await self.child();ident=self.c.project.id;old=self.c.project.get()['version']
        self.c.begin_turn('fixture modify')
        result=await self.child(expected=old)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.c.project.id,ident)
        self.assertGreater(self.c.project.get()['version'],old)
        restored=Coordinator(self.c.task_id,store=self.c.store,project=ProjectService.open(ident,workspace=self.root/'projects'))
        self.assertEqual(restored.project.id,ident)

    async def test_claim_without_usage_or_build_is_rejected(self):
        result=await self.child('claim')
        self.assertEqual(result['result']['blockers'],['UNREAD_HARDWARE'])
        self.assertNotIn('generation',self.c.state()['latest'])

    async def test_token_stop_prevents_parent_or_stage_restart_in_turn(self):
        with patch.object(limits,'GENERATION_TOTAL_TOKENS',24):
            result=await self.child()
        self.assertEqual(result['result']['blockers'],['GENERATION_TOKEN_BUDGET'])
        with self.assertRaises(WorkflowError): self.c.check_budget()
        with self.assertRaises(WorkflowError): await self.child()
        self.c.begin_turn('new explicit request');self.c.check_budget()

    async def test_budget_after_candidate_write_still_exports_without_extra_call(self):
        with patch.object(limits,'GENERATION_TOTAL_TOKENS',72), patch.object(limits,'COORDINATOR_TOTAL_TOKENS',60+1):
            result=await self.child()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.c.project.delivery()['delivery_status'],'ready_for_vscode')
        self.assertNotIn('generation_repair_reserve',self.c.state())

    async def test_model_limit_still_checks_fresh_candidate_without_another_model_call(self):
        for mode, expected in (('normal', 'completed'), ('repair', 'blocked')):
            with self.subTest(mode=mode):
                version = self.c.project.get()['version'] if self.c.project else None
                self.c.begin_turn('check bounded candidate recovery')
                with patch.object(limits, 'GENERATION_MODEL_CALLS', 5):
                    result = await self.child(mode, expected=version)
                self.assertEqual(result['status'], expected)
                detail = self.c.store.record(self.c.task_id, result['result']['detail_ref'])
                self.assertEqual(detail['metrics']['api_attempts'], 5)
                self.assertEqual([e['reason'] for e in detail['events'] if e['kind']=='candidate_recovered'],
                                 ['ModelCallLimitExceededError'])
                self.assertTrue(any(e['kind']=='candidate_check' for e in detail['events']))
                self.assertFalse(any(e['kind']=='candidate_repair_request' for e in detail['events']))

    async def test_token_stop_before_report_recovers_candidate_and_parent_does_not_recall(self):
        self.c.builtin_stages=True; events=[]
        async def emit(k,d):events.append((k,d))
        # The sixth child response requests another tool, but the budget has now been exhausted.
        with patch.object(limits,'COORDINATOR_TOTAL_TOKENS',85), \
                patch('hardware_claw.adapters.compiler.compile_project',side_effect=self.fake_compile):
            status=await execute_turn(GenerationModel(mode='preempted_report'),'fixture generate',[],emit,coordinator=self.c)
        self.assertEqual(status,'completed')
        self.assertEqual(events[-1][1]['project']['delivery_status'],'ready_for_vscode')
        self.assertEqual(events[-1][1]['main_model_responses'],2)

    async def test_one_extra_repair_for_actionable_diagnostics(self):
        with patch.object(limits,'GENERATION_TOTAL_TOKENS',72):
            result=await self.child('repair')
        self.assertEqual(result['status'],'completed')
        self.assertIn('delay(75)',self.c.project.read_file('src/main.cpp')['content'])
        detail=self.c.store.record(self.c.task_id,result['result']['detail_ref'])
        self.assertEqual(detail['metrics']['api_attempts'],7)
        self.assertEqual([e['reserve'] for e in detail['events'] if e['kind']=='candidate_repair_request'],[True])
        self.assertEqual([e['step'] for e in detail['events'] if e['kind']=='candidate_check'],['static','build'])
        self.assertIsNotNone(self.c.state().get('generation_repair_reserve'))

    async def test_out_of_scope_extra_repair_preserves_candidate_and_reserve_is_spent(self):
        with patch.object(limits,'GENERATION_TOTAL_TOKENS',72):
            result=await self.child('bad_repair')
        self.assertEqual(result['result']['blockers'],['REPAIR_SCOPE'])
        self.assertIn('void cycle',self.c.project.read_file('src/main.cpp')['content'])
        self.assertNotEqual(self.c.project.delivery()['delivery_status'],'ready_for_vscode')
        first = self.c.state()['generation_repair_reserve']
        self.c.begin_turn('retry fixture')
        with patch.object(limits,'GENERATION_TOTAL_TOKENS',72):
            retry=await self.child('repair',expected=self.c.project.get()['version'])
        self.assertEqual(retry['result']['blockers'],['CANDIDATE_STATIC_FAILED'])
        self.assertEqual(self.c.state()['generation_repair_reserve'],first)

    async def test_compiler_infrastructure_failure_does_not_consume_extra_request(self):
        attach_generation(self.c,GenerationModel())
        with patch.object(limits,'GENERATION_TOTAL_TOKENS',72), \
                patch('hardware_claw.adapters.compiler.compile_project',
                      return_value={'verdict':'fail','diagnostics':['UnknownPackageError: Could not find the package']}):
            result=await self.c.run_stage('generation','fixture',self.c.state()['version'])
        self.assertEqual(result['result']['blockers'],['CANDIDATE_BUILD_FAILED'])
        self.assertNotIn('generation_repair_reserve',self.c.state())

    async def test_repeat_tool_loop_stops_without_spending_full_budget(self):
        result=await self.child('loop')
        self.assertEqual(result['result']['blockers'],['GENERATION_NO_PROGRESS'])
        detail=self.c.store.record(self.c.task_id,result['result']['detail_ref'])
        self.assertEqual(detail['metrics']['model_responses'],3)

    async def test_generation_report_uses_shared_json_repair(self):
        result=await self.child('json')
        self.assertEqual(result['status'],'completed')
        detail=self.c.store.record(self.c.task_id,result['result']['detail_ref'])
        feedback=[e for e in detail['events'] if e['kind']=='submission_feedback' and 'INVALID_REPORT_JSON' in e['content']]
        self.assertEqual(len(feedback),1)
        self.assertIn('GenerationReport Schema',feedback[0]['content'])
        self.assertEqual(detail['metrics']['model_responses'],7)

    async def test_invalid_file_arguments_are_returned_to_same_agent_and_resubmitted(self):
        result=await self.child('file_json')
        self.assertEqual(result['status'],'completed')
        detail=self.c.store.record(self.c.task_id,result['result']['detail_ref'])
        feedback=[e for e in detail['events'] if e['kind']=='tool_argument_feedback']
        self.assertEqual(len(feedback),1)
        self.assertFalse(json.loads(feedback[0]['content'])['executed'])
        self.assertEqual(detail['metrics']['model_responses'],7)
        self.assertEqual(self.c.project.get()['version'],3)

    async def test_invalid_file_argument_retries_stop_without_writes(self):
        result=await self.child('file_json_repeat')
        self.assertEqual(result['result']['blockers'],['INVALID_TOOL_JSON'])
        self.assertEqual(self.c.project.get()['version'],2)
        self.assertNotIn('src/main.cpp', [f['path'] for f in self.c.project.get()['files']])

    async def test_scope_and_tool_surface(self):
        await self.child()
        trace=GenerationTrace(self.c,[BOARD]);tools={t.name:t for t in trace.make_tools()}
        self.assertEqual(set(tools),{'read_hardware','load_template','get_project','update_project_design','scaffold_project',
            'read_project_file','write_project_files','apply_project_patch'})
        bad=await tools['read_hardware'].ainvoke({'hardware_ids':['sg90_180']})
        self.assertEqual(bad['error_code'],'SELECTION_SCOPE')
        await tools['read_hardware'].ainvoke({'hardware_ids':[BOARD]})
        design=DESIGN|{'components':[{'instance_id':'extra','hardware_id':'sg90_180'}]}
        bad=await tools['update_project_design'].ainvoke({'expected_version':self.c.project.get()['version'],'design':design})
        self.assertEqual(bad['error_code'],'SELECTION_SCOPE')

    async def test_changed_or_missing_selection_cannot_create_project(self):
        with self.c.store.edit(self.c.task_id) as (state,_):state['latest']={}
        result=await self.child()
        self.assertEqual(result['error_code'],'MISSING_HANDOFF');self.assertIsNone(self.c.project)

    async def test_missing_evidence_cannot_create_project(self):
        with self.c.store.connect() as con:
            self.c.store.save_record(con,self.c.task_id,{'run_id':'b'*32,'kind':'wrong'})
        result=await self.child()
        self.assertEqual(result['error_code'],'STALE_SELECTION');self.assertIsNone(self.c.project)

    async def test_cancel_keeps_project_and_releases_active_stage(self):
        async def hang(*args,**kwargs): await asyncio.sleep(30)
        attach_generation(self.c,GenerationModel())
        with patch.object(GenerationModel,'_agenerate',hang):
            task=asyncio.create_task(self.c.run_stage('generation','fixture',self.c.state()['version']))
            await asyncio.sleep(0.15);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNotNone(self.c.project)
        self.assertIsNone(self.c.state()['active_run'])
        self.assertEqual(self.c.state()['latest_outcome'],'cancelled')
