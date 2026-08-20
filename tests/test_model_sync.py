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
                    {"id": "cliproxy/gpt-5.6-terra"},
                    {"id": "cliproxy/gpt-5.6-sol"},
                    {"id": "cliproxy/gpt-5.6-luna"},
                    {"id": "cliproxy/codex-auto-review"},
                ]
            }

            ids, default = MODULE.update_pi_files(catalog, models, settings, "gpt-5.6-sol")

            self.assertEqual(len(ids), 4)
            self.assertEqual(default, "cliproxy/gpt-5.6-sol")
            written_models = json.loads(models.read_text())
            self.assertEqual(
                [entry["id"] for entry in written_models["providers"]["bifrost"]["models"]],
                sorted(ids),
            )
            written_settings = json.loads(settings.read_text())
            self.assertEqual(written_settings["defaultProvider"], "bifrost")
            self.assertEqual(written_settings["defaultModel"], default)
            self.assertEqual(written_settings["defaultThinkingLevel"], "high")
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


if __name__ == "__main__":
    unittest.main()
