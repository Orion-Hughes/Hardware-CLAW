import asyncio
import copy
import hashlib
import json
import os
import sys
import unittest
import uuid
import zipfile
from unittest.mock import patch

from hardware_claw.projects.service import ProjectService, ProjectError, ROOT, atomic_json
from hardware_claw.adapters.compiler import compile_project, fingerprint, run_process
from hardware_claw.tools.templates import load_template, read_template
from tests.test_projects import DESIGN


class VSCodeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.base = ROOT / "temp/vscode-tests" / uuid.uuid4().hex
        self.p = ProjectService.create("delivery-test", "DHT22 UART", "vscode", workspace=self.base)
        self.p.update_design(0, copy.deepcopy(DESIGN))
        self.p.scaffold(1)
        self.p.write_files(2, {"src/main.cpp": read_template("dht22_uart_example"), "README.md": "Simulation test"})

    def fake_build(self):
        state = self.p._load()
        attempt = uuid.uuid4().hex
        artifacts = {}
        for name in ("firmware.bin", "firmware.elf"):
            path = self.p.meta / "builds" / attempt / name
            path.parent.mkdir(parents=True, exist_ok=True)
            blob = ("TEST_DOUBLE_ONLY:" + name).encode()
            path.write_bytes(blob)
            artifacts[name] = {"sha256": hashlib.sha256(blob).hexdigest(), "path": str(path)}
        atomic_json(self.p.meta / "build.json", {"version": state["version"], "source_sha256": fingerprint(state),
                    "verdict": "pass", "attempt": attempt, "artifacts": artifacts})

    def test_templates_read_only_ids(self):
        self.assertEqual(load_template.invoke({"template_id": "../DS_Api.txt"})["error_code"], "NOT_FOUND")
        self.assertIn("sha256", load_template.invoke({"template_id": "esp32s3_vscode"})["data"])
        with self.assertRaises(ProjectError):
            self.p.write_files(3, {"../../LangChain/templates/esp32s3_vscode.json": "bad"})

    def test_serial_auto_added_and_missing_rejected(self):
        self.assertEqual(self.p.check_files()["verdict"], "pass")
        diagram = json.loads(self.p.read_file("diagram.json")["content"])
        diagram["connections"] = [e for e in diagram["connections"] if "$serialMonitor" not in str(e)]
        self.p.write_files(3, {"diagram.json": json.dumps(diagram)})
        self.assertIn("SERIAL_CONNECTION_REQUIRED", [e["code"] for e in self.p.check_files()["issues"]])

    def test_fixed_config_and_serial_conflict(self):
        self.p.write_files(3, {"platformio.ini": self.p.read_file("platformio.ini")["content"] + "extra_scripts = bad.py\n"})
        self.assertEqual(self.p.check_files()["verdict"], "fail")
        bad = copy.deepcopy(DESIGN)
        bad["connections"].append({"a": "mcu:TX", "b": "$serialMonitor:TX"})
        with self.assertRaises(ProjectError):
            self.p.update_design(4, bad)

    def test_export_requires_real_build_record(self):
        self.p.check_files()
        with self.assertRaises(ProjectError) as caught:
            self.p.export(3)
        self.assertEqual(caught.exception.code, "BUILD_REQUIRED")

    def test_portable_export_and_stale_invalidation(self):
        self.p.check_files()
        self.fake_build()
        exported = self.p.export(3)
        with zipfile.ZipFile(exported["archive"]) as z:
            self.assertIn("firmware/firmware.bin", z.namelist())
            self.assertIn(".vscode/extensions.json", z.namelist())
            self.assertNotIn(b"D:/", z.read("wokwi.toml"))
        self.assertEqual(self.p.delivery()["delivery_status"], "ready_for_vscode")
        self.p.write_files(3, {"README.md": "new revision"})
        self.assertEqual(self.p.delivery()["delivery_status"], "incomplete")
        self.assertEqual(self.p.get()["build"], "not_run")

    def test_tampered_firmware_and_folder_not_delivered(self):
        self.p.check_files()
        self.fake_build()
        result = self.p.export(3)
        from pathlib import Path
        (Path(result["simulation_folder"]) / "firmware/firmware.bin").write_bytes(b"tampered")
        self.assertEqual(self.p.delivery()["delivery_status"], "incomplete")
        with self.assertRaises(ProjectError):
            self.p.export(3)

    async def test_failed_compile_does_not_reuse_previous_artifacts(self):
        self.p.check_files()
        self.fake_build()
        async def fail_compile(command, cwd, env, log, timeout):
            log.write_text("error: injected failure", encoding="utf-8")
            return "fail", 1
        with patch("hardware_claw.adapters.compiler.run_process", side_effect=fail_compile):
            result = await compile_project(self.p, 3)
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["artifacts"], {})
        with self.assertRaises(ProjectError):
            self.p.export(3)
        with self.assertRaises(ProjectError) as caught:
            await compile_project(self.p, 3)
        self.assertEqual(caught.exception.code, "NO_PROGRESS")

    async def test_compile_requires_check_and_version(self):
        with self.assertRaises(ProjectError):
            await compile_project(self.p, 3)
        self.p.check_files()
        with self.assertRaises(ProjectError):
            await compile_project(self.p, 1)

    async def test_timeout_and_cancel_kill_process(self):
        marker = self.base / "should-not-exist.txt"
        # Real subprocess fixture, no API. A child tries to write after the parent is killed.
        child = "import time,pathlib; time.sleep(2); pathlib.Path(" + repr(str(marker)) + ").write_text('leaked')"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-B','-c'," + repr(child) + "]); print('spawned',flush=True); time.sleep(30)"
        log = self.base / "timeout.log"
        result = await run_process([sys.executable, "-B", "-c", parent], self.base, os.environ.copy(), log, 0.6)
        self.assertEqual(result[0], "timeout")
        task = asyncio.create_task(run_process([sys.executable, "-B", "-c", parent], self.base, os.environ.copy(), self.base / "cancel.log", 30))
        await asyncio.sleep(0.6)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(2.1)
        self.assertFalse(marker.exists(), "Child process survived timeout/cancellation")


if __name__ == "__main__":
    unittest.main()
