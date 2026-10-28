"""Official MCP SDK + Wokwi CLI, one bounded, version-bound session per batch.

No simulator protocol reimplementation and no generated source modifications.
"""
import asyncio
import hashlib
import json
import os
import re
import time
import tomllib
import uuid
import traceback
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError

from .compiler import compiler_env
from .simulator import CLI, read_token, subject
from ..contracts.simulation_mcp import InspectSimulationInput
from ..projects.service import ROOT, ProjectError, atomic_json, fail, safe_path
from ..projects.vscode_delivery import verified_build
from ..validation.files import check
from ..catalog import KnowledgeCatalog
from .. import limits

TESTED_CLI_VERSION = "0.29.0"
CALL_TIMEOUT = limits.MCP_CALL_SECONDS
SESSION_TIMEOUT = limits.MCP_SESSION_SECONDS
MAX_EVIDENCE_BYTES = limits.MCP_EVIDENCE_BYTES
PLAN = {"mode": "official_mcp_v1", "scope": "interactive observations; no functional acceptance"}


def decode_result(raw, operation):
    """Interpret only the versioned official envelope, never business serial text."""
    texts = [c.get("text", "") for c in raw.get("content", []) if c.get("type") == "text"]
    text = "\n".join(texts)
    status = "ok"
    if raw.get("isError") or (operation != "wokwi_read_serial" and any(t.startswith("Error: ") for t in texts)):
        status = "tool_error"
    if operation == "wokwi_take_screenshot" and status == "ok" and text.startswith("Screenshot taken (base64): ") and text.endswith("..."):
        status = "unsupported"
    data = {"status": status, "text": text[-4000:], "text_characters": len(text), "text_truncated": len(text) > 4000}
    if operation == "wokwi_take_screenshot" and status == "unsupported":
        data["reason"] = "Official CLI 0.29.0 returns only the first 100 base64 characters; no complete image."
    if operation == "wokwi_get_status" and status == "ok":
        try:
            data["simulation_status"] = json.loads(text)
        except ValueError:
            data.update(status="tool_error", reason="Malformed official status response")
    if operation == "wokwi_read_pin" and status == "ok":
        match = re.fullmatch(r"Pin .+ on .+: (true|false|[\d.+-]+) \(([^)]+)V\)", text)
        if match:
            value, voltage = match.groups()
            try:
                numeric_voltage = float(voltage)
            except ValueError:
                numeric_voltage = None
            data["pin_state"] = {"value": value == "true" if value in {"true", "false"} else float(value), "voltage": numeric_voltage}
            if numeric_voltage is None:
                data.update(status="partial", reason="Official MCP returned logical value but no numeric voltage.")
    if operation in {"wokwi_set_control", "wokwi_write_serial"}:
        data["effect_verified"] = False
        data["verification_note"] = "Acknowledgement alone does not prove the firmware received or acted on this input."
    return data


def validate_controls(state, actions):
    """Official controlSet may acknowledge unknown names; require local sourced metadata."""
    design = state["design"]
    ids = {"mcu": design["board_id"], **{c["instance_id"]: c["hardware_id"] for c in design["components"]}}
    catalog = KnowledgeCatalog()
    for action in actions:
        if action.operation != "wokwi_set_control":
            continue
        args = action.arguments
        if args["partId"] not in ids:
            fail("MCP_CONTROL_UNDOCUMENTED", "元件未在当前设计登记，不能确认控制接口。")
        profile = catalog.get(ids[args["partId"]])["profile"]
        controls = profile.get("generation_profile", {}).get("controls", [])
        control = next((c for c in controls if isinstance(c, dict) and c.get("name") == args["control"]), None)
        if not control or not control.get("source_ref"):
            fail("MCP_CONTROL_UNDOCUMENTED", "控制项缺少本地有来源的资料，不能凭官方确认文本推断有效。")
        bounds = control.get("range")
        if isinstance(bounds, list) and len(bounds) == 2 and not bounds[0] <= args["value"] <= bounds[1]:
            fail("INVALID_ARGUMENT", "控制值超出登记范围。")
        if control.get("type") == "int" and not float(args["value"]).is_integer():
            fail("INVALID_ARGUMENT", "该控制项需要整数。")


