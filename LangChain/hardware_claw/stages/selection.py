"""Read-only selection agent with isolated context and auditable handoffs."""
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model, model_validator

from .. import limits
from ..coordinator.contracts import StageResult
from ..coordinator.store import WorkflowError
from ..tools.hardware_catalog import HARDWARE_TOOLS, ReadHardwareInput, _invalid_input

ROOT = Path(__file__).resolve().parents[2]


class SelectionReport(StageResult):
    """Submit the final selection handoff after consulting tools; never claim runtime validation."""
    next_stage: Literal['generation'] | None = None
    detail_ref: None = None  # Assigned by the host, never invented by the model.
    project_version: None = None


class SelectionReadInput(ReadHardwareInput):
    view: Literal['selection', 'usage'] = Field(default='selection',
        description='选型默认selection。usage仅允许带references定向补读，不允许加载整包编程原文。')


class SelectionTrace(AgentMiddleware):
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.started = time.monotonic()
        self.usage, self.events, self.observed, self.sources = [], [], {}, set()
        self.attempts = 0
        self.recorded_messages = set()

    def record_message(self, msg):
        key = msg.id or id(msg)
        if key in self.recorded_messages:
            return
        self.recorded_messages.add(key)
        usage = dict(msg.usage_metadata) if msg.usage_metadata else None
        self.usage.append(usage)
        self.coordinator.record_usage(usage, role='selection')
        self.events.append({'kind': 'model', 'content': msg.content,
            'tool_calls': msg.tool_calls, 'invalid_tool_calls': msg.invalid_tool_calls,
            'usage': usage, 'response_metadata': msg.response_metadata})

    async def awrap_model_call(self, request, handler):
        self.coordinator.check_budget()
        if sum(u.get('total_tokens', 0) for u in self.usage if u) >= limits.SELECTION_TOTAL_TOKENS:
            raise WorkflowError('SELECTION_TOKEN_BUDGET', '选型阶段已报告token达到上限。')
        self.attempts += 1
        response = await handler(request)
        for msg in response.result:
            if isinstance(msg, AIMessage):
                self.record_message(msg)
            elif isinstance(msg, ToolMessage):
                self.events.append({'kind': 'submission_feedback', 'name': msg.name, 'content': msg.content})
        return response

    def make_tools(self):
        def wrap(source):
            async def invoke(**kwargs):
                if source.name == 'read_hardware' and kwargs.get('view') == 'usage' and not kwargs.get('references'):
                    result = {'execution_status': 'error', 'error_code': 'STAGE_SCOPE',
                        'summary': '选型只能使用selection视图；核对具体参数时用usage并指定已登记references，不能整包加载编程资料。',
                        'data': None}
                else:
                    result = await source.ainvoke(kwargs)
                self.events.append({'kind': 'tool', 'name': source.name, 'args': kwargs, 'result': result})
                if source.name == 'read_hardware' and isinstance(result, dict) and result.get('execution_status') == 'ok':
                    data = result['data']
                    for item in data.get('hardware', []):
                        if 'simulation' in item:
                            self.observed[item['id']] = item
                        self.sources.update(p['ref'] for p in item.get('provenance', {}).values()
                                            if isinstance(p, dict) and p.get('ref'))
                    self.sources.update(d['ref'] for d in data.get('documents', []) if d.get('status') == 'included')
                    self.sources.update(p['ref'] for p in data.get('platforms', []) if 'content' in p)
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
        for ident in report.hardware_ids:
            item = self.observed.get(ident)
            if item is None:
                raise WorkflowError('UNREAD_HARDWARE', '所选硬件必须在本轮通过read_hardware读取，不只搜索或沿用旧摘要。')
            availability = item['availability']
            if availability['generation_status'] != 'documented_not_tested' or availability['blockers']:
                raise WorkflowError('UNSUPPORTED_SELECTION', f"{ident}的资料状态为{availability['generation_status']}，"
                    f"缺口={availability['blockers'] or availability.get('missing_information', [])}；"
                    '不能作为completed方案。用户允许替代时查询其他合适候选，否则如实返回blocked。')

    def metrics(self):
        return {'role': 'selection', 'api_attempts': self.attempts, 'model_responses': len(self.usage),
            'elapsed_seconds': round(time.monotonic() - self.started, 2), 'usage': self.usage,
            'input_tokens_reported': sum(u.get('input_tokens', 0) for u in self.usage if u),
            'output_tokens_reported': sum(u.get('output_tokens', 0) for u in self.usage if u),
            'tokens_reported': sum(u.get('total_tokens', 0) for u in self.usage if u),
            'usage_complete': self.attempts == len(self.usage) and all(u is not None for u in self.usage),
            'tool_calls': sum(e['kind'] == 'tool' for e in self.events)}


class SelectionExecutor:
    def __init__(self, model, coordinator, emit=None):
        self.model, self.coordinator, self.emit = model, coordinator, emit

    async def __call__(self, request):
        trace = SelectionTrace(self.coordinator)
        detail_id = uuid.uuid4().hex
        # Fixed fields only: no parent transcript, arbitrary prompts or filesystem paths.
        context = {k: request.get(k) for k in ('objective', 'user_request', 'project_id', 'current_handoffs')}
        context['handoffs'] = [{'run_id': h['run_id'], 'stage': h['stage'], 'status': h['status'],
                                'result': h.get('result')} for h in request.get('handoffs', [])]
        prompt = (ROOT / 'prompts/selection.md').read_text(encoding='utf8')
        prompt += '\n\n' + (ROOT / 'skills/stages/selection.md').read_text(encoding='utf8')
        last_validation_error = None
        invalid_reports = 0
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
            nonlocal invalid_reports
            invalid_reports += 1
            if invalid_reports >= 2:
                # Structured-output handling can raise before the model wrapper returns.
                # Preserve the billed response even when its final report is rejected.
                if isinstance(getattr(exc, 'ai_message', None), AIMessage):
                    trace.record_message(exc.ai_message)
                raise last_validation_error or WorkflowError('INVALID_HANDOFF', '两次交接校验未通过，停止本阶段。')
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
            with self.coordinator.store.connect() as con:
                self.coordinator.store.save_record(con, self.coordinator.task_id, {
                    'run_id': detail_id, 'kind': 'selection_detail', 'stage_run_id': request['run_id'],
                    'context': context, 'metrics': metrics, 'events': trace.events, 'error_code': error,
                    'observed_hardware': trace.observed,
                    'proposed_result': proposed.model_dump() if proposed is not None else None,
                    'result': report.model_dump()})
            if self.emit:
                await self.emit('stage_summary', metrics | {'status': report.status, 'detail_ref': detail_id})
        return report.model_dump()


def attach_selection(coordinator, model, emit=None):
    existing = coordinator.executors.get('selection')
    if existing is None or isinstance(existing, SelectionExecutor):
        coordinator.executors['selection'] = SelectionExecutor(model, coordinator, emit)
