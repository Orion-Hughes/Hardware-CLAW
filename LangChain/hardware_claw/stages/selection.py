"""Read-only selection agent with isolated context and auditable handoffs."""
import asyncio
import json
import uuid
from pathlib import Path
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model, model_validator

from .. import limits
from ..coordinator.contracts import StageResult
from ..coordinator.store import WorkflowError
from ..tools.hardware_catalog import HARDWARE_TOOLS, ReadHardwareInput, _invalid_input
from .selection_state import SelectionEvidence, accepted_baseline
from .common import StageTrace

ROOT = Path(__file__).resolve().parents[2]


class SelectionReport(StageResult):
    """Submit the final selection handoff after consulting tools; never claim runtime validation."""
    next_stage: Literal['generation'] | None = None
    detail_ref: None = None  # Assigned by the host, never invented by the model.
    project_version: None = None
    selection_update: None = None  # Host computes changes, not a model claim.


class SelectionReadInput(ReadHardwareInput):
    view: Literal['selection', 'usage'] = Field(default='selection',
        description='选型默认selection。usage仅允许带references定向补读，不允许加载整包编程原文。')


class SelectionTrace(StageTrace):
    def __init__(self, coordinator, evidence=None, baseline=None):
        super().__init__(coordinator, role='selection', report_name='SelectionReport')
        self.evidence = evidence or SelectionEvidence()
        self.baseline = baseline or {'reusable_ids': [], 'previous': {}, 'invalidated': []}
        self.observed, self.sources = self.evidence.items, set(self.evidence.hashes)
        self.read_ids, self.failed_ids = set(), set()

    def make_tools(self):
        def wrap(source):
            async def invoke(**kwargs):
                reused = []
                actual = dict(kwargs)
                if source.name == 'read_hardware' and kwargs.get('view', 'selection') == 'selection':
                    reused = [i for i in kwargs['hardware_ids'] if i in self.baseline['reusable_ids']]
                    actual['hardware_ids'] = [i for i in kwargs['hardware_ids'] if i not in reused]
                if source.name == 'read_hardware' and kwargs.get('view') == 'usage' and not kwargs.get('references'):
                    result = {'execution_status': 'error', 'error_code': 'STAGE_SCOPE',
                        'summary': '选型只能使用selection视图；核对具体参数时用usage并指定已登记references，不能整包加载编程资料。',
                        'data': None}
                elif reused and not actual['hardware_ids'] and not kwargs.get('references'):
                    result = {'execution_status': 'ok', 'error_code': None, 'data': {
                        'mode': 'selection_reuse', 'hardware': [], 'reused_hardware_ids': reused,
                        'note': '宿主已提供这些器件的有效选型资料，请使用accepted_selection，不再重复读取。'}}
                else:
                    result = await source.ainvoke(actual)
                    if reused and isinstance(result, dict) and result.get('data'):
                        result['data']['reused_hardware_ids'] = reused
                self.events.append({'kind': 'tool', 'name': source.name, 'args': kwargs, 'result': result})
                if source.name == 'read_hardware' and isinstance(result, dict) and result.get('execution_status') == 'ok':
                    data = result['data']
                    self.evidence.observe(data)
                    self.sources.update(self.evidence.hashes)
                    self.failed_ids.update(e['hardware_id'] for e in data.get('errors', []) if e.get('hardware_id'))
                    for item in data.get('hardware', []):
                        if 'simulation' in item:
                            self.read_ids.add(item['id'])
                            self.failed_ids.discard(item['id'])
                return result
            wrapped = StructuredTool.from_function(coroutine=invoke, name=source.name,
                description=(source.description + '\nSelection stage: default view=selection. usage requires targeted references; no whole programming packet.')
                    if source.name == 'read_hardware' else source.description,
                args_schema=SelectionReadInput if source.name == 'read_hardware' else source.args_schema)
            wrapped.handle_validation_error = _invalid_input
            return wrapped
        return [wrap(t) for t in HARDWARE_TOOLS]

    def validate(self, report):
        if len(json.dumps(report.model_dump(), ensure_ascii=False)) > 10000:
            raise WorkflowError('HANDOFF_TOO_LARGE', '选型交接过长，应保留简要结论。')
        if set(report.source_refs) - self.sources:
            missing = sorted(set(report.source_refs) - self.sources)
            raise WorkflowError('UNREAD_SOURCE', f'未读取的引用：{missing}；目录条目不等于读取原文，请移除或按需实际读取。')
        if report.status != 'completed':
            return
        if report.blockers or not report.requirements or not report.hardware_ids:
            raise WorkflowError('INCOMPLETE_SELECTION', '完成选型必须包含需求和硬件，且无未解决阻碍。')
        previous_ids = set(self.baseline.get('previous', {}).get('hardware_ids', []))
        final_ids = set(report.hardware_ids)
        removed = previous_ids - final_ids
        if set(report.removed_hardware_ids) != removed or (removed and not report.change_reason):
            raise WorkflowError('UNEXPLAINED_SELECTION_CHANGE', '删除/替换旧器件必须在removed_hardware_ids列出全部移除ID，并用change_reason解释原因。')
        if previous_ids:
            review = report.compatibility
            if review is None or set(review.hardware_ids) != final_ids:
                raise WorkflowError('COMPATIBILITY_REQUIRED', '请对最终全部器件填写compatibility：需求、接口、资源、供电适用范围和平台。旧器件不必重新读取。')
            if review.verdict != 'compatible':
                raise WorkflowError('COMPATIBILITY_UNRESOLVED', '兼容性仍有冲突或未知时不能completed；先局部调整，无法解决则blocked/needs_input。')
        for ident in report.hardware_ids:
            item = self.observed.get(ident)
            if item is None or ident in self.failed_ids:
                raise WorkflowError('UNREAD_HARDWARE', f'{ident}既不在宿主有效选型中，也未在本轮成功读取。仅新增或资料变化的器件需要读取。')
            availability = item['availability']
            if availability['generation_status'] != 'documented_not_tested' or availability['blockers']:
                raise WorkflowError('UNSUPPORTED_SELECTION', f"{ident}的资料状态为{availability['generation_status']}，"
                    f"缺口={availability['blockers'] or availability.get('missing_information', [])}；"
                    '不能作为completed方案。用户允许替代时查询其他合适候选，否则如实返回blocked。')

    def changes(self, report):
        final = set(report.hardware_ids)
        return {'baseline_handoff_ref': self.baseline.get('handoff_ref'),
            'applied': report.status == 'completed',
            'reused_hardware_ids': sorted(final & set(self.baseline['reusable_ids'])),
            'read_hardware_ids': sorted(self.read_ids),
            'removed_hardware_ids': sorted(set(self.baseline.get('previous', {}).get('hardware_ids', [])) - final)
                if report.status == 'completed' else [],
            'invalidated_hardware': self.baseline['invalidated']}


