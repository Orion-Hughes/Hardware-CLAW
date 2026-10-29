"""Deterministic configuration, assembled from maintained templates and saved design."""
import json
from ..tools.templates import read_template
from .service import fail


def baseline():
    return json.loads(read_template("esp32s3_vscode"))


def normalize_design(design):
    if design["board_id"] != "esp32_s3_devkitc1_n32r16v":
        fail("UNSUPPORTED_BASELINE", "vscode当前仅支持登记的ESP32-S3 UART0仿真基线。")
    expected = {tuple(sorted(e[:2])) for e in baseline()["serial_connections"]}
    for edge in design["connections"]:
        pair = tuple(sorted((edge["a"], edge["b"])))
        if any(x.startswith("$serialMonitor:") or x in {"mcu:TX", "mcu:RX"} for x in pair) and pair not in expected:
            fail("SERIAL_CONFLICT", "当前UART0串口端点必须用于交叉连接的serialMonitor。")
    present = {tuple(sorted((e["a"], e["b"]))) for e in design["connections"]}
    for a, b, *_ in baseline()["serial_connections"]:
        if tuple(sorted((a, b))) not in present:
            design["connections"].append({"a": a, "b": b})


def render(state):
    design = state["design"]
    if not design:
        fail("DESIGN_REQUIRED", "先保存设计。")
    if state["template"] != "vscode":
        fail("UNSUPPORTED_TEMPLATE", "scaffold仅用于vscode交付模式。")
    # Dependencies must come from the pinned hardware snapshot, not arbitrary URLs/scripts.
    from .implementations import dependency_problems
    problems = dependency_problems(state)
    if problems:
        fail(*problems[0])
    data = baseline()
    dependencies = "\n".join("    " + d["name"] + "@" + d["version"] for d in design["dependencies"])
    diagram = {"version": 1, "author": "Hardware-CLAW", "editor": "wokwi",
               "parts": [{"type": info["upstream_definition"]["type"], "id": name,
                          "top": i * 150, "left": i * 230, "attrs": {}}
                         for i, (name, info) in enumerate(state["hardware"].items())],
               "connections": [[e["a"], e["b"], wire_color(e), []] for e in design["connections"]],
               "serialMonitor": data["serialMonitor"]}
    if any(p["type"].startswith("chip-") for p in diagram["parts"]):
        fail("UNSUPPORTED_CUSTOM_CHIP", "当前交付未包含自定义芯片wasm资源。")
    return {"platformio.ini": data["platformio"].replace("{{dependencies}}", dependencies),
            "wokwi.toml": data["wokwi"], "diagram.json": json.dumps(diagram, ensure_ascii=False, indent=2)}


def wire_color(edge):
    ends = (edge["a"], edge["b"])
    if any(x.startswith("$serialMonitor:") for x in ends):
        return ""
    if any(":GND" in x for x in ends):
        return "black"
    if any(":3V3" in x or ":VCC" in x or x.endswith(":5V") for x in ends):
        return "red"
    return "green"
