"""FTA-style fixed planning pipeline. No simulator or build tools are imported/called."""
import asyncio
import json
import time
import uuid
from pathlib import Path
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError
from .. import limits
from ..contracts.verification import (Requirements, TestPlan, Timeline, check_requirements,
                                       check_plan, compile_timeline)
from ..coordinator.contracts import StageResult
from ..coordinator.store import WorkflowError
from ..projects.service import atomic_json, digest
from .verification_context import planning_context, project_identity

ROOT = Path(__file__).resolve().parents[2]
SIMULATION_EXECUTION_ENABLED = False


def parse_json(raw):
    text = raw.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    return json.loads(text, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'非法JSON数值:{x}')))


class Planner:
    def __init__(self, coordinator, model, folder, emit=None):
        self.coordinator, self.model, self.folder, self.emit = coordinator, model, folder, emit
        self.calls, self.usage, self.rounds = 0, [], []
        self.started = time.monotonic()

    def metrics(self):
        return {'role':'verification', 'api_attempts':self.calls,'model_responses':len(self.usage),
            'elapsed_seconds':round(time.monotonic()-self.started,3),'usage':self.usage,
            'input_tokens_reported':sum(u.get('input_tokens',0) for u in self.usage if u),
            'output_tokens_reported':sum(u.get('output_tokens',0) for u in self.usage if u),
            'tokens_reported':sum(u.get('total_tokens',0) for u in self.usage if u),
            'usage_complete':len(self.usage)==self.calls and all(u is not None for u in self.usage),
            'tool_calls':0}

    def budget(self):
        self.coordinator.check_budget()
        if self.metrics()['tokens_reported'] >= limits.VERIFICATION_TOTAL_TOKENS or self.calls >= limits.VERIFICATION_MODEL_CALLS:
            exc = WorkflowError('VERIFICATION_BUDGET','规划已达预算，保留候选，不继续调用')
            self.coordinator.stop_model_calls(exc)
            raise exc

    async def ask(self, step, key, schema, context, validate):
        instruction = (ROOT/'prompts/verification'/f'{step}.md').read_text('utf8')
        example = (ROOT/'templates/verification'/f'{step}.json').read_text('utf8')
        schema_text = json.dumps(schema.model_json_schema(),ensure_ascii=False)
        system = instruction+'\n输出Schema:\n'+schema_text+'\n格式示例(占位通道必须替换):\n'+example
        previous, errors = None, None
        for attempt in range(1,4):
            self.budget()
            payload = {'input':context}
            if errors is not None:
                payload['correction'] = {'previous_candidate':previous,'all_errors':errors,
                                         'instruction':'只修正当前候选，返回完整修正JSON。'}
            body = json.dumps(payload,ensure_ascii=False)
            self.calls += 1
            number = self.calls
            request = {'step':step,'key':key,'attempt':attempt,
                'messages':[{'role':'system','content':system},{'role':'user','content':body}],
                'response_format':{'type':'json_object'},'tools':[],
                'characters':{'instruction':len(instruction),'schema':len(schema_text),'example':len(example),
                    'context':len(json.dumps(context,ensure_ascii=False)),
                    'correction':len(json.dumps(payload.get('correction',{}),ensure_ascii=False)),
                    'system':len(system),'user':len(body)}}
            atomic_json(self.folder/f'request-{number:03d}.json',request)
            start = time.monotonic()
            try:
                response = await self.model.bind(response_format={'type':'json_object'}).ainvoke(
                    [SystemMessage(content=system),HumanMessage(content=body)])
            except Exception as exc:
                atomic_json(self.folder/f'response-{number:03d}.json',
                    {'error_type':type(exc).__name__,'usage':None,'elapsed_seconds':time.monotonic()-start})
                raise WorkflowError('MODEL_REQUEST_FAILED',f'模型请求失败:{type(exc).__name__}；请求已保留') from exc
            usage = dict(response.usage_metadata) if response.usage_metadata else None
            self.usage.append(usage)
            self.coordinator.record_usage(usage,role='verification')
            raw = response.content
            record = {'step':step,'key':key,'attempt':attempt,'round':number,
                'content':raw,'usage':usage,'response_metadata':response.response_metadata,
                'elapsed_seconds':round(time.monotonic()-start,3),'characters':request['characters']}
            self.rounds.append(record)
            atomic_json(self.folder/f'response-{number:03d}.json',record)
            if self.emit: await self.emit('planning_response',{k:v for k,v in record.items() if k not in {'content','response_metadata'}})
            if usage is None:
                exc = WorkflowError('USAGE_MISSING','提供方未返回用量，保留响应并停止后续付费调用')
                self.coordinator.stop_model_calls(exc)
                raise exc
            previous = raw
            try:
                if not isinstance(raw,str): raise ValueError('需要JSON文本响应')
                candidate = parse_json(raw)
                value = schema.model_validate(candidate)
                validate(value)
                atomic_json(self.folder/f'{key}.json',value.model_dump())
                return value
            except (ValueError,TypeError) as exc:
                errors = exc.errors(include_input=False,include_context=False,include_url=False) if isinstance(exc,ValidationError) else [str(exc)]
                atomic_json(self.folder/f'errors-{number:03d}.json',{'errors':errors,'candidate':raw})
        raise WorkflowError('PLAN_INVALID',f'{key}三次提交仍未通过:{errors}')


