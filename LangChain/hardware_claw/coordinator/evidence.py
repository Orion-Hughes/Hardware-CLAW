"""Bounded, read-only evidence linked to a coordinator's task and project."""
import hashlib
import json
import re

from .store import WorkflowError
from ..projects.service import safe_path


def page(text, offset, limit):
    if offset > len(text):
        raise WorkflowError('INVALID_OFFSET', 'offset超过证据末尾。')
    end = min(offset + limit, len(text))
    return {'content': text[offset:end], 'unit': 'characters', 'offset': offset, 'total_characters': len(text),
            'next_offset': end if end < len(text) else None}


def stage_evidence(coordinator, ref):
    handoff = coordinator.store.record(coordinator.task_id, ref)
    if not handoff.get('stage') or not isinstance(handoff.get('result'), dict):
        raise WorkflowError('INVALID_REFERENCE', '证据索引只接受已结束阶段的交接ID。')
    result = handoff['result']
    detail = coordinator.store.record(coordinator.task_id, result['detail_ref']) if result.get('detail_ref') else {}
    if detail and (detail.get('stage_run_id') != ref or detail.get('kind') != f"{handoff['stage']}_detail"):
        raise WorkflowError('INVALID_REFERENCE', '详细证据与阶段交接不匹配。')
    checks = []
    for event in detail.get('events', []):
        if event.get('kind') != 'candidate_check':
            continue
        report = event['report']
        checks.append({'step': event['step'], 'version': event['version'], 'verdict': report.get('verdict'),
                       'attempt': report.get('attempt'),
                       'issues': report.get('issues', [])[:24],
                       'diagnostics': list(dict.fromkeys(report.get('diagnostics', [])))[:40]})
    checks = checks[-4:]
    return {'handoff_ref': ref, 'stage': handoff['stage'], 'status': handoff['status'],
            'project_id': handoff.get('project_id'), 'revision': (checks[-1]['version'] if checks else result.get('project_version')),
            'error_code': detail.get('error_code') or handoff.get('error_code'),
            'summary': result['summary'], 'blockers': result.get('blockers', []),
            'verification_plan_ref': result.get('verification_plan_ref'), 'checks': list(reversed(checks))}


def repair_evidence(coordinator, ref, revision):
    from ..stages.generation_finish import DESIGN_ISSUES, SOURCE_ISSUES, compiler_paths
    row = stage_evidence(coordinator, ref)
    if (row['stage'] != 'generation' or row['status'] not in {'blocked', 'failed'}
            or row['project_id'] != coordinator.project.id or not row['checks']):
        raise WorkflowError('REPAIR_EVIDENCE_REQUIRED', '需要本工程已结束、包含诊断的失败生成交接。')
    check = row['checks'][0]
    if check['version'] != revision or check['verdict'] != 'fail':
        raise WorkflowError('STALE_REPAIR_EVIDENCE', '当前修订没有对应的失败检查，不能套用旧诊断。')
    if check['step'] == 'static':
        actionable = any(i.get('code') in SOURCE_ISSUES | DESIGN_ISSUES for i in check['issues'])
    else:
        actionable = bool(compiler_paths(check, [f['path'] for f in coordinator.project.get()['files']]))
    if not actionable:
        raise WorkflowError('REPAIR_NOT_ACTIONABLE', '没有可定位的工程诊断；依赖、环境或仿真服务故障不自动改固件。')
    return {k: row[k] for k in ('handoff_ref', 'error_code', 'summary')} | {'check': check}


