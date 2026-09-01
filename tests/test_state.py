import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

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
            self.assertTrue(first["pr_agent_bifrost_virtual_key"].startswith("sk-bf-pr-"))
            self.assertRegex(first["pr_agent_webhook_secret"], r"^[0-9a-f]{64}$")
            self.assertRegex(first["agent_console_password_salt"], r"^[0-9a-f]{16}$")

    def test_rotation_replaces_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / ".state", Runner())
            first = state.ensure_secrets()
            second = state.ensure_secrets(rotate=True)
            self.assertNotEqual(first["bifrost_virtual_key"], second["bifrost_virtual_key"])
            self.assertNotEqual(
                first["pr_agent_webhook_secret"], second["pr_agent_webhook_secret"]
            )

    def test_generated_git_signing_key_is_stable_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Mock()
            fingerprint = "A" * 40
            runner.run.side_effect = (
                subprocess.CompletedProcess(
                    [], 0, f"[GNUPG:] KEY_CREATED P {fingerprint}\n", ""
                ),
                subprocess.CompletedProcess(
                    [], 0, "-----BEGIN PGP PRIVATE KEY BLOCK-----\nprivate\n", ""
                ),
                subprocess.CompletedProcess(
                    [], 0, "-----BEGIN PGP PUBLIC KEY BLOCK-----\npublic\n", ""
                ),
            )
            state = State(Path(directory) / ".state", runner)

            first = state.ensure_git_signing_key("Agent User", "agent@example.test")
            second = state.ensure_git_signing_key("Agent User", "agent@example.test")

            self.assertEqual(first, second)
            self.assertEqual(fingerprint, first["fingerprint"])
            self.assertEqual(3, runner.run.call_count)
            self.assertEqual(
                os.stat(state.git_signing_private_key_path).st_mode & 0o777,
                0o600,
            )
            generated_command = runner.run.call_args_list[0].args[0]
            self.assertIn("Agent User <agent@example.test>", generated_command)
            self.assertIn("ed25519", generated_command)
            self.assertIn("sign", generated_command)

    def test_clear_generated_state_removes_provisioning_files(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / ".state", Runner())
            state.ensure_secrets()
            state.write_json(state.versions_path, {"test": "version"})
            state.write_json(state.metadata_path, {"address": "192.0.2.1"})
            state.git_signing_private_key_path.write_text("private", encoding="utf-8")
            state.git_signing_public_key_path.write_text("public", encoding="utf-8")
            state.git_signing_fingerprint_path.write_text("fingerprint", encoding="utf-8")
            state.clear_generated_state()
            self.assertFalse(state.secrets_path.exists())
            self.assertFalse(state.versions_path.exists())
            self.assertFalse(state.metadata_path.exists())
            self.assertFalse(state.git_signing_private_key_path.exists())
            self.assertFalse(state.git_signing_public_key_path.exists())
            self.assertFalse(state.git_signing_fingerprint_path.exists())


if __name__ == "__main__":
    unittest.main()
