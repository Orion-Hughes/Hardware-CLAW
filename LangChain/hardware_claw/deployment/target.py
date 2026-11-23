"""Host-owned physical target, separate from the Wokwi compilation baseline.

Sources: Espressif DevKitC-1 v1.1 module table; Arduino-ESP32 2.0.17
boards.txt (ESP32S3 Dev Module OPI/32MB options) and tools/platformio-build.py;
platform-espressif32 6.12.0 builder/main.py. No user firmware is patched.
"""
import json

from ..projects.service import fail

TARGET = "esp32s3-n32r16v"
REPORT = "build-physical.json"
PROFILE = {
    "id": TARGET,
    "board": "esp32-s3-devkitc-1",
    "module": "ESP32-S3-WROOM-2-N32R16V",
    "platform": "espressif32@6.12.0",
    "framework_package": "3.20017.241212+sha.dcc1105b",
    "esptool_package": "2.40900.250804",
    "chip": "esp32s3",
    # DOUT is the image header/ROM boot mode used by the official OPI bootloader,
    # not a claim that this module's flash runs in legacy DOUT at runtime.
    "flash_mode": "dout",
    "flash_freq": "80m",
    "flash_size": "32MB",
    "flash_bytes": 32 * 1024 * 1024,
    "memory_type": "opi_opi",
    "psram_enabled": True,
    "psram_physical_bytes": 16 * 1024 * 1024,
    "partitions": "large_fat_32MB.csv",
    "serial": "UART0 / USB-to-UART bridge; native USB CDC is not enabled",
    "physical_identity": "purchase_record_not_verified",
    "hardware_test": "not_run",
}

OVERRIDES = (
    "\n; Hardware-CLAW physical target: ESP32-S3-WROOM-2-N32R16V\n"
    "; Source: Arduino-ESP32 2.0.17 boards.txt / OPI bootloader\n"
    "board_build.arduino.memory_type = opi_opi\n"
    "board_build.flash_mode = dout\n"
    "board_build.boot = opi\n"
    "board_build.f_flash = 80000000L\n"
    "board_build.psram_type = opi\n"
    "board_upload.flash_size = 32MB\n"
    "board_build.partitions = large_fat_32MB.csv\n"
    "build_flags = -DBOARD_HAS_PSRAM\n"
)


def platformio_for(state):
    """Only transform a deterministic scaffold, never accept arbitrary build flags."""
    from .images import require_simulation_profile
    require_simulation_profile(state)
    # Source-design protection rather than silently rewriting unsafe GPIO.
    design = state.get("design") or {}
    board_names = {name for name, info in state["hardware"].items()
                   if info.get("summary", {}).get("id") == design.get("board_id")}
    board_names.add("mcu")
    reserved = {"35", "36", "37", "GPIO35", "GPIO36", "GPIO37"}
    for edge in design.get("connections", []):
        for endpoint in (edge["a"], edge["b"]):
            owner, _, pin = endpoint.partition(":")
            if owner in board_names and pin in reserved:
                fail("PHYSICAL_GPIO_RESERVED", "N32R16V 的 GPIO35/36/37 用于内部存储器，请让 Agent 重新设计接线。")
    return state["files"]["platformio.ini"].rstrip() + "\n" + OVERRIDES


def build_status(project, state):
    path = project.meta / REPORT
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "not_run"
        if isinstance(value, dict) and value.get("version") == state["version"]:
            return value
    return "not_run"


def matches(build, state):
    from ..adapters.compiler import fingerprint
    return (isinstance(build, dict) and build.get("source_sha256") == fingerprint(state)
            and build.get("build_profile") == PROFILE
            and build.get("effective_platformio") == platformio_for(state))
