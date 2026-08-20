from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from .errors import AgentVMError
from .process import Runner


class State:
    def __init__(self, directory: Path, runner: Runner):
        self.directory = directory
        self.runner = runner
        self.secrets_path = directory / "secrets.json"
        self.versions_path = directory / "versions.json"
        self.metadata_path = directory / "metadata.json"

    def ensure(self) -> None:
        created = not self.directory.exists()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if created:
            os.chmod(self.directory, 0o700)
            return
        try:
            os.getxattr(self.directory, "system.posix_acl_access")
        except OSError:
            os.chmod(self.directory, 0o700)

    def clear_generated_state(self) -> None:
        """Remove stale identities and provisioning inputs before a rebuild."""
        for name in (
            "admin_ed25519",
            "admin_ed25519.pub",
            "github_ed25519",
            "github_ed25519.pub",
            "known_hosts",
            "secrets.json",
            "versions.json",
            "metadata.json",
            "inventory.ini",
            "ansible-vars.json",
            "user-data",
            "meta-data",
        ):
            (self.directory / name).unlink(missing_ok=True)

    def read_json(self, path: Path, default=None):
        if not path.exists():
            return {} if default is None else default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise AgentVMError(f"Cannot read state file {path}: {exc}") from exc

    def write_json(self, path: Path, value: dict, *, secret: bool = False) -> None:
        self.ensure()
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600 if secret else 0o644)
        temporary.replace(path)

    def ensure_secrets(self, *, rotate: bool = False) -> dict:
        self.ensure()
        values = {} if rotate else self.read_json(self.secrets_path)
        defaults = {
            "agent_console_password_salt": secrets.token_hex(8),
            "cliproxy_api_key": "sk-cpa-" + secrets.token_urlsafe(32),
            "cliproxy_management_secret": secrets.token_urlsafe(36),
            "bifrost_admin_username": "admin",
            "bifrost_admin_password": secrets.token_urlsafe(32),
            "bifrost_encryption_key": secrets.token_urlsafe(48),
            "bifrost_virtual_key": "sk-bf-" + secrets.token_urlsafe(32),
        }
        for key, value in defaults.items():
            values.setdefault(key, value)
        self.write_json(self.secrets_path, values, secret=True)
        return values

    def ensure_ssh_key(self, name: str, *, rotate: bool = False) -> Path:
        self.ensure()
        private_key = self.directory / name
        public_key = Path(str(private_key) + ".pub")
        if rotate:
            private_key.unlink(missing_ok=True)
            public_key.unlink(missing_ok=True)
        if not private_key.exists():
            self.runner.run([
                "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"agent-vm-{name}", "-f", str(private_key)
            ])
        if not self.runner.dry_run:
            os.chmod(private_key, 0o600)
            os.chmod(public_key, 0o644)
        return private_key

    def versions(self) -> dict:
        return self.read_json(self.versions_path)

    def metadata(self) -> dict:
        return self.read_json(self.metadata_path)
