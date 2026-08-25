from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Config
from .process import Runner
from .state import State


class Ansible:
    def __init__(self, root: Path, config: Config, state: State, runner: Runner):
        self.root = root
        self.config = config
        self.state = state
        self.runner = runner

    def _console_agent_password_hash(self, secrets: dict) -> str:
        return self.runner.run(
            [
                "openssl",
                "passwd",
                "-6",
                "-salt",
                secrets["agent_console_password_salt"],
                "-stdin",
            ],
            capture=True,
            sensitive=True,
            stdin=self.config.guest["console_agent_password"] + "\n",
        ).stdout.strip()

    def write_inputs(
        self,
        address: str,
        private_key: Path,
        secrets: dict,
        versions: dict,
        netbird: dict,
        *,
        perform_update: bool = False,
    ) -> tuple[Path, Path]:
        self.state.ensure()
        inventory = self.state.directory / "inventory.ini"
        variables = self.state.directory / "ansible-vars.json"
        ssh_args = f"-o UserKnownHostsFile={self.state.directory / 'known_hosts'} -o StrictHostKeyChecking=yes"
        inventory.write_text(
            "[agent_vm]\n"
            f"{self.config.vm['name']} ansible_host={address} ansible_user={self.config.guest['user']} "
            f"ansible_ssh_private_key_file={private_key} ansible_python_interpreter=/usr/bin/python3 "
            f"ansible_ssh_common_args='{ssh_args}'\n",
            encoding="utf-8",
        )
        values = {
            "agent_user": self.config.guest["user"],
            "agent_console_password_hash": self._console_agent_password_hash(secrets),
            "workspace_dir": self.config.guest["workspace_dir"],
            "node_major": self.config.services["node_major"],
            "ports": self.config.ports,
            "services": self.config.services,
            "pi_skills": self.config.pi_skills,
            "versions": versions,
            "generated_secrets": secrets,
            "stripe_api_key": self.config.stripe_api_key,
            "github_public_key": Path(str(self.state.directory / "github_ed25519") + ".pub").read_text(encoding="utf-8").strip(),
            "github_private_key": (self.state.directory / "github_ed25519").read_text(encoding="utf-8"),
            "netbird": netbird,
            "perform_update": perform_update,
        }
        variables.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
        os.chmod(inventory, 0o600)
        os.chmod(variables, 0o600)
        return inventory, variables

    def run(self, inventory: Path, variables: Path, *, tags: list[str] | None = None) -> None:
        command = [
            "ansible-playbook", "-i", str(inventory), str(self.root / "ansible" / "playbook.yml"),
            "--extra-vars", f"@{variables}",
        ]
        if tags:
            command.extend(["--tags", ",".join(tags)])
        self.runner.run(
            command,
            sensitive=True,
            env={"ANSIBLE_CONFIG": str(self.root / "ansible" / "ansible.cfg")},
        )
