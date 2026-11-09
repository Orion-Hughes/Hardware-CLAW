import copy
import json
import os
import unittest
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hardware_claw.projects.service import ProjectService, ProjectError, ROOT
from hardware_claw.tools.skills import load_skill

DESIGN = {
    "goal": "ESP32-S3 DHT22每2秒采样，串口输出",
    "simulation_only": True, "board_id": "esp32_s3_devkitc1_n32r16v",
    "components": [{"instance_id": "dht", "hardware_id": "dht22_red_module"}],
    "connections": [{"a": "mcu:4", "b": "dht:SDA"}, {"a": "mcu:3V3.1", "b": "dht:VCC"}, {"a": "mcu:GND.1", "b": "dht:GND"}],
    "dependencies": [],
    "assumptions": ["仅仿真，未编译或运行"], "pin_defines": {"DHT_PIN": 4},
}


def artifacts():
    return {
        "sketch.ino": "#include <DHTesp.h>\nconstexpr int DHT_PIN = 4;\nvoid setup() {}\nvoid loop() {}\n",
        "diagram.json": json.dumps({"version": 1, "parts": [{"id": "mcu", "type": "board-esp32-s3-devkitc-1", "attrs": {}}, {"id": "dht", "type": "wokwi-dht22", "attrs": {}}], "connections": [[e["a"], e["b"], "green", []] for e in DESIGN["connections"]]}),
        "libraries.txt": "# Local driver bundles are injected by the host.\n",
        "README.md": "仿真示例，未编译、未仿真。",
    }


