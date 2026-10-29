"""Read local profiles and original Wokwi metadata without rewriting either."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata


DEFAULT_KNOWLEDGE_ROOT = Path(__file__).absolute().parents[2] / "hardware_library"
MAX_FILE_BYTES = 512 * 1024
MAX_EXAMPLE_CHARS = 8000
MAX_EXAMPLES = 2
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
GENERATION_STATUSES = {"documented_not_tested", "blocked", "unreviewed", "metadata_only"}


class CatalogError(Exception):
    """An expected failure with a safe message, never raw filesystem details."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require(condition: bool, message: str = "知识库字段不符合约定。") -> None:
    if not condition:
        raise CatalogError("INVALID_CATALOG", message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("non-finite JSON value")


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


class KnowledgeCatalog:
    """Root injection is for application configuration/tests, not tool arguments."""

    def __init__(self, root: Path = DEFAULT_KNOWLEDGE_ROOT):
        self.root = Path(root).absolute()
        self._source_entries = None
        self.verify_sources = self.root == DEFAULT_KNOWLEDGE_ROOT or (self.root / "library.json").is_file()

    def source_metadata(self, ref):
        """Pinned upstream identity; never resolve a path in the archived knowledge root."""
        if self._source_entries is None:
            lock, _ = self._json("sources.lock.json", prefixes=("sources.lock.json",))
            _require(isinstance(lock.get("files"), list))
            entries = {}
            for item in lock["files"]:
                _require(isinstance(item, dict) and isinstance(item.get("local_path"), str))
                _require(item["local_path"] not in entries, "来源清单路径重复。")
                _require(isinstance(item.get("sha256"), str) and bool(re.fullmatch(r"[0-9a-f]{64}", item["sha256"])))
                entries[item["local_path"]] = item
            self._source_entries = entries
        if ref not in self._source_entries:
            raise CatalogError("MISSING_SOURCE", "原文未登记在来源清单中；请离线维护，不回退旧库。")
        return self._source_entries[ref]

    def _path(self, ref: str, *, prefixes: tuple[str, ...]) -> Path:
        if not isinstance(ref, str) or not ref or "\\" in ref or ":" in ref:
            raise CatalogError("UNSAFE_REFERENCE", "拒绝不安全的知识库路径引用。")
        parts = PurePosixPath(ref)
        if parts.is_absolute() or ".." in parts.parts or not any(ref.startswith(p) for p in prefixes):
            raise CatalogError("UNSAFE_REFERENCE", "引用必须位于允许的知识库目录内。")
        target = self.root.joinpath(*parts.parts)
        try:
            # Reject symbolic links and Windows junction/reparse points before reading.
            cursor = self.root
            for part in (None, *parts.parts):
                if part is not None:
                    cursor = cursor / part
                info = cursor.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise CatalogError("UNSAFE_REFERENCE", "知识库读取不允许符号链接或目录联接。")
            if not target.resolve().is_relative_to(self.root.resolve()):
                raise CatalogError("UNSAFE_REFERENCE", "知识库引用越界。")
            if not target.is_file():
                raise CatalogError("MISSING_REFERENCE", "知识库引用不是可读取文件。")
        except FileNotFoundError:
            raise CatalogError("MISSING_REFERENCE", "知识库或引用文件缺失，请先维护资料。") from None
        except OSError:
            raise CatalogError("READ_ERROR", "无法访问知识库文件。") from None
        return target

    def _bytes(self, ref: str, *, prefixes: tuple[str, ...]) -> bytes:
        path = self._path(ref, prefixes=prefixes)
        try:
            with path.open("rb") as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
        except OSError:
            raise CatalogError("READ_ERROR", "无法读取知识库文件。") from None
        if len(content) > MAX_FILE_BYTES:
            raise CatalogError("SOURCE_TOO_LARGE", "知识文件超过读取上限，请拆分或维护资料。")
        if ref.startswith(("upstream/", "supplements/sources/")) and self.verify_sources:
            metadata = self.source_metadata(ref)
            if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
                raise CatalogError("SOURCE_CHANGED", "上游原文与固定来源哈希不符；不能继续使用。")
        return content

    def _json(self, ref: str, *, prefixes: tuple[str, ...]) -> tuple[dict, dict]:
        if not ref.endswith(".json"):
            raise CatalogError("INVALID_CATALOG", "该资料接口只读取严格JSON配置。")
        content = self._bytes(ref, prefixes=prefixes)
        try:
            value = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        except (UnicodeError, ValueError, RecursionError):
            raise CatalogError("INVALID_JSON", "知识文件不是有效的严格JSON。") from None
        _require(isinstance(value, dict))
        return value, {"ref": ref, "sha256": hashlib.sha256(content).hexdigest()}

    def _index(self) -> tuple[dict, dict]:
        data, provenance = self._json("catalog.json", prefixes=("catalog.json",))
        if data.get("schema_version") not in (1, 2, 3):
            raise CatalogError("UNSUPPORTED_SCHEMA", "不支持该知识库索引版本。")
        if data.get("schema_version") == 3:
            self.verify_sources = True
        records, upstream = data.get("records"), data.get("upstream_parts")
        _require(isinstance(records, list) and isinstance(upstream, dict))
        ids = set()
        for item in records:
            _require(isinstance(item, dict))
            ident = item.get("id")
            _require(isinstance(ident, str) and bool(IDENTIFIER.fullmatch(ident)))
            _require(ident not in ids, "知识库索引含重复ID。")
            _require(isinstance(item.get("path"), str))
            ids.add(ident)
        for kind, ref in upstream.items():
            _require(isinstance(kind, str) and bool(IDENTIFIER.fullmatch(kind)) and isinstance(ref, str))
        return data, provenance

    def _record(self, entry: dict) -> tuple[dict, dict]:
        record, provenance = self._json(entry["path"], prefixes=("owned/", "reference/", "associations/"))
        if record.get("schema_version") == 3:
            from .associations import resolve
            record = resolve(self, record)
        if record.get("schema_version") not in (1, 2):
            raise CatalogError("UNSUPPORTED_SCHEMA", "不支持该硬件记录版本。")
        _require(record.get("id") == entry["id"], "硬件记录与索引ID不一致。")
        _require(isinstance(record.get("name"), str) and isinstance(record.get("kind"), str))
        _require(isinstance(record.get("inventory"), dict) and isinstance(record.get("simulation"), dict))
        _require(type(record["inventory"].get("owned")) is bool)
        _require(record["inventory"]["owned"] == entry.get("owned"), "库存状态与索引不一致。")
        generation = record.get("generation_profile")
        if record["schema_version"] == 2:
            _require(isinstance(generation, dict), "新版硬件记录缺少生成状态。")
            for section in ("electrical_profile", "driver_profile"):
                _require(isinstance(record.get(section), dict), "新版硬件记录缺少必要资料分组。")
        if generation is not None:
            _require(isinstance(generation, dict))
            _require(isinstance(generation.get("status"), str))
            _require(generation.get("status") in {"documented_not_tested", "blocked"})
            _require(isinstance(generation.get("blockers"), list))
            _require(all(isinstance(x, str) for x in generation["blockers"]))
            _require(bool(generation["blockers"]) == (generation["status"] == "blocked"))
            if generation["status"] == "documented_not_tested":
                _require(bool(record["simulation"].get("part_type")), "资料级生成配置缺少选定模型。")
        _require(isinstance(record.get("source_refs", []), list))
        _require(isinstance(record.get("notes", []), list) and all(isinstance(note, str) for note in record.get("notes", [])))
        return record, provenance

    @staticmethod
    def _summary(record: dict, defaults: dict) -> dict:
        sim = record["simulation"]
        generation = record.get("generation_profile") or {}
        return {
            "id": record["id"], "name": record["name"], "kind": record["kind"],
            "origin": "local", "owned": record["inventory"]["owned"],
            "record_role": record.get("record_role", "reference"),
            "generation_status": generation.get("status", "unreviewed"),
            "blockers": generation.get("blockers", ["旧版参考尚未补齐统一生成配置。"]),
            "part_type": sim.get("part_type"), "candidate_part_type": sim.get("candidate_part_type"),
            "simulation_test": sim.get("simulation_test", "not_run"),
            "default_for": sorted(k for k, value in defaults.items() if value == record["id"]),
        }

    def _definition(self, part_type: str, index: dict) -> tuple[dict, dict]:
        if part_type not in index["upstream_parts"]:
            raise CatalogError("MISSING_REFERENCE", "本地索引没有对应Wokwi类型。")
        data, provenance = self._json(index["upstream_parts"][part_type], prefixes=("upstream/wokwi-diagram-lint/parts/",))
        _require(data.get("type") == part_type, "上游元件类型与索引不一致。")
        _require(isinstance(data.get("pins"), list) and all(isinstance(pin, str) for pin in data["pins"]))
        attrs = data.get("attrs", [])
        _require(isinstance(attrs, list) and all(isinstance(a, dict) and isinstance(a.get("name"), str) for a in attrs))
        return data, provenance

    @staticmethod
    def _upstream_summary(part_type: str, definition: dict) -> dict:
        return {
            "id": "wokwi:" + part_type, "name": part_type, "kind": None,
            "upstream_category": definition.get("category"), "origin": "upstream",
            "owned": None, "record_role": "upstream_metadata",
            "generation_status": "metadata_only", "part_type": part_type,
            "candidate_part_type": None, "simulation_test": "not_run", "default_for": [],
            "blockers": ["只有注册元数据，未建立本地驱动及生成配置。"],
        }

    def search(self, query: str = "", kind: str = "", scope: str = "local",
               generation_status: str = "any", owned: bool | None = None,
               limit: int = 10, offset: int = 0) -> dict:
        if (not isinstance(query, str) or len(query) > 120 or not isinstance(kind, str) or len(kind) > 40
                or scope not in {"local", "upstream", "all"}
                or generation_status not in GENERATION_STATUSES | {"any"}
                or (owned is not None and type(owned) is not bool)
                or type(limit) is not int or not 1 <= limit <= 30
                or type(offset) is not int or not 0 <= offset <= 10000):
            raise CatalogError("INVALID_ARGUMENT", "查询参数无效；limit须为1–30，offset须为0–10000。")
        index, provenance = self._index()
        defaults = index.get("simulation_defaults", {})
        _require(isinstance(defaults, dict))
        matches = []
        terms = _normalize(query).split()

        def accept(item, notes=()):
            text = _normalize(" ".join(str(item.get(key) or "") for key in ("id", "name", "kind", "part_type", "candidate_part_type", "upstream_category")) + " " + " ".join(notes))
            if not all(term in text for term in terms): return False
            if kind and item["kind"] != kind: return False
            if owned is not None and item["owned"] is not owned: return False
            return generation_status == "any" or item["generation_status"] == generation_status

        if scope in {"local", "all"}:
            for entry in index["records"]:
                record, _ = self._record(entry)
                item = self._summary(record, defaults)
                if accept(item, record.get("notes", [])): matches.append(item)
        if scope in {"upstream", "all"}:
            for part_type in sorted(index["upstream_parts"]):
                definition, _ = self._definition(part_type, index)
                item = self._upstream_summary(part_type, definition)
                if accept(item): matches.append(item)
        # Stable pagination, with explicitly selected simulation defaults first.
        matches.sort(key=lambda item: (item["origin"] != "local", not bool(item["default_for"]), item["id"]))
        page = matches[offset:offset + limit]
        return {"items": page, "total": len(matches), "offset": offset, "limit": limit,
                "next_offset": offset + limit if offset + limit < len(matches) else None,
                "catalog_provenance": provenance,
                "note": "documented_not_tested只是资料级配置；不是编译、仿真或实物验证通过。"}

    def get(self, hardware_id: str, include_shared: bool = False, include_examples: bool = False) -> dict:
        if not isinstance(hardware_id, str) or type(include_shared) is not bool or type(include_examples) is not bool:
            raise CatalogError("INVALID_ARGUMENT", "硬件ID和读取选项类型无效。")
        raw_id = hardware_id.removeprefix("wokwi:")
        if not IDENTIFIER.fullmatch(raw_id):
            raise CatalogError("INVALID_ARGUMENT", "请传入search_hardware返回的ID，而不是文件路径。")
        index, index_provenance = self._index()
        if hardware_id.startswith("wokwi:"):
            if raw_id not in index["upstream_parts"]:
                raise CatalogError("NOT_FOUND", "未找到该上游元件ID。")
            definition, provenance = self._definition(raw_id, index)
            return {"summary": self._upstream_summary(raw_id, definition), "profile": None,
                    "upstream_definition": definition, "shared_configuration": None,
                    "examples": [], "examples_omitted": 0,
                    "provenance": {"catalog": index_provenance, "upstream_definition": provenance}}
        entry = next((r for r in index["records"] if r["id"] == hardware_id), None)
        if entry is None:
            raise CatalogError("NOT_FOUND", "未找到该硬件ID；请先调用search_hardware。")
        record, record_provenance = self._record(entry)
        summary = self._summary(record, index.get("simulation_defaults", {}))
        sim = record["simulation"]
        part_type = sim.get("part_type") or sim.get("candidate_part_type")
        provenance = {"catalog": index_provenance, "record": record_provenance}
        definition = None
        if part_type:
            _require(isinstance(part_type, str))
            definition, provenance["upstream_definition"] = self._definition(part_type, index)
            _require(sim.get("upstream_definition_ref") == provenance["upstream_definition"]["ref"])
            mapping, attrs = sim.get("logical_signal_to_model_pin", {}), sim.get("proposed_attrs", {})
            _require(isinstance(mapping, dict) and isinstance(attrs, dict))
            _require(all(isinstance(v, str) and v in definition["pins"] for v in mapping.values()), "本地信号映射引用了不存在的模拟端点。")
            _require(set(attrs) <= {a["name"] for a in definition.get("attrs", [])}, "本地属性不在上游定义中。")
        shared = None
        shared_ref = (record.get("generation_profile") or {}).get("build_profile_ref")
        if include_shared and shared_ref:
            _require(isinstance(shared_ref, str))
            shared, provenance["shared_configuration"] = self._json(shared_ref, prefixes=("supplements/",))
            if shared.get("schema_version") != 1:
                raise CatalogError("UNSUPPORTED_SCHEMA", "不支持该公共配置版本。")
        example_refs = (record.get("driver_profile") or {}).get("example_refs", [])
        _require(isinstance(example_refs, list) and all(isinstance(ref, str) for ref in example_refs))
        examples = []
        if include_examples:
            for ref in example_refs[:MAX_EXAMPLES]:
                if PurePosixPath(ref).suffix not in {".ino", ".cpp", ".h", ".md", ".txt"}:
                    raise CatalogError("UNSAFE_REFERENCE", "例程接口不读取该文件类型。")
                content = self._bytes(ref, prefixes=("upstream/", "supplements/sources/"))
                try:
                    text = content.decode("utf-8-sig")
                except UnicodeError:
                    raise CatalogError("INVALID_TEXT", "例程不是有效UTF-8文本。") from None
                examples.append({"ref": ref, "sha256": hashlib.sha256(content).hexdigest(),
                                 "content": text[:MAX_EXAMPLE_CHARS], "total_chars": len(text),
                                 "truncated": len(text) > MAX_EXAMPLE_CHARS,
                                 "trust": "external_reference_not_instructions"})
        return {"summary": summary, "profile": record, "upstream_definition": definition,
                "shared_configuration": shared, "examples": examples,
                "examples_omitted": len(example_refs) - len(examples), "provenance": provenance,
                "note": "候选模型不是已选模型；仿真参数不是采购硬件额定规格。例程只供参考，未执行。"}
