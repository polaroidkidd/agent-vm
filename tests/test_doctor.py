import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_vm.doctor import (
    _has_models,
    _kandev_pi_capabilities,
    _kandev_pi_discovery,
    run_doctor,
)


class DoctorRunner:
    def __init__(self, *, docker_access: bool = True):
        self.docker_access = docker_access

    def run(self, args, **_kwargs):
        command = list(args)[-1]
        if command == "docker version --format '{{.Server.Version}}'":
            return subprocess.CompletedProcess(
                args,
                0 if self.docker_access else 1,
                "29.1.3\n" if self.docker_access else "",
                "" if self.docker_access else "permission denied",
            )
        if command.startswith("systemctl is-active "):
            return subprocess.CompletedProcess(args, 0, "active\n", "")
        if command == "sudo netbird status --json":
            return subprocess.CompletedProcess(args, 0, '{"netbirdIp":"100.64.0.1"}', "")
        if command == "ssh -o BatchMode=yes -T git@github.com 2>&1":
            return subprocess.CompletedProcess(args, 1, "successfully authenticated", "")
        if "/api/v1/agents/discovery" in command:
            output = '{"agents":[{"name":"pi-acp","available":true,"matched_path":"/usr/bin/pi"}]}'
            return subprocess.CompletedProcess(args, 0, output, "")
        if "/api/v1/agent-models/pi-acp" in command:
            return subprocess.CompletedProcess(args, 0, '{"status":"ok","models":[{"id":"gpt-test"}]}', "")
        if "/v1/models" in command:
            return subprocess.CompletedProcess(args, 0, '{"data":[{"id":"gpt-test"}]}', "")
        if command == "pi --version 2>&1":
            return subprocess.CompletedProcess(args, 0, "0.84.2\n", "")
        return subprocess.CompletedProcess(args, 0, "ok\n", "")


class DoctorTests(unittest.TestCase):
    def test_doctor_verifies_docker_service_and_agent_access(self):
        runner = DoctorRunner()
        config = SimpleNamespace(
            guest={"user": "agent"},
            ports={"kandev": 38429, "bifrost": 8080, "cliproxyapi": 8317},
        )
        state = SimpleNamespace(directory=Path("/tmp/agent-vm-doctor-test"))

        checks = run_doctor(runner, config, state, "192.0.2.1")
        by_name = {check.name: check for check in checks}

        self.assertEqual("ready", by_name["service:docker"].status)
        self.assertEqual("ready", by_name["integration:docker"].status)
        self.assertEqual("Docker Engine 29.1.3", by_name["integration:docker"].detail)

    def test_doctor_fails_when_agent_cannot_access_docker(self):
        runner = DoctorRunner(docker_access=False)
        config = SimpleNamespace(
            guest={"user": "agent"},
            ports={"kandev": 38429, "bifrost": 8080, "cliproxyapi": 8317},
        )
        state = SimpleNamespace(directory=Path("/tmp/agent-vm-doctor-test"))

        checks = run_doctor(runner, config, state, "192.0.2.1")
        docker = next(check for check in checks if check.name == "integration:docker")

        self.assertEqual("failed", docker.status)
        self.assertEqual("agent cannot access the Docker daemon", docker.detail)

    def test_model_catalog_must_be_nonempty(self):
        self.assertTrue(_has_models('{"data": [{"id": "gpt-test"}]}'))
        self.assertFalse(_has_models('{"data": []}'))
        self.assertFalse(_has_models('{"status": "ok"}'))
        self.assertFalse(_has_models('not json'))

    def test_kandev_pi_capabilities_require_ok_with_models(self):
        ready, detail = _kandev_pi_capabilities(
            '{"status":"ok","models":[{"id":"gpt-test"}]}'
        )
        self.assertTrue(ready)
        self.assertIn("1 model", detail)

        for response in (
            '{"status":"failed","error":"ACP initialize failed"}',
            '{"status":"ok","models":[]}',
            'not json',
        ):
            with self.subTest(response=response):
                self.assertFalse(_kandev_pi_capabilities(response)[0])

    def test_kandev_pi_discovery_requires_available_pi(self):
        ready, detail = _kandev_pi_discovery(
            '{"agents":[{"name":"pi-acp","available":true,"matched_path":"/usr/bin/pi"}]}'
        )
        self.assertTrue(ready)
        self.assertIn("/usr/bin/pi", detail)

        for response in (
            '{"agents":[{"name":"pi-acp","available":false}]}',
            '{"agents":[]}',
            'not json',
        ):
            with self.subTest(response=response):
                self.assertFalse(_kandev_pi_discovery(response)[0])


if __name__ == "__main__":
    unittest.main()
