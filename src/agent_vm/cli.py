from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from .ansible import Ansible
from .config import Config
from .doctor import (
    _kandev_pi_capabilities,
    _kandev_workflow_sync_command,
    _kandev_workflow_sync_status,
    print_checks,
    run_doctor,
)
from .errors import AgentVMError
from .host import validate_host
from .process import Runner
from .releases import resolve_all
from .state import State
from .vm import VM, prepare_cloud_image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "agent-vm.yaml"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="agent-vm", description="Provision the private agent development VM")
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument("--verbose", action="store_true")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("create", help="create and provision a new VM")
    sub.add_parser("provision", help="idempotently apply recorded versions")
    sub.add_parser("configure-netbird", help="enroll or repair the NetBird client")
    github = sub.add_parser(
        "configure-github", help="show, apply, and test VM GitHub authentication and signing keys"
    )
    github.add_argument("--show-only", action="store_true")
    sub.add_parser("configure-cliproxy", help="perform interactive Codex OAuth login")
    sub.add_parser("configure-models", help="synchronize Pi models directly from CLIProxyAPI")
    sub.add_parser(
        "configure-kandev-workflow",
        help="force and validate the configured Kandev Workflow Sync",
    )
    doctor = sub.add_parser("doctor", help="check infrastructure and integrations")
    doctor.add_argument("--json", action="store_true", dest="json_output")
    doctor.add_argument(
        "--live-model-test",
        action="store_true",
        help="send one small, potentially billable Pi model request",
    )
    sub.add_parser("status", help="show VM and resolved-version status")
    sub.add_parser("update", help="resolve and install latest stable releases")
    rebuild = sub.add_parser("rebuild", help="destroy and recreate the VM")
    rebuild.add_argument("--yes-destroy", action="store_true", help="acknowledge permanent guest-data deletion")
    return result