def render_plan(record):
    lines = ['# 仿真计划（未执行）','',f"工程：{record['project_id']}，版本：{record['project_version']}",
             '', '仅生成和静态校验计划；未编译、未仿真、未自动判定功能。',
             '仿真执行归属verification阶段；当前执行模块未启用。',
             'at_ms为宿主相对调度时间，不是精确仿真时间；expected为文字判据，不是已实现的自动断言。', '', '## 需求']
    for r in record['requirements']: lines.append(f"- {r['id']}：{r['description']}（原文行{r['source_line']}）")
    for scenario,timeline,compiled in zip(record['test_plan'],record['timelines'],record['compiled']):
        lines.extend(['',f"## {scenario['test_id']}：{scenario['reason']}",
            '关联需求：'+', '.join(scenario['requirement_ids']), '预期：'+scenario['expected_observable'],
            '', '|计划时间 ms|动作|通道|值|观察预期|','|---:|---|---|---|---|'])
        for e in timeline['events']:
            cells=[e['at_ms'],e['action'],e['channel'],json.dumps(e.get('value'),ensure_ascii=False),e.get('expected') or '']
            lines.append('| '+' | '.join(str(c).replace('|','\\|').replace('\n','<br>') for c in cells)+' |')
        lines.extend(['',f"程序转换：{len(compiled['actions'])}个MCP/等待操作，{len(compiled['observations'])}个采证点；每例独立会话。"])
    lines.extend(['','## 无法覆盖或需人工判断的部分'])
    lines.extend('- '+', '.join(g['requirement_ids'])+'：'+g['reason'] for g in record['gaps'])
    lines.extend(['','完整操作参数见同目录plan.json；逐轮请求、响应和校验错误保留。'])
    return '\n'.join(lines)+'\n'


