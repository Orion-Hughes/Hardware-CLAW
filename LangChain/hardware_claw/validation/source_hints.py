"""Conservative textual hints; only a compiler can resolve C/C++ translation units."""
import re
from pathlib import PurePosixPath

SOURCE_SUFFIXES = {".c", ".cpp", ".h", ".hpp", ".ino"}
TOKENS = re.compile(
    r'R"(?P<delimiter>[^\s()\\]{0,16})\([\s\S]*?\)(?P=delimiter)"'
    r'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')


def blank(text):
    return re.sub(r"[^\n]", " ", text)


def strip_comments(text):
    return TOKENS.sub(lambda m: blank(m[0]) if m[0].startswith(("//", "/*")) else m[0], text)


def code_only(text):
    """Mask comments and literals so diagnostic text cannot look like executable code."""
    return TOKENS.sub(lambda m: blank(m[0]), text)


def source_hints(state, issue):
    sources = {name: code_only(text) for name, text in state["files"].items()
               if PurePosixPath(name).suffix in SOURCE_SUFFIXES}
    source = "\n".join(sources.values())
    conditional = bool(re.search(r"^\s*#\s*(?:if|ifdef|ifndef|elif)\b", source, re.M))
    for entry in ("setup", "loop"):
        if not re.search(r"\bvoid\s+" + entry + r"\s*\(\s*\)", source):
            issue("ENTRY_UNVERIFIED", "sources", f"未在简单文本扫描中确认{entry}；由真实编译/链接判断。", severity="unverified")
    for name, pin in state["design"].get("pin_defines", {}).items():
        literal = r"(-?\d+)(?=\s*(?:;|,|$))"
        definitions = re.findall(r"(?:^\s*#define\s+" + re.escape(name) + r"\s+|\b" + re.escape(name) + r"\s*=\s*)" + literal,
                                 source, flags=re.MULTILINE)
        numbers = {int(v) for v in definitions}
        if numbers and pin not in numbers and len(numbers) == 1 and len(definitions) == 1 and not conditional:
            issue("PIN_DEFINE_MISMATCH", "sources", f"简单字面量{name}={next(iter(numbers))}与声明{pin}不符；请核对设计。",
                  blocks=("simulation", "delivery"))
        elif numbers != {pin}:
            issue("PIN_DEFINE_UNVERIFIED", "sources", f"无法静态确认{name}={pin}；表达式、条件编译或间接定义需要进一步证据。", severity="unverified")
    if state["template"] == "vscode":
        baud = ((state.get("hardware", {}).get("mcu", {}).get("shared_configuration") or {}).get("build") or {}).get("serial_baud", 115200)
        literals = {int(v) for v in re.findall(r"\bSerial\s*\.\s*begin\s*\(\s*(\d+)\s*[,)]", source)}
        if len(literals) == 1 and baud not in literals and not conditional:
            issue("SERIAL_BAUD_MISMATCH", "sources", f"Serial.begin的字面量与当前{baud}串口观测配置不符。", blocks=("simulation", "delivery"))
        elif literals != {baud}:
            issue("SERIAL_UNVERIFIED", "sources", "未确认当前串口初始化；串口观察可能无输出，不能据此判断功能失败。", severity="unverified")
