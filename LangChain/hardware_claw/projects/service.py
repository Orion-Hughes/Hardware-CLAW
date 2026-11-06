"""Bound project storage. The model never supplies an absolute filesystem path."""
import contextlib
import hashlib
import json
import os
import re
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from .. import limits

ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = ROOT / "workspace"
TEMP = ROOT / "temp" / "project-service"
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}\Z")
LOCKS = {}
LOCKS_GUARD = threading.Lock()
MAX_FILE = limits.FILE_BYTES
MAX_TOTAL = limits.PROJECT_BYTES
ALLOWED_EXTENSIONS = {".ino", ".cpp", ".h", ".hpp", ".c", ".json", ".toml", ".ini", ".txt", ".md"}


class ProjectError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(code, message):
    raise ProjectError(code, message)


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or len(relative) > 180:
        fail("INVALID_PATH", "使用files内的短相对路径。")
    parts = relative.split("/")
    if any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", p) or p.endswith((".", " ")) or p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))} for p in parts):
        fail("INVALID_PATH", "禁止绝对路径、目录穿越、隐藏文件及Windows特殊路径。")
    candidate = root.joinpath(*parts)
    for part in [candidate, *candidate.parents]:
        if part.is_symlink() or part.is_junction():
            fail("UNSAFE_PATH", "工程路径包含链接或junction。")
        if part.exists() and part.is_file() and part.stat().st_nlink > 1:
            fail("UNSAFE_PATH", "工程文件不能是硬链接。")
    return candidate