def validate_config(text):
    config = tomllib.loads(text)
    wokwi = config.get("wokwi", {})
    if (set(config) != {"wokwi"} or set(wokwi) - {"version", "firmware", "elf"}
            or wokwi.get("version") != 1 or wokwi.get("firmware") != "firmware/firmware.bin"
            or wokwi.get("elf") != "firmware/firmware.elf"):
        fail("UNSUPPORTED_MCP_CONFIG", "MCP当前仅支持受控固件路径的标准配置；外部路径、自定义芯片和SD卡暂不开放。")


async def run_session(work, actions, token, *, timeout=SESSION_TIMEOUT):
    """Raw evidence is saved incrementally, including failures and cancellation."""
    started = time.monotonic()
    records = []
    result = {"mode": PLAN["mode"], "execution_status": "running", "records": records,
              "full_project_acceptance": "not_evaluated"}
    env = compiler_env(work)
    env["WOKWI_CLI_TOKEN"] = token
    params = StdioServerParameters(command=str(CLI), args=["mcp", "--quiet", str(work)], cwd=str(work), env=env)
    used_bytes = 0

    def persist(name, value):
        nonlocal used_bytes
        raw = json.dumps(value, ensure_ascii=False, indent=2).replace(token, "[REDACTED]").encode()
        used_bytes += len(raw)
        if used_bytes > MAX_EVIDENCE_BYTES:
            fail("MCP_OUTPUT_LIMIT", "MCP证据超过输出预算，停止会话。")
        (work / name).write_bytes(raw)

    try:
        async with asyncio.timeout(timeout):
            with (work / "server.log").open("w", encoding="utf-8") as err:
                async with stdio_client(params, errlog=err) as (reader, writer):
                    async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=CALL_TIMEOUT)) as session:
                        init = await session.initialize()
                        listing = await session.list_tools()
                        resources = await session.list_resources()
                        result["server"] = init.serverInfo.model_dump(mode="json")
                        result["tools"] = [t.name for t in listing.tools]
                        result["resources"] = [r.name for r in resources.resources]
                        persist("inventory.json", {"initialize": init.model_dump(mode="json"), "tools": listing.model_dump(mode="json"), "resources": resources.model_dump(mode="json")})
                        if init.serverInfo.version != TESTED_CLI_VERSION:
                            fail("MCP_VERSION_UNTESTED", "Wokwi MCP版本变化，请重新验证接口后再启用。")
                        resource_uris = {r.name: str(r.uri) for r in resources.resources if r.name in {"diagram.json", "wokwi.toml"}}

                        async def call(operation, arguments):
                            number = len(records)
                            begin = time.monotonic()
                            record = {"operation": operation, "arguments": arguments,
                                      "elapsed_start_seconds": round(begin - started, 3), "status": "pending"}
                            records.append(record)
                            atomic_json(work / "progress.json", result)
                            if operation == "wait":
                                await asyncio.sleep(arguments["milliseconds"] / 1000)
                                raw = {"content": [{"type": "text", "text": "Host wait completed; simulated time may differ."}]}
                            elif operation == "read_resource":
                                name = arguments["name"]
                                if name not in resource_uris:
                                    fail("MCP_RESOURCE_UNAVAILABLE", "官方服务未登记该资源。")
                                try:
                                    response = await session.read_resource(resource_uris[name])
                                    raw = response.model_dump(mode="json", by_alias=True)
                                    # Keep resource text in evidence, not reinsert entire diagram into context.
                                    raw["content"] = [{"type": "text", "text": f"Resource {name} saved to evidence."}]
                                except McpError as exc:
                                    original_error = str(exc).replace(token, "[REDACTED]")
                                    # Official Windows reader strips file:// instead of decoding a file URI.
                                    # Fixed relative URI stays within the server's host-selected cwd.
                                    if os.name == "nt":
                                        try:
                                            response = await session.read_resource(f"file://./{name}")
                                            raw = response.model_dump(mode="json", by_alias=True)
                                            if len(response.contents) != 1 or getattr(response.contents[0], "text", None) != (work/name).read_text(encoding="utf-8"):
                                                fail("MCP_RESOURCE_MISMATCH", "资源内容与绑定快照不一致。")
                                            raw["advertised_uri_error"] = original_error
                                            raw["compatibility_uri"] = f"file://./{name}"
                                            raw["content"] = [{"type":"text", "text": f"Resource {name} saved and matched snapshot; Windows relative URI compatibility used."}]
                                        except McpError as retry_error:
                                            raw = {"isError": True, "advertised_uri_error": original_error,
                                                   "content": [{"type":"text", "text": str(retry_error).replace(token,"[REDACTED]")} ]}
                                    else:
                                        raw = {"isError": True, "content": [{"type": "text", "text": original_error}]}
                            else:
                                if operation not in result["tools"]:
                                    fail("MCP_TOOL_UNAVAILABLE", "官方服务未登记该工具。")
                                bound = dict(arguments)
                                if operation == "wokwi_start_simulation":
                                    bound = {"projectPath": str(work)}
                                if operation == "wokwi_export_vcd":
                                    bound = {"outputPath": str(work / f"waveform-{number:03d}.vcd")}
                                response = await session.call_tool(operation, bound)
                                raw = response.model_dump(mode="json", by_alias=True)
                            evidence_name = f"response-{number:03d}.json"
                            persist(evidence_name, raw)
                            raw = json.loads(json.dumps(raw, ensure_ascii=False).replace(token, "[REDACTED]"))
                            record.update(decode_result(raw, operation))
                            record.update(evidence=evidence_name, duration_seconds=round(time.monotonic() - begin, 3))
                            if operation == "wokwi_export_vcd":
                                vcd = work / f"waveform-{number:03d}.vcd"
                                record["artifact"] = vcd.name if vcd.is_file() else None
                                if not vcd.is_file() and record["status"] == "ok":
                                    record.update(status="no_data", reason="No waveform file returned; analyzer and samples are required.")
                                if vcd.is_file() and vcd.stat().st_size > MAX_EVIDENCE_BYTES:
                                    fail("MCP_OUTPUT_LIMIT", "VCD超过输出预算。")
                            atomic_json(work / "progress.json", result)
                            return record

                        first = await call("wokwi_start_simulation", {})
                        if first["status"] != "ok":
                            result["execution_status"] = "tool_error"
                        else:
                            for action in actions:
                                await call(action.operation, action.arguments)
                            await call("wokwi_stop_simulation", {})
                            result["execution_status"] = "completed_with_gaps" if any(r["status"] != "ok" for r in records) else "completed"
    except asyncio.CancelledError:
        result["execution_status"] = "cancelled"
        raise
    except TimeoutError:
        result["execution_status"] = "timeout"
    except Exception as exc:
        # Do not echo exception text which may contain credentials or transport internals.
        result.update(execution_status="tool_error", error_code=exc.code if isinstance(exc, ProjectError) else type(exc).__name__)
        persist("error.json", {"traceback": traceback.format_exc()[-12000:]})
    finally:
        for record in records:
            if record["status"] == "pending":
                record["status"] = result["execution_status"]
        log = work / "server.log"
        if log.exists():
            with log.open("rb") as f:
                data = f.read(MAX_EVIDENCE_BYTES)
            log.write_text(data.decode("utf-8", "replace").replace(token, "[REDACTED]"), encoding="utf-8")
        result["wall_seconds"] = round(time.monotonic() - started, 3)
        # All model-visible fields are redacted too.
        clean = json.loads(json.dumps(result, ensure_ascii=False).replace(token, "[REDACTED]"))
        result.clear()
        result.update(clean)
        atomic_json(work / "result.json", result)
    return result


