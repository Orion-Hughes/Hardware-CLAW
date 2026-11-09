import re
import json
import tempfile
import unittest
from pathlib import Path

from hardware_claw.projects.naming import build_project_id, hardware_slug, resolve_tester, task_slug
from hardware_claw.projects.service import ProjectService, ProjectError


class ProjectNamingTests(unittest.TestCase):
    def test_readable_id_contains_tester_hardware_task_and_suffix(self):
        ident = build_project_id(
            "web-project",
            "ESP32-S3 和 DHT22 每2秒通过串口输出温湿度",
            "hmy",
        )
        self.assertRegex(ident, r"^hmy-dht22_esp32_s3-serial_output-[0-9a-f]{6}$")

    def test_hardware_and_task_are_separate_segments(self):
        self.assertEqual(hardware_slug("web-project", "摇杆和屏幕显示输入位置"), "joystick_display")
        self.assertEqual(task_slug("web-project", "摇杆和屏幕显示输入位置"), "input_visualizer")

    def test_unknown_names_have_stable_fallbacks(self):
        self.assertEqual(hardware_slug("task-1234567890", "请做一个嵌入式系统"), "hardware")
        self.assertEqual(task_slug("task-1234567890", "请做一个嵌入式系统"), "embedded_task")

    def test_service_persists_tester_and_opens_new_id(self):
        with tempfile.TemporaryDirectory() as directory:
            project = ProjectService.create(
                "web-project", "摇杆控制屏幕上的小圆点", "vscode",
                tester="hmy", workspace=Path(directory),
            )
            self.assertRegex(project.id, r"^hmy-joystick_display-input_visualizer-[0-9a-f]{6}$")
            state = project.get()
            self.assertEqual(state["tester"], "hmy")
            self.assertEqual(ProjectService.open(project.id, workspace=Path(directory)).id, project.id)

    def test_invalid_tester_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProjectError) as caught:
                ProjectService.create("test", "requirement", workspace=Path(directory), tester="///")
            self.assertEqual(caught.exception.code, "INVALID_TESTER")

    def test_legacy_project_without_tester_remains_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            project = ProjectService.create("legacy", "requirement", workspace=Path(directory))
            state_path = project.meta / "revisions" / "v000000" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            del state["tester"]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            self.assertIsNone(project.get()["tester"])


if __name__ == "__main__":
    unittest.main()
