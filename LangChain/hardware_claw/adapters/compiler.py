"""Bounded asynchronous PlatformIO adapter. Builds snapshots outside live files/."""
import asyncio
import hashlib
import os
import re
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

from ..projects.service import ROOT, ProjectError, atomic_json, fail
from ..validation.files import check
from ..validation.report import allows
from .. import limits
from .build_state import (FINGERPRINT_VERSION, build_inputs, environment_fingerprint,
                          failure_kind, fingerprint, retry_problem)

PIO = ROOT / "tools/platformio-venv/Scripts/pio.exe"
BUILD_TIMEOUT = limits.BUILD_TIMEOUT_SECONDS
MAX_LOG = 8 * 1024 * 1024


async def kill_tree(process):
    if process.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
            "/PID", str(process.pid), "/T", "/F", stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        await killer.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


async def run_process(command, cwd, env, log, timeout):
    """No shell; bounded logs, host deadline and cancellation cleanup of process tree."""
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    proc = await asyncio.create_subprocess_exec(*command, cwd=cwd, env=env,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, **options)
    size = 0
    try:
        async with asyncio.timeout(timeout):
            with log.open("wb") as stream:
                while chunk := await proc.stdout.read(8192):
                    size += len(chunk)
                    if size > MAX_LOG:
                        await kill_tree(proc)
                        return "log_limit", proc.returncode
                    stream.write(chunk)
                code = await proc.wait()
                return ("pass" if code == 0 else "fail"), code
    except TimeoutError:
        await kill_tree(proc)
        return "timeout", proc.returncode
    except BaseException:
        await asyncio.shield(kill_tree(proc))
        raise


def compiler_env(work):
    # Deliberately omit provider keys and unrelated credential-bearing environment variables.
    allowed = {"systemroot", "windir", "path", "pathext", "comspec", "userprofile", "appdata", "localappdata",
               "programfiles", "programfiles(x86)", "programdata", "home", "http_proxy", "https_proxy", "no_proxy"}
    env = {k: v for k, v in os.environ.items() if k.lower() in allowed}
    scratch = work / "tmp"
    scratch.mkdir()
    env.update(PLATFORMIO_CORE_DIR=str(ROOT / "pio"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
               TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch))
    return env


async def compile_project(project, expected_version, *, timeout=BUILD_TIMEOUT):
    started = time.monotonic()
    started_at = time.time()
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        if state["template"] != "vscode":
            fail("UNSUPPORTED_TEMPLATE", "编译工具当前仅支持vscode受控模板。")
        report = project._summary(state)["file_check"]
        if not allows(report, "build") or not allows(check(state), "build"):
            fail("CHECK_REQUIRED", "先对当前版本运行check_project_files；build阶段不能有阻断项。")
        source_hash = fingerprint(state)
        environment = environment_fingerprint(ROOT, PIO)
        problem = retry_problem(project, state, environment)
        if problem:
            fail("NO_PROGRESS", problem)
    if not PIO.is_file():
        fail("COMPILER_UNAVAILABLE", "受控PlatformIO编译器未安装。")
    # This is an application-level gate, NOT an OS sandbox. Do not accept host include paths.
    for name, content in state["files"].items():
        if Path(name).suffix in {".cpp", ".c", ".h", ".hpp", ".ino"}:
            for include in re.findall(r'#\s*include\s*[<"]([^>"\n]+)', content):
                if ":" in include or "\\" in include or include.startswith("/") or ".." in include.split("/"):
                    fail("EXTERNAL_INCLUDE", "不允许引用工程外源码路径。")
    attempt = uuid.uuid4().hex
    work = ROOT / "temp" / "builds" / project.id / attempt
    work.mkdir(parents=True)
    for name, content in state["files"].items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
    log = work / "build.log"
    cancelled = False
    try:
        verdict, code = await run_process([str(PIO), "run", "--project-dir", str(work), "--environment", "esp32s3"],
                                          work, compiler_env(work), log, timeout)
    except OSError:
        verdict, code = "tool_error", None
        log.write_text("Compiler could not start; inspect the controlled installation.", encoding="utf-8")
    except asyncio.CancelledError:
        verdict, code, cancelled = "cancelled", None, True
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    diagnostics = [line for line in text.splitlines() if re.search(
        r"error:|fatal|FAILED|Error|could not|unable to|not found|undefined reference|multiple definition", line, re.I)]
    data = {"version": expected_version, "source_sha256": source_hash, "attempt": attempt,
            "fingerprint_version": FINGERPRINT_VERSION, "build_input_paths": sorted(build_inputs(state)),
            "environment_before_sha256": environment, "environment_sha256": environment_fingerprint(ROOT, PIO),
            "started_at": started_at, "finished_at": time.time(),
            "verdict": verdict, "exit_code": code, "elapsed_seconds": round(time.monotonic() - started, 2),
            "log": str(log), "diagnostics": diagnostics[-20:], "log_tail": text[-2500:],
            "artifacts": {}, "simulation": "not_run", "behavior": "not_run"}
    outputs = {"firmware." + ext: work / ".pio/build/esp32s3" / ("firmware." + ext) for ext in ("bin", "elf")}
    if verdict == "pass" and not all(path.is_file() and path.stat().st_size > 0 for path in outputs.values()):
        data["verdict"] = "tool_error"
        data["diagnostics"] = ["Compiler exited zero but firmware artifacts are missing."]
    data["failure_kind"] = failure_kind(data["verdict"], text)
    atomic_json(work / "result.json", data)
    with project.locked():
        target = project.meta / "builds" / attempt
        target.mkdir(parents=True)
        if data["verdict"] == "pass":
            for name, source in outputs.items():
                shutil.copyfile(source, target / name)
                data["artifacts"][name] = {"path": str(target / name), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "bytes": source.stat().st_size}
        try:
            current = project._load()
            project._check_version(current, expected_version)
            project._check_live_files(current)
            if fingerprint(current) != source_hash:
                fail("VERSION_CONFLICT", "编译期间源码发生变化，不能交付旧固件。")
        except ProjectError:
            data["stale"] = True
            atomic_json(target / "result.json", data)
            raise
        atomic_json(target / "result.json", data)
        atomic_json(project.meta / "build.json", data)
    if cancelled:
        raise asyncio.CancelledError
    return data
