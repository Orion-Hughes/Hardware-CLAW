"""Fixed generation child: selected hardware -> design/files -> checked build."""
import asyncio
import json
import uuid
from pathlib import Path
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model, model_validator

from .. import limits
from ..coordinator.contracts import StrictModel, StageResult
from ..coordinator.store import WorkflowError
from ..coordinator.service import TOKEN_STOPS
from ..projects.service import ProjectError
from ..tools.hardware_catalog import read_hardware, ReadHardwareInput, _invalid_input
from ..tools.project_tools import make_project_tools
from ..tools.templates import load_template
from .common import StageTrace
from .generation_finish import finish_candidate
from .selection_state import SelectionEvidence, accepted_baseline
from ..validation.files import REQUIRED

ROOT = Path(__file__).resolve().parents[2]
PROJECT_TOOLS = {'get_project', 'update_project_design', 'scaffold_project', 'read_project_file',
                 'write_project_files', 'apply_project_patch'}


class GenerationReport(StrictModel):
    """Submit the current candidate for host checks; only the host can complete delivery."""
    status: Literal['candidate', 'needs_input', 'blocked', 'failed']
    summary: str = Field(min_length=1, max_length=2000)
    project_version: int | None = Field(default=None, ge=0)
    hardware_ids: list[str] = Field(default_factory=list, max_length=32)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    decisions: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    blockers: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=32)
    next_stage: Literal['verification'] | None = None


class GenerationReadInput(ReadHardwareInput):
    view: Literal['usage'] = 'usage'