class ProjectTests(unittest.TestCase):
    def test_design_schema_explains_board_and_instance_identifiers(self):
        from hardware_claw.contracts.project import UpdateDesignInput
        schema = UpdateDesignInput.model_json_schema()
        self.assertIn('自动创建', schema['$defs']['Design']['properties']['board_id']['description'])
        self.assertIn('外设', schema['$defs']['Design']['properties']['components']['description'])
        self.assertIn('mcu', schema['$defs']['Component']['properties']['instance_id']['description'])

    def test_reserved_and_duplicate_instance_feedback_preserves_design(self):
        from hardware_claw.tools.project_tools import make_project_tools
        tool = next(t for t in make_project_tools(self.p) if t.name == 'update_project_design')
        for instance in ('mcu', 'dht'):
            with self.subTest(instance=instance):
                bad = copy.deepcopy(DESIGN)
                bad['components'].append({'instance_id': instance, 'hardware_id': DESIGN['board_id'] if instance == 'mcu' else 'dht22_red_module'})
                result = tool.invoke({'expected_version': 0, 'design': bad})
                self.assertEqual(result['error_code'], 'DUPLICATE_INSTANCE')
                self.assertIn('components[1]', result['summary'])
                self.assertIn('此次未保存', result['summary'])
                self.assertIn('board_id' if instance == 'mcu' else 'connections', result['summary'])
                self.assertEqual(self.p.get()['version'], 0)
                self.assertIsNone(self.p.get()['design'])

    def setUp(self):
        self.workspace = ROOT / "temp" / "project-tests" / uuid.uuid4().hex
        self.p = ProjectService.create("test", "DHT22监控", "arduino", workspace=self.workspace)

    def ready(self):
        self.p.update_design(0, copy.deepcopy(DESIGN))
        self.p.write_files(1, artifacts())

    def test_skill_unknown_and_workflow(self):
        self.assertEqual(load_skill.invoke({"skill_id": "../DS_Api.txt"})["error_code"], "NOT_FOUND")
        self.assertIn("content", load_skill.invoke({"skill_id": "wokwi_generation"})["data"])

    def test_versions_snapshot_and_stale_write(self):
        self.ready()
        snapshot = self.p.meta / "revisions/v000002/state.json"
        original = snapshot.read_bytes()
        self.p.patch_file(2, "README.md", "仿真示例", "新版示例")
        self.assertEqual(snapshot.read_bytes(), original)
        with self.assertRaises(ProjectError) as caught:
            self.p.write_files(2, {"README.md": "stale"})
        self.assertEqual(caught.exception.code, "VERSION_CONFLICT")
        self.assertIn("新版", self.p.read_file("README.md")["content"])

    def test_all_or_nothing_invalid_batch(self):
        self.ready()
        with self.assertRaises(ProjectError):
            self.p.write_files(2, {"README.md": "modified", "../secret.txt": "blocked"})
        self.assertEqual(self.p.get()["version"], 2)
        self.assertEqual(self.p.read_file("README.md")["content"], artifacts()["README.md"])

    def test_paths_and_file_types(self):
        self.p.update_design(0, DESIGN)
        for name in ("../DS_Api.txt", "D:/secret.txt", "x/../../DS_Api.txt", "x\\README.md", "NUL.txt", "README.md:stream", ".hwclaw/project.json", "script.ps1", "image.bin"):
            with self.subTest(name=name), self.assertRaises(ProjectError):
                self.p.write_files(1, {name: "bad"})

    def test_external_file_change_refused(self):
        self.ready()
        (self.p.files / "README.md").write_text("manual change", encoding="utf-8")
        with self.assertRaises(ProjectError) as caught:
            self.p.write_files(2, {"README.md": "overwrite"})
        self.assertEqual(caught.exception.code, "EXTERNAL_CHANGE")

    def test_newline_preserving_writes_remain_editable(self):
        self.ready()
        version = 2
        for content in ("中文\nnext\n", "中文\r\nnext\r\n", "中文\rnext\r", "中文\r\nnext\nlast\r"):
            with self.subTest(content=repr(content)):
                self.p.write_files(version, {"README.md": content})
                version += 1
                snapshot = self.p.meta / f"revisions/v{version:06d}/state.json"
                original = snapshot.read_bytes()
                self.assertEqual((self.p.files / "README.md").read_bytes(), content.encode("utf-8"))
                self.assertEqual(self.p.read_file("README.md")["content"], content)
                self.p.patch_file(version, "README.md", "next", "updated")
                version += 1
                self.assertEqual((self.p.files / "README.md").read_bytes(), content.replace("next", "updated").encode("utf-8"))
                self.assertEqual(snapshot.read_bytes(), original)

    def test_newline_only_and_invalid_utf8_external_changes_refused(self):
        self.ready()
        self.p.write_files(2, {"README.md": "line\r\n"})
        for changed in (b"line\n", b"line\r", b"\xff"):
            with self.subTest(changed=changed):
                (self.p.files / "README.md").write_bytes(changed)
                with self.assertRaises(ProjectError) as caught:
                    self.p.write_files(3, {"README.md": "overwrite"})
                self.assertEqual(caught.exception.code, "EXTERNAL_CHANGE")
                self.assertEqual(self.p.get()["version"], 3)

    def test_hardlink_refused(self):
        self.ready()
        target = self.workspace / "outside.txt"
        target.write_text("private", encoding="utf-8")
        os.link(target, self.p.files / "linked.txt")
        with self.assertRaises(ProjectError) as caught:
            self.p.read_file("linked.txt")
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")

    def test_patch_requires_unique_text(self):
        self.ready()
        self.p.write_files(2, {"README.md": "same same"})
        with self.assertRaises(ProjectError) as caught:
            self.p.patch_file(3, "README.md", "same", "new")
        self.assertEqual(caught.exception.code, "PATCH_MISMATCH")

    def test_concurrent_writes_only_one_wins(self):
        self.ready()
        def write(text):
            try:
                self.p.write_files(2, {"README.md": text})
                return "ok"
            except ProjectError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ("first", "second")))
        self.assertEqual(sorted(results), ["VERSION_CONFLICT", "ok"])

    def test_design_blocks_unsupported_and_bad_endpoint(self):
        bad = copy.deepcopy(DESIGN)
        bad["components"][0]["hardware_id"] = "st7789_2in_240x320"
        with self.assertRaises(ProjectError) as caught:
            self.p.update_design(0, bad)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_HARDWARE")
        bad = copy.deepcopy(DESIGN)
        bad["connections"][0]["a"] = "mcu:999"
        with self.assertRaises(ProjectError) as caught:
            self.p.update_design(0, bad)
        self.assertEqual(caught.exception.code, "INVALID_ENDPOINT")

    def test_missing_and_basic_pass_are_not_behavior_pass(self):
        self.assertEqual(self.p.check_files()["verdict"], "fail")
        self.ready()
        report = self.p.check_files()
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["behavior"], "not_run")
        self.p.patch_file(2, "sketch.ino", "DHT_PIN = 4", "DHT_PIN = 9")
        self.assertIsNone(self.p.get()["file_check"])
        self.assertIn("PIN_DEFINE_MISMATCH", {i["code"] for i in self.p.check_files()["issues"]})

    def test_connection_fault_and_power_short(self):
        self.ready()
        diagram = json.loads(artifacts()["diagram.json"])
        diagram["connections"].append(["dht:VCC", "dht:GND", "red", []])
        self.p.write_files(2, {"diagram.json": json.dumps(diagram)})
        codes = {i["code"] for i in self.p.check_files()["issues"]}
        self.assertTrue({"POWER_SHORT", "CONNECTION_MISMATCH"} <= codes)

    def test_duplicate_json_rejected(self):
        self.ready()
        self.p.write_files(2, {"diagram.json": '{"version":1,"version":1,"parts":[],"connections":[]}'})
        self.assertIn("INVALID_DIAGRAM", {i["code"] for i in self.p.check_files()["issues"]})

    def test_export_gated_versioned_and_artifacts_only(self):
        self.ready()
        with self.assertRaises(ProjectError) as caught:
            self.p.export(2)
        self.assertEqual(caught.exception.code, "CHECK_REQUIRED")
        self.p.check_files()
        exported = self.p.export(2)
        with zipfile.ZipFile(exported["archive"]) as z:
            self.assertEqual(set(z.namelist()), set(artifacts()) | {"_hwclaw_manifest.json"})
        self.assertEqual(self.p.export(2)["sha256"], exported["sha256"])
        self.assertEqual(self.p.delivery()["delivery_status"], "generated_not_simulated")
        self.p.patch_file(2, "README.md", "仿真示例", "修改示例")
        self.assertEqual(self.p.delivery()["delivery_status"], "incomplete")
        self.assertTrue(Path(exported["archive"]).exists())

    def test_platformio_build_paths_and_script_rejection(self):
        p = ProjectService.create("pio", "DHT22监控", "platformio", workspace=self.workspace)
        p.update_design(0, DESIGN)
        files = artifacts()
        files["src/main.cpp"] = "#include <Arduino.h>\n" + files.pop("sketch.ino")
        files.pop("libraries.txt")
        files["platformio.ini"] = "[env:esp32-s3-devkitc-1]\nplatform = espressif32@6.12.0\nboard = esp32-s3-devkitc-1\nframework = arduino\n"
        files["wokwi.toml"] = '[wokwi]\nversion = 1\nfirmware = ".pio/build/esp32-s3-devkitc-1/firmware.bin"\nelf = ".pio/build/esp32-s3-devkitc-1/firmware.elf"\n'
        p.write_files(1, files)
        self.assertEqual(p.check_files()["verdict"], "pass")
        p.write_files(2, {"platformio.ini": files["platformio.ini"] + "extra_scripts = outside.py\n"})
        self.assertIn("UNSUPPORTED_BUILD_OPTION", {i["code"] for i in p.check_files()["issues"]})

    def test_design_change_invalidates_files(self):
        self.ready()
        self.p.check_files()
        updated = copy.deepcopy(DESIGN)
        updated["goal"] = "updated goal"
        self.p.update_design(2, updated)
        self.assertIn("STALE_FILES", {i["code"] for i in self.p.check_files()["issues"]})

    def test_missing_wokwi_version_has_actionable_feedback(self):
        from hardware_claw.validation.files import check
        self.ready()
        state = self.p._load()
        state["template"] = "platformio"
        state["files"]["src/main.cpp"] = "#include <Arduino.h>\n" + state["files"].pop("sketch.ino")
        state["files"]["platformio.ini"] = "[env:esp32s3]\nplatform=espressif32@6.12.0\nboard=esp32-s3-devkitc-1\nframework=arduino\n"
        state["files"]["wokwi.toml"] = '[wokwi]\nfirmware=".pio/build/esp32s3/firmware.bin"\nelf=".pio/build/esp32s3/firmware.elf"'
        codes = {i["code"] for i in check(state)["issues"]}
        self.assertEqual(codes, {"WOKWI_VERSION_REQUIRED"})
        state["files"]["wokwi.toml"] = 'wokwi = []'
        self.assertIn("INVALID_WOKWI_SECTION", {i["code"] for i in check(state)["issues"]})

    def test_export_root_link_refused(self):
        outside = self.workspace / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, self.p.root / "exports", target_is_directory=True)
        except OSError:
            self.skipTest("directory symlink permission unavailable")
        with self.assertRaises(ProjectError) as caught:
            self.p.get()
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")
