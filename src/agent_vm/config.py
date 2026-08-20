from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .errors import AgentVMError


HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?!-)[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*(?<!-)$")
VM_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$", re.I)


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise AgentVMError(
            "PyYAML is required by create; install python3-yaml for /usr/bin/python3"
        ) from exc
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgentVMError(f"Configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise AgentVMError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AgentVMError("Configuration root must be a mapping")
    return value


def _required(mapping: dict, key: str, expected: type, context: str):
    value = mapping.get(key)
    if (
        not isinstance(value, expected)
        or (expected is int and isinstance(value, bool))
        or (expected is str and not value.strip())
    ):
        raise AgentVMError(f"{context}.{key} must be a non-empty {expected.__name__}")
    return value


@dataclass(frozen=True)
class Config:
    path: Path
    root: Path
    raw: dict

    @classmethod
    def load(cls, path: Path, root: Path) -> "Config":
        if path.exists() and path.stat().st_mode & 0o077:
            raise AgentVMError(
                f"{path} contains secrets and must have mode 0600; run chmod 600 {path}"
            )
        raw = _load_yaml(path)
        config = cls(path=path, root=root, raw=raw)
        config.validate()
        return config

    def validate(self) -> None:
        if self.raw.get("schema_version") != 1:
            raise AgentVMError("schema_version must be 1")
        vm = _required(self.raw, "vm", dict, "config")
        vm_name = _required(vm, "name", str, "vm")
        if not VM_NAME_RE.fullmatch(vm_name):
            raise AgentVMError("vm.name may contain only letters, numbers, dots, underscores, and hyphens")
        if vm.get("architecture") != "x86_64":
            raise AgentVMError("Only vm.architecture=x86_64 is supported")
        for key in ("vcpus", "memory_gib", "disk_gib"):
            value = _required(vm, key, int, "vm")
            if value <= 0:
                raise AgentVMError(f"vm.{key} must be greater than zero")
        image = _required(vm, "image", dict, "vm")
        for key in ("url", "checksum_url"):
            self._validate_url(_required(image, key, str, "vm.image"), f"vm.image.{key}")
        guest = _required(self.raw, "guest", dict, "config")
        guest_user = _required(guest, "user", str, "guest")
        if not USER_RE.fullmatch(guest_user):
            raise AgentVMError("guest.user is not a valid Unix account name")
        console_passwords = {}
        for key in ("console_agent_password", "console_root_password"):
            password = _required(guest, key, str, "guest")
            if any(character in password for character in "\r\n\0"):
                raise AgentVMError(f"guest.{key} must be a single-line string")
            console_passwords[key] = password
        if console_passwords["console_agent_password"] == console_passwords["console_root_password"]:
            raise AgentVMError("guest console passwords must be distinct")
        workspace = Path(_required(guest, "workspace_dir", str, "guest"))
        if not workspace.is_absolute():
            raise AgentVMError("guest.workspace_dir must be absolute")
        ports = _required(self.raw, "ports", dict, "config")
        seen: set[int] = set()
        for name in ("kandev", "bifrost", "cliproxyapi"):
            port = _required(ports, name, int, "ports")
            if not 1 <= port <= 65535 or port in seen:
                raise AgentVMError(f"ports.{name} must be unique and between 1 and 65535")
            seen.add(port)
        netbird_values: dict[str, str] = {}
        for name in ("NB_HOSTNAME", "NB_MANAGEMENT_URL", "NB_SETUP_KEY"):
            value = self.raw.get(name)
            if not isinstance(value, str) or not value.strip():
                raise AgentVMError(f"{name} must be defined in {self.path}")
            netbird_values[name] = value.strip()
        netbird_hostname = netbird_values["NB_HOSTNAME"]
        if not HOSTNAME_RE.fullmatch(netbird_hostname):
            raise AgentVMError("config.NB_HOSTNAME is invalid; expected a DNS-compatible hostname")
        self._validate_url(
            netbird_values["NB_MANAGEMENT_URL"],
            "config.NB_MANAGEMENT_URL",
        )
        services = _required(self.raw, "services", dict, "config")
        _required(services, "node_major", int, "services")
        for name in ("kandev", "pi", "bifrost"):
            service = _required(services, name, dict, "services")
            _required(service, "npm_package", str, f"services.{name}")
        if services["pi"]["npm_package"] != "@earendil-works/pi-coding-agent":
            raise AgentVMError(
                "services.pi.npm_package must be @earendil-works/pi-coding-agent "
                "for Kandev Pi ACP compatibility"
            )
        _required(services["pi"], "default_model", str, "services.pi")
        cliproxy = _required(services, "cliproxyapi", dict, "services")
        _required(cliproxy, "github_repository", str, "services.cliproxyapi")
        pattern = _required(cliproxy, "asset_pattern", str, "services.cliproxyapi")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise AgentVMError(f"services.cliproxyapi.asset_pattern is invalid: {exc}") from exc
        local = self.raw.get("local", {})
        if not isinstance(local, dict):
            raise AgentVMError("config.local must be a mapping")
        for key, default in (("state_dir", ".state"), ("cache_dir", ".cache")):
            value = local.get(key, default)
            if not isinstance(value, str) or not value.strip():
                raise AgentVMError(f"local.{key} must be a non-empty relative path")
            path = Path(value)
            candidate = (self.root.resolve() / path).resolve()
            if (
                path.is_absolute()
                or ".." in path.parts
                or not candidate.is_relative_to(self.root.resolve())
            ):
                raise AgentVMError(f"local.{key} must stay inside the repository")

    @staticmethod
    def _validate_url(value: str, name: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AgentVMError(f"{name} must be an http(s) URL")

    @property
    def state_dir(self) -> Path:
        return (self.root / self.raw.get("local", {}).get("state_dir", ".state")).resolve()

    @property
    def cache_dir(self) -> Path:
        return (self.root / self.raw.get("local", {}).get("cache_dir", ".cache")).resolve()

    @property
    def vm(self) -> dict:
        return self.raw["vm"]

    @property
    def guest(self) -> dict:
        return self.raw["guest"]

    @property
    def ports(self) -> dict:
        return self.raw["ports"]

    @property
    def services(self) -> dict:
        return self.raw["services"]

    @property
    def netbird(self) -> dict:
        return {
            "hostname": self.raw["NB_HOSTNAME"].strip(),
            "management_url": self.raw["NB_MANAGEMENT_URL"].strip().rstrip("/"),
            "setup_key": self.raw["NB_SETUP_KEY"].strip(),
        }
