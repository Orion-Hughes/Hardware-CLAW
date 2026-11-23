"""Images for separate simulation and N32R16V physical build profiles.

Layout and flash settings follow platform-espressif32 6.12.0 builder/main.py,
Arduino-ESP32 2.0.17 tools/platformio-build.py and esp32-s3-devkitc-1.json.
This is not a universal ESP32 layout or proof of physical-board compatibility.
"""
import hashlib
import json
import configparser
from pathlib import Path

from ..projects.service import ROOT, ProjectError, fail
from ..projects.scaffold import baseline
from .target import PROFILE

SIMULATION_PROFILE = {
    "id": "esp32s3-devkitc1-arduino2-default8mb",
    "board": "esp32-s3-devkitc-1",
    "platform": "espressif32@6.12.0",
    "framework_package": "3.20017.241212+sha.dcc1105b",
    "esptool_package": "2.40900.250804",
    "chip": "esp32s3",
    "flash_mode": "dio",
    "flash_freq": "80m",
    "flash_size": "8MB",
    "flash_bytes": 8 * 1024 * 1024,
    "psram_enabled": False,
}
LAYOUT = (("bootloader.bin", 0), ("partitions.bin", 0x8000),
          ("boot_app0.bin", 0xE000), ("firmware.bin", 0x10000))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require_simulation_profile(state):
    if state.get("template") != "vscode" or (state.get("design") or {}).get("board_id") != "esp32_s3_devkitc1_n32r16v":
        fail("UPLOAD_PROFILE_UNSUPPORTED", "当前烧录仅支持登记的 ESP32-S3 / Arduino 仿真构建基线，不自动适配其他板卡。")
    # The maintained scaffold is the authority; don't accept model-supplied
    # upload commands, addresses, extra scripts or alternative partition maps.
    from ..projects.scaffold import render
    if state.get("files", {}).get("platformio.ini") != render(state)["platformio.ini"]:
        fail("UPLOAD_PROFILE_UNSUPPORTED", "构建配置与登记平台不符，需新增并验证烧录配置，不能猜测镜像偏移。")
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(state["files"]["platformio.ini"])
    if (ini["env:esp32s3"].get("platform") != SIMULATION_PROFILE["platform"]
            or ini["env:esp32s3"].get("board") != SIMULATION_PROFILE["board"]
            or ini["env:esp32s3"].get("framework") != "arduino"):
        fail("UPLOAD_PROFILE_UNSUPPORTED", "烧录配置仅适用于登记的平台/板卡/框架版本。")
    if "board = " + SIMULATION_PROFILE["board"] not in baseline()["platformio"]:
        fail("UPLOAD_PROFILE_UNSUPPORTED", "平台模板已变化，请维护对应的烧录配置。")
    return dict(SIMULATION_PROFILE)


def require_profile(state):
    from .target import platformio_for
    platformio_for(state)
    return dict(PROFILE)


def package_dir(name, version):
    packages = ROOT / "pio/packages"
    matches = []
    if packages.is_dir():
        for folder in packages.iterdir():
            if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
                continue
            manifest = folder / "package.json"
            if not manifest.is_file():
                continue
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if value.get("name") == name and value.get("version") == version:
                matches.append(folder)
    if len(matches) != 1:
        fail("UPLOAD_PACKAGE_UNAVAILABLE", f"需要且只能解析到一份 {name}@{version}，请核对 PlatformIO 安装。")
    return matches[0]


def capture_images(state, work, build_folder, *, physical=True):
    """Persist all flash images while a successful build still has its cache.

    Missing upload support must not turn a valid simulation build into a failure.
    Callers store this result separately from the compiler verdict.
    """
    try:
        profile = require_profile(state) if physical else require_simulation_profile(state)
        framework = package_dir("framework-arduinoespressif32", profile["framework_package"])
        outputs = Path(work) / ".pio/build/esp32s3"
        sources = {name: outputs / name for name, _ in LAYOUT}
        sources["boot_app0.bin"] = framework / "tools/partitions/boot_app0.bin"
        payloads = {}
        for name, _ in LAYOUT:
            path = sources[name]
            if not path.is_file() or path.is_symlink() or path.is_junction():
                fail("UPLOAD_IMAGES_MISSING", f"缺少完整烧录镜像 {name}；请重新编译，不使用其他工程的镜像补齐。")
            data = path.read_bytes()
            if not data:
                fail("UPLOAD_IMAGES_MISSING", f"烧录镜像 {name} 为空。")
            payloads[name] = data
        validate_layout([{"name": name, "offset": offset, "bytes": len(payloads[name]),
                          "sha256": sha(payloads[name])} for name, offset in LAYOUT], profile=profile)
        # Only after validating the whole set do we persist auxiliary images.
        for name, data in payloads.items():
            if name != "firmware.bin":
                (Path(build_folder) / name).write_bytes(data)
        return {"status": "ready", "profile": profile,
                "images": [{"name": name, "offset": offset, "bytes": len(payloads[name]),
                            "sha256": sha(payloads[name])} for name, offset in LAYOUT],
                "layout_source": "platform-espressif32 6.12.0 + Arduino-ESP32 2.0.17",
                "framework_source": str(framework)}
    except ProjectError as exc:
        return {"status": "unavailable", "error_code": exc.code, "summary": str(exc)}
    except OSError:
        return {"status": "unavailable", "error_code": "UPLOAD_IMAGES_IO_ERROR",
                "summary": "无法保存完整烧录镜像；编译状态单独记录。"}


def validate_layout(images, *, profile=None):
    profile = PROFILE if profile is None else profile
    if not isinstance(images, list) or len(images) != len(LAYOUT):
        fail("UPLOAD_IMAGES_INVALID", "烧录镜像清单不完整。")
    for index, (name, offset) in enumerate(LAYOUT):
        image = images[index]
        limit = LAYOUT[index + 1][1] if index + 1 < len(LAYOUT) else profile["flash_bytes"]
        if (not isinstance(image, dict) or image.get("name") != name or image.get("offset") != offset
                or type(image.get("offset")) is not int or type(image.get("bytes")) is not int
                or not 0 < image["bytes"] <= limit - offset):
            fail("UPLOAD_IMAGES_INVALID", "镜像名称、偏移或大小不符合当前平台，禁止重叠/越界写入。")


def verified_images(project, state, build):
    upload = build.get("upload") or {}
    if upload.get("status") != "ready" or upload.get("profile") != require_profile(state):
        fail("UPLOAD_REBUILD_REQUIRED", "旧构建未保留完整烧录镜像，或平台不匹配。请显式重新编译，不从仿真 bin 猜测烧录。")
    images = upload.get("images")
    validate_layout(images)
    if not isinstance(build.get("attempt"), str) or len(build["attempt"]) != 32 or any(c not in "0123456789abcdef" for c in build["attempt"]):
        fail("UPLOAD_IMAGES_INVALID", "编译记录的 attempt 无效。")
    payloads = {}
    for image in images:
        path = project.meta / "builds" / build["attempt"] / image["name"]
        data = path.read_bytes() if path.is_file() else b""
        if len(data) != image["bytes"] or sha(data) != image.get("sha256"):
            fail("BUILD_CHANGED", "烧录镜像缺失或哈希变化，需重新编译。")
        payloads[image["name"]] = data
    return upload, payloads
