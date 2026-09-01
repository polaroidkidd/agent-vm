from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
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
        self.git_signing_private_key_path = directory / "git_signing_private.asc"
        self.git_signing_public_key_path = directory / "git_signing_public.asc"
        self.git_signing_fingerprint_path = directory / "git_signing_fingerprint"

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
            "git_signing_private.asc",
            "git_signing_public.asc",
            "git_signing_fingerprint",
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
            "pr_agent_bifrost_virtual_key": "sk-bf-pr-" + secrets.token_urlsafe(32),
            "pr_agent_webhook_secret": secrets.token_hex(32),
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

    def ensure_git_signing_key(
        self, name: str, email: str, *, rotate: bool = False
    ) -> dict[str, str]:
        self.ensure()
        paths = (
            self.git_signing_private_key_path,
            self.git_signing_public_key_path,
            self.git_signing_fingerprint_path,
        )
        if rotate:
            for path in paths:
                path.unlink(missing_ok=True)
        if all(path.exists() for path in paths):
            return self.git_signing_key()
        for path in paths:
            path.unlink(missing_ok=True)

        identity = f"{name} <{email}>"
        with tempfile.TemporaryDirectory(prefix=".gnupg-", dir=self.directory) as directory:
            gpg_home = Path(directory)
            os.chmod(gpg_home, 0o700)
            generated = self.runner.run(
                [
                    "gpg",
                    "--batch",
                    "--homedir",
                    str(gpg_home),
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    "",
                    "--status-fd",
                    "1",
                    "--quick-generate-key",
                    identity,
                    "ed25519",
                    "sign",
                    "0",
                ],
                capture=True,
                sensitive=True,
            )
            match = re.search(
                r"^\[GNUPG:\] KEY_CREATED \S+ ([0-9A-F]{40,64})$",
                generated.stdout,
                re.MULTILINE,
            )
            if not match:
                raise AgentVMError("GnuPG did not report the generated signing key fingerprint")
            fingerprint = match.group(1)
            private_key = self.runner.run(
                [
                    "gpg",
                    "--batch",
                    "--homedir",
                    str(gpg_home),
                    "--armor",
                    "--export-secret-keys",
                    fingerprint,
                ],
                capture=True,
                sensitive=True,
            ).stdout
            public_key = self.runner.run(
                [
                    "gpg",
                    "--batch",
                    "--homedir",
                    str(gpg_home),
                    "--armor",
                    "--export",
                    fingerprint,
                ],
                capture=True,
            ).stdout

        if "-----BEGIN PGP PRIVATE KEY BLOCK-----" not in private_key:
            raise AgentVMError("GnuPG did not export the generated private signing key")
        if "-----BEGIN PGP PUBLIC KEY BLOCK-----" not in public_key:
            raise AgentVMError("GnuPG did not export the generated public signing key")
        self.git_signing_private_key_path.write_text(private_key, encoding="utf-8")
        self.git_signing_public_key_path.write_text(public_key, encoding="utf-8")
        self.git_signing_fingerprint_path.write_text(fingerprint + "\n", encoding="utf-8")
        os.chmod(self.git_signing_private_key_path, 0o600)
        os.chmod(self.git_signing_public_key_path, 0o644)
        os.chmod(self.git_signing_fingerprint_path, 0o644)
        return self.git_signing_key()

    def git_signing_key(self) -> dict[str, str]:
        return {
            "private_key": self.git_signing_private_key_path.read_text(encoding="utf-8"),
            "public_key": self.git_signing_public_key_path.read_text(encoding="utf-8"),
            "fingerprint": self.git_signing_fingerprint_path.read_text(encoding="utf-8").strip(),
        }

    def versions(self) -> dict:
        return self.read_json(self.versions_path)

    def metadata(self) -> dict:
        return self.read_json(self.metadata_path)
