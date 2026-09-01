from __future__ import annotations

import os
import platform
import pwd
import shutil
from pathlib import Path

from .config import Config
from .errors import AgentVMError


REQUIRED_COMMANDS = (
    "ansible-playbook",
    "virsh",
    "virt-install",
    "qemu-img",
    "cloud-localds",
    "ssh",
    "ssh-keygen",
    "ssh-keyscan",
    "gpg",
    "openssl",
    "setfacl",
)

def _validate_platform() -> None:
    os_release = Path("/etc/os-release").read_text(encoding="utf-8") if Path("/etc/os-release").exists() else ""
    if (
        platform.system() != "Linux"
        or platform.machine() not in {"x86_64", "amd64"}
        or "ID=ubuntu" not in os_release
    ):
        raise AgentVMError("Only x86-64 Ubuntu Linux hosts are supported")


def validate_host(config: Config, *, check_resources: bool = True) -> None:
    _validate_platform()
    missing = [command for command in REQUIRED_COMMANDS if shutil.which(command) is None]
    problems: list[str] = []
    if missing:
        problems.append("missing required host commands: " + ", ".join(missing))
    if not Path("/dev/kvm").exists():
        problems.append("/dev/kvm is unavailable; enable KVM virtualization")
    try:
        pwd.getpwnam("libvirt-qemu")
    except KeyError:
        problems.append("the libvirt-qemu service account is unavailable")
    if problems:
        raise AgentVMError("Host prerequisite check failed: " + "; ".join(problems))
    if not check_resources:
        return
    requested_cpus = config.vm["vcpus"]
    available_cpus = os.cpu_count() or 0
    if requested_cpus > available_cpus:
        raise AgentVMError(f"VM requests {requested_cpus} CPUs but host has {available_cpus}")
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    available_kib = int(next(line.split()[1] for line in meminfo.splitlines() if line.startswith("MemAvailable:")))
    requested_kib = config.vm["memory_gib"] * 1024 * 1024
    if requested_kib > available_kib:
        raise AgentVMError("Insufficient currently available RAM for configured VM")
    target = config.state_dir.parent
    free_bytes = shutil.disk_usage(target).free
    if config.vm["disk_gib"] * 1024**3 > free_bytes:
        raise AgentVMError("Insufficient free disk for configured QCOW2 maximum size")
