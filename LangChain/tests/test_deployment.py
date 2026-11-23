"""Deployment mechanism tests only; no hardware, provider or Wokwi calls."""
import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hardware_claw.deployment import images, service
from hardware_claw.deployment import target
from hardware_claw.deployment.web import preview_command
from hardware_claw.projects.service import ProjectService, ProjectError, ROOT, atomic_json
from hardware_claw.adapters.compiler import fingerprint, compile_project
from tests.test_projects import DESIGN

PORT = {"device": "COM7", "description": "TEST DOUBLE", "vid": 0x303A, "pid": 0x1001,
        "serial_number": "fixture", "location": "fixture-port"}


class DeploymentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        base = ROOT / "temp/deployment-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Mocked compiler tests must also run in a fresh clone with no toolchain.
        fixture_pio = self.root / "fixture-pio"
        fixture_pio.write_text("TEST DOUBLE; never executable", encoding="utf-8")
        compiler_path = patch("hardware_claw.adapters.compiler.PIO", fixture_pio)
        compiler_path.start()
        self.addCleanup(compiler_path.stop)
        self.project = ProjectService.create("mechanism", "Upload interface fixture, not a hardware acceptance case",
                                             workspace=self.root / "workspace")
        design = copy.deepcopy(DESIGN)
        design.update(components=[], connections=[], dependencies=[], pin_defines={})
        self.project.update_design(0, design)
        self.project.scaffold(1)
        self.project.write_files(2, {"src/main.cpp": "#include <Arduino.h>\n"
            "void setup(){Serial.begin(115200); Serial.println(\"HWCLAW_BOOT\");}\n"
            "void loop(){delay(100);}\n", "README.md": "Software fixture, no physical or functional acceptance."})
        self.assertEqual(self.project.check_files()["verdict"], "pass")
        self.framework = self.root / "framework"
        boot = self.framework / "tools/partitions/boot_app0.bin"
        boot.parent.mkdir(parents=True)
        boot.write_bytes(b"fixture-ota")
        self.work = self.root / "work"
        self.out = self.work / ".pio/build/esp32s3"
        self.out.mkdir(parents=True)
        for name in ("bootloader.bin", "partitions.bin", "firmware.bin", "firmware.elf"):
            (self.out / name).write_bytes(b"TEST_DOUBLE:" + name.encode())
        self.build_folder = self.project.meta / "builds" / ("a" * 32)
        self.build_folder.mkdir(parents=True)
        (self.build_folder / "firmware.bin").write_bytes((self.out / "firmware.bin").read_bytes())
        self.identity = {"python": "fixed-python", "script": "fixed-esptool",
                         "script_sha256": "a" * 64, "package_version": images.PROFILE["esptool_package"]}
        self.ports = patch.object(service, "list_ports", return_value=[dict(PORT)]).start()
        self.tool = patch.object(service, "tool_identity", return_value=self.identity).start()
        self.runner = patch.object(service, "run_process", new_callable=AsyncMock).start()
        self.runner.return_value = ("pass", 0)
        self.addCleanup(patch.stopall)
        self.store_build()

    def store_build(self):
        state = self.project._load()
        with patch.object(images, "package_dir", return_value=self.framework):
            upload = images.capture_images(state, self.work, self.build_folder)
        self.assertEqual(upload["status"], "ready")
        self.build = {"version": state["version"], "verdict": "pass", "attempt": "a" * 32,
                      "source_sha256": fingerprint(state), "artifacts": {}, "upload": upload,
                      "build_profile": dict(target.PROFILE), "effective_platformio": target.platformio_for(state)}
        atomic_json(self.project.meta / target.REPORT, self.build)

    def prepare(self, **kwargs):
        return service.prepare_upload(self.project, 3, port="COM7", board=images.PROFILE["board"],
                                      hardware_reviewed=True, **kwargs)

    def edit_plan(self, plan, mutate):
        path = Path(plan["plan_path"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        mutate(saved)
        atomic_json(path, saved)

    async def assert_blocked(self, plan, code, token=None):
        with self.assertRaises(ProjectError) as caught:
            await service.execute_upload(self.project, plan["plan_id"],
                                         plan["confirmation"] if token is None else token)
        self.assertEqual(caught.exception.code, code)
        self.runner.assert_not_awaited()

    def test_preview_has_complete_images_but_never_opens_or_flashes(self):
        plan = service.prepare_upload(self.project, 3)
        self.assertFalse(plan["ready"])
        self.assertIsNone(plan["confirmation"])
        self.assertEqual(len(plan["blockers"]), 3)
        self.assertEqual([i["offset"] for i in plan["images"]], [0, 0x8000, 0xE000, 0x10000])
        self.runner.assert_not_called()
        self.assertEqual(self.project.get()["version"], 3)

    async def test_unconfirmed_preview_and_wrong_token_cannot_execute(self):
        await self.assert_blocked(service.prepare_upload(self.project, 3), "UPLOAD_CONFIRMATION_REQUIRED")
        await self.assert_blocked(self.prepare(), "UPLOAD_CONFIRMATION_REQUIRED", token="wrong")

    def test_wrong_board_and_network_or_absent_port_are_rejected(self):
        for args, code in (({"board": "esp32dev"}, "UPLOAD_BOARD_MISMATCH"),
                           ({"port": "192.168.1.1"}, "INVALID_UPLOAD_PORT"),
                           ({"port": "COM8"}, "UPLOAD_PORT_NOT_FOUND")):
            with self.subTest(args=args), self.assertRaises(ProjectError) as caught:
                service.prepare_upload(self.project, 3, **args)
            self.assertEqual(caught.exception.code, code)
        self.runner.assert_not_called()

    async def test_stale_version_external_edit_and_build_mismatch_rejected(self):
        plan = self.prepare()
        self.project.write_files(3, {"README.md": "revision changed"})
        await self.assert_blocked(plan, "VERSION_CONFLICT")
        # A separate fixture is not needed to show preparation refuses stale builds.
        self.project.check_files()
        with self.assertRaises(ProjectError) as caught:
            service.prepare_upload(self.project, 4)
        self.assertEqual(caught.exception.code, "BUILD_REQUIRED")

    async def test_external_edit_blocks_upload(self):
        plan = self.prepare()
        (self.project.files / "README.md").write_text("external change")
        await self.assert_blocked(plan, "EXTERNAL_CHANGE")

    async def test_expired_and_reconfigured_plans_are_rejected(self):
        plan = self.prepare()
        self.edit_plan(plan, lambda p: p.update(expires_at=0))
        await self.assert_blocked(plan, "UPLOAD_PLAN_EXPIRED")
        plan = self.prepare()
        self.edit_plan(plan, lambda p: p["images"][0].update(offset=0x1000))
        await self.assert_blocked(plan, "UPLOAD_PLAN_STALE")

    async def test_changed_port_identity_and_changed_tool_rejected(self):
        plan = self.prepare()
        self.ports.return_value = [{**PORT, "serial_number": "another-device"}]
        await self.assert_blocked(plan, "UPLOAD_DEVICE_CHANGED")
        self.ports.return_value = [dict(PORT)]
        self.tool.return_value = {**self.identity, "script_sha256": "b" * 64}
        await self.assert_blocked(plan, "UPLOADER_CHANGED")

    async def test_modified_plan_snapshot_and_build_images_are_rejected(self):
        plan = self.prepare()
        (Path(plan["plan_path"]).parent / "images/bootloader.bin").write_bytes(b"tampered")
        await self.assert_blocked(plan, "BUILD_CHANGED")
        plan = self.prepare()
        (self.build_folder / "partitions.bin").write_bytes(b"tampered")
        await self.assert_blocked(plan, "BUILD_CHANGED")

    async def test_mock_upload_claims_once_and_does_not_claim_behavior_pass(self):
        plan = self.prepare()
        saved = json.loads(Path(plan["plan_path"]).read_text(encoding="utf-8"))
        self.assertNotIn(plan["confirmation"], json.dumps(saved))
        report = await service.execute_upload(self.project, plan["plan_id"], plan["confirmation"])
        self.assertEqual(report["status"], "uploaded")
        self.assertEqual(report["behavior"], "not_run")
        self.assertEqual(self.project.get()["version"], 3)
        args = self.runner.await_args.args[0]
        self.assertIn("--chip", args)
        self.assertIn("write_flash", args)
        self.assertNotIn("erase_flash", args)
        self.assertNotIn("--force", args)
        with self.assertRaises(ProjectError) as caught:
            await service.execute_upload(self.project, plan["plan_id"], plan["confirmation"])
        self.assertEqual(caught.exception.code, "UPLOAD_ALREADY_ATTEMPTED")
        self.assertEqual(self.runner.await_count, 1)

    async def test_failed_timeout_or_cancelled_upload_does_not_auto_retry(self):
        for verdict in ("fail", "timeout"):
            plan = self.prepare()
            self.runner.return_value = (verdict, 1)
            result = await service.execute_upload(self.project, plan["plan_id"], plan["confirmation"])
            self.assertEqual(result["status"], verdict)
        plan = self.prepare()
        self.runner.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await service.execute_upload(self.project, plan["plan_id"], plan["confirmation"])
        report = json.loads((Path(plan["plan_path"]).parent / "execution.json").read_text())
        self.assertEqual(report["status"], "cancelled")

    async def test_start_error_is_recorded_and_cannot_be_retried(self):
        plan = self.prepare()
        self.runner.side_effect = OSError("fixture launch failure")
        result = await service.execute_upload(self.project, plan["plan_id"], plan["confirmation"])
        self.assertEqual(result["status"], "tool_error")
        with self.assertRaises(ProjectError) as caught:
            await service.execute_upload(self.project, plan["plan_id"], plan["confirmation"])
        self.assertEqual(caught.exception.code, "UPLOAD_ALREADY_ATTEMPTED")
        self.assertEqual(self.runner.await_count, 1)

    def test_build_fingerprint_and_image_integrity_block_preparation(self):
        self.build["source_sha256"] = "0" * 64
        atomic_json(self.project.meta / target.REPORT, self.build)
        with self.assertRaises(ProjectError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "BUILD_REQUIRED")
        self.build["source_sha256"] = fingerprint(self.project._load())
        atomic_json(self.project.meta / target.REPORT, self.build)
        (self.build_folder / "firmware.bin").write_bytes(b"changed")
        with self.assertRaises(ProjectError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "BUILD_CHANGED")

    async def test_replaced_build_requires_a_new_confirmation(self):
        plan = self.prepare()
        self.build["attempt"] = "b" * 32
        other = self.project.meta / "builds" / self.build["attempt"]
        other.mkdir()
        for name, _ in images.LAYOUT:
            (other / name).write_bytes((self.build_folder / name).read_bytes())
        atomic_json(self.project.meta / target.REPORT, self.build)
        await self.assert_blocked(plan, "UPLOAD_PLAN_STALE")

    def test_old_build_still_passes_but_requires_rebuild_for_upload(self):
        self.build.pop("upload")
        atomic_json(self.project.meta / target.REPORT, self.build)
        with self.assertRaises(ProjectError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "UPLOAD_REBUILD_REQUIRED")
        self.assertEqual(target.build_status(self.project, self.project._load())["verdict"], "pass")

    def test_layout_overlaps_and_unsupported_profiles_are_rejected(self):
        layout = copy.deepcopy(self.build["upload"]["images"])
        layout[0]["bytes"] = 0x8001
        with self.assertRaises(ProjectError):
            images.validate_layout(layout)
        state = self.project._load()
        state["template"] = "arduino"
        result = images.capture_images(state, self.work, self.build_folder)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["error_code"], "UPLOAD_PROFILE_UNSUPPORTED")

    def test_physical_profile_requires_opi_and_leaves_source_scaffold_unchanged(self):
        state = self.project._load()
        source = copy.deepcopy(state)
        ini = target.platformio_for(state)
        self.assertIn("board_build.arduino.memory_type = opi_opi", ini)
        self.assertIn("board_build.boot = opi", ini)
        self.assertIn("board_upload.flash_size = 32MB", ini)
        self.assertIn("board_build.partitions = large_fat_32MB.csv", ini)
        self.assertIn("-DBOARD_HAS_PSRAM", ini)
        self.assertEqual(state, source)
        self.assertNotIn("opi_opi", state["files"]["platformio.ini"])
        plan = self.prepare()
        self.assertEqual(plan["profile"]["flash_size"], "32MB")
        self.assertEqual(plan["profile"]["memory_type"], "opi_opi")
        self.assertEqual(plan["profile"]["hardware_test"], "not_run")
        command = plan["command_preview"]
        self.assertEqual(command[command.index("--flash_mode") + 1], "dout")
        self.assertEqual(command[command.index("--flash_size") + 1], "32MB")

    def test_reserved_wroom2_pins_are_not_silently_rewired(self):
        for pin in ("35", "36", "37"):
            state = self.project._load()
            state["design"]["connections"].append({"a": "mcu:" + pin, "b": "peripheral:SIG"})
            with self.assertRaises(ProjectError) as caught:
                target.platformio_for(state)
            self.assertEqual(caught.exception.code, "PHYSICAL_GPIO_RESERVED")
            self.assertEqual(state["design"]["connections"][-1]["a"], "mcu:" + pin)

    def test_simulation_build_never_substitutes_for_physical_build(self):
        (self.project.meta / target.REPORT).unlink()
        atomic_json(self.project.meta / "build.json", self.build)
        with self.assertRaises(ProjectError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "BUILD_REQUIRED")

    def test_target_configuration_change_invalidates_physical_build(self):
        for key, value in (("memory_type", "qio_qspi"), ("flash_size", "8MB")):
            record = copy.deepcopy(self.build)
            record["build_profile"][key] = value
            atomic_json(self.project.meta / target.REPORT, record)
            with self.assertRaises(ProjectError) as caught:
                self.prepare()
            self.assertEqual(caught.exception.code, "BUILD_REQUIRED")
        self.build["effective_platformio"] += "\nboard_build.flash_mode = dio\n"
        atomic_json(self.project.meta / target.REPORT, self.build)
        with self.assertRaises(ProjectError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "BUILD_REQUIRED")

    async def test_physical_compile_uses_host_config_and_separate_report(self):
        before = self.project._load()
        simulation = {"version": 3, "verdict": "pass", "source_sha256": "SIMULATION_EVIDENCE"}
        atomic_json(self.project.meta / "build.json", simulation)

        async def fake_build(command, cwd, env, log, timeout):
            self.assertEqual((cwd / "platformio.ini").read_text(encoding="utf-8"), target.platformio_for(before))
            self.assertEqual((cwd / "src/main.cpp").read_text(encoding="utf-8"), before["files"]["src/main.cpp"])
            out = cwd / ".pio/build/esp32s3"
            out.mkdir(parents=True)
            for name in ("firmware.bin", "firmware.elf", "bootloader.bin", "partitions.bin"):
                (out / name).write_bytes(b"TEST_DOUBLE:" + name.encode())
            log.write_text("fixture physical compilation", encoding="utf-8")
            return "pass", 0
        with patch("hardware_claw.adapters.compiler.run_process", side_effect=fake_build), \
                patch.object(images, "package_dir", return_value=self.framework):
            result = await compile_project(self.project, 3, target=target.TARGET)
        self.assertEqual(result["verdict"], "pass")
        self.assertTrue(target.matches(result, before))
        self.assertEqual(result["upload"]["profile"], target.PROFILE)
        self.assertEqual(json.loads((self.project.meta / "build.json").read_text()), simulation)
        self.assertEqual(target.build_status(self.project, before)["attempt"], result["attempt"])
        self.assertEqual(self.project._load(), before)

    async def test_compile_captures_images(self):
        async def fake_build(command, cwd, env, log, timeout):
            out = cwd / ".pio/build/esp32s3"
            out.mkdir(parents=True)
            for name in ("firmware.bin", "firmware.elf", "bootloader.bin", "partitions.bin"):
                (out / name).write_bytes(b"TEST_DOUBLE:" + name.encode())
            log.write_text("fixture compile", encoding="utf-8")
            return "pass", 0
        with patch("hardware_claw.adapters.compiler.run_process", side_effect=fake_build), \
                patch.object(images, "package_dir", return_value=self.framework):
            result = await compile_project(self.project, 3)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["upload"]["status"], "ready")
        self.assertEqual(result["upload"]["profile"]["flash_size"], "8MB")
        self.assertNotIn("build_profile", result)

    async def test_missing_auxiliary_images_do_not_break_simulation_compile(self):
        async def fake_compile(command, cwd, env, log, timeout):
            out = cwd / ".pio/build/esp32s3"
            out.mkdir(parents=True)
            for name in ("firmware.bin", "firmware.elf"):
                (out / name).write_bytes(b"TEST_DOUBLE:" + name.encode())
            log.write_text("fixture", encoding="utf-8")
            return "pass", 0
        with patch("hardware_claw.adapters.compiler.run_process", side_effect=fake_compile), \
                patch.object(images, "package_dir", return_value=self.framework):
            result = await compile_project(self.project, 3)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["upload"]["status"], "unavailable")
        self.assertEqual(result["upload"]["error_code"], "UPLOAD_IMAGES_MISSING")

    async def test_web_preview_commands_do_not_execute(self):
        self.assertIn("绑定", await preview_command("/flash-plan", None))
        with patch("hardware_claw.deployment.web.list_ports", return_value=[dict(PORT)]):
            self.assertIn("未连接", await preview_command("/ports", None))
        self.assertIn("未烧录", await preview_command("/flash-plan", self.project))
        self.runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
