import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent_vm.config import Config
from agent_vm.process import Runner
from agent_vm.state import State
from agent_vm.vm import VM

from test_config import VALID


class VMTests(unittest.TestCase):
    def test_console_root_password_is_hashed_through_stdin(self):
        config = Config(path=Path("config.yaml"), root=Path("/tmp"), raw=VALID)
        runner = Mock()
        runner.run.return_value = subprocess.CompletedProcess([], 0, "$6$hash\n", "")
        vm = VM(config, State(Path("/tmp/state"), runner), runner)

        self.assertEqual(vm._console_root_password_hash(), "$6$hash")
        runner.run.assert_called_once_with(
            ["openssl", "passwd", "-6", "-stdin"],
            capture=True,
            sensitive=True,
            stdin="console-secret\n",
        )

    def test_cloud_init_disables_password_ssh_but_sets_console_root_password(self):
        config = Config(path=Path("config.yaml"), root=Path("/tmp"), raw=VALID)
        vm = VM(config, State(Path("/tmp/state"), Runner(dry_run=True)), Runner(dry_run=True))
        data = vm._user_data("ssh-ed25519 test", "$6$hash")
        self.assertIn("ssh_pwauth: false", data)
        self.assertIn("disable_root: true", data)
        self.assertIn("name: root", data)
        self.assertIn("password: $6$hash", data)
        self.assertIn("ssh-ed25519 test", data)

    def test_host_key_scan_retries_while_ssh_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Config(path=root / "config.yaml", root=root, raw=VALID)
            state = State(root / ".state", Runner(dry_run=True))
            state.ensure()
            runner = Mock()
            runner.run.side_effect = [
                subprocess.CompletedProcess([], 1, "", "connection refused"),
                subprocess.CompletedProcess([], 0, "host ssh-ed25519 key\n", ""),
            ]
            vm = VM(config, state, runner)
            with patch("agent_vm.vm.time.sleep"):
                vm.pin_host_key("192.0.2.10")
            self.assertEqual(vm.known_hosts.read_text(encoding="utf-8"), "host ssh-ed25519 key\n")
            self.assertEqual(runner.run.call_count, 2)

    def test_ip_address_ignores_guest_loopback(self):
        root = Path("/tmp")
        config = Config(path=root / "config.yaml", root=root, raw=VALID)
        runner = Mock()
        runner.run.return_value = subprocess.CompletedProcess(
            [],
            0,
            """ Name       MAC address          Protocol     Address
-------------------------------------------------------------------------------
 lo         00:00:00:00:00:00    ipv4         127.0.0.1/8
 enp1s0     52:54:00:12:34:56    ipv4         192.168.122.42/24
""",
            "",
        )
        vm = VM(config, State(root / "state", runner), runner)
        self.assertEqual(vm.ip_address(), "192.168.122.42")


if __name__ == "__main__":
    unittest.main()
