"""Deterministic, readable workspace project identifiers."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path


TESTER_FILE = Path(__file__).resolve().parents[2] / "tester.txt"
PROJECT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}\Z")
TESTER_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,15}\Z")
GENERIC_TITLE = re.compile(r"^(?:web-project|agent-trial|task-[0-9a-f]+|project)$", re.IGNORECASE)
STOP_WORDS = {
    "a", "an", "and", "the", "for", "with", "using", "use", "make", "build",
    "generate", "create", "esp32", "esp32s3", "wokwi", "only", "this", "your",
}

# Vocabulary used only for readable folder names. It is not a generation rule
# and does not affect hardware selection, firmware, validation, or repair.
HARDWARE_TERMS = (
    ("dht22", ("dht22", "温湿度", "temperature humidity")),
    ("joystick", ("joystick", "摇杆")),
    ("ws2812", ("ws2812", "neopixel", "灯环")),
    ("hc_sr04", ("hc-sr04", "hcsr04", "超声波")),
    ("potentiometer", ("potentiometer", "电位器", "旋钮")),
    ("servo", ("servo", "舵机")),
    ("mpu6050", ("mpu6050", "六轴")),
    ("ds1307", ("ds1307", "rtc", "时钟")),
    ("st7789", ("st7789", "tft")),
    ("ssd1306", ("ssd1306", "oled")),
    ("display", ("display", "屏幕", "显示")),
    ("camera", ("camera", "摄像头")),
    ("audio", ("audio", "microphone", "speaker", "音频", "麦克风", "扬声器")),
    ("esp32_s3", ("esp32-s3", "esp32s3", "esp32 s3")),
)

TASK_TERMS = (
    ("serial_output", ("serial", "uart", "串口")),
    ("environment_monitor", ("温湿度", "temperature humidity", "环境监测")),
    ("input_visualizer", ("joystick", "摇杆", "圆点", "界面")),
    ("distance_detection", ("distance", "测距", "超声波")),
    ("control", ("control", "控制")),
    ("display", ("display", "屏幕", "显示")),
    ("game", ("game", "游戏")),
    ("test", ("test", "测试")),
)


def _slug(value: str, limit: int) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:limit].strip("-")


def resolve_tester(value: str | None = None) -> str:
    if value is None or not value.strip():
        configured = os.environ.get("HARDWARE_CLAW_TESTER", "").strip()
        if not configured and TESTER_FILE.is_file():
            configured = TESTER_FILE.read_text(encoding="utf-8-sig").splitlines()[0].strip()
        value = configured or "local"
    tester = _slug(value, 16)
    if not TESTER_ID.fullmatch(tester):
        raise ValueError("tester must contain readable ASCII letters, digits, '-' or '_'")
    return tester


def hardware_slug(title: str, requirement: str) -> str:
    title = title or ""
    requirement = requirement or ""
    text = f"{title}\n{requirement}".lower()
    matches = [name for name, needles in HARDWARE_TERMS if any(needle in text for needle in needles)]
    if matches:
        return "_".join(matches[:3])[:40].strip("-_")
    return "hardware"


def task_slug(title: str, requirement: str) -> str:
    title = title or ""
    requirement = requirement or ""
    explicit = _slug(title, 32)
    if explicit and not GENERIC_TITLE.fullmatch(explicit):
        return explicit[:40].strip("-_")

    text = f"{title}\n{requirement}".lower()
    matches = [name for name, needles in TASK_TERMS if any(needle in text for needle in needles)]
    if matches:
        return matches[0][:40].strip("-_")
    words = [word for word in re.findall(r"[a-zA-Z0-9]+", requirement) if word.lower() not in STOP_WORDS]
    fallback = "-".join(words[:3])[:32].strip("-")
    return fallback[:40].strip("-_") or "embedded_task"


def build_project_id(title: str, requirement: str, tester: str | None = None) -> str:
    owner = resolve_tester(tester)
    hardware = hardware_slug(title, requirement)
    task = task_slug(title, requirement)
    ident = f"{owner}-{hardware}-{task}-{uuid.uuid4().hex[:6]}"
    if not PROJECT_ID.fullmatch(ident):
        raise ValueError("generated project ID is invalid")
    return ident
