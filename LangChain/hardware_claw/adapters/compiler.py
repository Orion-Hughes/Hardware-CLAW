"""Bounded asynchronous PlatformIO adapter. Builds snapshots outside live files/."""
import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

from ..projects.service import ROOT, atomic_json, digest, fail
from ..validation.files import check
from ..catalog.driver_bundles import bundle_bytes, project_driver_bundles
from .. import limits

PIO = ROOT / "tools/platformio-venv/Scripts/pio.exe"
BUILD_TIMEOUT = limits.BUILD_TIMEOUT_SECONDS
MAX_LOG = 8 * 1024 * 1024


def fingerprint(state):
    bundles = [{
        "manifest_ref": bundle["manifest_ref"], "manifest_sha256": bundle["manifest_sha256"],
        "library_name": bundle["library_name"], "version": bundle["version"],
        "files": [(item["path"], item["sha256"]) for item in bundle["files"]],
    } for bundle in project_driver_bundles(state)]
    return digest(json.dumps({"files": state["files"], "driver_bundles": bundles},
                             sort_keys=True, ensure_ascii=False))


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


async def compile_project(project, expected_version, *, timeout=BUILD_TIMEOUT, on_log=None, target=None):
    started = time.monotonic()
    from ..deployment import target as physical
    if target not in (None, physical.TARGET):
        fail("UNSUPPORTED_BUILD_TARGET", "未登记的构建目标。")
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        if state["template"] != "vscode":
            fail("UNSUPPORTED_TEMPLATE", "编译工具当前仅支持vscode受控模板。")
        report = project._summary(state)["file_check"]
        if not report or report["verdict"] != "pass" or check(state)["verdict"] != "pass":
            fail("CHECK_REQUIRED", "先对当前版本运行check_project_files并通过。")
        source_hash = fingerprint(state)
        effective_ini = physical.platformio_for(state) if target else state["files"].get("platformio.ini")
        previous = physical.build_status(project, state) if target else project.build_status(state)
        same_profile = physical.matches(previous, state) if target else True
        if same_profile and isinstance(previous, dict) and previous.get("source_sha256") == source_hash and previous["verdict"] == "fail":
            fail("NO_PROGRESS", "相同源码已编译失败，先根据日志修改，不能原样重复编译。")
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
        if name == "platformio.ini":
            content = effective_ini
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
    injected_bundles = []
    for bundle in project_driver_bundles(state):
        outputs = bundle_bytes(bundle)
        for destination, data in outputs.items():
            if destination in state["files"]:
                fail("HOST_MANAGED_DEPENDENCY", f"{destination}保留给宿主注入的本地驱动包。")
            path = work / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        injected_bundles.append({"library_name": bundle["library_name"], "version": bundle["version"],
                                 "bundle_ref": bundle["bundle_ref"], "manifest_sha256": bundle["manifest_sha256"],
                                 "files": list(outputs)})
    log = work / "build.log"
    if on_log is not None:
        on_log(log)
    try:
        verdict, code = await run_process([str(PIO), "run", "--project-dir", str(work), "--environment", "esp32s3"],
                                          work, compiler_env(work), log, timeout)
    except OSError:
        fail("COMPILER_START_FAILED", "编译器无法启动。")
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    diagnostics = [line for line in text.splitlines() if re.search(r"error:|fatal|FAILED|Error", line, re.I)]
    data = {"version": expected_version, "source_sha256": source_hash, "attempt": attempt,
            "verdict": verdict, "exit_code": code, "elapsed_seconds": round(time.monotonic() - started, 2),
            "log": str(log), "diagnostics": list(dict.fromkeys(diagnostics))[:40],
            "diagnostics_total_unique": len(set(diagnostics)), "log_tail": text[-2500:],
            "artifacts": {}, "driver_bundles": injected_bundles,
            "simulation": "not_run", "behavior": "not_run"}
    if target:
        data.update(build_profile=dict(physical.PROFILE), effective_platformio=effective_ini)
    outputs = {"firmware." + ext: work / ".pio/build/esp32s3" / ("firmware." + ext) for ext in ("bin", "elf")}
    if verdict == "pass" and not all(path.is_file() and path.stat().st_size > 0 for path in outputs.values()):
        data["verdict"] = "tool_error"
        data["diagnostics"] = ["Compiler exited zero but firmware artifacts are missing."]
    with project.locked():
        current = project._load()
        project._check_version(current, expected_version)
        project._check_live_files(current)
        if fingerprint(current) != source_hash:
            fail("VERSION_CONFLICT", "编译期间源码发生变化，不能交付旧固件。")
        if data["verdict"] == "pass":
            build_folder = project.meta / "builds" / attempt
            build_folder.mkdir(parents=True)
            for name, source in outputs.items():
                shutil.copyfile(source, build_folder / name)
                data["artifacts"][name] = {"path": str(build_folder / name), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "bytes": source.stat().st_size}
            from ..deployment.images import capture_images
            data["upload"] = capture_images(current, work, build_folder, physical=bool(data.get("build_profile")))
            if data.get("build_profile"):
                (build_folder / "platformio.ini").write_text(effective_ini, encoding="utf-8")
        atomic_json(project.meta / (physical.REPORT if data.get("build_profile") else "build.json"), data)
    return data
