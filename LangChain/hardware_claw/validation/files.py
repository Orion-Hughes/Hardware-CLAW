"""Stage-scoped structural checks and explicit uncertainty; never functional acceptance."""
import json
import re
from pathlib import PurePosixPath
from .report import STAGES, make_report
from .build_config import validate_config
from .source_hints import source_hints, strip_comments
from ..projects.implementations import choice, dependency_problems


def strict_json(text):
    def unique(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("duplicate key")
            output[key] = value
        return output
    def invalid(value):
        raise ValueError("non finite number")
    return json.loads(text, object_pairs_hook=unique, parse_constant=invalid)


def check(state):
    findings = []
    def issue(code, path, message, *, severity="error", blocks=None):
        if blocks is None:
            blocks = ("simulation", "delivery") if path in {"diagram.json", "wokwi.toml"} else STAGES
        findings.append({"code": code, "path": path, "message": message, "severity": severity,
                         "blocks": list(blocks) if severity == "error" else []})
    files, design = state["files"], state["design"]
    template = state["template"]
    required = {"diagram.json"}
    if template == "arduino":
        required |= {"sketch.ino", "libraries.txt"}
    else:
        required |= {"platformio.ini", "wokwi.toml"}
        if not any(name.startswith("src/") and PurePosixPath(name).suffix in {".c", ".cpp", ".ino"}
                   and text.strip() for name, text in files.items()):
            issue("MISSING_SOURCE", "src/", "src下缺少可编译的源文件。")
    for name in sorted(required):
        if name not in files or (name != "libraries.txt" and not files[name].strip()):
            issue("MISSING_FILE", name, "缺少该阶段必需文件或内容为空。")
    if not files.get("README.md", "").strip():
        issue("MISSING_DOCUMENTATION", "README.md", "交付说明尚未补齐；不阻断编译和仿真。", severity="warning")
    if not design:
        issue("MISSING_DESIGN", "design", "未保存设计。")
    if state["files_design_version"] != state["design_version"]:
        issue("STALE_FILES", "design", "文件未对应当前设计版本，需同步并检查。")
    hardware = state.get("hardware", {})
    if design:
        try:
            diagram = strict_json(files.get("diagram.json", ""))
            if not isinstance(diagram, dict) or diagram.get("version") != 1:
                raise ValueError("diagram version must be 1")
            parts = diagram["parts"]
            if not isinstance(parts, list) or not all(isinstance(p, dict) for p in parts):
                raise ValueError("parts must be objects")
            ids = [p.get("id") for p in parts]
            if not all(isinstance(x, str) for x in ids) or len(set(ids)) != len(ids):
                raise ValueError("duplicate or invalid part ids")
            actual = {p["id"]: p for p in parts}
            if set(actual) != set(hardware):
                issue("PART_MISMATCH", "diagram.json", "元件实例必须与保存设计一致，板卡实例为mcu。")
            endpoints = {"$serialMonitor:TX", "$serialMonitor:RX"}
            for ident, info in hardware.items():
                definition = info["upstream_definition"]
                endpoints.update(f"{ident}:{pin}" for pin in definition["pins"])
                part = actual.get(ident, {})
                if part.get("type") != definition["type"]:
                    issue("PART_TYPE_MISMATCH", "diagram.json", f"{ident}的type应为{definition['type']}。")
                attrs = part.get("attrs", {})
                if not isinstance(attrs, dict):
                    raise ValueError("attrs must be object")
                known = {a["name"] for a in definition.get("attrs", [])}
                if set(attrs) - known:
                    issue("UNKNOWN_ATTRIBUTE", "diagram.json", f"{ident}包含上游定义未登记的属性。")
                if any(not isinstance(v, str) for v in attrs.values()):
                    issue("ATTRIBUTE_TYPE", "diagram.json", "Wokwi attrs值必须是字符串。")
            connections = diagram["connections"]
            if not isinstance(connections, list):
                raise ValueError("connections must be list")
            pairs = []
            for edge in connections:
                if not isinstance(edge, list) or len(edge) != 4 or not all(isinstance(v, str) for v in edge[:3]) or not isinstance(edge[3], list) or not all(isinstance(v, str) for v in edge[3]):
                    raise ValueError("connection must be [endpoint,endpoint,color,route-list]")
                a, b = edge[:2]
                if a not in endpoints or b not in endpoints or a == b:
                    issue("INVALID_ENDPOINT", "diagram.json", f"无效端点：{a} -> {b}")
                pairs.append(tuple(sorted((a, b))))
            expected = {tuple(sorted((e["a"], e["b"]))) for e in design["connections"]}
            if len(set(pairs)) != len(pairs) or set(pairs) != expected:
                issue("CONNECTION_MISMATCH", "diagram.json", "diagram连接与design不一致或存在重复连接。")
            # Union/find catches rail shorts through indirect wiring, not just direct pairs.
            parent = {}
            def find(node):
                parent.setdefault(node, node)
                if parent[node] != node:
                    parent[node] = find(parent[node])
                return parent[node]
            board_pins = hardware.get("mcu", {}).get("upstream_definition", {}).get("pins", [])
            for prefix in ("GND", "3V3"):
                same_rail = ["mcu:" + pin for pin in board_pins if pin.startswith(prefix)]
                for pin in same_rail[1:]:
                    parent[find(pin)] = find(same_rail[0])
            for a, b in pairs:
                parent[find(a)] = find(b)
            rails = {pin: find("mcu:" + pin) for pin in hardware.get("mcu", {}).get("upstream_definition", {}).get("pins", []) if pin.startswith(("3V3", "GND")) or pin == "5V"}
            groups = {"ground": {v for k, v in rails.items() if k.startswith("GND")}, "3v3": {v for k, v in rails.items() if k.startswith("3V3")}, "5v": {v for k, v in rails.items() if k == "5V"}}
            if groups["ground"] & (groups["3v3"] | groups["5v"]) or groups["3v3"] & groups["5v"]:
                issue("POWER_SHORT", "diagram.json", "供电轨与地或不同供电轨相连。")
            shared = hardware.get("mcu", {}).get("shared_configuration") or {}
            policy = shared.get("gpio_policy", {})
            preferred = set(policy.get("preferred_digital_gpio", []))
            pins = {int(endpoint[4:]) for pair in pairs for endpoint in pair
                    if endpoint.startswith("mcu:") and endpoint[4:].isdigit()}
            for pin in sorted(pins):
                if pin in policy.get("unavailable_gpio", []):
                    issue("GPIO_UNAVAILABLE", "diagram.json", f"GPIO{pin}在当前板卡资料中明确不可用。")
                elif template == "vscode" and pin in policy.get("reserve_uart0_gpio", []):
                    issue("GPIO_RESOURCE_CONFLICT", "diagram.json", f"GPIO{pin}被当前UART0观测配置占用。")
                elif preferred and pin not in preferred:
                    issue("GPIO_NOT_PREFERRED", "diagram.json", f"GPIO{pin}不在默认推荐列表；需核对复用/启动/板卡变体限制。", severity="warning")
            for ident, info in hardware.items():
                if ident == "mcu":
                    continue
                mapping = info["profile"]["simulation"].get("logical_signal_to_model_pin", {})
                for signal, pin in mapping.items():
                    endpoint = f"{ident}:{pin}"
                    if signal in {"POWER", "GROUND"}:
                        voltage = info["profile"].get("electrical_profile", {}).get("supply_v")
                        targets = groups["ground"] if signal == "GROUND" else groups["3v3"] if voltage == 3.3 else groups["5v"] if voltage == 5 else groups["3v3"] | groups["5v"]
                        if find(endpoint) not in targets:
                            issue("POWER_NOT_CONNECTED", "diagram.json", f"{endpoint}未连接对应供电或地。")
        except (ValueError, KeyError, TypeError, RecursionError):
            issue("INVALID_DIAGRAM", "diagram.json", "diagram不是合法的Wokwi基础结构；检查JSON、version、parts和connections。")
        for code, message in dependency_problems(state):
            issue(code, "design", message)
        selections = design.get("implementations", {})
        if set(selections) - set(hardware):
            issue("INVALID_IMPLEMENTATION", "design", "实现方案引用未知元件实例。")
        for instance, info in hardware.items():
            selected = choice(design, instance)
            if selected["mode"] == "framework":
                evidence = state.get("implementation_evidence", {}).get(instance, [])
                if not selected["api_refs"] or {item["ref"] for item in evidence} != set(selected["api_refs"]):
                    issue("IMPLEMENTATION_EVIDENCE_REQUIRED", "design", "framework实现缺少保存设计时核验的API依据。")
                issue("FRAMEWORK_IMPLEMENTATION_UNVERIFIED", "design", f"{instance}声明使用框架API；资料引用不证明协议、时序或功能正确。", severity="unverified")
            elif selected["mode"] != "catalog":
                issue("INVALID_IMPLEMENTATION", "design", "未知实现模式。")
            else:
                text = "\n".join(strip_comments(body) for name, body in files.items()
                                 if PurePosixPath(name).suffix in {".c", ".cpp", ".h", ".hpp", ".ino"})
                for header in info["profile"].get("driver_profile", {}).get("headers", []):
                    if header == "Arduino.h" and template == "arduino":
                        continue
                    if not re.search(r'#\s*include\s*[<"]' + re.escape(header) + r'[>"]', text):
                        issue("DRIVER_USAGE_UNVERIFIED", "sources", f"未直接找到{header}；可能经间接引用，编译器负责头文件解析。实现变化时须同步设计。", severity="unverified")
        source_hints(state, issue)
        if template == "vscode":
            try:
                from ..projects.scaffold import baseline
                diagram = strict_json(files.get("diagram.json", ""))
                required_serial = {tuple(sorted(e[:2])) for e in baseline()["serial_connections"]}
                present = {tuple(sorted(e[:2])) for e in diagram.get("connections", [])}
                if not required_serial <= present:
                    issue("SERIAL_CONNECTION_REQUIRED", "diagram.json", "当前UART0观测配置缺少serialMonitor交叉连接。")
                if diagram.get("serialMonitor", {}).get("display") != "always":
                    issue("SERIAL_DISPLAY_HINT", "diagram.json", "串口面板未设为始终显示；可按需在仿真界面打开。", severity="warning")
            except (ValueError, KeyError, TypeError, AttributeError):
                pass  # Structural diagram diagnostics already reported above.
    validate_config(state, issue)
    return make_report(state, findings)
