"""Chainlit adapter. Agent, tools and credentials remain on the server."""
import json
import os
import uuid
from datetime import datetime, timezone

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import chainlit as cl
from chainlit.server import app, UserParam
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route
from fastapi import HTTPException
from fastapi.routing import APIRoute
from langchain_core.messages import HumanMessage, AIMessage

from hardware_claw.api_config import create_model
from hardware_claw.runtime import error_message, execute_turn
from hardware_claw.projects.service import ProjectService, ProjectError
from hardware_claw.chat_store import LocalChatStore, configure_local_auth
from hardware_claw import limits
from hardware_claw.coordinator import Coordinator, TaskStore
from hardware_claw.web import ToolTimeline

configure_local_auth()
_store = None


@cl.data_layer
def chat_store():
    global _store
    if _store is None:
        _store = LocalChatStore()
    return _store


@cl.header_auth_callback
def local_user(headers):
    # This app is intentionally bound to 127.0.0.1, not a multi-user server.
    if headers.get("host", "").split(":")[0] in {"127.0.0.1", "localhost"}:
        return cl.User(identifier="hardware-claw-local", display_name="本地用户")
    return None


async def stored_asset(thread_id: str, element_id: str, current_user: UserParam):
    store = chat_store()
    if not current_user or await store.get_thread_author(thread_id) != current_user.identifier:
        raise HTTPException(404)
    data = await store.get_element(thread_id, element_id)
    key = (data or {}).get("objectKey", "")
    if len(key) != 32 or any(c not in "0123456789abcdef" for c in key):
        raise HTTPException(404)
    path = store.root / "assets" / key
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=data["name"], media_type=data.get("mime"))


app.router.routes.insert(0, APIRoute("/hardware-claw-assets/{thread_id}/{element_id}", stored_asset, methods=["GET"]))


def thread_id():
    return cl.context.session.thread_id


async def save_chat():
    project = cl.user_session.get("project")
    history = cl.user_session.get("history") or []
    chat_store().put("state", thread_id(), {
        "project_id": project.id if project else None,
        "mode": cl.user_session.get("mode") or "generate",
        "coordinator_task_id": cl.user_session.get('coordinator_task_id'),
        "history": [{"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content} for m in history[-2*limits.HISTORY_TURNS:]],
    })


@cl.on_chat_resume
async def resume(thread):
    state = chat_store().get("state", thread["id"]) or {}
    cl.user_session.set("mode", state.get("mode", "generate"))
    cl.user_session.set("project", None)
    cl.user_session.set('coordinator_task_id', state.get('coordinator_task_id'))
    cl.user_session.set("history", [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]) for m in state.get("history", [])[-2*limits.HISTORY_TURNS:]])
    if state.get("project_id"):
        try:
            project = ProjectService.open(state["project_id"])
            cl.user_session.set("project", project)
            notice = cl.Message(content=f"已恢复工程 `{project.id}`，当前版本 {project.get()['version']}。后续反馈继续修改此工程；历史消息中的旧交付路径不会自动更新。")
        except ProjectError:
            cl.user_session.set("mode", "query")
            notice = cl.Message(content="此聊天绑定的工程无法打开，已切换只读查询，未另建工程。请检查工程文件夹或用 `/project 工程ID` 重新绑定。")
        notice.id = str(uuid.uuid5(uuid.NAMESPACE_URL, "hardware-claw-resume:" + thread["id"]))
        await notice.send()
        # Chainlit replays the supplied snapshot after this callback returns.
        thread["steps"] = [s for s in thread.get("steps", []) if s.get("id") != notice.id] + [notice.to_dict()]


async def identity(request):
    return JSONResponse({"service": "hardware-claw-chainlit", "pid": os.getpid()})


# Place before Chainlit's SPA catch-all route.
app.router.routes.insert(0, Route("/hardware-claw-health", identity))


def chainlit_step_parent_id():
    """Attach manual presentation Steps to Chainlit's current on_message run."""
    try:
        return cl.context.current_step.id
    except Exception:
        # Unit tests can execute the adapter outside a live Chainlit websocket.
        return None


