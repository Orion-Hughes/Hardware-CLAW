"""Build a smaller model-only view; never mutate graph history or raw run events."""
import hashlib
import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from .catalog.views import compact_hardware

RECENT_TOOL_ROUNDS = 3
PINNED_API_READS = 2


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def parsed(message):
    try:
        result = json.loads(message.content)
        return result if isinstance(result, dict) else None
    except (TypeError, ValueError):
        return None


def complete_rounds(messages):
    """Only complete contiguous request/result groups are eligible for projection."""
    rounds = []
    for i, msg in enumerate(messages):
        if not isinstance(msg, AIMessage) or not msg.tool_calls:
            continue
        ids = [c['id'] for c in msg.tool_calls]
        end = i+1
        while end < len(messages) and isinstance(messages[end], ToolMessage):
            end += 1
        got = [m.tool_call_id for m in messages[i+1:end]]
        if len(set(ids)) == len(ids) and len(got) == len(ids) and set(got) == set(ids):
            rounds.append((i, end))
    return rounds


def receipt(message, call, result):
    data = result.get('data')
    data = data if isinstance(data, dict) else {}
    # Keep all conclusions explicitly scoped to their original version; never
    # manufacture a verdict from tool success or the model's explanation.
    keys = ('project_id', 'version', 'design_version', 'execution_status',
            'execution_verdict', 'verdict', 'scope', 'full_project_acceptance',
            'uncovered', 'issues', 'warnings', 'unverified', 'stage_verdicts', 'validator_version',
            'failure_kind', 'reason', 'attempt',
            'fingerprint_version', 'built_version', 'reused_from_version', 'cached', 'identity_supported',
            'subject_sha256', 'source_sha256', 'build_source_sha256',
            'path', 'sha256', 'start_line', 'end_line', 'partial',
            'delivery_status', 'build', 'simulation', 'behavior', 'evaluation')
    brief = {k: data[k] for k in keys if k in data}
    # Nested reports sometimes contain long logs; preserve conclusions only.
    for key in ('build', 'simulation', 'evaluation'):
        if isinstance(brief.get(key), dict):
            brief[key] = {k: v for k, v in brief[key].items() if k in keys}
    if isinstance(data.get('records'), list):
        brief['records'] = [{k: r[k] for k in ('operation', 'status', 'evidence', 'effect_verified') if k in r}
                            for r in data['records']]
    if isinstance(data.get('reference'), dict):
        brief['reference'] = {k: v for k, v in data['reference'].items() if k != 'content'}
    brief['context_view'] = {
        'historical': True, 'body_omitted': True,
        'original_sha256': hashlib.sha256(message.content.encode('utf-8')).hexdigest(),
        'note': '仅压缩模型视图；原始工具结果保留在运行记录。需要内容时重新读取，不能把历史结果当当前版本。',
    }
    if call['name'] in {'get_driver_api', 'read_project_file', 'get_project', 'read_simulation_evidence'}:
        brief['context_view']['read_again'] = {'tool': call['name'], 'arguments': call['args']}
    return {k: result[k] for k in ('execution_status', 'error_code', 'summary', 'retryable') if k in result} | {'data': brief}


def build_view(messages):
    view = list(messages)
    rounds = complete_rounds(messages)
    old = rounds[:-RECENT_TOOL_ROUNDS]
    old_indexes = {i for start, end in old for i in range(start, end)}
    calls = {c['id']: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
    pinned_api, seen_api, skill_latest = set(), set(), {}
    # Keep a small recent source working set and each loaded skill's latest body.
    for i in range(len(messages)-1, -1, -1):
        m = messages[i]
        if not isinstance(m, ToolMessage):
            continue
        result = parsed(m)
        if not result or result.get('execution_status') != 'ok':
            continue
        name = calls.get(m.tool_call_id, {}).get('name')
        data = result.get('data') or {}
        if not isinstance(data, dict):
            continue
        if name == 'load_skill':
            # A newer read of the same page replaces an older body, including
            # when its hash changed; each different reference/page still survives.
            key = (data.get('skill_id'), data.get('reference'), data.get('offset'))
            skill_latest.setdefault(key, i)
        elif name == 'get_driver_api' and (data.get('reference') or data.get('matches')):
            key = dump(data.get('reference') or data.get('matches'))
            if key not in seen_api and len(pinned_api) < PINNED_API_READS:
                pinned_api.add(i)
                seen_api.add(key)
    pinned_skills = set(skill_latest.values())
    changed = 0
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            result = parsed(msg)
            call = calls.get(msg.tool_call_id)
            if not result or not call or result.get('execution_status') != 'ok':
                continue  # Errors are never silently dropped or summarized away.
            if call['name'] == 'get_hardware_info' and i in old_indexes and isinstance(result.get('data'), dict):
                result = result | {'data': compact_hardware(result['data'])}
            elif i in old_indexes and i not in pinned_api and i not in pinned_skills:
                if call['name'] in {'get_driver_api', 'load_skill', 'load_template', 'search_hardware',
                                     'get_project', 'update_project_design', 'scaffold_project',
                                     'read_project_file', 'write_project_files', 'apply_project_patch',
                                     'compile_project', 'simulate_project', 'inspect_simulation',
                                     'read_simulation_evidence', 'export_project'}:
                    candidate = receipt(msg, call, result)
                    # A receipt is optional, never expand an already short result.
                    if len(dump(candidate)) < len(dump(result)):
                        result = candidate
            text = dump(result)
            if text != msg.content:
                view[i] = msg.model_copy(update={'content': text})
                changed += 1
        elif isinstance(msg, AIMessage) and i in old_indexes:
            new_calls = []
            altered = False
            for call in msg.tool_calls:
                args = call['args']
                if call['name'] in {'write_project_files', 'apply_project_patch', 'update_project_design'}:
                    args = dict(args)
                    for field in ('files', 'old_text', 'new_text', 'design'):
                        if field in args and len(dump(args[field])) > 800:
                            args[field] = '[历史参数正文已从模型视图省略；已执行。当前文件用read_project_file，当前设计用get_project读取。]'
                            altered = True
                new_calls.append(call | {'args': args})
            if altered:
                extra = {k: v for k, v in msg.additional_kwargs.items() if k not in {'tool_calls', 'function_call'}}
                view[i] = msg.model_copy(update={'tool_calls': new_calls, 'additional_kwargs': extra})
                changed += 1
    before = len(dump([m.model_dump(mode='json') for m in messages]))
    after = len(dump([m.model_dump(mode='json') for m in view]))
    return view, {'original_message_chars': before, 'model_message_chars': after,
                  'messages_projected': changed, 'recent_tool_rounds': RECENT_TOOL_ROUNDS,
                  'pinned_api_reads': len(pinned_api)}


class MessageViewMiddleware(AgentMiddleware):
    def finish(self, response, stats):
        for i, message in enumerate(response.result):
            if isinstance(message, AIMessage):
                response.result[i] = message.model_copy(update={
                    'response_metadata': message.response_metadata | {'context_view': stats}})
        return response

    def wrap_model_call(self, request, handler):
        messages, stats = build_view(request.messages)
        return self.finish(handler(request.override(messages=messages)), stats)

    async def awrap_model_call(self, request, handler):
        messages, stats = build_view(request.messages)
        return self.finish(await handler(request.override(messages=messages)), stats)
