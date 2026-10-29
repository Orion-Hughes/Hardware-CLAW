"""Immutable, relocatable simulator folder containing actual checked firmware."""
import hashlib
import json
import os
import uuid
import time
import zipfile
from pathlib import Path
from .service import TEMP, atomic_json, fail
from .scaffold import baseline
from ..adapters.compiler import fingerprint
from ..adapters.build_state import FINGERPRINT_VERSION
from ..validation.files import check
from ..validation.report import allows


def sha(data):
    return hashlib.sha256(data).hexdigest()


def publish_directory(stage, target):
    """Bounded retries for Windows transient directory access/sharing failures."""
    for attempt in range(5):
        if target.exists():
            fail("EXPORT_CONFLICT", "交付目录已存在，不覆盖。")
        try:
            os.replace(stage, target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32} or attempt == 4:
                raise
            time.sleep(0.05 * 2 ** attempt)


def verified_build(project, state):
    build = project.build_status(state)
    if (not isinstance(build, dict) or build.get("fingerprint_version") != FINGERPRINT_VERSION
            or build.get("verdict") != "pass" or build.get("source_sha256") != fingerprint(state)):
        fail("BUILD_REQUIRED", "当前版本尚无匹配的真实编译固件，先compile_project。")
    blobs = {}
    for name in ("firmware.bin", "firmware.elf"):
        artifact = build.get("artifacts", {}).get(name, {})
        path = project.meta / "builds" / build["attempt"] / name
        if not path.is_file() or sha(path.read_bytes()) != artifact.get("sha256"):
            fail("BUILD_CHANGED", "固件缺失或哈希不一致，不能交付。")
        blobs["firmware/" + name] = path.read_bytes()
    return build, blobs


def verify_folder(folder, hashes):
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    return actual == set(hashes) and all(sha((folder / name).read_bytes()) == value for name, value in hashes.items())


def export(project, expected_version):
    with project.locked():
        state = project._load()
        project._check_version(state, expected_version)
        project._check_live_files(state)
        report = project._summary(state)["file_check"]
        if not allows(report, "delivery") or not allows(check(state), "delivery"):
            fail("CHECK_REQUIRED", "先对当前版本运行基础检查；delivery阶段不能有阻断项。")
        build, blobs = verified_build(project, state)
        validation = project.validation_status(state)
        reserved = {"OPEN_IN_VSCODE.md", "_hwclaw_manifest.json"}
        if set(state["files"]) & reserved or any(name.startswith("firmware/") for name in state["files"]):
            fail("RESERVED_FILE", "firmware目录和交付说明保留给导出服务。")
        blobs.update({n: c.encode() for n, c in state["files"].items()})
        blobs[".vscode/extensions.json"] = json.dumps(baseline()["extensions"], indent=2).encode()
        blobs["OPEN_IN_VSCODE.md"] = (
            "# 运行仿真\n\n用VS Code打开本文件所在文件夹，安装Wokwi扩展并激活你自己的授权，"
            "按F1执行 `Wokwi: Start Simulator`。固件已编译；串口内容取决于生成的固件及观测配置。\n\n"
            f"编译通过；仿真执行：{validation['simulation']}；行为判定：{validation['behavior']}。仅覆盖登记场景，不代表完整功能或真机验证。默认分区/4MB Flash仿真。\n\n"
            "请在工程副本中修改。仿真命令不会重新编译；推荐回到Hardware-CLAW修改并重新导出。"
            "手动重建需安装PlatformIO，执行 `pio run -e esp32s3`，将.pio/build/esp32s3/下"
            "firmware.bin和firmware.elf复制至firmware/后再启动。\n"
        ).encode()
        manifest = {"schema_version": 2, "project_id": project.id, "version": expected_version,
                    "source_sha256": build["source_sha256"], "files": {n: sha(b) for n, b in blobs.items()},
                    "fingerprint_version": build["fingerprint_version"], "build_attempt": build["attempt"],
                    "built_version": build.get("built_version", build["version"]),
                    "file_check": report,
                    "build": "pass", "simulation": validation['simulation'], "behavior": validation['behavior'],
                    "evaluation": validation['evaluation']}
        blobs["_hwclaw_manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        hashes = {n: sha(b) for n, b in blobs.items()}
        target = project.root / "exports" / f"v{expected_version:06d}"
        if target.exists():
            # Never silently replace a folder the user may have edited.
            if not verify_folder(target / "simulation", hashes):
                fail("EXPORT_CONFLICT", "交付文件夹已有变化，不覆盖；请创建新修订。")
            try:
                with zipfile.ZipFile(target / "project.zip") as z:
                    if set(z.namelist()) != set(blobs) or any(sha(z.read(n)) != hashes[n] for n in blobs):
                        fail("EXPORT_CONFLICT", "已有压缩包内容变化。")
            except (OSError, ValueError, zipfile.BadZipFile):
                fail("EXPORT_CONFLICT", "已有压缩包无法验证。")
        else:
            stage = TEMP / ("delivery-" + uuid.uuid4().hex)
            folder = stage / "simulation"
            folder.mkdir(parents=True)
            for name, data in blobs.items():
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            with zipfile.ZipFile(stage / "project.zip", "x", zipfile.ZIP_DEFLATED) as z:
                for name, data in blobs.items():
                    z.writestr(name, data)
            (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            target.parent.mkdir(exist_ok=True)
            publish_directory(stage, target)
        data = {"version": expected_version, "archive": str(target / "project.zip"),
                "manifest": str(target / "manifest.json"), "simulation_folder": str(target / "simulation"),
                "sha256": sha((target / "project.zip").read_bytes()), "folder_hashes": hashes,
                "delivery_status": "ready_for_vscode", "build": "pass", **validation}
        atomic_json(project.meta / "export.json", data)
        return data


def delivery(project):
    with project.locked():
        state = project._load()
        project._check_live_files(state)
        summary = project._summary(state)
        exported = summary["export"]
        valid = bool(exported and allows(summary["file_check"], "delivery") and allows(check(state), "delivery"))
        if valid:
            from .service import ProjectError
            try:
                verified_build(project, state)
                target = project.root / "exports" / f"v{state['version']:06d}"
                archive = target / "project.zip"
                valid = archive.is_file() and sha(archive.read_bytes()) == exported["sha256"] and verify_folder(target / "simulation", exported["folder_hashes"])
            except (ProjectError, OSError, KeyError):
                valid = False
        build = summary["build"]
        return {"project_id": project.id, "version": state["version"],
                "delivery_status": "ready_for_vscode" if valid else "incomplete",
                "archive": exported["archive"] if valid else None,
                "simulation_folder": exported["simulation_folder"] if valid else None,
                "build": build.get("verdict") if isinstance(build, dict) else build,
                **project.validation_status(state), "evaluation_required": True}
