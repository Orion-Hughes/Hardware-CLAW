"""Versioned build identity and bounded retry history, independent of project names."""
import hashlib
import json
import re
import time
from pathlib import PurePosixPath

from ..validation.source_hints import SOURCE_SUFFIXES, strip_comments

FINGERPRINT_VERSION = 2
NON_BUILD_FILES = {"README.md", "diagram.json", "wokwi.toml"}
TRANSIENT_ATTEMPTS = 2
RETRY_WINDOW_SECONDS = 300


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_inputs(state):
    """Exclude only known non-build files, conservatively retaining include candidates.

    A computed include (or alternate preprocessor spelling) keeps every file.
    This is a cache key for the restricted PIO adapter, not a C++ dependency parser.
    """
    sources = "\n".join(strip_comments(body) for name, body in state["files"].items()
                        if PurePosixPath(name).suffix in SOURCE_SUFFIXES)
    includes = re.findall(r"^\s*#\s*(?:include|include_next|import)\b([^\n]*)", sources, re.M)
    uncertain = "%:" in sources or "??=" in sources or any(
        not re.fullmatch(r'\s*[<"][^>"\n]+[>"]\s*', tail) for tail in includes)
    return {name: content for name, content in state["files"].items()
            if name not in NON_BUILD_FILES or uncertain or name in sources}


def fingerprint(state):
    return digest({"algorithm": FINGERPRINT_VERSION, "template": state["template"], "files": build_inputs(state)})


def environment_fingerprint(root, compiler):
    """Observe installed tool/package manifests; never read credentials or run a shell.

    Version metadata detects normal installations/upgrades, not arbitrary tampering
    with installed tool binaries. Network recovery is handled by bounded retry windows.
    """
    paths = {compiler}
    for directory, names in ((root / "pio/platforms", ("platform.json", ".piopm")),
                             (root / "pio/packages", ("package.json", ".piopm"))):
        if directory.is_dir():
            for child in directory.iterdir():
                if child.is_dir():
                    paths.update(child / name for name in names)
    paths.update((root / "tools/platformio-venv/Lib/site-packages").glob("platformio-*.dist-info/METADATA"))
    values = {}
    for path in sorted(paths):
        try:
            values[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        except OSError:
            values[str(path)] = "unreadable"
    return digest(values)


def history(project):
    records = {}
    for path in [*(project.meta / "builds").glob("*/result.json"), project.meta / "build.json"]:
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("attempt"):
                    records.setdefault(value["attempt"], value)
            except (OSError, ValueError):
                continue  # Unreadable history never authorizes a successful build.
    return sorted(records.values(), key=lambda r: r.get("finished_at", r.get("started_at", 0)))


def matching_history(project, state, environment):
    source_hash = fingerprint(state)
    return [r for r in history(project) if r.get("fingerprint_version") == FINGERPRINT_VERSION
            and r.get("source_sha256") == source_hash and r.get("environment_sha256") == environment]


def failure_kind(verdict, log):
    if verdict == "pass":
        return None
    # Classify generic toolchain messages, never device/package names or expected logs.
    if re.search(r"could not find the package|unknownpackageerror|packageexception|"
                 r"could not (?:install|download)|(?:failed|unable) to (?:install|download)|"
                 r"connection(?:error| refused| reset)|proxyerror|sslerror|"
                 r"name resolution|network is unreachable|read timed out|http.*\b[45]\d\d\b", log, re.I):
        return "dependency_or_infrastructure"
    if verdict == "fail" and re.search(r"\berror:|\bfatal error:|undefined reference|multiple definition", log, re.I):
        return "compile_error"
    return "infrastructure_or_unknown"


def retry_problem(project, state, environment, *, now=None):
    """Return a diagnostic, not permission to run. Normal budgets still apply."""
    matches = matching_history(project, state, environment)
    # A later successful build supersedes earlier failures for this identity.
    failures = []
    for record in matches:
        if record.get("verdict") == "pass":
            failures.clear()
        else:
            failures.append(record)
    deterministic = next((r for r in reversed(failures) if r.get("failure_kind") == "compile_error"), None)
    if deterministic:
        detail = "\n".join(deterministic.get("diagnostics", [])[-3:])[-700:]
        return f"相同编译输入和工具链已失败（attempt={deterministic['attempt']}）。修改源码/构建输入后再试；改说明或改版本号不算进展。\n{detail}"
    now = time.time() if now is None else now
    recent = [r for r in failures if now - r.get("started_at", 0) < RETRY_WINDOW_SECONDS]
    if len(recent) >= TRANSIENT_ATTEMPTS:
        return (f"相同编译输入/环境在{RETRY_WINDOW_SECONDS}秒内已失败{len(recent)}次。"
                "环境/依赖失败暂时停止重试；修复环境或等待窗口结束后可再试，不必伪改业务源码。")
    return None