async def inspect(project, expected_version, actions):
    request = InspectSimulationInput.model_validate({"expected_version": expected_version,
        "actions": [a.model_dump() if hasattr(a, "model_dump") else a for a in actions]})
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        if state["template"] != "vscode" or check(state)["verdict"] != "pass":
            fail("CHECK_REQUIRED", "MCP需要通过基础检查的VS Code工程。")
        build, blobs = verified_build(project, state)
        validate_controls(state, request.actions)
        validate_config(state["files"]["wokwi.toml"])
        identity = subject(state, build, PLAN)
        if not CLI.is_file():
            fail("SIMULATOR_UNAVAILABLE", "未找到Wokwi CLI。")
        token = read_token()
        attempt = uuid.uuid4().hex
        work = ROOT / "temp/mcp-simulations" / project.id / attempt
        work.mkdir(parents=True)
        for name in ("diagram.json", "wokwi.toml"):
            (work / name).write_text(state["files"][name], encoding="utf-8")
        for name, data in blobs.items():
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        atomic_json(work / "binding.json", {"project_id": project.id, "version": expected_version,
                    "subject_sha256": identity, "actions": [a.model_dump() for a in request.actions]})
    report = await run_session(work, request.actions, token)
    with project.locked():
        current = project._load()
        project._check_version(current, expected_version)
        project._check_live_files(current)
        fresh, _ = verified_build(project, current)
        if subject(current, fresh, PLAN) != identity:
            fail("STALE_SIMULATION", "MCP运行期间工程变化，证据只保留在temp。")
        folder = project.meta / "mcp" / attempt
        folder.mkdir(parents=True)
        hashes = {}
        # Fixed host evidence filenames only; never copy project sources or credentials.
        for path in work.iterdir():
            if path.is_file() and (path.name in {"binding.json", "inventory.json", "server.log", "result.json", "progress.json", "error.json"}
                                  or path.name.startswith("response-") and path.suffix == ".json"
                                  or path.name.startswith("waveform-") and path.suffix == ".vcd"):
                data = path.read_bytes()
                if len(data) > MAX_EVIDENCE_BYTES:
                    fail("MCP_OUTPUT_LIMIT", "MCP证据文件超过保存预算，原始数据保留在temp。")
                (folder / path.name).write_bytes(data)
                hashes[path.name] = hashlib.sha256(data).hexdigest()
        report = report | {"version": expected_version, "attempt": attempt, "subject_sha256": identity,
                           "evidence_directory": str(folder), "evidence_sha256": hashes}
        atomic_json(folder / "manifest.json", report)
    return report


