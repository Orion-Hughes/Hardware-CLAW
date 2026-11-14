"""UI-independent, bounded execution of one user turn."""
import asyncio
import time
import uuid
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .agent import RUN_TIMEOUT_SECONDS, build_agent
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


def final_delivery(project, require_delivery):
    """Host packaging only: never edit sources, generate firmware or change verdicts."""
    delivery = project.delivery()
    packaged = False
    if require_delivery and delivery.get("build") == "pass" and not delivery.get("archive"):
        project.export(delivery["version"])
        delivery = project.delivery()
        packaged = True
    return delivery, packaged


async def execute_turn(model, question, history, emit, timeout=None, project=None, require_delivery=False, coordinator=None):
    """Keep only completed user/answer pairs; never retain partial tool chains."""
    started = time.monotonic()
    if timeout is None:
        timeout = limits.COORDINATOR_STAGE_TIMEOUT_SECONDS if coordinator is not None else (limits.PROJECT_TIMEOUT_SECONDS if project else RUN_TIMEOUT_SECONDS)
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
    sink = emit
    async def emit(kind, data):
        events.append({"kind": kind, "data": data})
        if kind == 'stage_summary':
            child_summaries.append(data)
        await sink(kind, data)
    delivery = None
    initial_version = project.get()["version"] if project else None
    try:
        if coordinator is not None:
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
        else:
            graph = build_agent(model, project=project) if project else build_agent(model)
        # A fresh graph invocation resets per-run middleware counters.
        async with asyncio.timeout(timeout):
            async for update in graph.astream(
                {"messages": [*history[-2*limits.HISTORY_TURNS:], HumanMessage(content=question)]},
                config={"recursion_limit": limits.PROJECT_GRAPH_STEPS if project else limits.QUERY_GRAPH_STEPS}, stream_mode="updates",
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
                            if coordinator is not None:
                                coordinator.record_usage(dict(msg.usage_metadata) if msg.usage_metadata else None)
                            if msg.invalid_tool_calls:
                                invalid_calls = True
                                await emit("invalid_tool_call", {"calls": msg.invalid_tool_calls})
                                await emit("error", {"text": "模型返回了无法解析的工具参数；该调用未执行，请重试并缩小文件批次。"})
                            for call in msg.tool_calls:
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
        if coordinator is not None and status == 'completed':
            outcome = coordinator.store.load(coordinator.task_id)['latest_outcome']
            if outcome in {'blocked', 'needs_input', 'failed', 'cancelled'}:
                status = outcome
        if project and coordinator is None:
            require_delivery = require_delivery or project.get()["version"] != initial_version
            delivery, packaged = final_delivery(project, require_delivery)
            if packaged:
                await emit("host_export", {"text": "宿主已打包当前已编译工程；未修改源码。当前仿真执行未启用，行为状态保持not_run。"})
            if require_delivery and delivery["delivery_status"] not in {"generated_not_simulated", "ready_for_vscode"}:
                status = "incomplete"
                await emit("error", {"text": "工程尚未完成当前版本的基础检查与导出；已保存的进度保留，模型回答不作为交付成功依据。"})
            elif require_delivery:
                verdict = delivery.get("behavior", "not_run")
                if verdict in {"fail", "timeout"}:
                    status = "validation_failed"
                elif verdict in {"tool_error", "unsupported"}:
                    status = "validation_unavailable"
        if status in {"completed", "validation_failed", "validation_unavailable"} or (
                coordinator is not None and answer and status in {'blocked', 'needs_input', 'failed'}):
            history[:] = [*history[-2*(limits.HISTORY_TURNS-1):], HumanMessage(content=question), AIMessage(content=answer)]
        return status
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:
        from .coordinator.service import TOKEN_STOPS
        if coordinator is not None and getattr(exc, 'code', None) in TOKEN_STOPS:
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
        elif coordinator is not None and coordinator.model_stop_reason is not None:
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
            "run_id": run_id, "project": delivery,
            "status": status, "elapsed_seconds": round(time.monotonic() - started, 2),
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
                and status in {"completed", "validation_failed", "validation_unavailable", "blocked", "needs_input", "failed"},
        }
        if coordinator is not None:
            try:
                summary['coordinator'] = coordinator.state()
                if coordinator.project:
                    summary['project'] = coordinator.project.delivery()
                with coordinator.store.connect() as con:
                    coordinator.store.save_record(con, coordinator.task_id,
                        {'run_id': run_id, 'kind': 'main_turn', 'question': question, 'summary': summary, 'events': events})
            except Exception:
                summary['log_status'] = 'write_failed'
        if project and coordinator is None:
            try:
                require_delivery = require_delivery or project.get()["version"] != initial_version
                if summary["project"] is None:
                    summary["project"], packaged = final_delivery(project, require_delivery)
                    if packaged:
                        summary["host_packaged"] = True
                        await emit("host_export", {"text": "任务已停止，宿主保留并打包现有已编译工程；失败/未验证状态未改变。"})
                project.record_run(run_id, {"question": question, "summary": summary, "events": events})
            except Exception:
                summary["log_status"] = "write_failed"
        await emit("summary", summary)
