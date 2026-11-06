"""Isolated software-mechanism fixtures; no simulator, network, or hardware acceptance."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from hardware_claw import limits
from hardware_claw.contracts.verification import (Requirements, TestPlan, Scenario, Timeline,
    check_requirements, check_plan, compile_timeline)
from hardware_claw.coordinator import Coordinator, TaskStore, WorkflowError
from hardware_claw.projects.service import ProjectService, ROOT
from hardware_claw.runtime import execute_turn
from hardware_claw.stages.verification import attach_verification, validate_saved_plan
from hardware_claw.stages.verification_context import planning_context, project_identity

REQS = {'requirements':[{'id':'R1','description':'fixture requirement','source_line':1}]}
CASE = {'test_id':'T1','requirement_ids':['R1'],'fault_type':'nominal','channel':'serial',
        'reason':'fixture observation','expected_observable':'fixture output, not hardware evidence'}
TIMELINE = {'test_id':'T1','requirement_ids':['R1'],'duration_ms':100,
    'events':[{'at_ms':100,'action':'read','channel':'serial','expected':'fixture output'}]}
IO = {'inputs':{'control':{'action':'set','operation':'wokwi_set_control',
    'arguments':{'partId':'part','control':'position'},'type':'float','range':[0,1]}},
    'outputs':{'serial':{'action':'read','operation':'wokwi_read_serial','arguments':{'clear':True}}}}


class PlanningModel(BaseChatModel):
    mode: str = 'normal'
    _calls: list = PrivateAttr(default_factory=list)
    _bad: bool = PrivateAttr(default=False)
    @property
    def _llm_type(self): return 'offline-planning-fixture'
    def bind_tools(self, tools, **kwargs): return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        usage={'input_tokens':10,'output_tokens':2,'total_tokens':12}
        if kwargs.get('response_format'):
            self._calls.append(messages)
            payload=json.loads(messages[-1].content)
            context=payload['input']
            if 'spec_text' in context:
                data=REQS
                if self.mode=='bad_json' and not self._bad:
                    self._bad=True
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content='{broken',usage_metadata=usage))])
            elif 'scenario' in context:
                data=copy.deepcopy(TIMELINE)
                if self.mode=='bad_channel': data['events'][0]['channel']='not_registered'
            else:
                data={'test_plan':[CASE], 'gaps':[]}
                if self.mode=='all_gaps': data={'test_plan':[], 'gaps':[{'requirement_ids':['R1'],'reason':'not observable'}]}
            msg=AIMessage(content=json.dumps(data),usage_metadata=None if self.mode=='no_usage' else usage)
        else:
            last=messages[-1]
            if not isinstance(last,ToolMessage): name,args='get_task_state',{}
            elif last.name=='get_task_state':
                state=json.loads(last.content)['data']
                name,args='run_stage',{'stage':'verification','objective':'fixture planning',
                    'expected_task_version':state['version'],'expected_project_version':state['project']['version']}
            else: name,args=None,None
            msg=AIMessage(content='' if name else 'Plan only; no simulation.',
                tool_calls=[{'name':name,'args':args,'id':str(len(messages))}] if name else [],usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=msg)])


class ContractTests(unittest.TestCase):
    def test_requirements_and_coverage_reject_missing_unknown_and_duplicate(self):
        reqs=Requirements.model_validate(REQS)
        check_requirements(reqs,['fixture'])
        with self.assertRaises(ValueError): check_requirements(reqs,[])
        with self.assertRaises(ValueError):
            check_requirements(Requirements.model_validate({'requirements':REQS['requirements']*2}),['fixture'])
        for plan in ({'test_plan':[]}, {'test_plan':[CASE|{'requirement_ids':['R2']}]},
                     {'test_plan':[CASE,CASE]}, {'test_plan':[CASE|{'channel':'missing'}]}):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                check_plan(TestPlan.model_validate(plan),reqs,IO)

    def test_compiler_maps_controls_waits_and_evidence_indices(self):
        data=copy.deepcopy(TIMELINE)
        data['events'].insert(0,{'at_ms':0,'action':'set','channel':'control','value':0.5})
        result=compile_timeline(Timeline.model_validate(data),Scenario.model_validate(CASE),IO)
        self.assertEqual([a['operation'] for a in result['actions']],['wokwi_set_control','wait','wokwi_read_serial'])
        self.assertEqual(result['observations'][0]['action_index'],2)
        self.assertEqual(result['actions'][0]['arguments'],{'partId':'part','control':'position','value':0.5})
        self.assertFalse(result['execution_performed'])
        self.assertIn('host_wall',result['time_basis'])

    def test_invalid_events_fail_without_silent_fallback(self):
        for event in ({'at_ms':0,'action':'set','channel':'control','value':2},
            {'at_ms':0,'action':'set','channel':'control','value':True},
            {'at_ms':0,'action':'set','channel':'control','value':float('nan')},
            {'at_ms':0,'action':'read','channel':'missing','expected':'x'},
            {'at_ms':0,'action':'read','channel':'serial'},
            {'at_ms':101,'action':'read','channel':'serial','expected':'x'}):
            data=copy.deepcopy(TIMELINE);data['events']=[event]
            with self.subTest(event=event),self.assertRaises(ValueError):
                compile_timeline(Timeline.model_validate(data),Scenario.model_validate(CASE),IO)

    def test_inserted_wait_overflow_reports_actionable_counts(self):
        data=copy.deepcopy(TIMELINE)
        data['duration_ms']=1700
        data['events']=[{'at_ms':i*100,'action':'read','channel':'serial','expected':'fixture'} for i in range(1,18)]
        with self.assertRaisesRegex(ValueError,'34操作（17个事件\\+17个等待）'):
            compile_timeline(Timeline.model_validate(data),Scenario.model_validate(CASE),IO)

    def test_event_limit_does_not_hide_expanded_limit_or_channel_errors(self):
        data=copy.deepcopy(TIMELINE)
        data['duration_ms']=2600
        data['events']=[{'at_ms':i*100,'action':'read','channel':'serial','expected':'fixture'} for i in range(1,27)]
        data['events'][0]['channel']='unknown'
        original=copy.deepcopy(data)
        value=Timeline.model_validate(data)
        with self.assertRaises(ValueError) as caught:
            compile_timeline(value,Scenario.model_validate(CASE),IO)
        message=str(caught.exception)
        self.assertIn('events数量为26，上限24',message)
        self.assertIn('52操作（26个事件+26个等待）',message)
        self.assertIn('至少减少20个最终操作',message)
        self.assertIn('events[0]',message)
        self.assertEqual(data,original)
        self.assertEqual(Timeline.model_json_schema()['properties']['events']['maxItems'],24)

    def test_event_count_limit_still_applies_when_actions_fit(self):
        data=copy.deepcopy(TIMELINE)
        data['events']=[{'at_ms':0,'action':'read','channel':'serial','expected':'fixture'} for _ in range(25)]
        with self.assertRaisesRegex(ValueError,'events数量为25，上限24'):
            compile_timeline(Timeline.model_validate(data),Scenario.model_validate(CASE),IO)

    def test_counts_include_long_gaps_and_trailing_wait(self):
        data=copy.deepcopy(TIMELINE)
        data['duration_ms']=60000
        data['events']=[{'at_ms':20000,'action':'read','channel':'serial','expected':'fixture'} for _ in range(27)]
        with self.assertRaises(ValueError) as caught:
            compile_timeline(Timeline.model_validate(data),Scenario.model_validate(CASE),IO)
        self.assertIn('33操作（27个事件+6个等待）',str(caught.exception))


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        base=ROOT/'temp/verification-tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.tmp.name)
        self.project=ProjectService.create('fixture','fixture requirement','vscode',workspace=self.root/'projects')
        self.project.update_design(0,{'goal':'fixture','simulation_only':True,
            'board_id':'esp32_s3_devkitc1_n32r16v','components':[], 'connections':[],
            'dependencies':[], 'pin_defines':{},'assumptions':[]})
        self.project.scaffold(1)
        self.project.write_files(2,{'src/main.cpp':'#include <Arduino.h>\nvoid setup() {}\nvoid loop() {}\n'})
        self.store=TaskStore(self.root/'tasks')
        self.c=Coordinator(self.store.create(project_id=self.project.id),store=self.store,project=self.project)
        self.c.begin_turn('fixture planning')
        self.before=project_identity(self.project)
        self.events=[]
        async def emit(k,d):self.events.append((k,d))
        self.emit=emit
        # Any accidental compilation or simulation dispatch is a test failure.
        self.build=patch('hardware_claw.adapters.compiler.compile_project',new=AsyncMock(side_effect=AssertionError('no compilation')))
        self.build_mock=self.build.start()
        self.mcp=patch('hardware_claw.adapters.wokwi_mcp.inspect',new=AsyncMock(side_effect=AssertionError('no simulation')))
        self.mcp_mock=self.mcp.start()
        self.cli=patch('hardware_claw.adapters.simulator.simulate',new=AsyncMock(side_effect=AssertionError('no simulation')))
        self.cli_mock=self.cli.start()

    async def asyncTearDown(self):
        self.build.stop();self.mcp.stop();self.cli.stop();self.tmp.cleanup()

    async def invoke(self,mode='normal'):
        self.model=PlanningModel(mode=mode)
        attach_verification(self.c,self.model,self.emit)
        return await self.c.run_stage('verification','fixture planning',self.c.state()['version'],
                                      expected_project_version=self.project.get()['version'])

    def detail(self,result):
        return self.store.record(self.c.task_id,result['result']['detail_ref'])

    async def test_fixed_pipeline_preserves_project_and_does_not_claim_verified(self):
        result=await self.invoke()
        self.assertEqual(result['status'],'completed',result)
        detail=self.detail(result)
        self.assertEqual(detail['metrics']['model_responses'],3)
        self.assertEqual(detail['metrics']['tokens_reported'],36)
        self.assertEqual(self.c.state()['usage_by_role']['verification']['total_tokens'],36)
        plan=self.store.record(self.c.task_id,result['result']['verification_plan_ref'])
        self.assertFalse(plan['execution_performed'])
        self.assertTrue((Path(detail['path'])/'plan.md').is_file())
        self.assertEqual(project_identity(self.project),self.before)
        self.assertEqual(self.project.delivery()['behavior'],'not_run')
        self.build_mock.assert_not_called()
        self.mcp_mock.assert_not_called()
        self.cli_mock.assert_not_called()
        with self.assertRaises(WorkflowError) as err:
            self.c.deliver(self.c.state()['version'],self.project.get()['version'],'verified')
        self.assertEqual(err.exception.code,'NOT_VERIFIED')
        for call in self.model._calls: self.assertEqual(len(call),2)
        for path in Path(detail['path']).glob('request-*.json'):
            self.assertEqual(json.loads(path.read_text('utf8'))['tools'],[])

    async def test_json_retry_includes_candidate_and_actual_errors_only_current_step(self):
        result=await self.invoke('bad_json')
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(len(self.model._calls),4)
        repaired=json.loads(self.model._calls[1][-1].content)
        self.assertEqual(repaired['correction']['previous_candidate'],'{broken')
        self.assertTrue(repaired['correction']['all_errors'])
        self.assertNotIn('correction',json.loads(self.model._calls[2][-1].content))

    async def test_invalid_case_is_not_silently_dropped(self):
        result=await self.invoke('bad_channel')
        self.assertEqual(result['status'],'blocked')
        self.assertIn('PLAN_INVALID',result['result']['blockers'])
        self.assertEqual(len(self.model._calls),5)
        detail=self.detail(result)
        self.assertFalse((Path(detail['path'])/'plan.json').exists())
        self.assertEqual(len(list(Path(detail['path']).glob('errors-*.json'))),3)

    async def test_budget_stops_next_call_and_preserves_response(self):
        with patch.object(limits,'VERIFICATION_TOTAL_TOKENS',11):
            result=await self.invoke()
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(len(self.model._calls),1)
        self.assertEqual(self.detail(result)['metrics']['tokens_reported'],12)
        self.assertTrue((Path(self.detail(result)['path'])/'requirements.json').is_file())
        with self.assertRaises(WorkflowError):self.c.check_budget()

    async def test_missing_usage_stops_unmetered_calls(self):
        result=await self.invoke('no_usage')
        self.assertEqual(result['status'],'blocked')
        self.assertIn('USAGE_MISSING',result['result']['blockers'])
        self.assertEqual(len(self.model._calls),1)
        self.assertFalse(self.detail(result)['metrics']['usage_complete'])

    async def test_all_gaps_cannot_be_completed(self):
        result=await self.invoke('all_gaps')
        self.assertEqual(result['status'],'blocked')
        self.assertIn('NO_EXECUTABLE_SCENARIOS',result['result']['blockers'])
        self.assertEqual(len(self.model._calls),2)

    async def test_changed_project_invalidates_record(self):
        result=await self.invoke()
        with self.store.edit(self.c.task_id) as (state,_): state['active_run']=result['run_id']
        validate_saved_plan(self.c,result['result']['verification_plan_ref'])
        self.project.write_files(self.project.get()['version'],{'README.md':'changed fixture'})
        with self.assertRaises(WorkflowError) as err:
            validate_saved_plan(self.c,result['result']['verification_plan_ref'])
        self.assertEqual(err.exception.code,'UNPROVEN_COMPLETION')

    async def test_main_routes_to_builtin_planner_and_includes_child_usage(self):
        self.c.builtin_stages=True
        status=await execute_turn(PlanningModel(),'fixture planning',[],self.emit,coordinator=self.c)
        self.assertEqual(status,'completed')
        summary=next(d for k,d in reversed(self.events) if k=='summary')
        self.assertEqual(summary['tokens_reported'],72)
        self.assertEqual(summary['model_responses'],6)
        self.assertTrue(any(k=='verification_plan' for k,_ in self.events))
        self.assertEqual(project_identity(self.project),self.before)

    async def test_context_is_local_and_includes_scope_without_api_docs(self):
        context=planning_context(self.c,{'objective':'only inspect startup','user_request':'fixture planning'})
        self.assertNotIn('only inspect startup',context['spec_lines'])
        self.assertEqual(context['planning_request']['objective'],'only inspect startup')
        self.assertEqual(context['spec_lines'],['fixture requirement'])
        self.assertIn('serial',context['io_map']['outputs'])
        self.assertTrue(context['documents'])
        self.assertFalse(any('/drivers/' in ref for ref in context['documents']))
        self.assertEqual(project_identity(self.project),self.before)


if __name__=='__main__': unittest.main()