class VerificationExecutor:
    planning_only = True

    def __init__(self,model,coordinator,emit=None):
        self.model,self.coordinator,self.emit = model,coordinator,emit

    async def __call__(self,request):
        c = self.coordinator
        ident = uuid.uuid4().hex
        folder = c.project.meta/'verification_plans'/ident
        folder.mkdir(parents=True,exist_ok=False)
        planner = Planner(c,self.model,folder,self.emit)
        report, context, error = None, None, None
        if self.emit: await self.emit('stage_start',{'stage':'verification','mode':'fta_planning_only','run_id':ident})
        try:
            async with asyncio.timeout(limits.VERIFICATION_TIMEOUT_SECONDS):
                context = planning_context(c,request)
                atomic_json(folder/'context.json',context)
                numbered = '\n'.join(f'{i}: {line}' for i,line in enumerate(context['spec_lines'],1))
                reqs = await planner.ask('requirements','requirements',Requirements,
                    {'spec_text':numbered,'planning_request':context['planning_request']},
                    lambda v:check_requirements(v,context['spec_lines']))
                shared = {k:context[k] for k in ('io_map','constraints','documents','project_files','source_gaps','planning_request')}
                shared['original_spec'] = numbered
                plan = await planner.ask('plan','test_plan',TestPlan,
                    {**shared,'requirements':reqs.model_dump()['requirements']},
                    lambda v:check_plan(v,reqs,context['io_map']))
                timelines,compiled = [],[]
                for scenario in plan.test_plan:
                    relevant = [r.model_dump() for r in reqs.requirements if r.id in scenario.requirement_ids]
                    timeline = await planner.ask('timeline',f'timeline-{scenario.test_id}',Timeline,
                        {**shared,'requirements':relevant,'scenario':scenario.model_dump()},
                        lambda v:compile_timeline(v,scenario,context['io_map']))
                    timelines.append(timeline.model_dump())
                    compiled.append(compile_timeline(timeline,scenario,context['io_map']))
                if project_identity(c.project)!=context['project_identity']:
                    raise WorkflowError('STALE_PLAN','工程已变化，旧输入不定稿')
                record = {'run_id':ident,'kind':'verification_plan','stage_run_id':request['run_id'],
                    'project_id':c.project.id,'project_version':context['project_version'],
                    'project_identity':context['project_identity'],'execution_performed':False,
                    'simulation_execution_enabled':SIMULATION_EXECUTION_ENABLED,
                    'status':'planned_with_gaps' if plan.gaps else 'planned',
                    **reqs.model_dump(),**plan.model_dump(),'timelines':timelines,'compiled':compiled}
                record['plan_sha256'] = digest(json.dumps(record,ensure_ascii=False,sort_keys=True))
                atomic_json(folder/'plan.json',record)
                (folder/'plan.md').write_text(render_plan(record),encoding='utf8',newline='\n')
                with c.store.connect() as con: c.store.save_record(con,c.task_id,record)
                report = StageResult(status='completed' if compiled else 'blocked',
                    summary=f'FTA规划完成：{len(compiled)}场景，{len(plan.gaps)}覆盖缺口；未执行仿真或功能验收。',
                    project_version=context['project_version'],verification_plan_ref=ident,
                    blockers=[] if compiled else ['NO_EXECUTABLE_SCENARIOS'],
                    decisions=[str(folder/'plan.md')])
                if self.emit: await self.emit('verification_plan',{'path':str(folder/'plan.md'),'plan_ref':ident,
                    'execution_performed':False,'cases':len(compiled),'gaps':len(plan.gaps)})
        except asyncio.CancelledError:
            error='CANCELLED'; report=StageResult(status='cancelled',summary='规划取消；已保存请求与候选，未仿真。')
            raise
        except Exception as exc:
            error=getattr(exc,'code',type(exc).__name__)
            report=StageResult(status='blocked',summary=f'规划未完成：{error}；保留所有中间结果，未仿真。',blockers=[error])
            atomic_json(folder/'failure.json',{'code':error,'message':str(exc)})
        finally:
            report=report or StageResult(status='failed',summary='规划未完成')
            detail_id=uuid.uuid4().hex
            report.detail_ref=detail_id
            detail={'run_id':detail_id,'kind':'verification_detail','stage_run_id':request['run_id'],
                'path':str(folder),'metrics':planner.metrics(),'rounds':planner.rounds,'error_code':error}
            atomic_json(folder/'metrics.json',detail['metrics'])
            with c.store.connect() as con: c.store.save_record(con,c.task_id,detail)
            if self.emit: await self.emit('stage_summary',detail['metrics']|{'status':report.status,'detail_ref':detail_id})
        return report.model_dump()


def validate_saved_plan(coordinator,ref):
    record=coordinator.store.record(coordinator.task_id,ref)
    payload={k:v for k,v in record.items() if k!='plan_sha256'}
    if (record.get('kind')!='verification_plan' or record.get('execution_performed') is not False
        or record.get('stage_run_id')!=coordinator.store.load(coordinator.task_id)['active_run']
        or record.get('project_identity')!=project_identity(coordinator.project)
        or not record.get('compiled')
        or record.get('plan_sha256')!=digest(json.dumps(payload,ensure_ascii=False,sort_keys=True))):
        raise WorkflowError('UNPROVEN_COMPLETION','缺少本次当前工程的有效规划记录')
    return record


def attach_verification(coordinator,model,emit=None):
    if coordinator.executors.get('verification') is None or isinstance(coordinator.executors['verification'],VerificationExecutor):
        if 'max_tokens' in getattr(type(model), 'model_fields', {}):
            model=model.model_copy(update={'max_tokens':limits.VERIFICATION_OUTPUT_TOKENS})
        coordinator.executors['verification']=VerificationExecutor(model,coordinator,emit)
