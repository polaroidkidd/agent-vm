import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from agent_vm.ansible import Ansible
from agent_vm.config import Config
from agent_vm.state import State

from test_config import VALID


class AnsibleTests(unittest.TestCase):
    def test_console_agent_password_hash_is_stable_and_secret(self):
        config = Config(path=Path("config.yaml"), root=Path("/tmp"), raw=VALID)
        runner = Mock()
        runner.run.return_value = subprocess.CompletedProcess([], 0, "$6$salt$hash\n", "")
        ansible = Ansible(Path("/tmp"), config, State(Path("/tmp/state"), runner), runner)

        result = ansible._console_agent_password_hash(
            {"agent_console_password_salt": "0123456789abcdef"}
        )

        self.assertEqual(result, "$6$salt$hash")
        runner.run.assert_called_once_with(
            ["openssl", "passwd", "-6", "-salt", "0123456789abcdef", "-stdin"],
            capture=True,
            sensitive=True,
            stdin="agent-console-secret\n",
        )

    def test_write_inputs_passes_git_commit_signing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = State(root / "state", Mock())
            state.ensure()
            (state.directory / "github_ed25519").write_text("private-key\n", encoding="utf-8")
            (state.directory / "github_ed25519.pub").write_text("public-key\n", encoding="utf-8")
            state.git_signing_private_key_path.write_text(
                "-----BEGIN PGP PRIVATE KEY BLOCK-----\nprivate\n", encoding="utf-8"
            )
            state.git_signing_public_key_path.write_text(
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\npublic\n", encoding="utf-8"
            )
            state.git_signing_fingerprint_path.write_text("A" * 40 + "\n", encoding="utf-8")
            runner = Mock()
            runner.run.return_value = subprocess.CompletedProcess([], 0, "$6$salt$hash\n", "")
            config = Config(path=root / "config.yaml", root=root, raw=VALID)
            ansible = Ansible(root, config, state, runner)

            _, variables = ansible.write_inputs(
                "192.0.2.1",
                root / "admin_ed25519",
                {"agent_console_password_salt": "0123456789abcdef"},
                {},
                {},
            )

            values = json.loads(variables.read_text(encoding="utf-8"))
            self.assertTrue(values["git_sign_commits"])
            self.assertEqual(
                values["git_identity"],
                {"name": "Agent User", "email": "agent@example.test"},
            )
            self.assertIn("BEGIN PGP PRIVATE KEY BLOCK", values["git_signing_private_key"])
            self.assertEqual("A" * 40, values["git_signing_fingerprint"])


if __name__ == "__main__":
    unittest.main()
