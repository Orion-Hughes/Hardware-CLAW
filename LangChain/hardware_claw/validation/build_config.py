"""Parse supported configurations by meaning; do not accept executable extensions."""
import configparser
import re
import tomllib


def parse_ini(text):
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    parser.read_string(text)
    return parser


def validate_config(state, issue):
    files, design, template = state["files"], state["design"], state["template"]
    if template == "arduino":
        entries = {line.strip() for line in files.get("libraries.txt", "").splitlines()
                   if line.strip() and not line.lstrip().startswith("#")}
        wanted = {d["name"] + "@" + d["version"] for d in (design or {}).get("dependencies", [])}
        if entries != wanted:
            issue("BUILD_DEPENDENCY_MISMATCH", "libraries.txt", "库清单须匹配设计中的固定依赖，不能添加任意来源。")
        return
    env = None
    try:
        ini = parse_ini(files.get("platformio.ini", ""))
        sections = ini.sections()
        if len(sections) != 1 or ini.defaults() or not re.fullmatch(r"env:[A-Za-z0-9_-]+", sections[0]):
            raise ValueError("one supported environment required")
        env = sections[0]
        if template == "vscode" and env != "env:esp32s3":
            issue("BUILD_ENV_MISMATCH", "platformio.ini", "当前编译适配器使用env:esp32s3。")
        allowed = {"platform", "board", "framework", "monitor_speed", "lib_deps"}
        if set(ini[env]) - allowed:
            issue("UNSUPPORTED_BUILD_OPTION", "platformio.ini", "构建参数超出受控范围；不开放脚本、外部路径或任意环境扩展。")
        shared = (state.get("hardware", {}).get("mcu", {}).get("shared_configuration") or {}).get("build", {})
        wanted = {"platform": shared.get("platformio_platform"), "board": shared.get("board"), "framework": "arduino"}
        for key, value in wanted.items():
            if not value or ini[env].get(key) != value:
                issue("BUILD_BASELINE_MISMATCH", "platformio.ini", f"{key}与所选平台配置不一致。")
        speed = ini[env].get("monitor_speed")
        if speed is not None and (not speed.isdecimal() or int(speed) != shared.get("serial_baud", 115200)):
            issue("MONITOR_BAUD_MISMATCH", "platformio.ini", "监视器波特率与所选串口观测配置不一致。",
                  blocks=("simulation", "delivery"))
        actual = [re.sub(r"\s*@\s*", "@", line.strip()) for line in ini[env].get("lib_deps", "").splitlines() if line.strip()]
        expected = {d["name"] + "@" + d["version"] for d in (design or {}).get("dependencies", [])}
        if set(actual) != expected or len(actual) != len(set(actual)):
            issue("BUILD_DEPENDENCY_MISMATCH", "platformio.ini", "lib_deps须与设计中固定依赖逐项一致；别名需先登记来源。")
    except (ValueError, TypeError, configparser.Error):
        issue("INVALID_BUILD_CONFIG", "platformio.ini", "构建配置无法解析或包含多个/无效环境。")
    try:
        config = tomllib.loads(files.get("wokwi.toml", ""))
        wokwi = config.get("wokwi")
        if set(config) != {"wokwi"} or not isinstance(wokwi, dict):
            issue("INVALID_WOKWI_SECTION", "wokwi.toml", "当前适配器需要[wokwi]配置表。", blocks=("simulation", "delivery"))
            return
        if set(wokwi) - {"version", "firmware", "elf"}:
            issue("UNSUPPORTED_WOKWI_OPTION", "wokwi.toml", "额外资源/路径尚未由当前仿真适配器支持。", blocks=("simulation", "delivery"))
        if type(wokwi.get("version")) is not int or wokwi["version"] != 1:
            issue("WOKWI_VERSION_REQUIRED", "wokwi.toml", "在[wokwi]表下添加整数version = 1。", blocks=("simulation", "delivery"))
        for key, ext in (("firmware", "bin"), ("elf", "elf")):
            expected_path = f"firmware/firmware.{ext}" if template == "vscode" else f".pio/build/{env[4:] if env else ''}/firmware.{ext}"
            if wokwi.get(key) != expected_path:
                issue("FIRMWARE_PATH_MISMATCH", "wokwi.toml", f"{key}须指向当前适配器的相对路径{expected_path}。", blocks=("simulation", "delivery"))
    except (ValueError, TypeError):
        issue("INVALID_WOKWI_CONFIG", "wokwi.toml", "Wokwi配置无法解析。", blocks=("simulation", "delivery"))