class App:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.runner = Runner(verbose=args.verbose)
        self.config = Config.load(args.config.resolve(), ROOT)
        self.state = State(self.config.state_dir, self.runner)
        self.vm = VM(self.config, self.state, self.runner)
        self.ansible = Ansible(ROOT, self.config, self.state, self.runner)

    def _existing(self) -> tuple[str, Path, dict, dict]:
        validate_host(self.config, check_resources=False)
        if not self.vm.exists():
            raise AgentVMError("VM does not exist; run create")
        private_key = self.state.directory / "admin_ed25519"
        if not private_key.exists():
            raise AgentVMError("Administrative SSH key is missing; rebuild is required")
        secrets = self.state.ensure_secrets()
        self._ensure_git_signing_key()
        versions = self.state.versions()
        if not versions:
            raise AgentVMError("Resolved version state is missing; run update or rebuild")
        address = self.vm.ip_address()
        metadata = self.state.metadata()
        if not self.vm.known_hosts.exists() or metadata.get("address") != address:
            self.vm.pin_host_key(address)
            metadata["address"] = address
            self.state.write_json(self.state.metadata_path, metadata)
        return address, private_key, secrets, versions

    def _ensure_git_signing_key(self, *, rotate: bool = False) -> dict[str, str] | None:
        if not self.config.git_sign_commits:
            return None
        return self.state.ensure_git_signing_key(
            self.config.git_identity["name"],
            self.config.git_identity["email"],
            rotate=rotate,
        )

    def _provision(self, *, versions: dict | None = None, tags: list[str] | None = None, perform_update: bool = False) -> None:
        address, private_key, secrets, recorded = self._existing()
        selected = versions or recorded
        inventory, variables = self.ansible.write_inputs(
            address,
            private_key,
            secrets,
            selected,
            self.config.netbird,
            perform_update=perform_update,
        )
        self.ansible.run(inventory, variables, tags=tags)
        if tags is None:
            selected = {key: value for key, value in selected.items() if key not in {"bifrost", "pr_agent"}}
            self.state.write_json(self.state.versions_path, selected)

    def create(self, *, rotate: bool = False) -> None:
        validate_host(self.config)
        if self.vm.exists():
            raise AgentVMError(f"VM {self.vm.name!r} already exists; use provision or rebuild")
        self.state.ensure()
        if rotate:
            self.state.clear_generated_state()
        admin_key = self.state.ensure_ssh_key("admin_ed25519", rotate=rotate)
        self.state.ensure_ssh_key("github_ed25519", rotate=rotate)
        self._ensure_git_signing_key(rotate=rotate)
        secrets = self.state.ensure_secrets(rotate=rotate)
        versions = resolve_all(self.config)
        self.state.write_json(self.state.versions_path, versions)
        base_image = prepare_cloud_image(self.config)
        public_key = Path(str(admin_key) + ".pub").read_text(encoding="utf-8")
        self.vm.create(base_image, public_key)
        address = self.vm.ip_address()
        self.vm.pin_host_key(address)
        self.vm.wait_for_ssh(address, admin_key)
        self.state.write_json(self.state.metadata_path, {"address": address, "vm_name": self.vm.name})
        inventory, variables = self.ansible.write_inputs(
            address, admin_key, secrets, versions, self.config.netbird
        )
        self.ansible.run(inventory, variables)
        print(f"Created {self.vm.name} at {address}")
        print("Next: run configure-github --show-only and register both public keys")

    def provision(self) -> None:
        self._provision()

    def configure_netbird(self) -> None:
        self._provision(tags=["netbird"])

    def configure_github(self) -> None:
        public_key = Path(str(self.state.directory / "github_ed25519") + ".pub")
        print("Register this SSH authentication key at https://github.com/settings/keys:\n")
        print(public_key.read_text(encoding="utf-8").strip())
        signing_key = self._ensure_git_signing_key()
        if signing_key:
            print("\nRegister this GPG key at https://github.com/settings/gpg/new:\n")
            print(signing_key["public_key"].strip())
        if self.args.show_only:
            return
        self._provision(tags=["git"])
        address, private_key, _, _ = self._existing()
        result = self.runner.run(self._ssh_args(address, private_key) + ["ssh -o BatchMode=yes -T git@github.com 2>&1"], check=False, capture=True)
        text = (result.stdout + result.stderr).strip()
        if "successfully authenticated" not in text:
            raise AgentVMError("GitHub did not accept the VM key; register it and retry configure-github")
        print(text)

    def configure_cliproxy(self) -> None:
        address, private_key, _, _ = self._existing()
        guest_user = shlex.quote(self.config.guest["user"])
        remote = (
            "set -eu; "
            "sudo systemctl stop cliproxyapi; "
            "cleanup() { trap - EXIT; sudo systemctl start cliproxyapi; }; "
            "trap cleanup EXIT; "
            f"sudo -u {guest_user} sh -lc "
            "'cd ~/.config/cliproxyapi && exec /usr/local/bin/cli-proxy-api --codex-login --no-browser'"
        )
        command = self._ssh_args(address, private_key)
        command[1:1] = ["-L", "1455:127.0.0.1:1455"]
        command.insert(1, "-tt")
        self.runner.run(command + [remote])
        print("Codex OAuth completed; run doctor to verify the model catalog")

    def configure_models(self) -> None:
        self._provision(tags=["model-sync"])
        address, private_key, _, _ = self._existing()
        guest_home = f"/home/{self.config.guest['user']}"
        sync_command = shlex.join([
            "/usr/local/bin/agent-vm-sync-pi-models",
            "--base-url", f"http://127.0.0.1:{self.config.ports['cliproxyapi']}",
            "--config-path", f"{guest_home}/.config/cliproxyapi/config.yaml",
            "--models-path", f"{guest_home}/.pi/agent/models.json",
            "--settings-path", f"{guest_home}/.pi/agent/settings.json",
            "--preferred", self.config.services["pi"]["default_model"],
        ])
        synced = self.runner.run(
            self._ssh_args(address, private_key) + [sync_command],
            capture=True,
        )
        print(synced.stdout.strip())
        refreshed = self.runner.run(
            self._ssh_args(address, private_key) + [
                "curl -fsS --max-time 60 "
                f"'http://127.0.0.1:{self.config.ports['kandev']}/api/v1/agent-models/pi-acp?refresh=true'"
            ],
            check=False,
            capture=True,
        )
        kandev_ready, kandev_detail = _kandev_pi_capabilities(refreshed.stdout)
        if refreshed.returncode != 0 or not kandev_ready:
            raise AgentVMError("Kandev did not refresh the synchronized Pi model catalog")
        print(kandev_detail)
        self._configure_kandev_runtime(address, private_key)
        print("Pi is configured to use CLIProxyAPI directly.")

    def _configure_kandev_runtime(self, address: str, private_key: Path) -> None:
        configured = self.runner.run(
            self._ssh_args(address, private_key) + [shlex.join([
                "/usr/local/bin/agent-vm-configure-kandev",
                "--base-url", f"http://127.0.0.1:{self.config.ports['kandev']}",
                "--config", "/etc/agent-vm/kandev.json",
            ])], capture=True,
        )
        print(configured.stdout.strip())

    def configure_kandev_workflow(self) -> None:
        if not self.config.kandev_workflow_sync:
            raise AgentVMError(
                "Kandev Workflow Sync is disabled in services.kandev.workflow_sync"
            )
        self._provision(tags=["kandev-workflow"])
        address, private_key, _, _ = self._existing()
        result = self.runner.run(
            self._ssh_args(address, private_key)
            + [_kandev_workflow_sync_command(self.config, mode="sync")],
            check=False,
            capture=True,
        )
        status, detail = _kandev_workflow_sync_status(result.stdout)
        if result.returncode != 0 or status != "ready":
            raise AgentVMError(f"Kandev Workflow Sync failed: {detail}")
        print(f"Kandev Workflow Sync is ready: {detail}")
        self._configure_kandev_runtime(address, private_key)

    def doctor(self) -> None:
        address, _, _, _ = self._existing()
        healthy = print_checks(
            run_doctor(
                self.runner,
                self.config,
                self.state,
                address,
                live_model_test=self.args.live_model_test,
            ),
            json_output=self.args.json_output,
        )
        if not healthy:
            raise AgentVMError("One or more infrastructure checks failed")

    def status(self) -> None:
        output = {"vm": self.vm.name, "state": self.vm.state_text(), "versions": self.state.versions()}
        if self.vm.exists():
            try:
                output["address"] = self.vm.ip_address(timeout=15)
            except AgentVMError:
                output["address"] = None
        print(json.dumps(output, indent=2, sort_keys=True))

    def update(self) -> None:
        versions = resolve_all(self.config)
        self._provision(versions=versions, perform_update=True)
        self.state.write_json(self.state.versions_path, versions)
        print("Updated all components to their latest stable releases")

    def rebuild(self) -> None:
        if not self.args.yes_destroy:
            raise AgentVMError("rebuild permanently deletes the guest; repeat with --yes-destroy")
        self.vm.destroy()
        self.create(rotate=True)
        print("Rebuild complete; the previous guest data and generated identities are not recoverable")

    def _ssh_args(self, address: str, private_key: Path) -> list[str]:
        return [
            "ssh", "-F", "/dev/null", "-i", str(private_key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", f"UserKnownHostsFile={self.state.directory / 'known_hosts'}",
            "-o", "StrictHostKeyChecking=yes", f"{self.config.guest['user']}@{address}",
        ]


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        app = App(args)
        getattr(app, args.command.replace("-", "_"))()
        return 0
    except AgentVMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