class GenerationTrace(StageTrace):
    def __init__(self, coordinator, selected_ids):
        super().__init__(coordinator, role='generation', report_name='GenerationReport')
        self.selected = set(selected_ids)
        self.evidence = SelectionEvidence()
        self.loaded, self.required_docs, self.included_docs = set(), set(), set()
        self.repetitions = {}
        self.read_plans, self.read_blockers = [], {}
        self.authored_revision = None

    def usage_status(self):
        """Stage-wide progress; a successful supplement is not the entire stage."""
        unread = sorted(self.selected - self.loaded)
        missing = self.required_docs - self.included_docs
        calls = [{'tool': 'read_hardware', 'args': {
            'hardware_ids': unread[i:i+8], 'view': 'usage',
            'max_characters': limits.HARDWARE_READ_CHARACTERS}} for i in range(0, len(unread), 8)]
        planned = set()
        for call in reversed(self.read_plans):
            refs = [r for r in call['args']['references'] if r in missing and r not in planned and r not in self.read_blockers]
            if refs:
                calls.append({'tool': call['tool'], 'args': call['args'] | {'references': refs}})
                planned.update(refs)
        return {'ready': not unread and not missing, 'unread_hardware_ids': unread,
                'missing_required_refs': sorted(missing), 'next_reads': calls,
                'blockers': [b for r, b in self.read_blockers.items() if r in missing],
                'scope': 'generation_required_sources_not_functional_validation'}

    def require_usage(self):
        if self.selected - self.loaded:
            raise WorkflowError('UNREAD_HARDWARE', '生成前需读取所选器件usage资料；执行data.next_reads后再提交。此次未写入工程。')
        missing = sorted(self.required_docs - self.included_docs)
        if missing:
            raise WorkflowError('MISSING_USAGE_SOURCE', f'必要原文尚未返回：{missing}。执行data.next_reads；有blockers则报告缺口。'
                                '无需重新查询候选或重读整包，此次未写入工程。')

    def validate_design(self, design):
        value = design.model_dump() if hasattr(design, 'model_dump') else design
        ids = {value['board_id'], *(c['hardware_id'] for c in value['components'])}
        if ids != self.selected:
            raise WorkflowError('SELECTION_SCOPE', '设计必须使用已确认器件；增加/删除型号需先回到selection。')

    def make_tools(self):
        sources = [read_hardware, load_template, *[t for t in make_project_tools(self.coordinator.project) if t.name in PROJECT_TOOLS]]
        def wrap(source):
            async def invoke(**kwargs):
                kwargs = {k: v.model_dump() if hasattr(v, 'model_dump') else v for k, v in kwargs.items()}
                try:
                    self.coordinator.check_budget()
                    if source.name == 'read_hardware' and set(kwargs['hardware_ids']) - self.selected:
                        raise WorkflowError('SELECTION_SCOPE', '只能读取已确认器件；新选型请交回主Agent。')
                    if source.name in {'update_project_design', 'scaffold_project', 'write_project_files', 'apply_project_patch'}:
                        self.require_usage()
                        if source.name == 'update_project_design':
                            self.validate_design(kwargs['design'])
                        else:
                            design = self.coordinator.project.get()['design']
                            if design is not None:
                                self.validate_design(design)
                    stamp = (source.name, json.dumps(kwargs, ensure_ascii=False, sort_keys=True), self.coordinator.project.get()['version'])
                    self.repetitions[stamp] = self.repetitions.get(stamp, 0) + 1
                    if self.repetitions[stamp] > 2:
                        error = WorkflowError('GENERATION_NO_PROGRESS', '同一修订上相同工具参数已调用两次，停止重复循环。')
                        self.coordinator.stop_model_calls(error)
                        raise error
                    result = await source.ainvoke(kwargs)
                except WorkflowError as exc:
                    if self.coordinator.model_stop_reason is not None:
                        raise
                    result = {'execution_status':'error','error_code':exc.code,'summary':str(exc),
                              'data': self.usage_status() if exc.code in {'UNREAD_HARDWARE', 'MISSING_USAGE_SOURCE'} else None}
                self.events.append({'kind':'tool','name':source.name,'args':kwargs,'result':result})
                if result.get('execution_status') == 'ok' and source.name in {'write_project_files', 'apply_project_patch'}:
                    version = result['data']['version']
                    self.authored_revision = max(version, self.authored_revision or 0)
                if source.name == 'read_hardware' and isinstance(result, dict) and result.get('execution_status') == 'ok':
                    data = result['data']
                    self.evidence.observe(data)
                    self.loaded.update(h['id'] for h in data.get('hardware', []) if 'simulation' in h)
                    self.read_plans.extend(data.get('next_reads', []))
                    for d in data.get('documents', []):
                        self.read_blockers.pop(d['ref'], None)
                        if d.get('essential_for'):
                            self.required_docs.add(d['ref'])
                        if d['status'] == 'included':
                            self.included_docs.add(d['ref'])
                    self.read_blockers.update({b['ref']: b for b in data.get('blockers', [])})
                    # Keep the host-stage envelope outside the tool's data JSON budget.
                    result['stage_usage'] = self.usage_status()
                return result
            wrapped = StructuredTool.from_function(coroutine=invoke, name=source.name, description=source.description,
                args_schema=GenerationReadInput if source.name == 'read_hardware' else source.args_schema)
            wrapped.handle_validation_error = _invalid_input
            return wrapped
        return [wrap(t) for t in sources]

    def validate(self, report):
        if set(report.source_refs) - set(self.evidence.hashes):
            raise WorkflowError('UNREAD_SOURCE', '报告引用必须来自本轮实际返回的来源。')
        if report.status != 'candidate':
            return
        self.require_usage()
        if report.blockers or set(report.hardware_ids) != self.selected:
            raise WorkflowError('INCOMPLETE_GENERATION', '候选提交必须保留全部已选器件且无未解决阻碍。')
        p = self.coordinator.project.get()
        if p['design'] is None:
            raise WorkflowError('DESIGN_REQUIRED', '尚未保存设计。')
        self.validate_design(p['design'])
        if report.project_version != p['version']:
            raise WorkflowError('PROJECT_VERSION_CONFLICT', '候选报告不是当前工程修订。')

    def recover_candidate(self, request):
        """Keep a saved complete revision when the token stop preempts the report."""
        p = self.coordinator.project.get()
        version = self.authored_revision
        if (version is None or version == request['expected_project_version'] or p['version'] != version
                or not p['design'] or p['design_version'] != p['files_design_version']
                or not REQUIRED[p['template']] <= {f['path'] for f in p['files']}):
            return None
        proposal = GenerationReport(status='candidate', project_version=version, hardware_ids=sorted(self.selected),
                                    summary='模型预算耗尽前已保存候选；程序接管检查。')
        self.validate(proposal)
        self.events.append({'kind': 'candidate_recovered', 'version': version})
        return proposal