def read_evidence(project, expected_version, attempt, filename, offset=0, limit=4000):
    from ..contracts.simulation_mcp import ReadSimulationEvidenceInput
    ReadSimulationEvidenceInput.model_validate(dict(expected_version=expected_version, attempt=attempt, filename=filename, offset=offset, limit=limit))
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        folder = safe_path(project.meta, f"mcp/{attempt}")
        manifest = safe_path(folder, "manifest.json")
        if not manifest.is_file():
            fail("NOT_FOUND", "未找到该MCP会话证据。")
        report = json.loads(manifest.read_text(encoding="utf-8"))
        build, _ = verified_build(project, state)
        if report.get("version") != expected_version or report.get("subject_sha256") != subject(state, build, PLAN):
            fail("STALE_SIMULATION", "证据不属于当前固件/电路版本。")
        checksum = report.get("evidence_sha256", {}).get(filename)
        if checksum is None:
            fail("NOT_FOUND", "文件未在该会话证据清单登记。")
        path = safe_path(folder, filename)
        if not path.is_file() or path.stat().st_size > MAX_EVIDENCE_BYTES:
            fail("EVIDENCE_CHANGED", "证据文件缺失或超过大小限制。")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            fail("EVIDENCE_CHANGED", "证据哈希不匹配。")
        text = raw.decode("utf-8")
        if offset > len(text):
            fail("INVALID_ARGUMENT", "offset超过证据末尾。")
        end = min(offset+limit, len(text))
        return {"version": expected_version, "attempt": attempt, "filename": filename,
                "sha256": checksum, "offset": offset, "total_characters": len(text),
                "content": text[offset:end], "next_offset": end if end < len(text) else None,
                "full_project_acceptance": "not_evaluated"}
