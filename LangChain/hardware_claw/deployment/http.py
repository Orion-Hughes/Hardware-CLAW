"""Local-only firmware workspace and guarded HTTP endpoints, independent of LLMs."""
import asyncio
import json
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, StrictInt
from starlette.responses import FileResponse, JSONResponse

from ..adapters.compiler import compile_project
from ..catalog.service import CatalogError
from ..projects.service import ProjectService, ProjectError, WORKSPACE, ID, atomic_json
from .images import PROFILE, require_profile
from .service import list_ports, prepare_upload, execute_upload
from .target import TARGET, build_status, matches

PREFIX = "/hardware-claw-flash"
UI = Path(__file__).with_name("ui")
COOKIE = "hwclaw_flash_session"
SESSION_SECONDS = 7200
TERMINAL = {"completed", "failed", "cancelled"}


class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: StrictStr
    version: StrictInt
    port: StrictStr | None = None
    board: StrictStr | None = None
    hardware_reviewed: StrictBool = False
    rebuild: StrictBool = False


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: StrictStr
    confirmation_text: StrictStr


class FlashController:
    def __init__(self, workspace=WORKSPACE):
        self.workspace = Path(workspace)
        self.sessions = {}
        self.jobs = {}
        self.running = None

    def session(self, key):
        value = self.sessions.get(key)
        if not value or value["expires"] < time.time():
            raise HTTPException(403, "页面会话已失效，请刷新烧录页面。")
        return value

    def new_session(self, existing=None):
        if existing in self.sessions and self.sessions[existing]["expires"] > time.time():
            return existing
        for key in list(self.sessions):
            if self.sessions[key]["expires"] < time.time():
                self.sessions.pop(key)
        if len(self.sessions) >= 128:
            raise HTTPException(429, "烧录页面会话过多，请稍后重试。")
        key = secrets.token_urlsafe(32)
        self.sessions[key] = {"csrf": secrets.token_urlsafe(32), "expires": time.time() + SESSION_SECONDS,
                              "plan": None, "latest_job": None}
        return key

    def open_project(self, ident):
        return ProjectService.open(ident, workspace=self.workspace)

    def projects(self):
        """Lightweight folder listing; full guards run on selection and mutation."""
        result = []
        if not self.workspace.is_dir():
            return result
        for folder in sorted(self.workspace.iterdir(), key=lambda p: p.name):
            if not folder.is_dir() or folder.is_symlink() or folder.is_junction() or not ID.fullmatch(folder.name):
                continue
            try:
                pointer = folder / ".hwclaw/project.json"
                # Don't traverse links just to build a dropdown.
                if any(p.is_symlink() or p.is_junction() for p in (folder / ".hwclaw", pointer)):
                    continue
                version = json.loads(pointer.read_text(encoding="utf-8"))["version"]
                if type(version) is not int or version < 0:
                    continue
                state_path = folder / f".hwclaw/revisions/v{version:06d}/state.json"
                if any(p.is_symlink() or p.is_junction() for p in (state_path, *state_path.parents) if p != self.workspace.parent):
                    continue
                if state_path.stat().st_size > 8 * 1024 * 1024:
                    continue
                state = json.loads(state_path.read_text(encoding="utf-8"))
                result.append({"id": folder.name, "title": str(state.get("title", folder.name))[:120],
                               "version": version, "folder": str(folder)})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return result

    def project_info(self, ident):
        project = self.open_project(ident)
        with project.locked():
            state = project._load()
            project._check_live_files(state)
            summary = project._summary(state)
            build = build_status(project, state)
            try:
                profile = require_profile(state)
                supported, reason = True, None
                matching = matches(build, state)
            except (ProjectError, CatalogError, ValueError) as exc:
                profile, supported, reason, matching = None, False, str(exc), False
            return {"id": ident, "folder": str(project.root), "version": state["version"],
                    "title": state.get("title"), "requirement": state.get("requirements", {}).get("original", "")[:3000],
                    "board_id": (state.get("design") or {}).get("board_id"),
                    "components": (state.get("design") or {}).get("components", []),
                    "check": (summary.get("file_check") or {}).get("verdict", "not_run"),
                    "build": build.get("verdict", "not_run") if isinstance(build, dict) else "not_run",
                    "build_matches": matching, "upload_images": (build.get("upload") or {}).get("status", "unavailable") if isinstance(build, dict) else "unavailable",
                    "supported": supported, "unsupported_reason": reason, "profile": profile}

    def get_job(self, session_key, ident):
        job = self.jobs.get(ident)
        if not job or job["owner"] != session_key:
            raise HTTPException(404, "任务不存在。")
        return job

    def public_job(self, job):
        value = {key: job.get(key) for key in ("id", "kind", "project_id", "version", "status",
                 "phase", "message", "created_at", "result", "error")}
        value["log_tail"] = ""
        log = job.get("log")
        if log and log.is_file() and not log.is_symlink() and not log.is_junction():
            try:
                with log.open("rb") as stream:
                    stream.seek(max(0, log.stat().st_size - 48000))
                    value["log_tail"] = stream.read(48000).decode("utf-8", errors="replace")
            except OSError:
                pass
        return value

    def _persist(self, job):
        project = job.get("project")
        if project is not None:
            try:
                record = {key: value for key, value in self.public_job(job).items() if key != "log_tail"}
                atomic_json(project.meta / "uploads/web_jobs" / f"{job['id']}.json", record)
            except OSError:
                pass

    def start_job(self, owner, kind, project_id, version, operation):
        if self.running and self.jobs[self.running]["status"] not in TERMINAL:
            raise HTTPException(409, "已有编译或烧录任务运行，请等待或先取消。")
        # Finished jobs are in-memory UI state; durable evidence stays per-project.
        for ident in list(self.jobs):
            if len(self.jobs) >= 64 and self.jobs[ident]["status"] in TERMINAL:
                self.jobs.pop(ident)
        ident = uuid.uuid4().hex
        job = {"id": ident, "owner": owner, "kind": kind, "project_id": project_id, "version": version,
               "status": "queued", "phase": "queued", "created_at": time.time(), "message": "正在准备任务",
               "result": None, "error": None, "log": None}
        self.jobs[ident] = job
        self.running = ident
        self.session(owner)["latest_job"] = ident

        async def run():
            job["status"] = "running"
            try:
                await operation(job)
                job["status"] = "completed"
            except asyncio.CancelledError:
                job.update(status="cancelled", message="任务已取消；已有写入不会回滚，实际状态以记录为准。")
                raise
            except (ProjectError, CatalogError) as exc:
                job.update(status="failed", error={"code": exc.code, "summary": str(exc)}, message=str(exc))
            except Exception:
                job.update(status="failed", error={"code": "UPLOAD_WEB_ERROR", "summary": "本地操作异常，请查看任务记录。"},
                           message="本地操作异常，未自动重试。")
            finally:
                self._persist(job)
                if self.running == ident:
                    self.running = None
        job["task"] = asyncio.create_task(run())
        return self.public_job(job)

    def prepare(self, owner, args):
        # Check identity before creating a task; no filesystem paths from clients.
        if not ID.fullmatch(args.project_id) or type(args.version) is not int or args.version < 0:
            raise HTTPException(422, "工程 ID 或版本无效。")
        session = self.session(owner)
        session["plan"] = None

        async def operation(job):
            job.update(phase="checking", message="检查工程版本、源码和文件完整性")
            project = await asyncio.to_thread(self.open_project, args.project_id)
            job["project"] = project
            self._persist(job)
            with project.locked():
                project._check_version(project._load(), args.version)
            checked = await asyncio.to_thread(project.check_files, args.version)
            if checked["verdict"] != "pass":
                job["result"] = {"check": checked}
                raise ProjectError("CHECK_REQUIRED", "静态检查未通过，请回到对话修改工程后再准备。")
            if args.rebuild:
                job.update(phase="compiling", message="正在编译；不会烧录，不修改生成源码")
                build = await compile_project(project, args.version, target=TARGET, on_log=lambda path: job.update(log=path))
                if build["verdict"] != "pass":
                    job["result"] = {"build": build}
                    raise ProjectError("BUILD_FAILED", "编译未通过，请查看日志；未烧录。")
            job.update(phase="preparing", message="校验完整镜像并生成烧录预览")
            plan = await asyncio.to_thread(prepare_upload, project, args.version, port=args.port,
                                          board=args.board, hardware_reviewed=args.hardware_reviewed)
            session["plan"] = {"project_id": args.project_id, "id": plan["plan_id"],
                               "confirmation": plan["confirmation"]}
            public = {key: value for key, value in plan.items()
                      if key not in {"confirmation", "confirmation_sha256", "tool", "command_preview"}}
            job.update(result={"plan": public}, message="预览已就绪，尚未烧录" if plan["ready"] else "预览完成，仍有待确认项")
        return self.start_job(owner, "prepare", args.project_id, args.version, operation)

    def execute(self, owner, args):
        plan = self.session(owner).get("plan")
        if args.confirmation_text != "确认烧录":
            raise HTTPException(422, "请在二次确认框中输入“确认烧录”。")
        if not plan or plan["id"] != args.plan_id or not plan.get("confirmation"):
            raise HTTPException(409, "当前页面没有匹配的可执行预览，请先完成准备与实物确认。")
        # Consume the UI authorization on task creation, never on mere GET requests.
        async def operation(job):
            project = await asyncio.to_thread(self.open_project, plan["project_id"])
            job.update(project=project, phase="uploading", message="正在烧录，请勿断开电源或 USB",
                       log=project.meta / "uploads" / plan["id"] / "upload.log")
            report = await execute_upload(project, plan["id"], plan["confirmation"])
            job.update(version=report["version"], result=report)
            if report["status"] != "uploaded":
                raise ProjectError("UPLOAD_FAILED", f"烧录结果：{report['status']}，请查看日志，不会自动重试。")
            job["message"] = "烧录工具执行成功；硬件功能尚未验证"
        job = self.start_job(owner, "execute", plan["project_id"], None, operation)
        self.session(owner)["plan"] = None
        return job

    async def cancel(self, owner, ident):
        job = self.get_job(owner, ident)
        if job["status"] not in TERMINAL:
            job["task"].cancel()
            await asyncio.gather(job["task"], return_exceptions=True)
            # A task cancelled before its first scheduling never enters finally.
            if job["status"] not in TERMINAL:
                job.update(status="cancelled", message="任务在开始前已取消。")
                self._persist(job)
                if self.running == ident:
                    self.running = None
        return self.public_job(job)

    async def shutdown(self):
        for job in list(self.jobs.values()):
            if job["status"] not in TERMINAL:
                await self.cancel(job["owner"], job["id"])


