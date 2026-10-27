"""Version-bound Wokwi execution and immutable, secret-free evidence."""
import asyncio
import hashlib
import json
import os
import subprocess
import time
import uuid
import io
from pathlib import Path
from .compiler import kill_tree, compiler_env
from ..projects.service import ROOT, atomic_json, digest, fail
from ..projects.vscode_delivery import verified_build
from ..validation.files import check
from ..validation.scenarios import get_plan, scenario, assess

CLI = Path.home() / ".wokwi/bin/wokwi-cli.exe"
TOKEN_FILE = ROOT / ".secrets/wokwi-cli-token.txt"
MAX_OUTPUT = 1024 * 1024


def read_token():
    try:
        if TOKEN_FILE.is_symlink() or TOKEN_FILE.stat().st_size > 8192:
            raise ValueError()
        token = TOKEN_FILE.read_text(encoding="utf-8-sig").strip()
        if not token or any(c.isspace() for c in token):
            raise ValueError()
        return token
    except (OSError, ValueError):
        fail("WOKWI_TOKEN_UNAVAILABLE", "Wokwi凭据文件缺失或格式不正确；不会将其内容发送给模型。")


async def run_cli(work, token, *, timeout=90):
    """Bounded stdout in memory; redact before persistence. Token only in child env."""
    env = compiler_env(work)
    env["WOKWI_CLI_TOKEN"] = token
    command = [str(CLI), str(work), "--scenario", str(work / "scenario.yaml"), "--timeout", "25000",
               "--serial-log-file", str(work / "serial.txt")]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    proc = None
    chunks, size = [], 0
    verdict, code = "tool_error", None
    try:
        proc = await asyncio.create_subprocess_exec(*command, cwd=work, env=env, stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **options)
        async with asyncio.timeout(timeout):
            while chunk := await proc.stdout.read(8192):
                size += len(chunk)
                if size > MAX_OUTPUT:
                    verdict = "log_limit"
                    await kill_tree(proc)
                    break
                chunks.append(chunk)
                serial = work / "serial.txt"
                if serial.exists() and serial.stat().st_size > MAX_OUTPUT:
                    verdict = "log_limit"
                    await kill_tree(proc)
                    break
            else:
                code = await proc.wait()
                verdict = "completed"
    except TimeoutError:
        verdict = "timeout"
        if proc:
            await kill_tree(proc)
    except asyncio.CancelledError:
        verdict = "cancelled"
        if proc:
            await asyncio.shield(kill_tree(proc))
        raise
    except OSError:
        verdict = "tool_error"
    finally:
        if proc and proc.returncode is None:
            await asyncio.shield(kill_tree(proc))
        text = b"".join(chunks).decode("utf-8", "replace").replace(token, "[REDACTED]")
        (work / "cli.log").write_text(text, encoding="utf-8")
        serial = work / "serial.txt"
        with serial.open("rb") if serial.exists() else io.BytesIO() as handle:
            raw = handle.read(MAX_OUTPUT)
        serial.write_text(raw.decode("utf-8", "replace").replace(token, "[REDACTED]"), encoding="utf-8")
    return verdict, code


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def subject(state, build, plan):
    # README edits do not evade the unchanged-firmware retry guard.
    return digest(json.dumps({"bin": build["artifacts"]["firmware.bin"]["sha256"],
                              "elf": build["artifacts"]["firmware.elf"]["sha256"],
                              "diagram": state["files"]["diagram.json"], "plan": plan}, sort_keys=True))


def current_report(project, state):
    path = project.meta / "simulation.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != state["version"]:
        return None
    if value.get("subject_sha256"):
        from ..projects.service import ProjectError
        try:
            build, _ = verified_build(project, state)
            if subject(state, build, get_plan(project, state)) != value["subject_sha256"]:
                return None
        except ProjectError:
            return None
    return value


