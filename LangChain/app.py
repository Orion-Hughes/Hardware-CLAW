"""Chainlit adapter. Agent, tools and credentials remain on the server."""
import json
import os
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

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
from hardware_claw.deployment.web import preview_command
from hardware_claw.deployment.http import FlashController, create_router

configure_local_auth()
_store = None
flash_controller = FlashController()
# Register before Chainlit's SPA catch-all. This UI never constructs an LLM.
app.router.routes[0:0] = create_router(flash_controller).routes
_chainlit_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan_with_flash(application):
    async with _chainlit_lifespan(application) as lifespan_state:
        try:
            yield lifespan_state
        finally:
            await flash_controller.shutdown()


app.router.lifespan_context = lifespan_with_flash


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
        "project_id": project.id if project else cl.user_session.get("unavailable_project"),
        "coordinator_task_id": cl.user_session.get('coordinator_task_id'),
        "history": [{"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content} for m in history[-2*limits.HISTORY_TURNS:]],
    })


@cl.on_chat_resume
async def resume(thread):
    state = chat_store().get("state", thread["id"]) or {}
    cl.user_session.set("project", None)
    cl.user_session.set("unavailable_project", None)
    cl.user_session.set('coordinator_task_id', state.get('coordinator_task_id'))
    cl.user_session.set("history", [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]) for m in state.get("history", [])[-2*limits.HISTORY_TURNS:]])
    if state.get("project_id"):
        try:
            project = ProjectService.open(state["project_id"])
            cl.user_session.set("project", project)
            notice = cl.Message(content=f"已恢复工程 `{project.id}`，当前版本 {project.get()['version']}。后续反馈继续修改此工程；历史消息中的旧交付路径不会自动更新。")
        except ProjectError:
            cl.user_session.set("unavailable_project", state["project_id"])
            notice = cl.Message(content="此聊天绑定的工程无法打开。请恢复工程文件夹，或用 `/project 工程ID` 重新绑定；另建工程可以输入 `/new 需求`。")
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
    cl.user_session.set("unavailable_project", None)
    cl.user_session.set('coordinator_task_id', None)
    await save_chat()
    await cl.Message(content="直接输入需求或问题。Hardware-CLAW 会按需安排选型、生成和仿真规划。后续消息继续当前工程；`/new 需求` 另起任务，`/project 工程ID` 绑定已有工程。顶部“固件烧录”可选择工程文件夹、串口，完成编译准备、预览和人工确认烧录；打开页面不会连接或写入硬件。当前仿真只生成计划。").send()


@cl.on_message
async def respond(message: cl.Message):
    if len(message.content) > limits.INPUT_CHARACTERS:
        await cl.Message(content=f"问题过长，请控制在 {limits.INPUT_CHARACTERS} 字符以内。").send()
        return
    question = message.content.strip()
    if not question:
        return
    try:
        if question.split(maxsplit=1)[0] in {"/ports", "/flash-plan"}:
            await cl.Message(content=await preview_command(question, cl.user_session.get("project"))).send()
            return
        elif question.startswith("/new "):
            question = question.split(" ", 1)[1].strip()
            cl.user_session.set("project", None)
            cl.user_session.set("unavailable_project", None)
            cl.user_session.set('coordinator_task_id', None)
            cl.user_session.set("history", [])
            await save_chat()
        elif question.startswith("/project "):
            project = ProjectService.open(question.split(" ", 1)[1].strip())
            current = cl.user_session.get("project")
            if current is None or current.id != project.id:
                cl.user_session.set('coordinator_task_id', None)
                cl.user_session.set("history", [])
            cl.user_session.set("project", project)
            cl.user_session.set("unavailable_project", None)
            await save_chat()
            await cl.Message(content=f"已绑定工程 `{project.id}`，版本 {project.get()['version']}。可直接提出后续修改或导出要求。").send()
            return
        elif question.startswith("/"):
            await cl.Message(content="命令不完整或未知。请直接输入需求，或使用 `/new 需求`、`/project 工程ID`。").send()
            return
        elif cl.user_session.get("unavailable_project"):
            await cl.Message(content="当前绑定的工程无法打开。请恢复工程，或用 `/project 工程ID` 重新绑定。").send()
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
                if step.name == "read_task_evidence":
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
                f"对话：{data.get('conversation_status', data['status'])}；"
                f"工程：{data.get('workflow_status', 'unknown')}。编译交付与功能验证分别记录。"
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
        store = TaskStore()
        task_id = cl.user_session.get('coordinator_task_id')
        if task_id:
            bound = store.load(task_id)['project_id']
            if bound and (project is None or project.id != bound):
                project = ProjectService.open(bound)
                cl.user_session.set('project', project)
        else:
            task_id = store.create(project.id if project else None)
            cl.user_session.set('coordinator_task_id', task_id)
            await save_chat()
        coordinator = Coordinator(task_id, store=store, project=project, builtin_stages=True)
        model = create_model()
    except Exception as exc:
        await cl.Message(content=error_message(exc)).send()
        return
    try:
        await execute_turn(model, question, history, emit, coordinator=coordinator)
    finally:
        cl.user_session.set('project', coordinator.project)
        await save_chat()


@cl.on_stop
async def stop():
    await cl.Message(content="已请求停止本轮任务。已发出的 API 请求仍可能计费。未完成的回答不加入后续上下文。").send()