def create_router(controller):
    router = APIRouter()

    def local(request):
        try:
            host = urlsplit("http://" + request.headers.get("host", ""))
            allowed = host.hostname in {"localhost", "127.0.0.1"} and host.port is not None
        except ValueError:
            allowed = False
        if (not allowed or not request.client or request.client.host not in {"127.0.0.1", "::1"}
                or request.headers.get("sec-fetch-site") == "cross-site"):
            raise HTTPException(403, "烧录页面仅允许本机访问。")

    def session_key(request, *, mutation=False):
        local(request)
        key = request.cookies.get(COOKIE)
        session = controller.session(key)
        if mutation:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers['host']}"
            token = request.headers.get("x-hwclaw-csrf", "")
            if origin != expected or not secrets.compare_digest(token, session["csrf"]):
                raise HTTPException(403, "页面来源或确认会话无效，请刷新本地烧录页面。")
        return key

    @router.get(PREFIX)
    async def page(request: Request):
        local(request)
        key = controller.new_session(request.cookies.get(COOKIE))
        response = FileResponse(UI / "index.html", media_type="text/html", headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})
        response.set_cookie(COOKIE, key, httponly=True, samesite="strict", path=PREFIX, max_age=SESSION_SECONDS)
        return response

    @router.get(PREFIX + "/assets/{name}")
    async def asset(name: str, request: Request):
        local(request)
        types = {"app.js": "text/javascript", "style.css": "text/css", "flash.svg": "image/svg+xml"}
        if name not in types:
            raise HTTPException(404)
        return FileResponse(UI / name, media_type=types[name], headers={"Cache-Control": "no-cache"})

    @router.get(PREFIX + "/api/bootstrap")
    async def bootstrap(request: Request):
        owner = session_key(request)
        session = controller.session(owner)
        return JSONResponse({"csrf": session["csrf"], "workspace": str(controller.workspace),
                             "boards": [{"id": PROFILE["board"], "description": "N32R16V · 32MB OPI Flash · 16MB OPI PSRAM · 未实物验证"}],
                             "latest_job": session.get("latest_job")}, headers={"Cache-Control": "no-store"})

    @router.get(PREFIX + "/api/projects")
    async def projects(request: Request):
        session_key(request)
        return {"items": await asyncio.to_thread(controller.projects)}

    @router.get(PREFIX + "/api/projects/{ident}")
    async def project_info(ident: str, request: Request):
        session_key(request)
        try:
            return await asyncio.to_thread(controller.project_info, ident)
        except (ProjectError, CatalogError) as exc:
            raise HTTPException(400, {"code": exc.code, "summary": str(exc)})

    @router.get(PREFIX + "/api/ports")
    async def ports(request: Request):
        session_key(request)
        try:
            return {"items": await asyncio.to_thread(list_ports), "serial_opened": False}
        except ProjectError as exc:
            raise HTTPException(400, {"code": exc.code, "summary": str(exc)})

    @router.post(PREFIX + "/api/prepare")
    async def prepare(args: PrepareRequest, request: Request):
        return controller.prepare(session_key(request, mutation=True), args)

    @router.post(PREFIX + "/api/execute")
    async def execute(args: ExecuteRequest, request: Request):
        return controller.execute(session_key(request, mutation=True), args)

    @router.get(PREFIX + "/api/jobs/{ident}")
    async def job(ident: str, request: Request):
        return controller.public_job(controller.get_job(session_key(request), ident))

    @router.post(PREFIX + "/api/jobs/{ident}/cancel")
    async def cancel(ident: str, request: Request):
        return await controller.cancel(session_key(request, mutation=True), ident)

    return router