@cl.on_chat_start
async def start():
    cl.user_session.set("history", [])
    cl.user_session.set("project", None)
    cl.user_session.set("mode", "generate")
    cl.user_session.set('coordinator_task_id', None)
    await save_chat()
    await cl.Message(content="Hardware-CLAW 已就绪，默认工程生成模式。直接输入需求即可创建VS Code工程；后续消息继续当前工程。`/new 需求` 另建工程，`/project 工程ID` 恢复，`/query` 切换只读查询。`/coordinator` 切换新主协调模式（选型与生成子Agent已接入，验证阶段待实现）。仿真统一采集原始日志，自动功能验收尚未实现，不标记功能通过。每轮折叠显示工具过程，并显示耗时、Token及真实验证状态。").send()


@cl.on_message
async def respond(message: cl.Message):
    if len(message.content) > limits.INPUT_CHARACTERS:
        await cl.Message(content=f"问题过长，请控制在 {limits.INPUT_CHARACTERS} 字符以内。").send()
        return
    question = message.content.strip()
    if not question:
        return
    require_delivery = False
    if question == '/coordinator' or question.startswith('/coordinator '):
        project = cl.user_session.get('project')
        task_id = cl.user_session.get('coordinator_task_id')
        if not task_id:
            task_id = TaskStore().create(project.id if project else None)
        cl.user_session.set('coordinator_task_id', task_id)
        cl.user_session.set('mode', 'coordinator')
        cl.user_session.set('history', [])
        await save_chat()
        await cl.Message(content=f"已切换主协调模式，任务 `{task_id}`。现有工程绑定保留；选型子Agent已接入；生成和验证阶段尚未实现。输入 `/query` 或 `/new 需求` 可使用原流程。").send()
        question = question.partition(' ')[2].strip()
        if not question:
            return
    if question == "/query":
        cl.user_session.set("project", None)
        cl.user_session.set("mode", "query")
        cl.user_session.set("history", [])
        cl.user_session.set('coordinator_task_id', None)
        await save_chat()
        await cl.Message(content="已切换只读查询模式。已有工程保留在workspace；输入 `/new 需求` 恢复生成模式。").send()
        return
    try:
        # Default generation is an explicit UI mode, not keyword intent guessing.
        if not question.startswith("/") and cl.user_session.get("project") is None and cl.user_session.get("mode") not in {"query", "coordinator"}:
            question = "/new " + question
        if question.startswith(("/new ", "/new-pio ", "/new-arduino ")):
            template = "platformio" if question.startswith("/new-pio ") else "arduino" if question.startswith("/new-arduino ") else "vscode"
            requirement = question.split(" ", 1)[1].strip()
            project = ProjectService.create("web-project", requirement, template)
            cl.user_session.set("project", project)
            cl.user_session.set("mode", "generate")
            cl.user_session.set('coordinator_task_id', None)
            cl.user_session.set("history", [])
            await save_chat()
            question = requirement + "\n请实际完成绑定工程的文件生成、基础检查和导出。"
            require_delivery = True
            await cl.Message(content=f"已创建工程 `{project.id}`（{template}），保存在workspace。生成失败时进度也会保留。").send()
        elif question.startswith("/project "):
            project = ProjectService.open(question.split(" ", 1)[1].strip())
            cl.user_session.set("project", project)
            cl.user_session.set("mode", "generate")
            cl.user_session.set('coordinator_task_id', None)
            cl.user_session.set("history", [])
            await save_chat()
            await cl.Message(content=f"已绑定工程 `{project.id}`，版本 {project.get()['version']}。可直接提出后续修改或导出要求。").send()
            return
        elif question.startswith("/"):
            await cl.Message(content="命令不完整或未知。使用 `/new 需求`、`/project 工程ID`、`/query` 或 `/coordinator [需求]`。").send()
            return
    except ProjectError as exc:
        await cl.Message(content=f"{exc.code}：{exc}").send()
        return
    timeline = ToolTimeline(
        cl.Step,
        lambda: datetime.now(timezone.utc).isoformat(),
        root_parent_id=chainlit_step_parent_id(),
    )

    async def emit(kind, data):
        if kind == "tool_request":
            await timeline.start_tool(data["id"], data["name"], data["args"])
        elif kind == "tool_result":
            step = await timeline.finish_tool(data["id"], data["content"])
            if step:
                if step.name in {"inspect_simulation", "read_simulation_evidence"}:
                    try:
                        from hardware_claw.adapters.wokwi_mcp import read_evidence
                        payload = json.loads(data["content"]).get("data") or {}
                        names = [r.get("artifact", "") for r in payload.get("records", [])]
                        if payload.get("image"):
                            names.append(payload.get("filename", ""))
                        bound_project = cl.user_session.get("project")
                        for name in dict.fromkeys(n for n in names if isinstance(n, str) and n.endswith(".png")):
                            verified = read_evidence(bound_project, payload["version"], payload["attempt"], name)
                            await cl.Message(content="MCP截图（原始观测，尚未做视觉验收）", elements=[
                                cl.Image(name=name, path=verified["image_path"], display="inline")
                            ]).send()
                    except (ValueError, KeyError, OSError, ProjectError):
                        await cl.Message(content="截图预览未能通过证据校验，请查看工具记录；未使用未校验路径。").send()
        elif kind in ("model", "error", "host_export"):
            await cl.Message(content=data["text"]).send()
        elif kind == 'stage_start':
            await cl.Message(content=f"正在执行 `{data['stage']}` 子Agent；详细查询保存在阶段记录中。").send()
        elif kind == 'verification_plan':
            await cl.Message(content=f"仿真计划已生成：{data['cases']} 个场景，{data['gaps']} 个覆盖缺口。未执行仿真。",
                elements=[cl.File(name='simulation-plan.md', path=data['path'], display='inline')]).send()
        elif kind == 'stage_summary':
            await cl.Message(content=(f"{data['role']} 子Agent：{data['status']} · {data['model_responses']} 次模型响应 · "
                f"{data['elapsed_seconds']} 秒 · Token {data['tokens_reported']}"
                + ('' if data['usage_complete'] else '（提供方用量不完整）')),
                elements=[cl.Text(name=f"{data['role']} 阶段用量", content=json.dumps(data, ensure_ascii=False, indent=2), display='side')]).send()
        elif kind == "summary":
            await timeline.finish()
            tokens = data["tokens_reported"]
            label = str(tokens) if tokens is not None else "未返回"
            if not data["usage_complete"] and tokens is not None:
                label += "（仅已返回部分）"
            await cl.Message(content=(
                f"本轮：{data['status']} · {data['elapsed_seconds']} 秒 · "
                f"主流程工具结果 {data['tool_results']}/{data['tool_requests']} · "
                f"LLM响应 {data['model_responses']} 次 · Token {label}（含本轮子Agent）\n\n"
                "查询完成不代表硬件验证通过。"
            ), elements=[cl.Text(name="本轮用量明细", content=json.dumps(data, ensure_ascii=False, indent=2), display="side")]).send()
            delivery = data.get("project")
            if delivery:
                elements = [cl.File(name="project.zip", path=delivery["archive"], display="inline")] if delivery.get("archive") else []
                folder = delivery.get("simulation_folder")
                instructions = f"\n\nVS Code打开 `{folder}`，F1 → `Wokwi: Start Simulator`。" if folder else ""
                await cl.Message(content=f"工程 `{delivery['project_id']}` · 版本 {delivery['version']} · {delivery['delivery_status']}\n编译：{delivery['build']}；仿真执行：{delivery['simulation']}；行为判定：{delivery['behavior']}。当前仅采集仿真证据，功能未验证。{instructions}", elements=elements).send()

    history = cl.user_session.get("history")
    if history is None:
        history = []
        cl.user_session.set("history", history)
    try:
        project = cl.user_session.get("project")
        is_coordinator = cl.user_session.get('mode') == 'coordinator'
        if is_coordinator:
            bound = TaskStore().load(cl.user_session.get('coordinator_task_id'))['project_id']
            if bound and (project is None or project.id != bound):
                project = ProjectService.open(bound)
                cl.user_session.set('project', project)
        coordinator = Coordinator(cl.user_session.get('coordinator_task_id'), store=TaskStore(), project=project, builtin_stages=True) if is_coordinator else None
        model = create_model(max_tokens=limits.PROJECT_OUTPUT_TOKENS if project and not is_coordinator else limits.QUERY_OUTPUT_TOKENS)
    except Exception as exc:
        await cl.Message(content=error_message(exc)).send()
        return
    try:
        await execute_turn(model, question, history, emit, project=project, require_delivery=require_delivery, coordinator=coordinator)
    finally:
        if coordinator is not None:
            cl.user_session.set('project', coordinator.project)
        await save_chat()


@cl.on_stop
async def stop():
    await cl.Message(content="已请求停止本轮任务。已发出的 API 请求仍可能计费。未完成的回答不加入后续上下文。").send()
