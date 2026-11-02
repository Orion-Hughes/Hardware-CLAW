"""Host-owned dispatch of explicitly registered, fixed-stage executors."""
import asyncio
import json
import time
import uuid
from pydantic import ValidationError

from .contracts import StageResult
from .store import TaskStore, WorkflowError, timestamp
from .. import limits
from ..catalog import KnowledgeCatalog, CatalogError
from ..projects.service import ProjectError

STAGES = {
    'selection': '需求理解、资料查询与选型；讨论请求到此结束。',
    'generation': '接线与固件设计、生成和修正；通过当前修订基础检查与编译。',
    'verification': '仿真、证据分析与诊断；证据不足明确报告，不自行修改固件。',
}


def passed(report):
    return isinstance(report, dict) and report.get('verdict') == 'pass'


class Coordinator:
    def __init__(self, task_id, *, store=None, project=None, executors=None, builtin_stages=False):
        self.store = store or TaskStore()
        self.task_id, self.project = task_id, project
        self.executors = dict(executors or {})
        self.builtin_stages = builtin_stages
        self.model_stop_reason = None
        if set(self.executors) - STAGES.keys():
            raise WorkflowError('INVALID_STAGE', '只能注册固定的三个阶段。')
        state = self.store.load(task_id)
        if state['project_id'] != (project.id if project else None):
            raise WorkflowError('PROJECT_BINDING_MISMATCH', '任务必须恢复原工程绑定。')

    def begin_turn(self, question):
        with self.store.edit(self.task_id) as (state, _):
            self._idle(state)
            state['original_request'] = state['original_request'] or question
            state['current_request'] = question
            state['turn_count'] += 1
            state['latest_outcome'] = 'idle'
        self.model_stop_reason = None

    @staticmethod
    def _idle(state):
        if state['active_run']:
            raise WorkflowError('TASK_BUSY', '阶段正在运行或上次运行被中断，不能并行写入或自动重复执行。')

    @staticmethod
    def _version(state, expected):
        if state['version'] != expected:
            raise WorkflowError('TASK_VERSION_CONFLICT', '任务状态已变化，请重新get_task_state。')

    def project_state(self):
        if not self.project:
            return None
        p = self.project.get()
        return {k: p.get(k) for k in ('project_id', 'version', 'template', 'requirements',
                                     'file_check', 'build', 'simulation', 'behavior')}

    def state(self):
        state = self.store.load(self.task_id)
        return state | {'project': self.project_state(),
            'stages': {name: {'description': description, 'available': name in self.executors}
                       for name, description in STAGES.items()},
            'handoffs': [self.store.record(self.task_id, ref) for ref in state['latest'].values()],
            'budget': {'token_limit': limits.COORDINATOR_TOTAL_TOKENS,
                       'remaining_reported_tokens': max(0, limits.COORDINATOR_TOTAL_TOKENS - state['usage']['total_tokens']),
                       'usage_complete': state['usage']['missing_usage_responses'] == 0,
                       'note': '主Agent及已接入子Agent共享任务已报告用量；单次请求仍可能越过阈值。'}}

    def check_budget(self):
        if self.model_stop_reason is not None:
            raise self.model_stop_reason
        if self.store.load(self.task_id)['usage']['total_tokens'] >= limits.COORDINATOR_TOTAL_TOKENS:
            raise WorkflowError('TOKEN_BUDGET', '任务累计token达到预算，已停止继续调用。')

    def stop_model_calls(self, reason):
        """A stage cost/runaway stop cannot be bypassed by another delegation this turn."""
        self.model_stop_reason = reason

    def create_generation_project(self, request, requirement):
        from ..projects.service import ProjectService
        with self.store.edit(self.task_id) as (state, _):
            if state['active_run'] != request['run_id'] or state['project_id'] is not None:
                raise WorkflowError('PROJECT_BINDING_MISMATCH', '工程绑定状态已变化。')
            project = ProjectService.create('task-' + self.task_id[:12], requirement, 'vscode')
            state['project_id'] = project.id
            self.project = project
        request['project_id'] = project.id
        request['expected_project_version'] = project.get()['version']

    def record_usage(self, usage, role='main'):
        # Accounting does not change task_version used by tool calls in this response.
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            state = self.store._load(con, self.task_id)
            ledger = state['usage']
            role_ledger = state.setdefault('usage_by_role', {}).setdefault(role,
                {'model_responses': 0, 'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'missing_usage_responses': 0})
            for account in (ledger, role_ledger):
                account['model_responses'] += 1
                if usage is None:
                    account['missing_usage_responses'] += 1
                else:
                    for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                        account[key] += usage.get(key, 0)
            con.execute('UPDATE tasks SET data=? WHERE id=?', (json.dumps(state, ensure_ascii=False), self.task_id))

    def _check_project_version(self, expected):
        if not self.project:
            raise WorkflowError('NO_PROJECT', '该阶段需要绑定工程。')
        p = self.project.get()
        if expected != p['version']:
            raise WorkflowError('PROJECT_VERSION_CONFLICT', '请使用当前工程修订。')
        return p

    def _check_result(self, stage, result):
        if result.status != 'completed':
            return
        if result.blockers:
            raise WorkflowError('UNPROVEN_COMPLETION', '存在阶段阻碍时不能标记completed。')
        if stage == 'selection':
            for ident in result.hardware_ids:
                KnowledgeCatalog().get(ident)
        else:
            p = self._check_project_version(result.project_version)
            if stage == 'generation' and (not passed(p.get('file_check')) or not passed(p.get('build'))):
                raise WorkflowError('UNPROVEN_COMPLETION', '生成完成必须有当前检查和编译通过记录。')
            if stage == 'verification' and p.get('behavior') != 'pass':
                raise WorkflowError('UNPROVEN_COMPLETION', '未有当前修订的功能通过证据；返回blocked或failed并说明缺口。')

    async def run_stage(self, stage, objective, expected_task_version, input_refs=None, expected_project_version=None):
        if stage not in STAGES:
            raise WorkflowError('INVALID_STAGE', '未知阶段。')
        self.check_budget()
        start = time.monotonic()
        run_id = uuid.uuid4().hex
        with self.store.edit(self.task_id) as (state, con):
            self._idle(state)
            self._version(state, expected_task_version)
            if state['stage_attempts'] >= limits.COORDINATOR_STAGE_ATTEMPTS:
                raise WorkflowError('STAGE_BUDGET', '该任务的阶段委派次数达到上限。')
            refs = list(dict.fromkeys([*(input_refs or []), *state['latest'].values()]))
            handoffs = [self.store.record(self.task_id, ref) for ref in refs]
            if any(h.get('stage') not in STAGES or 'result' not in h or h.get('status') == 'running' for h in handoffs):
                raise WorkflowError('INVALID_REFERENCE', 'input_refs只接受已结束阶段的handoff_ref，不接受详细日志或主对话记录。')
            current_selection_ref = state['latest'].get('selection')
            selection_attempt_ref = state.get('latest_attempts', {}).get('selection', current_selection_ref)
            request = {'run_id': run_id, 'stage': stage, 'objective': objective,
                       'original_request': state['original_request'],
                       'user_request': state['current_request'], 'handoffs': handoffs,
                       'current_handoffs': dict(state['latest']),
                       'project_id': state['project_id'], 'expected_project_version': expected_project_version}
            state['stage_attempts'] += 1
            state['active_run'] = run_id
            self.store.save_record(con, self.task_id, request | {'status': 'running', 'created_at': timestamp()})
        code = None
        try:
            if stage not in self.executors:
                code = 'STAGE_UNAVAILABLE'
                result = StageResult(status='blocked', summary=f'{stage}阶段执行器尚未接入。',
                                     blockers=['主协调层已建立；未调用子Agent或修改工程。'])
            else:
                if stage == 'generation':
                    selected = next((h for h in handoffs if h['run_id'] == current_selection_ref
                                     and h['status'] == 'completed'), None)
                    if selection_attempt_ref != current_selection_ref:
                        raise WorkflowError('MISSING_HANDOFF', '最近一次选型尚未完成，不能沿用此前选型继续生成。')
                    if not selected or not selected['result']['hardware_ids'] or not selected['result']['requirements']:
                        raise WorkflowError('MISSING_HANDOFF', '生成需要明确需求和硬件选型交接。')
                    # Only the installed generation executor opts into first-project creation.
                    if getattr(self.executors[stage], 'creates_project', False):
                        from ..stages.selection_state import accepted_baseline
                        _, baseline = accepted_baseline(self)
                        if baseline['invalidated']:
                            raise WorkflowError('STALE_SELECTION', '选型证据已变化或缺失，先重新选型。')
                        if self.project is None:
                            if expected_project_version is not None:
                                raise WorkflowError('PROJECT_VERSION_CONFLICT', '尚无工程时expected_project_version应为null。')
                            self.create_generation_project(request, '\n'.join(selected['result']['requirements']))
                            expected_project_version = request['expected_project_version']
                if stage in ('generation', 'verification'):
                    p = self._check_project_version(expected_project_version)
                    if stage == 'verification' and (not passed(p.get('file_check')) or not passed(p.get('build'))):
                        raise WorkflowError('BUILD_REQUIRED', '验证需要当前修订检查和编译通过。')
                async with asyncio.timeout(limits.COORDINATOR_STAGE_TIMEOUT_SECONDS):
                    # Host adapters own child context/tools; no parent transcript is passed.
                    result = StageResult.model_validate(await self.executors[stage](request))
                if len(json.dumps(result.model_dump(), ensure_ascii=False)) > 12000:
                    raise WorkflowError('HANDOFF_TOO_LARGE', '阶段交接过大；详细内容应保存在工程或证据中。')
                self._check_result(stage, result)
        except asyncio.CancelledError:
            self._finish(request, StageResult(status='cancelled', summary='阶段被取消，未宣称完成。'), start, 'CANCELLED')
            raise
        except (WorkflowError, CatalogError, ProjectError) as exc:
            code = exc.code
            result = StageResult(status='blocked', summary=str(exc), blockers=[exc.code])
        except (TimeoutError, ValidationError) as exc:
            code = 'STAGE_TIMEOUT' if isinstance(exc, TimeoutError) else 'INVALID_HANDOFF'
            result = StageResult(status='failed', summary='阶段超时或返回格式无效。', blockers=[code])
        except Exception:
            code = 'STAGE_ERROR'
            result = StageResult(status='failed', summary='阶段执行异常，未宣称完成。', blockers=[code])
        return self._finish(request, result, start, code)

    def _finish(self, request, result, start, code):
        record = request | {'status': result.status, 'result': result.model_dump(), 'error_code': code,
                            'elapsed_seconds': round(time.monotonic() - start, 3), 'finished_at': timestamp()}
        # Stored handoffs refer to earlier runs; do not duplicate their contents recursively.
        record['input_refs'] = [r['run_id'] for r in record.pop('handoffs')]
        with self.store.edit(self.task_id) as (state, con):
            if state['active_run'] != request['run_id']:
                raise WorkflowError('TASK_VERSION_CONFLICT', '阶段归属已变化，拒绝覆盖。')
            state['active_run'] = None
            state['latest_outcome'] = result.status
            state.setdefault('latest_attempts', {})[request['stage']] = request['run_id']
            state['recent_runs'] = [*state['recent_runs'][-7:], request['run_id']]
            if result.status == 'completed':
                stage = request['stage']
                state['latest'][stage] = request['run_id']
                for dependent in {'selection': ('generation', 'verification'), 'generation': ('verification',), 'verification': ()}[stage]:
                    state['latest'].pop(dependent, None)
            self.store.save_record(con, self.task_id, record)
            version = state['version'] + 1
        return {'task_version': version, 'handoff_ref': request['run_id'], **record}

    def deliver(self, expected_task_version, expected_project_version, scope):
        if scope not in {'checked_artifacts', 'verified'}:
            raise WorkflowError('INVALID_ARGUMENT', '交付范围无效。')
        with self.store.edit(self.task_id) as (state, _):
            self._idle(state)
            self._version(state, expected_task_version)
            self._check_project_version(expected_project_version)
            before = self.project.delivery()
            if scope == 'verified' and before['behavior'] != 'pass':
                raise WorkflowError('NOT_VERIFIED', '当前没有功能通过证据；只能明确交付未验证工件。')
            self.project.export(expected_project_version)
            data = self.project.delivery()
            state['latest_delivery'] = data
            return {'task_version': state['version'] + 1, 'scope': scope, 'delivery': data}
