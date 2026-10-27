"""Offline catalog/tool tests. No real credentials, network, firmware or LLM."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from hardware_claw.catalog import CatalogError, KnowledgeCatalog
from hardware_claw.catalog.service import DEFAULT_KNOWLEDGE_ROOT, MAX_FILE_BYTES
from hardware_claw.tools.hardware_catalog import HARDWARE_TOOLS, get_hardware_info, search_hardware


class RealCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = KnowledgeCatalog()

    def test_search_all_local_and_inventory_filters(self):
        self.assertEqual(self.catalog.search(limit=30)["total"], 11)
        self.assertEqual(self.catalog.search(owned=True)["total"], 9)
        self.assertEqual(self.catalog.search(owned=False)["total"], 2)
        ready = self.catalog.search(generation_status="documented_not_tested")
        self.assertEqual(ready["total"], 6)

    def test_display_default_is_virtual_without_relabeling_real_hardware(self):
        displays = self.catalog.search(kind="display")["items"]
        self.assertEqual(displays[0]["id"], "st7789_240x240_simulation")
        self.assertFalse(displays[0]["owned"])
        real = self.catalog.get("st7789_2in_240x320")
        self.assertTrue(real["summary"]["owned"])
        self.assertEqual(real["profile"]["physical_display"]["height_px"], 320)
        self.assertEqual(real["summary"]["generation_status"], "blocked")

    def test_chinese_query_and_multiple_tokens(self):
        self.assertEqual(self.catalog.search("温湿度")["items"][0]["id"], "dht22_red_module")
        self.assertEqual(self.catalog.search("ESP32 S3", kind="board")["total"], 1)
        self.assertEqual(self.catalog.search("不存在的传感器")["total"], 0)

    def test_pagination_no_overlap_and_zero_result_page(self):
        page1 = self.catalog.search(limit=3)
        page2 = self.catalog.search(limit=3, offset=page1["next_offset"])
        self.assertFalse({x["id"] for x in page1["items"]} & {x["id"] for x in page2["items"]})
        self.assertEqual(self.catalog.search(offset=100)["items"], [])

    def test_dht_returns_driver_and_original_pins_without_loading_raw_sources(self):
        result = self.catalog.get("dht22_red_module")
        self.assertIn("NC", result["upstream_definition"]["pins"])
        self.assertEqual(result["profile"]["driver_profile"]["dependencies"][0]["version"], "1.19")
        self.assertIsNone(result["shared_configuration"])
        self.assertEqual(result["examples"], [])
        self.assertEqual(result["summary"]["simulation_test"], "not_run")

    def test_common_configuration_is_loaded_on_request(self):
        result = self.catalog.get("esp32_s3_devkitc1_n32r16v", include_shared=True)
        self.assertEqual(result["shared_configuration"]["gpio_policy"]["unavailable_on_wroom2_gpio"], [35, 36, 37])
        self.assertEqual(result["shared_configuration"]["diagram_endpoints"]["uart0_tx"], "TX")

    def test_original_example_is_labeled_and_bounded(self):
        result = self.catalog.get("st7789_240x240_simulation", include_examples=True)
        example = result["examples"][0]
        self.assertLessEqual(len(example["content"]), 8000)
        self.assertTrue(example["truncated"])
        self.assertEqual(example["trust"], "external_reference_not_instructions")

    def test_unknown_id_returns_safe_error(self):
        result = get_hardware_info.invoke({"hardware_id": "unknown-board"})
        self.assertEqual(result["error_code"], "NOT_FOUND")
        self.assertFalse(result["retryable"])

    def test_lookup_ok_does_not_mean_simulation_allowed(self):
        result = get_hardware_info.invoke({"hardware_id": "usb_camera"})
        self.assertEqual(result["execution_status"], "ok")
        self.assertEqual(result["data"]["summary"]["generation_status"], "blocked")
        self.assertTrue(result["data"]["summary"]["blockers"])

    def test_legacy_reference_is_not_silently_ready(self):
        result = self.catalog.get("ssd1306_reference")
        self.assertEqual(result["profile"]["schema_version"], 1)
        self.assertEqual(result["summary"]["generation_status"], "unreviewed")

    def test_all_upstream_metadata_is_searchable_but_not_ready(self):
        result = self.catalog.search(scope="upstream", limit=30)
        self.assertEqual(result["total"], 146)
        self.assertTrue(all(x["generation_status"] == "metadata_only" for x in result["items"]))
        self.assertEqual(self.catalog.search(scope="upstream", owned=True)["total"], 0)

    def test_ring_override_and_upstream_remain_separate(self):
        local = self.catalog.get("ws2812_ring_8")
        upstream = self.catalog.get("wokwi:wokwi-led-ring")
        self.assertEqual(local["profile"]["simulation"]["proposed_attrs"], {"pixels": "8"})
        self.assertEqual(local["upstream_definition"], upstream["upstream_definition"])
        self.assertIsNone(upstream["profile"])

    def test_no_network_and_no_catalog_writes(self):
        def hashes():
            return {p.relative_to(DEFAULT_KNOWLEDGE_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in DEFAULT_KNOWLEDGE_ROOT.rglob("*") if p.is_file()}
        before = hashes()
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            self.catalog.search(scope="all", limit=30)
            for item in self.catalog.search(limit=30)["items"]:
                self.catalog.get(item["id"], include_shared=True, include_examples=True)
        self.assertEqual(before, hashes())

    def test_tool_arguments_are_strict_and_do_not_echo_unknown_inputs(self):
        for args in ({"limit": 0}, {"limit": "3"}, {"root": "SENTINEL_DO_NOT_ECHO"}, {"offset": -1}):
            with self.subTest(args=args):
                result = search_hardware.invoke(args)
                result = json.loads(result) if isinstance(result, str) else result
                self.assertEqual(result["error_code"], "INVALID_ARGUMENT")
                self.assertNotIn("SENTINEL_DO_NOT_ECHO", json.dumps(result))
        result = get_hardware_info.invoke({"hardware_id": "../DS_Api.txt"})
        self.assertEqual(json.loads(result)["error_code"], "INVALID_ARGUMENT")


class DamagedCatalogTests(unittest.TestCase):
    """Retain fake test evidence beneath project temp; never touch actual secrets."""

    def setUp(self):
        temp_base = DEFAULT_KNOWLEDGE_ROOT.parents[1] / "temp" / "hardware-catalog-tests"
        temp_base.mkdir(parents=True, exist_ok=True)
        self.case = Path(tempfile.mkdtemp(prefix="case-", dir=temp_base))
        self.root = self.case / "knowledge"
        self.root.mkdir()
        full_index = json.loads((DEFAULT_KNOWLEDGE_ROOT / "catalog.json").read_text(encoding="utf-8"))
        entry = next(x for x in full_index["records"] if x["id"] == "dht22_red_module")
        upstream_ref = full_index["upstream_parts"]["wokwi-dht22"]
        self.index = {"schema_version": 2, "records": [entry], "upstream_parts": {"wokwi-dht22": upstream_ref}}
        for ref in (entry["path"], upstream_ref):
            dest = self.root / ref
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DEFAULT_KNOWLEDGE_ROOT / ref, dest)
        self.record_path = self.root / entry["path"]
        self.write_index()
        self.catalog = KnowledgeCatalog(self.root)

    def write_index(self):
        (self.root / "catalog.json").write_text(json.dumps(self.index), encoding="utf-8")

    def edit_record(self, fn):
        record = json.loads(self.record_path.read_text(encoding="utf-8"))
        fn(record)
        self.record_path.write_text(json.dumps(record), encoding="utf-8")

    def assert_error(self, code, operation=None):
        with self.assertRaises(CatalogError) as caught:
            (operation or (lambda: self.catalog.get("dht22_red_module")))()
        self.assertEqual(caught.exception.code, code)

    def test_path_traversal_in_index(self):
        self.index["records"][0]["path"] = "owned/../../private.json"
        self.write_index()
        self.assert_error("UNSAFE_REFERENCE")

    def test_absolute_path_in_index(self):
        self.index["records"][0]["path"] = "D:/outside.json"
        self.write_index()
        self.assert_error("UNSAFE_REFERENCE")

    def test_missing_source_is_not_not_found_hardware(self):
        self.index["upstream_parts"]["wokwi-dht22"] = "upstream/wokwi-diagram-lint/parts/missing.json"
        self.write_index()
        self.assert_error("MISSING_REFERENCE")

    def test_malformed_and_duplicate_json_are_rejected(self):
        for text in ('{"invalid":', '{"schema_version":1,"schema_version":2}'):
            self.record_path.write_text(text, encoding="utf-8")
            self.assert_error("INVALID_JSON")

    def test_unsupported_record_schema(self):
        self.edit_record(lambda r: r.update(schema_version=99))
        self.assert_error("UNSUPPORTED_SCHEMA")

    def test_duplicate_hardware_ids(self):
        self.index["records"].append(self.index["records"][0].copy())
        self.write_index()
        self.assert_error("INVALID_CATALOG")

    def test_pin_mapping_error(self):
        self.edit_record(lambda r: r["simulation"]["logical_signal_to_model_pin"].update(DATA="FAKE_PIN"))
        self.assert_error("INVALID_CATALOG")

    def test_new_profile_missing_generation_status(self):
        self.edit_record(lambda r: r.pop("generation_profile"))
        self.assert_error("INVALID_CATALOG")

    def test_oversize_record(self):
        self.record_path.write_text(" " * (MAX_FILE_BYTES + 1), encoding="utf-8")
        self.assert_error("SOURCE_TOO_LARGE")

    def test_example_reference_cannot_escape_to_secret(self):
        (self.case / "fake-secret.txt").write_text("FAKE_TEST_SENTINEL", encoding="utf-8")
        self.edit_record(lambda r: r["driver_profile"].update(example_refs=["../fake-secret.txt"]))
        self.assert_error("UNSAFE_REFERENCE", lambda: self.catalog.get("dht22_red_module", include_examples=True))

    def test_symbolic_link_is_rejected_before_read(self):
        outside = self.case / "outside.json"
        outside.write_text('{"secret":"FAKE_TEST_SENTINEL"}', encoding="utf-8")
        link = self.root / "owned" / "link.json"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"OS does not permit test symlink: {type(exc).__name__}")
        self.index["records"][0]["path"] = "owned/link.json"
        self.write_index()
        self.assert_error("UNSAFE_REFERENCE")

    def test_tool_exposes_safe_error_without_path(self):
        self.index["records"][0]["path"] = "owned/../../fake-secret.json"
        self.write_index()
        with patch("hardware_claw.tools.hardware_catalog.KnowledgeCatalog", return_value=self.catalog):
            result = get_hardware_info.invoke({"hardware_id": "dht22_red_module"})
        self.assertEqual(result["error_code"], "UNSAFE_REFERENCE")
        self.assertNotIn(str(self.case), json.dumps(result))


class QueryModel(BaseChatModel):
    _step: int = PrivateAttr(default=0)

    @property
    def _llm_type(self): return "offline-hardware-query-test"

    def bind_tools(self, tools, **kwargs): return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._step += 1
        if self._step == 1:
            message = AIMessage(content="", tool_calls=[{"name": "search_hardware", "args": {"query": "温湿度"}, "id": "search-1", "type": "tool_call"}])
        elif self._step == 2:
            feedback = json.loads(next(m.content for m in reversed(messages) if isinstance(m, ToolMessage)))
            hardware_id = feedback["data"]["items"][0]["id"]
            message = AIMessage(content="", tool_calls=[{"name": "get_hardware_info", "args": {"hardware_id": hardware_id}, "id": "detail-1", "type": "tool_call"}])
        else:
            feedback = json.loads(next(m.content for m in reversed(messages) if isinstance(m, ToolMessage)))
            assert feedback["data"]["profile"]["driver_profile"]["dependencies"][0]["version"] == "1.19"
            assert feedback["data"]["summary"]["simulation_test"] == "not_run"
            message = AIMessage(content="DHT22资料已读，仿真尚未运行。")
        return ChatResult(generations=[ChatGeneration(message=message)])


class QueryLoopTests(unittest.TestCase):
    def test_langchain_returns_real_tool_results_to_offline_model(self):
        agent = create_agent(model=QueryModel(), tools=HARDWARE_TOOLS)
        result = agent.invoke({"messages": [("user", "查温湿度传感器")]}, {"recursion_limit": 10})
        self.assertEqual(sum(isinstance(m, ToolMessage) for m in result["messages"]), 2)
        self.assertEqual(result["messages"][-1].content, "DHT22资料已读，仿真尚未运行。")


if __name__ == "__main__":
    unittest.main()
