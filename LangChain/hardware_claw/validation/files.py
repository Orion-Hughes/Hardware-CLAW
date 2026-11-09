"""Deterministic BASIC artifact checks; never a compilation/behavior verdict."""
import configparser
import json
import re
import tomllib

REQUIRED = {
    "vscode": {"src/main.cpp", "diagram.json", "platformio.ini", "wokwi.toml", "README.md"},
    "arduino": {"sketch.ino", "diagram.json", "libraries.txt", "README.md"},
    "platformio": {"src/main.cpp", "diagram.json", "platformio.ini", "wokwi.toml", "README.md"},
}


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
    issues = []
    def issue(code, path, message):
        issues.append({"code": code, "path": path, "message": message})
    files, design = state["files"], state["design"]
    template = state["template"]
    for name in sorted(REQUIRED[template]):
        if not files.get(name, "").strip():
            issue("MISSING_FILE", name, "缺少必需文件或内容为空。")
    if not design:
        issue("MISSING_DESIGN", "design", "未保存设计。")
    host_reserved_files = set()
    try:
        from ..catalog.driver_bundles import project_driver_bundles
        for bundle in project_driver_bundles(state):
            host_reserved_files.add(bundle["install"]["destination"] + "/bundle.json")
            host_reserved_files.update(bundle["install"]["destination"] + "/" + item["path"]
                                       for item in bundle["files"])
    except Exception as exc:
        issue("INVALID_DRIVER_BUNDLE", "design", getattr(exc, "message", str(exc)))
    if set(files) & host_reserved_files:
        issue("HOST_MANAGED_DEPENDENCY", ",".join(sorted(set(files) & host_reserved_files)),
              "本地驱动包由宿主在编译和导出时注入；模型不得生成或修改这些文件。")
    if state["files_design_version"] != state["design_version"]:
        issue("STALE_FILES", "design", "文件未对应当前设计版本，需重新生成并检查。")
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
                expected_attrs = info.get("profile", {}).get("simulation", {}).get("proposed_attrs", {})
                attrs = part.get("attrs", {})
                if not isinstance(attrs, dict):
                    raise ValueError("attrs must be object")
                if attrs != expected_attrs:
                    issue("SIMULATION_ATTRS_MISMATCH", "diagram.json",
                          f"{ident}的attrs必须为{json.dumps(expected_attrs, ensure_ascii=False, sort_keys=True)}，"
                          f"与硬件快照{info['summary']['id']}一致；请执行scaffold_project，不要手写或覆盖diagram。")
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
            preferred = set(shared.get("gpio_policy", {}).get("preferred_digital_gpio", []))
            for a, b in pairs:
                for endpoint in (a, b):
                    if endpoint.startswith("mcu:") and endpoint[4:].isdigit() and int(endpoint[4:]) not in preferred:
                        issue("RESERVED_GPIO", "diagram.json", f"{endpoint}不在当前保守GPIO分配范围。")
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
        source_name = "sketch.ino" if template == "arduino" else "src/main.cpp"
        source = files.get(source_name, "")
        for func in ("setup", "loop"):
            if not re.search(r"\bvoid\s+" + func + r"\s*\(\s*\)", source):
                issue("MISSING_ENTRY", source_name, f"缺少void {func}()入口。")
        for name, pin in design["pin_defines"].items():
            pattern = r"(?:#define\s+" + re.escape(name) + r"\s+|\b" + re.escape(name) + r"\s*=\s*)" + str(pin) + r"\b"
            if not re.search(pattern, source):
                issue("PIN_DEFINE_MISMATCH", source_name, f"未发现简单整数定义{name}={pin}；不能推断复杂表达式。")
        for info in hardware.values():
            for header in info["profile"].get("driver_profile", {}).get("headers", []):
                if header == "Arduino.h" and template == "arduino":
                    continue
                if not re.search(r'#\s*include\s*[<"]' + re.escape(header) + r'[>"]', source):
                    issue("MISSING_INCLUDE", source_name, f"缺少驱动头文件{header}。")
            for dep in info["profile"].get("driver_profile", {}).get("dependencies", []):
                if dep.get("resolution") == "local_bundle":
                    if any(d["name"] == dep["name"] and d["version"] == dep["version"] for d in design["dependencies"]):
                        issue("LOCAL_DEPENDENCY_MUST_BE_HOST_MANAGED", "design",
                              f"{dep['name']}@{dep['version']}是local_bundle；不要写入design.dependencies或lib_deps。")
                    continue
                if not any(d["name"] == dep["name"] and d["version"] == dep["version"] for d in design["dependencies"]):
                    issue("MISSING_DESIGN_DEPENDENCY", "design", f"设计未包含资料中的依赖{dep['name']}@{dep['version']}。")
        dependency_text = re.sub(r"[ \t]*@[ \t]*", "@", files.get("libraries.txt" if template == "arduino" else "platformio.ini", ""))
        for dep in design["dependencies"]:
            if dep["name"] + "@" + dep["version"] not in dependency_text:
                issue("MISSING_DEPENDENCY", "libraries.txt" if template == "arduino" else "platformio.ini", f"缺少固定依赖{dep['name']}@{dep['version']}。")
    if template == "vscode":
        try:
            from ..projects.scaffold import render, baseline
            expected_files = render(state)
            for name in ("platformio.ini", "wokwi.toml"):
                if files.get(name) != expected_files[name]:
                    issue("FIXED_CONFIG_MISMATCH", name, "运行scaffold_project恢复受控模板，不手写构建配置。")
            diagram = strict_json(files.get("diagram.json", ""))
            required = {tuple(sorted(e[:2])) for e in baseline()["serial_connections"]}
            present = {tuple(sorted(e[:2])) for e in diagram.get("connections", [])}
            if not required <= present:
                issue("SERIAL_CONNECTION_REQUIRED", "diagram.json", "缺少UART0到serialMonitor的交叉连接。")
            if diagram.get("serialMonitor", {}).get("display") != "always":
                issue("SERIAL_DISPLAY_REQUIRED", "diagram.json", "serialMonitor.display必须为always。")
            source = files.get("src/main.cpp", "")
            if not re.search(r"Serial\s*\.\s*begin\s*\(\s*115200\s*\)", source) or "HWCLAW_BOOT" not in source:
                issue("OBSERVATION_REQUIRED", "src/main.cpp", "初始化Serial.begin(115200)并输出HWCLAW_BOOT启动标记。")
        except (ValueError, KeyError, TypeError):
            issue("INVALID_VSCODE_CONFIG", "design", "vscode配置不符合受控基线；检查依赖、串口和设计。")
    if template == "platformio":
        try:
            ini = configparser.ConfigParser(interpolation=None)
            ini.read_string(files.get("platformio.ini", ""))
            envs = [s for s in ini.sections() if s.startswith("env:")]
            if len(envs) != 1 or len(ini.sections()) != 1 or ini.defaults():
                raise ValueError("one env section only")
            env = envs[0]
            if not re.fullmatch(r"env:[a-zA-Z0-9_-]+", env):
                raise ValueError("invalid env")
            allowed = {"platform", "board", "framework", "monitor_speed", "lib_deps"}
            if set(ini[env]) - allowed:
                issue("UNSUPPORTED_BUILD_OPTION", "platformio.ini", "只允许platform/board/framework/monitor_speed/lib_deps；禁止脚本与外部路径。")
            baseline = (hardware.get("mcu", {}).get("shared_configuration") or {}).get("build", {})
            for key, expected_value in {"platform": baseline.get("platformio_platform"), "board": baseline.get("board"), "framework": "arduino"}.items():
                if ini[env].get(key) != expected_value:
                    issue("BUILD_BASELINE_MISMATCH", "platformio.ini", f"{key}与共享构建基线不一致。")
            expected_deps = {d["name"] + "@" + d["version"] for d in (design or {}).get("dependencies", [])}
            if {re.sub(r"[ \t]*@[ \t]*", "@", x.strip()) for x in ini[env].get("lib_deps", "").splitlines() if x.strip()} != expected_deps:
                issue("BUILD_DEPENDENCY_MISMATCH", "platformio.ini", "lib_deps必须与设计中的名称和版本一致。")
            config = tomllib.loads(files.get("wokwi.toml", ""))
            wokwi = config.get("wokwi", {})
            if set(config) != {"wokwi"} or not isinstance(wokwi, dict):
                issue("INVALID_WOKWI_SECTION", "wokwi.toml", "当前支持的配置需要且仅包含[wokwi]表。")
                wokwi = {}
            if wokwi.get("version") != 1:
                issue("WOKWI_VERSION_REQUIRED", "wokwi.toml", "在[wokwi]表下添加整数version = 1。")
            for key, ext in (("firmware", "bin"), ("elf", "elf")):
                if wokwi.get(key) != f".pio/build/{env[4:]}/firmware.{ext}":
                    issue("FIRMWARE_PATH_MISMATCH", "wokwi.toml", f"{key}应为.pio/build/{env[4:]}/firmware.{ext}；文件尚未构建。")
        except (ValueError, KeyError, TypeError, configparser.Error):
            issue("INVALID_BUILD_CONFIG", "platformio.ini/wokwi.toml", "构建配置无法解析或超出支持范围。")
    return {"version": state["version"], "validator_version": 1, "verdict": "fail" if issues else "pass", "issues": issues,
            "scope": "basic_files_only", "warnings": ["不是C++编译器，不证明源码语义、GPIO实际用途、采样时序、电气或行为正确。", "第三方模型的额外芯片资源和运行时支持仍须编译/仿真验证。"],
            "build": "not_run", "simulation": "not_run", "behavior": "not_run"}