class SelectionExecutor:
    def __init__(self, model, coordinator, emit=None):
        self.model, self.coordinator, self.emit = model, coordinator, emit

    async def __call__(self, request):
        evidence, baseline = accepted_baseline(self.coordinator)
        trace = SelectionTrace(self.coordinator, evidence, baseline)
        detail_id = uuid.uuid4().hex
        # Fixed fields only: no parent transcript, arbitrary prompts or filesystem paths.
        context = {k: request.get(k) for k in ('objective', 'original_request', 'user_request', 'project_id')}
        context['accepted_selection'] = baseline
        context['feedback'] = [{'stage': h['stage'], 'status': h['status'],
                               'summary': h.get('result', {}).get('summary')}
                              for h in request.get('handoffs', []) if h.get('status') != 'completed']
        prompt = (ROOT / 'prompts/selection.md').read_text(encoding='utf8')
        prompt += '\n\n' + (ROOT / 'skills/stages/selection.md').read_text(encoding='utf8')
        last_validation_error = None
        @model_validator(mode='after')
        def audit_report(value):
            nonlocal last_validation_error
            try:
                trace.validate(value)
            except WorkflowError as exc:
                last_validation_error = exc
                raise
            return value
        audited_schema = create_model('SelectionReport', __base__=SelectionReport,
                                      __validators__={'audit_report': audit_report})
        def invalid_report(exc):
            # Structured-output handling can raise before the model wrapper returns.
            # Record rejected billed responses, including syntax -> schema failures.
            if isinstance(getattr(exc, 'ai_message', None), AIMessage):
                trace.record_message(exc.ai_message)
            trace.reject_report(last_validation_error or WorkflowError('INVALID_HANDOFF', '两次交接校验未通过，停止本阶段。'))
            reason = str(last_validation_error) if last_validation_error else '交接格式不符合Schema。'
            return f'宿主拒绝本次交接：{reason} 请修正报告或返回blocked。保留真实缺口，不重复已读资料，不降低标准。'
        graph = create_agent(self.model, tools=trace.make_tools(), system_prompt=prompt,
            response_format=ToolStrategy(audited_schema, handle_errors=invalid_report),
            middleware=[trace,
                ModelCallLimitMiddleware(run_limit=limits.SELECTION_MODEL_CALLS, exit_behavior='error'),
                ToolCallLimitMiddleware(run_limit=limits.SELECTION_TOOL_CALLS, exit_behavior='error')])
        report, proposed, error = None, None, None
        if self.emit:
            await self.emit('stage_start', {'stage': 'selection', 'run_id': request['run_id']})
        try:
            async with asyncio.timeout(limits.SELECTION_TIMEOUT_SECONDS):
                output = await graph.ainvoke({'messages': [HumanMessage(content=json.dumps(context, ensure_ascii=False))]},
                                            config={'recursion_limit': 80})
            proposed = output.get('structured_response')
            if proposed is None:
                raise WorkflowError('MISSING_REPORT', '子Agent未返回结构化选型交接。')
            trace.validate(proposed)
            report = StageResult.model_validate(proposed.model_dump())
        except asyncio.CancelledError:
            error = 'CANCELLED'
            report = StageResult(status='cancelled', summary='选型被取消，结果未标为完成。')
            raise
        except Exception as exc:
            error = exc.code if isinstance(exc, WorkflowError) else type(exc).__name__
            report = StageResult(status='blocked' if isinstance(exc, WorkflowError) else 'failed',
                summary=(f'选型未完成：{error}：{exc}' if isinstance(exc, WorkflowError)
                         else f'选型未完成：{error}。详见阶段记录。')[:2000], blockers=[error])
        finally:
            metrics = trace.metrics()
            report = report or StageResult(status='failed', summary='选型未返回结果。')
            report.detail_ref = detail_id
            report.selection_update = trace.changes(report)
            with self.coordinator.store.connect() as con:
                self.coordinator.store.save_record(con, self.coordinator.task_id, {
                    'run_id': detail_id, 'kind': 'selection_detail', 'stage_run_id': request['run_id'],
                    'context': context, 'metrics': metrics, 'events': trace.events, 'error_code': error,
                    'observed_hardware': trace.observed,
                    'selection_snapshot': trace.evidence.dump(report.hardware_ids),
                    'proposed_result': proposed.model_dump() if proposed is not None else None,
                    'result': report.model_dump()})
            if self.emit:
                await self.emit('stage_summary', metrics | {'status': report.status, 'detail_ref': detail_id})
        return report.model_dump()


def attach_selection(coordinator, model, emit=None):
    existing = coordinator.executors.get('selection')
    if existing is None or isinstance(existing, SelectionExecutor):
        coordinator.executors['selection'] = SelectionExecutor(model, coordinator, emit)