def digest(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def atomic_json(path, data):
    TEMP.mkdir(parents=True, exist_ok=True)
    scratch = TEMP / (uuid.uuid4().hex + ".json")
    scratch.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(scratch, path)


class ProjectService:
    def __init__(self, root):
        self.root = Path(root)
        self.meta = self.root / ".hwclaw"
        self.files = self.root / "files"
        self.id = self.root.name

    @classmethod
    def create(cls, title, requirement, template="vscode", *, workspace=WORKSPACE):
        if template not in {"arduino", "platformio", "vscode"} or not requirement.strip() or len(requirement) > limits.INPUT_CHARACTERS:
            fail("INVALID_ARGUMENT", "需要有效需求和vscode/arduino/platformio模板。")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:32] or "project"
        ident = f"{slug}-{uuid.uuid4().hex[:12]}"
        root = safe_path(Path(workspace), ident)
        root.mkdir(parents=True, exist_ok=False)
        service = cls(root)
        service.files.mkdir()
        service.meta.mkdir()
        state = {"schema_version": 1, "project_id": ident, "title": title[:120], "template": template,
                 "version": 0, "created_at": datetime.now(timezone.utc).isoformat(),
                 "requirements": {"original": requirement, "version": 1}, "design": None,
                 "design_version": 0, "files": {}, "files_design_version": None}
        service._save_snapshot(state)
        atomic_json(service.meta / "project.json", {"version": 0})
        return service

    @classmethod
    def open(cls, project_id, *, workspace=WORKSPACE):
        if not ID.fullmatch(project_id):
            fail("INVALID_PROJECT", "工程ID格式不合法。")
        service = cls(safe_path(Path(workspace), project_id))
        service.get()
        return service

    def _guard(self):
        for path in [self.root, self.meta, self.files, self.root / "exports", *self.root.parents]:
            if path.is_symlink() or path.is_junction():
                fail("UNSAFE_PATH", "工程目录包含链接。")
        if not self.meta.is_dir():
            fail("NOT_FOUND", "工程不存在。")
        for directory in (self.meta, self.files, self.root / "exports"):
            if directory.exists():
                for path in directory.rglob("*"):
                    if path.is_symlink() or path.is_junction() or (path.is_file() and path.stat().st_nlink > 1):
                        fail("UNSAFE_PATH", "工程内部包含链接。")

    @contextlib.contextmanager
    def locked(self):
        with LOCKS_GUARD:
            lock = LOCKS.setdefault(str(self.root), threading.RLock())
        with lock:
            self._guard()
            # Cross-process lock covers CLI and web operating on the same project.
            with (self.meta / "access.lock").open("a+b") as handle:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    if handle.read(1) == b"":
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    except OSError:
                        fail("PROJECT_BUSY", "工程正在写入，请稍后重试。")
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if os.name == "nt":
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load(self):
        try:
            pointer = json.loads((self.meta / "project.json").read_text(encoding="utf-8"))
            version = pointer["version"]
            if type(version) is not int or version < 0:
                fail("CORRUPT_PROJECT", "工程版本损坏。")
            return json.loads((self.meta / "revisions" / f"v{version:06d}" / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            fail("CORRUPT_PROJECT", "无法读取工程状态或修订。")

    def _save_snapshot(self, state):
        directory = self.meta / "revisions" / f"v{state['version']:06d}"
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / "state.json", state)

    def _check_version(self, state, expected):
        if state["version"] != expected:
            fail("VERSION_CONFLICT", f"版本已变化，当前version={state['version']}，先get_project。")

    def _check_live_files(self, state):
        actual = {p.relative_to(self.files).as_posix() for p in self.files.rglob("*") if p.is_file()}
        if actual != set(state["files"]):
            fail("EXTERNAL_CHANGE", "files目录被外部修改，需人工核对；不会自动覆盖。")
        for name, content in state["files"].items():
            path = safe_path(self.files, name)
            # Writes preserve newlines; universal-newline reads would falsely
            # flag CRLF or mixed-newline content as an external modification.
            if path.stat().st_size > MAX_FILE or path.read_bytes() != content.encode("utf-8"):
                fail("EXTERNAL_CHANGE", f"文件{name}被外部修改，需人工核对。")

    def get(self):
        with self.locked():
            state = self._load()
            return self._summary(state)

    def _summary(self, state):
        report_path = self.meta / "check.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
        current_check = report if report and report["version"] == state["version"] else None
        export_path = self.meta / "export.json"
        exported = json.loads(export_path.read_text(encoding="utf-8")) if export_path.exists() else None
        if exported and exported["version"] != state["version"]:
            exported = None
        return {k: state[k] for k in ("project_id", "title", "template", "version", "requirements", "design", "design_version")} | {
            "files": [{"path": name, "sha256": digest(content), "bytes": len(content.encode())} for name, content in sorted(state["files"].items())],
            "file_check": current_check, "build": self.build_status(state), **self.validation_status(state),
            "files_design_version": state["files_design_version"], "file_root": str(self.files), "export": exported}

    def _commit(self, state):
        existing = [int(p.name[1:]) for p in (self.meta / "revisions").iterdir() if re.fullmatch(r"v[0-9]+", p.name)]
        state["version"] = max(existing, default=state["version"]) + 1
        # A revision is a complete immutable bundle of requirements, design and text artifacts.
        self._save_snapshot(state)
        atomic_json(self.meta / "project.json", {"version": state["version"]})
        return self._summary(state)

    def update_design(self, expected_version, design):
        from ..contracts.project import Design
        from ..catalog import KnowledgeCatalog, CatalogError
        value = Design.model_validate(design).model_dump()
        if self.get()["template"] == "vscode":
            from .scaffold import normalize_design
            normalize_design(value)
        if any(len(a) > 2000 for a in value["assumptions"]):
            fail("INVALID_ARGUMENT", "假设说明过长。")
        identities = {"mcu": value["board_id"]}
        for index, component in enumerate(value["components"]):
            if component["instance_id"] in identities:
                if component["instance_id"] == "mcu":
                    fail("DUPLICATE_INSTANCE", f"components[{index}].instance_id=mcu 为保留ID。board_id已经自动创建主板；"
                         "删除components中重复的主板条目，保留board_id及connections中的mcu:*端点，重新提交完整design。此次未保存。")
                fail("DUPLICATE_INSTANCE", f"components[{index}].instance_id={component['instance_id']}重复。"
                     "为不同外设分配唯一instance_id，并同步调整指向该实例的connections；重新提交完整design。此次未保存。")
            identities[component["instance_id"]] = component["hardware_id"]
        hardware = {}
        try:
            for name, ident in identities.items():
                info = KnowledgeCatalog().get(ident, include_shared=(name == "mcu"))
                if info["summary"]["generation_status"] != "documented_not_tested":
                    fail("UNSUPPORTED_HARDWARE", f"{ident}没有可用的资料级生成配置。")
                if (name == "mcu") != (info["summary"]["kind"] == "board"):
                    fail("INVALID_BOARD", f"实例{name}使用的{ident}类型为{info['summary']['kind']}。"
                         "board_id必须指向板卡，components只含外设；不要把板卡改名后放入components。此次未保存。")
                hardware[name] = info
        except CatalogError as exc:
            fail(exc.code, str(exc))
        endpoints = {f"{name}:{pin}" for name, info in hardware.items() for pin in info["upstream_definition"]["pins"]}
        endpoints |= {"$serialMonitor:TX", "$serialMonitor:RX"}
        pairs = set()
        for connection in value["connections"]:
            a, b = connection["a"], connection["b"]
            if a not in endpoints or b not in endpoints or a == b:
                fail("INVALID_ENDPOINT", f"连接端点不合法：{a} -> {b}。"
                     "使用mcu或components.instance_id作为前缀、所选模型的精确引脚名作为后缀；禁止自连。"
                     "根据已读模型端点修正connections后重提完整design；此次未保存。")
            pair = tuple(sorted((a, b)))
            if pair in pairs:
                fail("DUPLICATE_CONNECTION", f"重复连线：{a} -> {b}；反向也算同一连接。保留一条后重提完整design；此次未保存。")
            pairs.add(pair)
        for name, pin in value["pin_defines"].items():
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", name) or f"mcu:{pin}" not in endpoints:
                fail("INVALID_PIN_DEFINE", "GPIO常量名或引脚不合法。")
        with self.locked():
            state = self._load()
            self._check_version(state, expected_version)
            self._check_live_files(state)
            state["design"] = value
            state["hardware"] = hardware
            state["design_version"] += 1
            return self._commit(state)

    def read_file(self, path):
        safe_path(self.files, path)
        with self.locked():
            state = self._load()
            self._check_live_files(state)
            if path not in state["files"]:
                fail("NOT_FOUND", "当前工程中没有该文件。")
            content = state["files"][path]
            return {"path": path, "content": content, "sha256": digest(content), "version": state["version"]}

    def write_files(self, expected_version, files):
        with self.locked():
            state = self._load()
            self._check_version(state, expected_version)
            self._check_live_files(state)
            if state["design"] is None:
                fail("DESIGN_REQUIRED", "先保存设计，再生成工程文件。")
            if not isinstance(files, dict) or not files or len(files) > limits.PROJECT_FILES:
                fail("INVALID_FILES", f"一次写入1到{limits.PROJECT_FILES}个文本文件。")
            for name, content in files.items():
                path = safe_path(self.files, name)
                if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                    fail("UNSUPPORTED_FILE", "仅支持源码、配置和说明文本，不能写脚本或二进制。")
                if not isinstance(content, str) or "\x00" in content or len(content.encode("utf-8")) > MAX_FILE:
                    fail("FILE_TOO_LARGE", f"文件必须为不超过{MAX_FILE}字节的UTF-8文本。")
            merged = state["files"] | files
            if len(merged) > limits.PROJECT_FILES or sum(len(c.encode()) for c in merged.values()) > MAX_TOTAL:
                fail("PROJECT_TOO_LARGE", f"工程超过{limits.PROJECT_FILES}文件或{MAX_TOTAL}字节上限。")
            old = state["files"].copy()
            try:
                for name, content in files.items():
                    path = safe_path(self.files, name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    TEMP.mkdir(parents=True, exist_ok=True)
                    scratch = TEMP / (uuid.uuid4().hex + ".txt")
                    scratch.write_text(content, encoding="utf-8", newline="")
                    os.replace(scratch, path)
                state["files"] = merged
                state["files_design_version"] = state["design_version"]
                return self._commit(state)
            except Exception:
                # Restore only files touched by this transaction, never external paths.
                for name in files:
                    path = safe_path(self.files, name)
                    if name in old:
                        path.write_text(old[name], encoding="utf-8", newline="")
                    elif path.is_file():
                        path.unlink()
                raise

    def patch_file(self, expected_version, path, old_text, new_text):
        # Read records a version; write rechecks it under the cross-process lock.
        current = self.read_file(path)
        if current["version"] != expected_version:
            fail("VERSION_CONFLICT", "版本已变化，先get_project和read_project_file。")
        if not old_text or current["content"].count(old_text) != 1:
            fail("PATCH_MISMATCH", "old_text必须在文件中恰好出现一次。")
        return self.write_files(expected_version, {path: current["content"].replace(old_text, new_text, 1)})

    def check_files(self):
        from ..validation.files import check
        with self.locked():
            state = self._load()
            self._check_live_files(state)
            report = check(state)
            atomic_json(self.meta / "check.json", report)
            return report

    def build_status(self, state):
        path = self.meta / "build.json"
        if path.exists():
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("version") == state["version"]:
                return report
        return "not_run"

    def validation_status(self, state):
        from ..adapters.simulator import current_report
        values = {"simulation": "not_run", "behavior": "not_run", "evaluation": None}
        simulation = current_report(self, state)
        if not simulation:
            return values
        if simulation.get("evidence_sha256"):
            folder = self.meta / "simulations" / simulation["attempt"]
            for name, checksum in simulation["evidence_sha256"].items():
                path = safe_path(folder, name)
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                    values["simulation"] = "evidence_invalid"
                    return values
        values["simulation"] = simulation["execution_verdict"]
        path = self.meta / "evaluation.json"
        if path.exists():
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("version") == state["version"] and report.get("attempt") == simulation.get("attempt"):
                values["behavior"] = report["verdict"]
                values["evaluation"] = report
        return values

    def scaffold(self, expected_version):
        from .scaffold import render
        with self.locked():
            state = self._load()
            self._check_version(state, expected_version)
            self._check_live_files(state)
            files = render(state)
        return self.write_files(expected_version, files)

    def export(self, expected_version):
        from ..validation.files import check
        if self.get()["template"] == "vscode":
            from .vscode_delivery import export
            return export(self, expected_version)
        with self.locked():
            state = self._load()
            self._check_version(state, expected_version)
            self._check_live_files(state)
            check_path = self.meta / "check.json"
            report = json.loads(check_path.read_text(encoding="utf-8")) if check_path.exists() else None
            if not report or report["version"] != expected_version or report["verdict"] != "pass":
                fail("CHECK_REQUIRED", "必须先对当前版本运行check_project_files并通过基础检查。")
            report = check(state)
            if report["verdict"] != "pass":
                fail("CHECK_FAILED", "当前文件基础检查失败，不能导出。")
            if "_hwclaw_manifest.json" in state["files"]:
                fail("RESERVED_FILE", "_hwclaw_manifest.json保留给导出服务。")
            target = self.root / "exports" / f"v{expected_version:06d}"
            manifest = {"schema_version": 1, "project_id": self.id, "version": expected_version,
                        "design_version": state["design_version"], "requirements_version": state["requirements"]["version"],
                        "files": {n: digest(c) for n, c in sorted(state["files"].items())}, "file_check": report,
                        "build": "not_run", "simulation": "not_run", "behavior": "not_run"}
            archive = target / "project.zip"
            if target.exists():
                try:
                    if json.loads((target / "manifest.json").read_text(encoding="utf-8")) != manifest:
                        fail("EXPORT_CONFLICT", "该修订导出目录内容已变化。")
                    with zipfile.ZipFile(archive) as z:
                        if set(z.namelist()) != set(state["files"]) | {"_hwclaw_manifest.json"}:
                            fail("EXPORT_CONFLICT", "已有压缩包内容不匹配。")
                        for name, content in state["files"].items():
                            if z.read(name) != content.encode():
                                fail("EXPORT_CONFLICT", "已有压缩包文件哈希不匹配。")
                except (OSError, ValueError, zipfile.BadZipFile, KeyError):
                    fail("EXPORT_CONFLICT", "已有导出损坏，不覆盖。")
            else:
                stage = TEMP / ("export-" + uuid.uuid4().hex)
                stage.mkdir(parents=True)
                (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                with zipfile.ZipFile(stage / "project.zip", "x", zipfile.ZIP_DEFLATED) as z:
                    for name, content in sorted(state["files"].items()):
                        z.writestr(name, content)
                    z.writestr("_hwclaw_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                target.parent.mkdir(exist_ok=True)
                os.replace(stage, target)
            data = {"version": expected_version, "archive": str(archive), "manifest": str(target / "manifest.json"),
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "delivery_status": "generated_not_simulated"}
            atomic_json(self.meta / "export.json", data)
            return data

    def delivery(self):
        """Host verdict: verify current artifacts, report, and the actual ZIP hash."""
        if self.get()["template"] == "vscode":
            from .vscode_delivery import delivery
            return delivery(self)
        with self.locked():
            state = self._load()
            self._check_live_files(state)
            info = self._summary(state)
            exported = info["export"]
            valid = bool(exported and info["file_check"] and info["file_check"]["verdict"] == "pass")
            if valid:
                archive = self.root / "exports" / f"v{state['version']:06d}" / "project.zip"
                valid = archive.is_file() and hashlib.sha256(archive.read_bytes()).hexdigest() == exported["sha256"]
            return {"project_id": self.id, "version": state["version"], "delivery_status": "generated_not_simulated" if valid else "incomplete",
                    "archive": str(archive) if valid else None, "build": "not_run", "simulation": "not_run", "behavior": "not_run"}

    def record_run(self, run_id, record):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            fail("INVALID_RUN", "运行ID格式无效。")
        with self.locked():
            atomic_json(self.meta / "runs" / run_id / "run.json", record)
