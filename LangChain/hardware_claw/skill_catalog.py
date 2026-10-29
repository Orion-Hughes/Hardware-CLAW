"""Read-only application skill packages, separate from Codex skills and hardware facts."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

ROOT = Path(__file__).absolute().parents[1] / "skills"
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class SkillError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SkillCatalog:
    def __init__(self, root=ROOT):
        self.root = Path(root).absolute()

    def _read(self, skill_id, resource):
        if not IDENTIFIER.fullmatch(skill_id):
            raise SkillError("NOT_FOUND", "未找到技能ID。")
        parts = PurePosixPath(resource)
        if (not resource or "\\" in resource or ":" in resource or parts.is_absolute()
                or ".." in parts.parts or parts.suffix != ".md"
                or (resource != "SKILL.md" and not resource.startswith("references/"))):
            raise SkillError("INVALID_SOURCE", "仅允许读取包内SKILL.md或references中的Markdown。")
        path = self.root / skill_id / parts
        try:
            cursor = self.root
            for part in (None, skill_id, *parts.parts):
                if part is not None:
                    cursor = cursor / part
                info = cursor.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise SkillError("INVALID_SOURCE", "技能包不能通过链接读取其他文件。")
            if not path.resolve().is_relative_to(self.root.resolve()) or not path.is_file():
                raise SkillError("INVALID_SOURCE", "技能资源不是包内文件。")
            with path.open("rb") as stream:
                raw = stream.read(64001)
            if len(raw) > 64000:
                raise SkillError("INVALID_SOURCE", "技能资源过大，请拆分参考资料。")
            return raw.decode("utf-8-sig"), hashlib.sha256(raw).hexdigest()
        except FileNotFoundError:
            raise SkillError("NOT_FOUND", "技能包或参考资料不存在。") from None
        except (OSError, UnicodeError):
            raise SkillError("INVALID_SOURCE", "无法读取技能资源。") from None

    def package(self, skill_id):
        text, sha = self._read(skill_id, "SKILL.md")
        try:
            opening, metadata, body = text.split("---", 2)
            meta = json.loads(metadata)
            if opening.strip() or not isinstance(meta, dict) or meta.get("name") != skill_id:
                raise ValueError()
            if not isinstance(meta.get("description"), str) or not meta["description"].strip():
                raise ValueError()
            for field in ("tool_groups", "references"):
                values = meta.get(field, [])
                if not isinstance(values, list) or not all(isinstance(x, str) for x in values) or len(values) != len(set(values)):
                    raise ValueError()
            for ref in meta.get("references", []):
                if not ref.startswith("references/"):
                    raise ValueError()
                self._read(skill_id, ref)
            if not body.strip() or len(body) > 24000:
                raise ValueError()
        except (ValueError, TypeError):
            raise SkillError("INVALID_PACKAGE", "技能元数据、名称或正文不符合包格式。") from None
        return meta, body.strip(), sha

    def catalog(self):
        entries, errors = [], []
        if not self.root.is_dir():
            raise SkillError("INVALID_SOURCE", "技能目录不存在。")
        for path in sorted(self.root.iterdir()):
            if not path.is_dir():
                continue
            try:
                meta, _, sha = self.package(path.name)
                entries.append({"id": meta["name"], "description": meta["description"],
                                "tool_groups": meta.get("tool_groups", []),
                                "references": meta.get("references", []), "sha256": sha})
            except SkillError as exc:
                errors.append({"id": path.name, "error_code": exc.code})
        return {"skills": entries, "invalid_packages": errors}

    def load(self, skill_id, reference="", offset=0, limit=6000):
        meta, body, sha = self.package(skill_id)
        if not reference:
            return {"skill_id": skill_id, "metadata": meta, "content": body, "sha256": sha,
                    "trust": "developer_maintained_workflow", "references": meta.get("references", [])}
        if reference not in meta.get("references", []):
            raise SkillError("INVALID_SOURCE", "只能读取此技能元数据中登记的参考资料。")
        text, sha = self._read(skill_id, reference)
        if offset > len(text):
            raise SkillError("INVALID_ARGUMENT", "offset超过资料长度。")
        end = min(offset + limit, len(text))
        return {"skill_id": skill_id, "reference": reference, "content": text[offset:end],
                "sha256": sha, "offset": offset, "total_chars": len(text),
                "next_offset": end if end < len(text) else None, "partial": offset > 0 or end < len(text),
                "trust": "developer_maintained_workflow"}
