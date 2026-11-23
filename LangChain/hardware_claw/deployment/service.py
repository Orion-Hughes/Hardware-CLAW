"""Host-only, two-step upload. Preparing plans never opens a serial port.

The model has no execute/upload tool. A human selects a port and confirms the
exact saved plan through the host UI or CLI; execution is single-use and logged.
"""
import asyncio
import hmac
import json
import os
import re
import secrets
import subprocess
import time
import uuid

from .. import limits
from ..adapters.compiler import compiler_env, run_process
from ..projects.service import ROOT, ProjectError, atomic_json, fail, safe_path
from ..validation.files import check
from .images import PROFILE, LAYOUT, package_dir, require_profile, sha, verified_images
from .target import build_status, matches

PYTHON = ROOT / "tools/platformio-venv/Scripts/python.exe"
ID = re.compile(r"[a-f0-9]{32}\Z")
PORT = re.compile(r"COM[1-9][0-9]{0,3}\Z", re.I)
PORT_SCRIPT = (
    "import json; from serial.tools.list_ports import comports; "
    "print(json.dumps([dict(device=p.device,description=p.description,vid=p.vid,pid=p.pid,"
    "serial_number=p.serial_number,location=p.location) for p in list(comports())[:128]]))"
)


def list_ports():
    """Enumerate OS device records; no Serial(), chip probing, DTR or reset."""
    if not PYTHON.is_file():
        fail("UPLOADER_UNAVAILABLE", "PlatformIO Python 环境未安装。")
    allowed = {"systemroot", "windir", "path", "pathext", "userprofile", "appdata", "localappdata"}
    env = {key: value for key, value in os.environ.items() if key.lower() in allowed}
    try:
        result = subprocess.run([str(PYTHON), "-I", "-B", "-c", PORT_SCRIPT],
                                capture_output=True, timeout=10, env=env, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode or len(result.stdout) > 128 * 1024:
            fail("PORT_ENUMERATION_FAILED", "串口枚举失败；没有尝试打开或复位设备。")
        ports = json.loads(result.stdout)
        if not isinstance(ports, list) or any(not isinstance(p, dict) or not isinstance(p.get("device"), str) for p in ports):
            raise ValueError
        return ports
    except (OSError, subprocess.TimeoutExpired, ValueError):
        fail("PORT_ENUMERATION_FAILED", "无法读取系统串口列表；没有尝试连接硬件。")


def port_record(port, ports):
    if port is None:
        return None
    if not isinstance(port, str) or not PORT.fullmatch(port):
        fail("INVALID_UPLOAD_PORT", "当前仅支持显式 Windows COM 串口，不自动选端口，不支持网络/OTA。")
    matches = [item for item in ports if item.get("device", "").upper() == port.upper()]
    if len(matches) != 1:
        fail("UPLOAD_PORT_NOT_FOUND", "指定串口不在当前系统设备列表中。")
    return {key: matches[0].get(key) for key in ("device", "vid", "pid", "serial_number", "location")}


def require_build(project, state):
    require_profile(state)
    report = project._summary(state)["file_check"]
    if not report or report.get("verdict") != "pass" or check(state)["verdict"] != "pass":
        fail("CHECK_REQUIRED", "当前工程必须先通过静态检查。")
    build = build_status(project, state)
    if not matches(build, state) or build.get("verdict") != "pass":
        fail("BUILD_REQUIRED", "需要当前版本的 N32R16V 实物构建；请勾选重新编译，不能使用 Wokwi 仿真固件或旧配置。")
    return build


def tool_identity():
    tool = package_dir("tool-esptoolpy", PROFILE["esptool_package"]) / "esptool.py"
    if not PYTHON.is_file() or not tool.is_file() or tool.is_symlink() or tool.is_junction():
        fail("UPLOADER_UNAVAILABLE", "登记版本的 esptool 或 PlatformIO Python 环境缺失。")
    return {"python": str(PYTHON), "script": str(tool), "script_sha256": sha(tool.read_bytes()),
            "package_version": PROFILE["esptool_package"]}


def command_for(folder, port):
    tool = tool_identity()
    # esptool imports its own adjacent package, so -I (which hides the script
    # directory) is not suitable here. compiler_env omits PYTHONPATH and keys.
    args = [tool["python"], "-B", tool["script"], "--chip", PROFILE["chip"],
            "--port", port or "<SELECT_COM_PORT>", "--baud", "115200",
            "--before", "default_reset", "--after", "hard_reset", "write_flash", "-z",
            "--flash_mode", PROFILE["flash_mode"], "--flash_freq", PROFILE["flash_freq"],
            "--flash_size", PROFILE["flash_size"]]
    for name, offset in LAYOUT:
        args.extend([hex(offset), str(folder / "images" / name)])
    return args


def prepare_upload(project, expected_version, *, port=None, board=None, hardware_reviewed=False):
    """Save immutable input identity and a preview, not a hardware action."""
    if type(hardware_reviewed) is not bool:
        fail("INVALID_ARGUMENT", "hardware_reviewed 必须由用户显式确认。")
    if board is not None and board != PROFILE["board"]:
        fail("UPLOAD_BOARD_MISMATCH", "用户选择的目标板与当前构建板不一致，请先配置对应平台并重新生成/编译。")
    ports = list_ports()
    selected = port_record(port, ports)
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        build = require_build(project, state)
        upload, payloads = verified_images(project, state, build)
        ident = uuid.uuid4().hex
        folder = project.meta / "uploads" / ident
        (folder / "images").mkdir(parents=True)
        for name, blob in payloads.items():
            (folder / "images" / name).write_bytes(blob)
        blockers = []
        if selected is None:
            blockers.append("请选择系统中存在的 COM 串口；不会自动选择。")
        if board is None:
            blockers.append("请确认目标构建板 esp32-s3-devkitc-1；采购名称不等于实际构建配置。")
        if not hardware_reviewed:
            blockers.append("请人工核对实物 Flash/供电/接线/屏幕尺寸和现有数据覆盖风险。")
        ready = not blockers
        token = secrets.token_hex(8) if ready else None
        plan = {
            "schema_version": 1, "plan_id": ident, "project_id": project.id, "version": expected_version,
            "created_at": time.time(), "expires_at": time.time() + limits.UPLOAD_PLAN_SECONDS,
            "source_sha256": build["source_sha256"], "build_attempt": build["attempt"],
            "profile": require_profile(state), "images": upload["images"],
            "port": selected, "board_confirmed": board, "hardware_reviewed": hardware_reviewed,
            "tool": tool_identity(), "ready": ready, "blockers": blockers,
            "confirmation_sha256": sha(token.encode()) if token else None,
            "warnings": [
                "此操作会写入 bootloader、分区表、OTA 初始数据与应用；可能使原有固件或数据不可用，不执行全片擦除。",
                "目标为采购记录 N32R16V：32MB OPI Flash / 16MB OPI PSRAM，80MHz；实物丝印、启动和可用 PSRAM 尚未验证。",
                "使用官方 large_fat_32MB 分区（双 4.5MiB 应用 + FAT）；与旧仿真分区不同，原文件系统/OTA 数据可能不可用。",
                "Serial 日志使用 UART0：优先连接 USB 转串口接口，当前未启用原生 USB CDC。",
                "Wokwi 接线/屏幕参数不代表实物兼容；上传成功不代表功能验收通过。",
                "串口枚举不能证明芯片型号或设备身份；无 USB 标识的串口尤其需要人工核对。",
            ],
        }
        atomic_json(folder / "plan.json", plan)
        return {**plan, "confirmation_sha256": None, "confirmation": token,
                "plan_path": str(folder / "plan.json"), "command_preview": command_for(folder, port),
                "execution": "not_run", "behavior": "not_run"}


def _load_plan(project, ident):
    if not isinstance(ident, str) or not ID.fullmatch(ident):
        fail("INVALID_UPLOAD_PLAN", "烧录计划 ID 必须是32位十六进制。")
    folder = safe_path(project.meta, f"uploads/{ident}")
    try:
        value = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("UPLOAD_PLAN_NOT_FOUND", "烧录计划不存在或损坏。")
    if not isinstance(value, dict) or value.get("plan_id") != ident or value.get("project_id") != project.id:
        fail("INVALID_UPLOAD_PLAN", "烧录计划与工程身份不符。")
    return folder, value


async def execute_upload(project, ident, confirmation):
    """Called only by explicit human UI/CLI confirmation. No shell, erase-all or force.

    Project lock is held through the bounded flash operation, preventing ordinary
    application mutations. Each claimed plan can execute at most once, including
    failed/cancelled attempts. The UART port is never probed during preparation.
    """
    with project.locked():
        folder, plan = _load_plan(project, ident)
        receipt = folder / "execution.json"
        if receipt.exists():
            fail("UPLOAD_ALREADY_ATTEMPTED", "计划已执行或已被占用；失败/取消也不自动重试，请检查日志并重新准备。")
        if not plan.get("ready") or not plan.get("hardware_reviewed") or plan.get("board_confirmed") != PROFILE["board"]:
            fail("UPLOAD_CONFIRMATION_REQUIRED", "预览尚未完成端口、板卡及实物核对，禁止烧录。")
        if not isinstance(confirmation, str) or not hmac.compare_digest(sha(confirmation.encode()), plan.get("confirmation_sha256") or ""):
            fail("UPLOAD_CONFIRMATION_REQUIRED", "确认码无效，禁止烧录。")
        if not isinstance(plan.get("expires_at"), (int, float)) or time.time() > plan["expires_at"]:
            fail("UPLOAD_PLAN_EXPIRED", "确认已过期，请重新预览当前工程和串口。")
        state = project._load()
        project._check_version(state, plan.get("version"))
        project._check_live_files(state)
        build = require_build(project, state)
        upload, payloads = verified_images(project, state, build)
        if (plan.get("source_sha256") != build["source_sha256"] or plan.get("build_attempt") != build["attempt"]
                or plan.get("profile") != require_profile(state) or plan.get("images") != upload["images"]):
            fail("UPLOAD_PLAN_STALE", "编译或烧录配置发生变化，请重新准备。")
        selected = plan.get("port")
        if not isinstance(selected, dict) or port_record(selected.get("device"), list_ports()) != selected:
            fail("UPLOAD_DEVICE_CHANGED", "串口已消失或设备标识变化，需要重新确认。")
        if plan.get("tool") != tool_identity():
            fail("UPLOADER_CHANGED", "烧录工具已变化，需要重新确认。")
        for name, blob in payloads.items():
            path = folder / "images" / name
            if not path.is_file() or path.read_bytes() != blob:
                fail("BUILD_CHANGED", "预览镜像被修改，禁止执行。")
        command = command_for(folder, selected["device"])
        report = {"plan_id": ident, "project_id": project.id, "version": state["version"],
                  "source_sha256": plan["source_sha256"], "port": selected,
                  "status": "started", "started_at": time.time(), "exit_code": None,
                  "command": command, "log": str(folder / "upload.log"), "behavior": "not_run"}
        atomic_json(receipt, report)  # Claim BEFORE the first hardware operation.
        work = ROOT / "temp/uploads" / project.id / ident
        try:
            work.mkdir(parents=True)
            verdict, code = await run_process(command, work, compiler_env(work), folder / "upload.log",
                                               limits.UPLOAD_TIMEOUT_SECONDS)
            report.update(status="uploaded" if verdict == "pass" else verdict, exit_code=code)
        except asyncio.CancelledError:
            report["status"] = "cancelled"
            raise
        except OSError:
            report["status"] = "tool_error"
        except Exception:
            report["status"] = "tool_error"
            raise
        finally:
            report["elapsed_seconds"] = round(time.time() - report["started_at"], 3)
            atomic_json(receipt, report)
        return report