def repair_action(coordinator, ref):
    """Host supplies exact delegation arguments; the parent need not scan source to recreate them."""
    if coordinator.project is None:
        return {'available': False, 'reason': 'NO_PROJECT'}
    state = coordinator.store.load(coordinator.task_id)
    revision = coordinator.project.get()['version']
    if state.get('last_evidence_repair_turn') == state['turn_count']:
        return {'available': False, 'reason': 'REPAIR_LIMIT'}
    latest = state.get('latest_attempts', {}).get('generation')
    if latest != ref:
        return {'available': False, 'reason': 'INVALID_REPAIR_REFERENCE'}
    try:
        coordinator.check_budget()
        repair_evidence(coordinator, ref, revision)
    except WorkflowError as exc:
        return {'available': False, 'reason': exc.code}
    return {'available': True, 'tool': 'run_stage', 'args': {
        'stage': 'generation', 'objective': '根据当前修订的全部检查诊断集中修复，保留原需求与已确认选型，重新提交候选。',
        'expected_task_version': state['version'], 'expected_project_version': revision, 'repair_from': ref},
        'instruction': '已有可定位诊断，直接委派生成阶段修复。无需主 Agent 扫描完整源码。'}


def simulation_evidence(project, ref, filename, offset, limit):
    from ..adapters.simulator import current_report
    from ..adapters.wokwi_mcp import read_evidence as read_mcp
    if ref is not None:
        if not re.fullmatch(r'[a-f0-9]{32}', ref):
            raise WorkflowError('INVALID_REFERENCE', 'MCP证据需使用已保存会话ID。')
        if filename is None:
            from ..adapters.simulator import subject
            from ..adapters.wokwi_mcp import PLAN
            from ..projects.vscode_delivery import verified_build
            with project.locked():
                state = project._load()
                project._check_live_files(state)
                path = safe_path(project.meta, f'mcp/{ref}/manifest.json')
                if not path.is_file():
                    raise WorkflowError('INVALID_REFERENCE', 'MCP会话未登记。')
                report = json.loads(path.read_text('utf8'))
                build, _ = verified_build(project, state)
                if report.get('version') != state['version'] or report.get('subject_sha256') != subject(state, build, PLAN):
                    raise WorkflowError('STALE_SIMULATION', '此MCP会话不对应当前固件和电路。')
                return {'version': state['version'], 'attempt': ref, 'files': list(report.get('evidence_sha256', {})),
                        'execution_status': report.get('execution_status'), 'full_project_acceptance': 'not_evaluated'}
        from ..contracts.simulation_mcp import ReadSimulationEvidenceInput
        args = dict(expected_version=project.get()['version'], attempt=ref, filename=filename, offset=offset, limit=limit)
        if not re.fullmatch(r'[a-z0-9-]+\.(json|log|vcd|png)', filename):
            raise WorkflowError('INVALID_REFERENCE', 'MCP证据文件名无效。')
        return read_mcp(project, **ReadSimulationEvidenceInput.model_validate(args).model_dump())
    with project.locked():
        state = project._load()
        project._check_live_files(state)
        report = current_report(project, state)
        status = project.validation_status(state)
        version = state['version']
        if not report:
            return {'version': version, 'simulation': 'not_run', 'behavior': 'not_run', 'files': []}
        files = report.get('evidence_sha256', {})
        if filename is None:
            return {'version': version, 'simulation': status['simulation'], 'behavior': status['behavior'],
                    'files': list(files), 'attempt': report['attempt']}
        if filename not in files:
            raise WorkflowError('INVALID_REFERENCE', '文件不在当前仿真证据清单中。')
        path = safe_path(project.meta, f"simulations/{report['attempt']}/{filename}")
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise WorkflowError('EVIDENCE_CHANGED', '仿真证据不存在或超过读取上限。')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != files[filename]:
            raise WorkflowError('EVIDENCE_CHANGED', '仿真证据哈希不匹配。')
        return {'version': version, 'filename': filename, **page(data.decode('utf8', errors='replace'), offset, limit)}