class GenerationExecutor:
    creates_project = True

    def __init__(self, model, coordinator, emit=None):
        self.model, self.coordinator, self.emit = model, coordinator, emit

    async def __call__(self, request):
        _, baseline = accepted_baseline(self.coordinator)
        if baseline['invalidated'] or not baseline['reusable_ids']:
            raise WorkflowError('STALE_SELECTION', '已接受选型证据不可用，先重新选型。')
        selected = self.coordinator.store.record(self.coordinator.task_id, baseline['handoff_ref'])['result']
        trace = GenerationTrace(self.coordinator, selected['hardware_ids'])
        detail_id = uuid.uuid4().hex
        context = {k: request.get(k) for k in ('objective','original_request','user_request','project_id','expected_project_version')}
        context['selection'] = {k: selected.get(k) for k in ('requirements','hardware_ids','decisions','assumptions','compatibility')}
        context['feedback'] = [{'stage':h['stage'],'status':h['status'],'summary':h['result']['summary']}
            for h in request['handoffs'] if h['stage'] != 'selection']
        prompt = (ROOT/'prompts/generation.md').read_text('utf8') + '\n\n' + (ROOT/'skills/stages/generation.md').read_text('utf8')
        prompt += '\n\n' + (ROOT/'skills/firmware_and_observation.md').read_text('utf8')
        last_error = None
        @model_validator(mode='after')
        def audit(value):
            nonlocal last_error
            last_error = None
            try: trace.validate(value)
            except WorkflowError as exc:
                last_error = exc
                raise
            return value
        schema = create_model('GenerationReport', __base__=GenerationReport, __validators__={'audit':audit})
        def invalid_report(exc):
            if isinstance(getattr(exc,'ai_message',None), AIMessage): trace.record_message(exc.ai_message)
            trace.reject_report(last_error or WorkflowError('INVALID_HANDOFF','两次报告校验失败，停止。'))
            return f'宿主拒绝报告：{last_error or "Schema格式错误"}。提交当前候选修订或说明阻碍。'
        graph = create_agent(self.model, tools=trace.make_tools(), system_prompt=prompt,
            response_format=ToolStrategy(schema, handle_errors=invalid_report), middleware=[trace,
                ModelCallLimitMiddleware(run_limit=limits.GENERATION_MODEL_CALLS, exit_behavior='error'),
                ToolCallLimitMiddleware(run_limit=limits.GENERATION_TOOL_CALLS, exit_behavior='error')])
        report, proposed, error = None, None, None
        if self.emit: await self.emit('stage_start',{'stage':'generation','run_id':request['run_id']})
        try:
            async with asyncio.timeout(limits.GENERATION_TIMEOUT_SECONDS):
                try:
                    output = await graph.ainvoke({'messages':[HumanMessage(content=json.dumps(context, ensure_ascii=False))]},
                        config={'recursion_limit':128})
                    proposed = output.get('structured_response')
                except WorkflowError as exc:
                    if exc.code not in TOKEN_STOPS:
                        raise
                    proposed = trace.recover_candidate(request)
                    if proposed is None:
                        raise
                if proposed is None:
                    raise WorkflowError('MISSING_REPORT','生成子Agent未提交有效报告。')
                trace.validate(proposed)
                values = proposed.model_dump()
                if proposed.status == 'candidate':
                    version = await finish_candidate(trace, request['run_id'], proposed.project_version, self.model)
                    values.update(status='completed', project_version=version,
                                  summary='程序已检查、编译并导出当前修订。功能状态以实际验证记录为准。')
                report = StageResult.model_validate(values)
        except asyncio.CancelledError:
            error = 'CANCELLED'
            report = StageResult(status='cancelled',summary='生成已取消，已有文件保留。')
            raise
        except Exception as exc:
            expected = isinstance(exc, (WorkflowError, ProjectError))
            error = exc.code if expected else type(exc).__name__
            report = StageResult(status='blocked' if expected else 'failed',
                summary=f'生成未完成：{error}。' + (str(exc) if expected else '详见阶段记录。'), blockers=[error])
        finally:
            report = report or StageResult(status='failed',summary='生成未返回结果。')
            report.detail_ref = detail_id
            metrics = trace.metrics()
            with self.coordinator.store.connect() as con:
                self.coordinator.store.save_record(con,self.coordinator.task_id,{'run_id':detail_id,'kind':'generation_detail',
                    'stage_run_id':request['run_id'],'context':context,'events':trace.events,'metrics':metrics,'error_code':error,
                    'proposed_result':proposed.model_dump() if proposed else None,'result':report.model_dump()})
            if self.emit: await self.emit('stage_summary',metrics | {'status':report.status,'detail_ref':detail_id})
        return report.model_dump()


def attach_generation(coordinator, model, emit=None):
    if coordinator.executors.get('generation') is None or isinstance(coordinator.executors['generation'], GenerationExecutor):
        if 'max_tokens' in type(model).model_fields:
            model = model.model_copy(update={'max_tokens':limits.PROJECT_OUTPUT_TOKENS})
        coordinator.executors['generation'] = GenerationExecutor(model, coordinator, emit)
