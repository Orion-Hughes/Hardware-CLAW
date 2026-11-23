"""UI-independent, bounded execution of one user turn."""
import asyncio
import time
import uuid
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from . import limits


def error_message(exc):
    from .coordinator.store import WorkflowError
    if isinstance(exc, WorkflowError):
        return f"{exc.code}：{exc}"
    name = type(exc).__name__
    if "Limit" in name or "Recursion" in name:
        return f"达到本轮调用预算，已停止（{name}）。请缩小问题范围后重试。"
    if isinstance(exc, TimeoutError):
        return "本轮超过运行时限，已停止。"
    return f"运行失败（{name}）；请检查 API 配置、余额或网络。"


async def execute_turn(model, question, history, emit, *, coordinator, timeout=None):
    """Keep only completed user/answer pairs; never retain partial tool chains."""
    started = time.monotonic()
    if timeout is None:
        timeout = limits.COORDINATOR_STAGE_TIMEOUT_SECONDS
    usage, requested, returned = [], set(), set()
    answer = ""
    model_calls = 0
    response_metrics = []
    tool_payloads = {}
    tool_names = {}
    status = "error"
    invalid_calls = False
    run_id = uuid.uuid4().hex
    events = []
    child_summaries = []
    generation_requested = False
    conversation_status = "incomplete"
    sink = emit
    async def emit(kind, data):
        events.append({"kind": kind, "data": data})
        if kind == 'stage_summary':
            child_summaries.append(data)
        await sink(kind, data)
    try:
        from .coordinator.agent import build_coordinator
        if coordinator.builtin_stages:
            from .stages.selection import attach_selection
            from .stages.generation import attach_generation
            from .stages.verification import attach_verification
            attach_selection(coordinator, model, emit)
            attach_generation(coordinator, model, emit)
            attach_verification(coordinator, model, emit)
        coordinator.begin_turn(question)
        graph = build_coordinator(model, coordinator)
        # A fresh graph invocation resets per-run middleware counters.
        async with asyncio.timeout(timeout):
            async for update in graph.astream(
                {"messages": [*history[-2*limits.HISTORY_TURNS:], HumanMessage(content=question)]},
                config={"recursion_limit": limits.COORDINATOR_GRAPH_STEPS}, stream_mode="updates",
            ):
                for value in update.values():
                    if not isinstance(value, dict):
                        continue
                    for msg in value.get("messages", []):
                        if isinstance(msg, AIMessage):
                            model_calls += 1
                            response_metrics.append({
                                "response_index": model_calls,
                                "finish_reason": msg.response_metadata.get("finish_reason"),
                                "model_name": msg.response_metadata.get("model_name"),
                                "input_tokens": (msg.usage_metadata or {}).get("input_tokens"),
                                "output_tokens": (msg.usage_metadata or {}).get("output_tokens"),
                                "invalid_tool_calls": len(msg.invalid_tool_calls),
                                "elapsed_seconds": round(time.monotonic() - started, 3),
                            })
                            if msg.usage_metadata:
                                usage.append(dict(msg.usage_metadata))
                            coordinator.record_usage(dict(msg.usage_metadata) if msg.usage_metadata else None)
                            if msg.invalid_tool_calls:
                                invalid_calls = True
                                await emit("invalid_tool_call", {"calls": msg.invalid_tool_calls})
                                await emit("error", {"text": "模型返回了无法解析的工具参数；该调用未执行，请重试并缩小文件批次。"})
                            for call in msg.tool_calls:
                                if call['name'] == 'run_stage' and call['args'].get('stage') == 'generation':
                                    generation_requested = True
                                requested.add(call["id"])
                                tool_names[call["id"]] = call["name"]
                                metric = tool_payloads.setdefault(call["name"], {"requests": 0, "argument_characters": 0, "result_characters": 0})
                                metric["requests"] += 1
                                metric["argument_characters"] += len(json.dumps(call["args"], ensure_ascii=False))
                                await emit("tool_request", call)
                            if msg.content:
                                await emit("model", {"text": msg.content, "final": not msg.tool_calls})
                            answer = msg.content if not msg.tool_calls else ""
                        elif isinstance(msg, ToolMessage):
                            returned.add(msg.tool_call_id)
                            name = tool_names.get(msg.tool_call_id)
                            if name:
                                content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, ensure_ascii=False)
                                tool_payloads[name]["result_characters"] += len(content)
                            await emit("tool_result", {"id": msg.tool_call_id, "content": msg.content})
        status = "completed" if answer and requested <= returned and not invalid_calls else "incomplete"
        conversation_status = status
        if status == 'completed':
            outcome = coordinator.store.load(coordinator.task_id)['latest_outcome']
            if outcome in {'blocked', 'needs_input', 'failed', 'cancelled'}:
                status = outcome
            elif generation_requested:
                delivery = coordinator.project.delivery() if coordinator.project else {}
                if delivery.get('delivery_status') != 'ready_for_vscode':
                    status = 'blocked'
        if answer and status in {'completed', 'blocked', 'needs_input', 'failed'}:
            history[:] = [*history[-2*(limits.HISTORY_TURNS-1):], HumanMessage(content=question), AIMessage(content=answer)]
        return status
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:
        from .coordinator.service import TOKEN_STOPS
        if getattr(exc, 'code', None) in TOKEN_STOPS:
            # A child can finish and export deterministically after paid calls have stopped.
            generated = next((c for c in reversed(child_summaries) if c['role'] == 'generation'), None)
            if (generated and generated['status'] == 'completed' and coordinator.project is not None
                    and coordinator.store.load(coordinator.task_id)['latest_outcome'] == 'completed'):
                delivered = coordinator.project.delivery()
                if delivered.get('delivery_status') == 'ready_for_vscode':
                    status = 'completed'
                    await emit('host_export', {'text': '模型预算已用尽；程序已完成候选工程的检查、编译和导出。'
                                                       '后续模型阶段没有继续，功能状态以验证记录为准。'})
                    return status
            status = 'blocked'
        elif coordinator.model_stop_reason is not None:
            status = 'blocked'
        await emit("error", {"text": error_message(exc)})
        return status
    finally:
        main_model_calls = model_calls
        main_usage = list(usage)
        for child in child_summaries:
            model_calls += child['model_responses']
            usage.extend(u for u in child['usage'] if u is not None)
        summary = {
            "run_id": run_id, "project": None,
            "status": status, "elapsed_seconds": round(time.monotonic() - started, 2),
            "conversation_status": conversation_status,
            "tool_requests": len(requested), "tool_results": len(returned),
            "model_responses": model_calls, "usage": usage,
            "main_model_responses": main_model_calls, "main_usage": main_usage,
            "child_runs": child_summaries,
            "budget_profile": limits.snapshot(), "effective_timeout_seconds": timeout,
            "response_metrics": response_metrics,
            "tool_payload_characters": tool_payloads,
            "input_tokens_reported": sum(u.get("input_tokens", 0) for u in usage) if usage else None,
            "output_tokens_reported": sum(u.get("output_tokens", 0) for u in usage) if usage else None,
            "tokens_reported": sum(u.get("total_tokens", 0) for u in usage) if usage else None,
            "usage_complete": bool(model_calls) and len(usage) == model_calls
                and all(c['usage_complete'] for c in child_summaries)
                and status in {"completed", "blocked", "needs_input", "failed"},
        }
        try:
            summary['coordinator'] = coordinator.state()
            if coordinator.project:
                summary['project'] = coordinator.project.delivery()
                latest = summary['coordinator']['stage_progress']['generation']['latest_status']
                summary['workflow_status'] = (
                    'ready_for_vscode' if summary['project']['delivery_status'] == 'ready_for_vscode'
                    else latest if latest != 'not_started' else 'incomplete')
            else:
                summary['workflow_status'] = 'no_project'
            with coordinator.store.connect() as con:
                coordinator.store.save_record(con, coordinator.task_id,
                    {'run_id': run_id, 'kind': 'main_turn', 'question': question, 'summary': summary, 'events': events})
        except Exception:
            summary['log_status'] = 'write_failed'
        await emit("summary", summary)