def read_task_evidence(coordinator, kind, ref, filename, offset, limit,
                       source_unit='lines', start_line=1, end_line=None):
    project = coordinator.project
    if kind == 'index':
        state = coordinator.store.load(coordinator.task_id)
        p = project.get() if project else None
        runs = []
        for stage, ident in state.get('latest_attempts', state['latest']).items():
            record = coordinator.store.record(coordinator.task_id, ident)
            result = record['result']
            runs.append({'stage': stage, 'handoff_ref': ident, 'status': record['status'],
                         'project_version': result.get('project_version'), 'has_detail': bool(result.get('detail_ref')),
                         'plan_ref': result.get('verification_plan_ref')})
        return {'latest_attempts': runs, 'recent_handoff_refs': state['recent_runs'],
                'project_version': p['version'] if p else None,
                'files': [f['path'] for f in p['files']] if p else [],
                'simulation': p['simulation'] if p else 'not_run', 'behavior': p['behavior'] if p else 'not_run',
                'simulation_execution_enabled': False}
    if kind == 'stage':
        row = stage_evidence(coordinator, ref)
        current = project.get()['version'] if project else None
        last_check = (row['checks'] or [{}])[0]
        if filename == 'build.log':
            from ..adapters.compiler import MAX_LOG
            from ..projects.service import ROOT
            check = next((c for c in row['checks'] if c['step'] == 'build'), {})
            attempt = check.get('attempt') or ''
            if not project or row['project_id'] != project.id or not re.fullmatch(r'[a-f0-9]{32}', attempt):
                raise WorkflowError('INVALID_REFERENCE', '该阶段没有本工程的编译日志引用。')
            path = safe_path(ROOT / 'temp' / 'builds', f'{project.id}/{attempt}/build.log')
            if not path.is_file() or path.stat().st_size > MAX_LOG:
                raise WorkflowError('EVIDENCE_UNAVAILABLE', '编译日志已清理或超出读取上限。')
            return {'handoff_ref': ref, 'version': check['version'], 'current_project_version': current,
                    **page(path.read_text('utf8', errors='replace'), offset, limit)}
        if filename is not None:
            if filename != 'plan.json' or not row['verification_plan_ref']:
                raise WorkflowError('INVALID_REFERENCE', '仅验证阶段可读取已登记的plan.json。')
            plan = coordinator.store.record(coordinator.task_id, row['verification_plan_ref'])
            if plan.get('kind') != 'verification_plan' or plan.get('stage_run_id') != ref:
                raise WorkflowError('INVALID_REFERENCE', '验证计划与阶段交接不匹配。')
            row = plan
        if filename is None:
            return {**row, 'current_project_version': current, 'last_check_revision': last_check.get('version'),
                    'repair_action': repair_action(coordinator, ref), 'unit': 'structured',
                    'instruction': 'checks 是结构化诊断，不需字符分页。完整编译日志可用 filename=build.log。'}
        return {'handoff_ref': ref, 'current_project_version': current, 'last_check_revision': last_check.get('version'),
                **page(json.dumps(row, ensure_ascii=False), offset, limit)}
    if not project:
        raise WorkflowError('NO_PROJECT', '当前任务没有绑定工程。')
    if kind == 'source':
        data = project.read_file(ref)
        if source_unit == 'lines':
            if offset != 0 or limit != 3000:
                raise WorkflowError('SOURCE_RANGE_REQUIRED',
                    '源码默认按行读取：使用 start_line/end_line，不要传 offset/limit。'
                    '若确需字符分页，显式设置 source_unit=characters。')
            from ..projects.source_context import line_excerpt
            return {k: data[k] for k in ('path', 'version', 'sha256')} | line_excerpt(
                data['content'], start_line, end_line if end_line is not None else start_line + 119)
        if start_line != 1 or end_line is not None:
            raise WorkflowError('SOURCE_RANGE_REQUIRED', '字符分页不能混用 start_line/end_line。')
        return {k: data[k] for k in ('path', 'version', 'sha256')} | page(data['content'], offset, limit)
    return simulation_evidence(project, ref, filename, offset, limit)