async def simulate(project, expected_version):
    started = time.monotonic()
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        if state["template"] != "vscode" or check(state)["verdict"] != "pass":
            fail("CHECK_REQUIRED", "仿真需要通过基础检查的vscode工程。")
        build, blobs = verified_build(project, state)
        plan = get_plan(project, state)
        if not plan["contract_id"]:
            result = {"version": expected_version, "execution_verdict": "unsupported", "exit_code": None,
                      "reason": plan["reason"], "scope": "no_supported_behavior_scenario"}
            atomic_json(project.meta / "simulation.json", result)
            return result
        scenario_text = scenario(state, plan)
        identity = subject(state, build, plan)
        previous = current_report(project, state)
        if not previous:
            for path in sorted((project.meta / "simulations").glob("*/result.json")):
                candidate = json.loads(path.read_text(encoding="utf-8"))
                if candidate.get("subject_sha256") == identity and candidate["execution_verdict"] == "completed":
                    previous = candidate
                    break
        if previous and previous.get("subject_sha256") == identity and previous["execution_verdict"] == "completed":
            cached = {**previous, "version": expected_version, "build_source_sha256": build["source_sha256"],
                      "reused_from_version": previous["version"], "cached": True,
                      "note": "相同固件/电路已有证据；请evaluate_tests。修正后才重新运行。"}
            atomic_json(project.meta / "simulation.json", cached)
            return cached
        if not CLI.is_file():
            fail("SIMULATOR_UNAVAILABLE", "未找到本机Wokwi CLI。")
        token = read_token()
        attempt = uuid.uuid4().hex
        work = ROOT / "temp/simulations" / project.id / attempt
        work.mkdir(parents=True)
        for name in ("diagram.json", "wokwi.toml"):
            (work / name).write_text(state["files"][name], encoding="utf-8")
        for name, data in blobs.items():
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (work / "scenario.yaml").write_text(scenario_text, encoding="utf-8")
    verdict, code = await run_cli(work, token)
    cli_log = (work / "cli.log").read_text(encoding="utf-8")
    serial = (work / "serial.txt").read_text(encoding="utf-8")
    result = {"version": expected_version, "attempt": attempt, "subject_sha256": identity,
              "build_source_sha256": build["source_sha256"], "contract_id": plan["contract_id"],
              "execution_verdict": verdict, "exit_code": code,
              "wall_seconds": round(time.monotonic() - started, 2), "simulation_limit_ms": 25000,
              "serial_tail": serial[-2000:], "cli_tail": cli_log[-1500:],
              "scope": plan["scope"], "uncovered": plan["uncovered"], "evaluation": "not_run"}
    with project.locked():
        current = project._load()
        project._check_version(current, expected_version)
        project._check_live_files(current)
        fresh, _ = verified_build(project, current)
        if subject(current, fresh, get_plan(project, current)) != identity:
            fail("STALE_SIMULATION", "仿真期间工程或固件变化，证据保留在temp，不用于当前版本。")
        folder = project.meta / "simulations" / attempt
        folder.mkdir(parents=True)
        evidence = {"scenario.yaml": scenario_text, "serial.txt": serial, "cli.log": cli_log}
        result["evidence_sha256"] = {name: digest(text) for name, text in evidence.items()}
        for name, content in evidence.items():
            (folder / name).write_text(content, encoding="utf-8", newline="")
        result["evidence_directory"] = str(folder)
        atomic_json(folder / "result.json", result)
        atomic_json(project.meta / "simulation.json", result)
    return result


def evaluate(project, expected_version):
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        record = current_report(project, state)
        if not record:
            fail("SIMULATION_REQUIRED", "先对当前版本调用simulate_project，不能用模型描述代替仿真证据。")
        if record["execution_verdict"] == "unsupported":
            result = {"version": expected_version, "verdict": "unsupported", "reason": record["reason"], "full_project_acceptance": "not_evaluated"}
        else:
            build, _ = verified_build(project, state)
            plan = get_plan(project, state)
            if subject(state, build, plan) != record["subject_sha256"]:
                fail("STALE_SIMULATION", "仿真证据与当前固件/电路/契约不匹配。")
            folder = project.meta / "simulations" / record["attempt"]
            evidence = {}
            for name, checksum in record["evidence_sha256"].items():
                data = (folder / name).read_bytes()
                if sha_bytes(data) != checksum:
                    fail("EVIDENCE_CHANGED", "仿真证据哈希变化，拒绝评估。")
                evidence[name] = data.decode("utf-8")
            result = {"version": expected_version, "attempt": record["attempt"], "subject_sha256": record["subject_sha256"],
                      "contract_id": plan["contract_id"], **assess(record, evidence["serial.txt"], evidence["cli.log"], plan)}
        atomic_json(project.meta / "evaluation.json", result)
        return result
