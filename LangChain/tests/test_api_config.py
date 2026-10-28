"""Mock-only configuration tests; never read real credentials."""
import unittest
from unittest.mock import patch
from hardware_claw import api_config


class ApiConfigTests(unittest.TestCase):
    def test_key_stays_in_project_root_after_restructure(self):
        from pathlib import Path
        self.assertEqual(api_config.KEY_FILE, Path(__file__).resolve().parents[1] / "DS_Api.txt")

    def test_file_preferred_and_trimmed(self):
        with patch.object(api_config, "KEY_FILE") as path, patch.dict(api_config.os.environ, {"DEEPSEEK_API_KEY": "other"}):
            path.exists.return_value = True
            path.read_text.return_value = "  test-key\n"
            self.assertEqual(api_config.load_api_key(), "test-key")
            path.read_text.assert_called_once_with(encoding="utf-8-sig")

    def test_invalid_file_does_not_fall_back(self):
        for content in ("", "first\nsecond", "label: value"):
            with self.subTest(content=content), patch.object(api_config, "KEY_FILE") as path:
                path.exists.return_value = True
                path.read_text.return_value = content
                with self.assertRaises(api_config.ApiConfigError):
                    api_config.load_api_key()

    def test_environment_fallback(self):
        with patch.object(api_config, "KEY_FILE") as path, patch.dict(api_config.os.environ, {"DEEPSEEK_API_KEY": "env-test"}):
            path.exists.return_value = False
            self.assertEqual(api_config.load_api_key(), "env-test")

    def test_missing(self):
        with patch.object(api_config, "KEY_FILE") as path, patch.dict(api_config.os.environ, {}, clear=True):
            path.exists.return_value = False
            with self.assertRaises(api_config.ApiConfigError):
                api_config.load_api_key()

    def test_model_receives_configuration(self):
        with patch.object(api_config, "load_api_key", return_value="fake-test"), patch.object(api_config, "ChatDeepSeek") as constructor:
            api_config.create_model()
            self.assertEqual(constructor.call_args.kwargs["api_key"], "fake-test")
            self.assertEqual(constructor.call_args.kwargs["api_base"], api_config.BASE_URL)
            self.assertEqual(constructor.call_args.kwargs["max_tokens"], api_config.limits.QUERY_OUTPUT_TOKENS)
            self.assertEqual(constructor.call_args.kwargs["timeout"], api_config.limits.API_TIMEOUT_SECONDS)
            api_config.create_model(max_tokens=api_config.limits.PROJECT_OUTPUT_TOKENS)
            self.assertEqual(constructor.call_args.kwargs["max_tokens"], api_config.limits.PROJECT_OUTPUT_TOKENS)


if __name__ == "__main__":
    unittest.main()
