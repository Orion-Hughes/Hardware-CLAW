"""UI-independent, bounded execution of one user turn."""
import asyncio
import time
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .agent import RUN_TIMEOUT_SECONDS, build_agent


def error_message(exc):
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


async def execute_turn(model, question, history, emit, timeout=None, project=None, require_delivery=False):
    """Keep only completed user/answer pairs; never retain partial tool chains."""
    started = time.monotonic()
    if timeout is None:
        timeout = 900 if project else RUN_TIMEOUT_SECONDS
    usage, requested, returned = [], set(), set()
    answer = ""
    model_calls = 0
    status = "error"
    invalid_calls = False
    run_id = uuid.uuid4().hex
    events = []
    sink = emit
    async def emit(kind, data):
        events.append({"kind": kind, "data": data})
        await sink(kind, data)
    delivery = None
    initial_version = project.get()["version"] if project else None
    try:
        # A fresh graph invocation resets per-run middleware counters.
        async with asyncio.timeout(timeout):
            async for update in (build_agent(model, project=project) if project else build_agent(model)).astream(
                {"messages": [*history[-6:], HumanMessage(content=question)]},
                config={"recursion_limit": 128 if project else 40}, stream_mode="updates",
            ):
                for value in update.values():
                    if not isinstance(value, dict):
                        continue
                    for msg in value.get("messages", []):
                        if isinstance(msg, AIMessage):
                            model_calls += 1
                            if msg.usage_metadata:
                                usage.append(dict(msg.usage_metadata))
                            if msg.invalid_tool_calls:
                                invalid_calls = True
                                await emit("invalid_tool_call", {"calls": msg.invalid_tool_calls})
                                await emit("error", {"text": "模型返回了无法解析的工具参数；该调用未执行，请重试并缩小文件批次。"})
                            for call in msg.tool_calls:
                                requested.add(call["id"])
                                await emit("tool_request", call)
                            if msg.content:
                                await emit("model", {"text": msg.content, "final": not msg.tool_calls})
                            answer = msg.content if not msg.tool_calls else ""
                        elif isinstance(msg, ToolMessage):
                            returned.add(msg.tool_call_id)
                            await emit("tool_result", {"id": msg.tool_call_id, "content": msg.content})
        status = "completed" if answer and requested <= returned and not invalid_calls else "incomplete"
        if project:
            require_delivery = require_delivery or project.get()["version"] != initial_version
            delivery, packaged = final_delivery(project, require_delivery)
            if packaged:
                await emit("host_export", {"text": "宿主已打包当前已编译工程；未修改源码，行为状态保持实际评估结果。"})
            if require_delivery and delivery["delivery_status"] not in {"generated_not_simulated", "ready_for_vscode"}:
                status = "incomplete"
                await emit("error", {"text": "工程尚未完成当前版本的基础检查与导出；已保存的进度保留，模型回答不作为交付成功依据。"})
            elif require_delivery and delivery.get("evaluation_required"):
                verdict = delivery.get("behavior", "not_run")
                if verdict == "not_run":
                    status = "incomplete"
                    await emit("error", {"text": "当前工程尚未执行仿真评估；可打开的交付物不等于功能通过。"})
                elif verdict in {"fail", "timeout"}:
                    status = "validation_failed"
                elif verdict in {"tool_error", "unsupported"}:
                    status = "validation_unavailable"
        if status in {"completed", "validation_failed", "validation_unavailable"}:
            history[:] = [*history[-4:], HumanMessage(content=question), AIMessage(content=answer)]
        return status
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:
        await emit("error", {"text": error_message(exc)})
        return status
    finally:
        summary = {
            "run_id": run_id, "project": delivery,
            "status": status, "elapsed_seconds": round(time.monotonic() - started, 2),
            "tool_requests": len(requested), "tool_results": len(returned),
            "model_responses": model_calls, "usage": usage,
            "tokens_reported": sum(u.get("total_tokens", 0) for u in usage) if usage else None,
            "usage_complete": bool(model_calls) and len(usage) == model_calls and status in {"completed", "validation_failed", "validation_unavailable"},
        }
        if project:
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
