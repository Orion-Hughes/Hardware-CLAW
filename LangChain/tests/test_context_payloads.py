"""Generic context-size mechanisms; no provider calls or production answer fixtures."""
import unittest
from unittest.mock import Mock

from hardware_claw.tools.project_tools import compact_build, mutation_receipt, make_project_tools
from hardware_claw.tools.hardware_catalog import get_hardware_info


class ContextPayloadTests(unittest.TestCase):
    def test_success_log_omission_does_not_change_stored_report(self):
        report = {"verdict": "pass", "log_tail": "build chatter", "log": "evidence.log", "diagnostics": [], "source_sha256": "hash"}
        compact = compact_build(report)
        self.assertNotIn("log_tail", compact)
        self.assertEqual(compact["log"], report["log"])
        self.assertIn("log_tail", report)
        for status in ("fail", "timeout", "tool_error"):
            failed = report | {"verdict": status}
            self.assertEqual(compact_build(failed), failed)

    def test_receipt_keeps_version_and_validation_without_design_echo(self):
        original = {"version": 7, "design_version": 2, "files": [{"path": "main.cpp"}],
                    "design": {"goal": "fixture"}, "requirements": "fixture", "behavior": "not_run"}
        receipt = mutation_receipt(original)
        self.assertEqual(receipt["version"], 7)
        self.assertEqual(receipt["files"], original["files"])
        self.assertEqual(receipt["behavior"], "not_run")
        self.assertNotIn("design", receipt)
        self.assertIn("design", original)

    def test_file_ranges_and_schema(self):
        project = Mock()
        project.read_file.return_value = {"path": "main.cpp", "content": "one\ntwo\nthree\n", "sha256": "full-hash", "version": 3}
        tool = next(t for t in make_project_tools(project) if t.name == "read_project_file")
        full = tool.invoke({"path": "main.cpp"})["data"]
        self.assertEqual(full["content"], "one\ntwo\nthree\n")
        self.assertFalse(full["partial"])
        part = tool.invoke({"path": "main.cpp", "start_line": 2, "end_line": 2})["data"]
        self.assertEqual(part["content"], "two\n")
        self.assertEqual(part["sha256"], "full-hash")
        self.assertTrue(part["partial"])
        self.assertEqual(part["total_lines"], 3)
        for start, end in ((4, None), (3, 1)):
            self.assertEqual(tool.invoke({"path": "main.cpp", "start_line": start, "end_line": end})["error_code"], "INVALID_ARGUMENT")
        patch = next(t for t in make_project_tools(project) if t.name == "apply_project_patch")
        self.assertNotIn("start_line", patch.args)

    def test_catalog_projection_keeps_constraints_for_multiple_profiles(self):
        for ident in ("dht22_red_module", "st7789_240x240_simulation", "esp32_s3_devkitc1_n32r16v"):
            with self.subTest(ident=ident):
                full = get_hardware_info.invoke({"hardware_id": ident})["data"]
                small = get_hardware_info.invoke({"hardware_id": ident, "sections": []})["data"]
                self.assertEqual(full["summary"], small["summary"])
                self.assertEqual(full["provenance"], small["provenance"])
                for key in ("generation_profile", "notes", "source_refs"):
                    self.assertEqual(full["profile"].get(key), small["profile"].get(key))
                self.assertIn("driver_profile", small["omitted_sections"])
                driver = get_hardware_info.invoke({"hardware_id": ident, "sections": ["driver_profile"]})["data"]
                self.assertEqual(driver["profile"]["driver_profile"], full["profile"]["driver_profile"])
        invalid = get_hardware_info.invoke({"hardware_id": "dht22_red_module", "sections": ["invented"]})
        self.assertEqual(invalid["error_code"], "INVALID_ARGUMENT")
