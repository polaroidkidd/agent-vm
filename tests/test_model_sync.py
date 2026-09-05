import importlib.util
from importlib.machinery import SourceFileLoader
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "ansible" / "files" / "agent-vm-sync-pi-models"
SPEC = importlib.util.spec_from_loader(
    "agent_vm_sync_pi_models",
    SourceFileLoader("agent_vm_sync_pi_models", str(SCRIPT)),
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ModelSyncTests(unittest.TestCase):
    def test_all_live_models_are_written_and_sol_is_the_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models.json"
            settings = root / "settings.json"
            models.write_text(json.dumps({"providers": {"bifrost": {"baseUrl": "http://localhost/v1"}}}))
            settings.write_text(json.dumps({"defaultThinkingLevel": "high"}))
            catalog = {
                "data": [
                    {"id": "gpt-5.6-terra"},
                    {"id": "gpt-5.6-sol"},
                    {"id": "gpt-5.6-luna"},
                    {"id": "codex-auto-review"},
                ]
            }

            ids, default = MODULE.update_pi_files(catalog, models, settings, "gpt-5.6-sol", base_url="http://127.0.0.1:8317", api_key="test-key")

            self.assertEqual(len(ids), 4)
            self.assertEqual(default, "gpt-5.6-sol")
            written_models = json.loads(models.read_text())
            self.assertEqual(
                [entry["id"] for entry in written_models["providers"]["cliproxy"]["models"]],
                sorted(ids),
            )
            written_settings = json.loads(settings.read_text())
            self.assertEqual(written_settings["defaultProvider"], "cliproxy")
            self.assertEqual(written_settings["defaultModel"], default)
            self.assertEqual(written_settings["defaultThinkingLevel"], "high")
            self.assertNotIn("bifrost", written_models["providers"])
            self.assertEqual("test-key", written_models["providers"]["cliproxy"]["apiKey"])
            self.assertEqual("http://127.0.0.1:8317/v1", written_models["providers"]["cliproxy"]["baseUrl"])
            self.assertEqual(models.stat().st_mode & 0o777, 0o600)
            self.assertEqual(settings.stat().st_mode & 0o777, 0o600)

    def test_missing_preference_falls_back_to_sol_not_auto_review(self):
        self.assertEqual(
            MODULE.choose_default(
                ["cliproxy/codex-auto-review", "cliproxy/gpt-5.7-sol"],
                "missing",
            ),
            "cliproxy/gpt-5.7-sol",
        )

    def test_empty_catalog_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty model catalog"):
            MODULE.catalog_ids({"data": []})

    def test_migration_preserves_extensions_and_other_providers_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            models, settings = Path(directory) / "models.json", Path(directory) / "settings.json"
            models.write_text(json.dumps({"providers": {"local": {"baseUrl": "http://local/v1"}, "bifrost": {}}}))
            settings.write_text(json.dumps({"packages": ["npm:pi-mcp-adapter"], "defaultThinkingLevel": "low"}))
            arguments = ({"data": [{"id": "model"}]}, models, settings, "model")
            MODULE.update_pi_files(*arguments, base_url="http://proxy", api_key="rotated-key")
            stamps = [path.stat().st_mtime_ns for path in (models, settings)]
            MODULE.update_pi_files(*arguments, base_url="http://proxy", api_key="rotated-key")
            self.assertEqual(stamps, [path.stat().st_mtime_ns for path in (models, settings)])
            self.assertEqual({"baseUrl": "http://local/v1"}, json.loads(models.read_text())["providers"]["local"])
            self.assertEqual(["npm:pi-mcp-adapter"], json.loads(settings.read_text())["packages"])
            self.assertEqual("low", json.loads(settings.read_text())["defaultThinkingLevel"])


if __name__ == "__main__":
    unittest.main()
