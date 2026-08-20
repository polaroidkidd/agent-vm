import os
import tempfile
import unittest
from pathlib import Path

from agent_vm.process import Runner
from agent_vm.state import State


class StateTests(unittest.TestCase):
    def test_generated_secrets_are_stable_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / ".state", Runner())
            first = state.ensure_secrets()
            second = state.ensure_secrets()
            self.assertEqual(first, second)
            self.assertEqual(os.stat(state.secrets_path).st_mode & 0o777, 0o600)
            self.assertTrue(first["bifrost_virtual_key"].startswith("sk-bf-"))
            self.assertRegex(first["agent_console_password_salt"], r"^[0-9a-f]{16}$")

    def test_rotation_replaces_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / ".state", Runner())
            first = state.ensure_secrets()
            second = state.ensure_secrets(rotate=True)
            self.assertNotEqual(first["bifrost_virtual_key"], second["bifrost_virtual_key"])

    def test_clear_generated_state_removes_provisioning_files(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / ".state", Runner())
            state.ensure_secrets()
            state.write_json(state.versions_path, {"test": "version"})
            state.write_json(state.metadata_path, {"address": "192.0.2.1"})
            state.clear_generated_state()
            self.assertFalse(state.secrets_path.exists())
            self.assertFalse(state.versions_path.exists())
            self.assertFalse(state.metadata_path.exists())


if __name__ == "__main__":
    unittest.main()
