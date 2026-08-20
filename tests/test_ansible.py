import subprocess
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


if __name__ == "__main__":
    unittest.main()
