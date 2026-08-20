from __future__ import annotations

import hashlib
import ipaddress
import os
import stat
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .config import Config
from .errors import AgentVMError
from .process import Runner
from .state import State


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "agent-vm/0.1"})
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(destination)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise AgentVMError(f"Download failed for {url}: {exc}") from exc


def _remote_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "agent-vm/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        raise AgentVMError(f"Cannot retrieve checksum file {url}: {exc}") from exc


def prepare_cloud_image(config: Config) -> Path:
    image = config.vm["image"]
    filename = Path(urlparse(image["url"]).path).name
    if not filename:
        raise AgentVMError("vm.image.url has no filename")
    destination = config.cache_dir / filename
    sums = _remote_text(image["checksum_url"])
    expected = None
    for line in sums.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[-1].lstrip("*") == filename:
            expected = fields[0]
            break
    if expected is None or len(expected) != 64:
        raise AgentVMError(f"No SHA-256 checksum found for {filename}")
    for attempt in range(2):
        if not destination.exists():
            _download(image["url"], destination)
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() == expected:
            break
        destination.unlink(missing_ok=True)
        if attempt:
            raise AgentVMError(f"Checksum mismatch for {filename}; downloaded file removed")
    return destination


class VM:
    def __init__(self, config: Config, state: State, runner: Runner):
        self.config = config
        self.state = state
        self.runner = runner
        self.name = config.vm["name"]
        self.disk = state.directory / f"{self.name}.qcow2"
        self.seed = state.directory / f"{self.name}-seed.img"
        self.known_hosts = state.directory / "known_hosts"

    def exists(self) -> bool:
        result = self.runner.run(["virsh", "dominfo", self.name], check=False, capture=True)
        return result.returncode == 0

    def create(self, base_image: Path, admin_public_key: str) -> None:
        if self.exists():
            raise AgentVMError(f"VM {self.name!r} already exists; use provision or rebuild")
        self.state.ensure()
        password_hash = self._console_root_password_hash()
        user_data = self.state.directory / "user-data"
        meta_data = self.state.directory / "meta-data"
        user_data.write_text(self._user_data(admin_public_key, password_hash), encoding="utf-8")
        meta_data.write_text(f"instance-id: {self.name}\nlocal-hostname: {self.name}\n", encoding="utf-8")
        os.chmod(user_data, 0o600)
        os.chmod(meta_data, 0o600)
        # A previous failed virt-install may have left partial storage behind.
        self.disk.unlink(missing_ok=True)
        self.seed.unlink(missing_ok=True)
        self.runner.run([
            "qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", str(base_image),
            str(self.disk), f"{self.config.vm['disk_gib']}G",
        ])
        self.runner.run(["cloud-localds", str(self.seed), str(user_data), str(meta_data)])
        self._grant_hypervisor_storage_access(base_image)
        self.runner.run([
            "virt-install", "--name", self.name,
            "--memory", str(self.config.vm["memory_gib"] * 1024),
            "--vcpus", str(self.config.vm["vcpus"]),
            "--import", "--disk", f"path={self.disk},format=qcow2,bus=virtio",
            "--disk", f"path={self.seed},device=cdrom",
            "--network", f"network={self.config.vm.get('libvirt_network', 'default')},model=virtio",
            "--os-variant", self.config.vm.get("os_variant", "ubuntu24.04"),
            "--graphics", "none", "--noautoconsole",
        ])

    def _console_root_password_hash(self) -> str:
        password = self.config.guest["console_root_password"]
        return self.runner.run(
            ["openssl", "passwd", "-6", "-stdin"],
            capture=True,
            sensitive=True,
            stdin=password + "\n",
        ).stdout.strip()

    def _grant_hypervisor_storage_access(self, base_image: Path) -> None:
        """Give system libvirt narrowly scoped access without exposing .state."""
        hypervisor_user = "libvirt-qemu"
        directories = {self.disk.parent, base_image.parent}
        for path in (self.disk, self.seed, base_image):
            directories.update(path.parents)
        for directory in sorted(directories, key=lambda item: len(item.parts)):
            if not directory.exists():
                continue
            mode = stat.S_IMODE(directory.stat().st_mode)
            if not mode & stat.S_IXOTH:
                self.runner.run([
                    "setfacl", "-m", f"u:{hypervisor_user}:--x", str(directory)
                ])
        self.runner.run(["setfacl", "-m", f"u:{hypervisor_user}:rw-", str(self.disk)])
        self.runner.run(["setfacl", "-m", f"u:{hypervisor_user}:r--", str(self.seed)])
        self.runner.run(["setfacl", "-m", f"u:{hypervisor_user}:r--", str(base_image)])

    def _user_data(self, public_key: str, password_hash: str) -> str:
        user = self.config.guest["user"]
        timezone = self.config.guest.get("timezone", "UTC")
        return f"""#cloud-config
hostname: {self.name}
manage_etc_hosts: true
timezone: {timezone}
ssh_pwauth: false
disable_root: true
users:
  - default
  - name: {user}
    gecos: Shared agent account
    groups: [adm, sudo]
    shell: /bin/bash
    sudo: [\"ALL=(ALL) NOPASSWD:ALL\"]
    lock_passwd: true
    ssh_authorized_keys:
      - {public_key.strip()}
chpasswd:
  expire: false
  users:
    - name: root
      password: {password_hash}
      type: hash
runcmd:
  - [systemctl, enable, --now, qemu-guest-agent]
package_update: true
packages:
  - qemu-guest-agent
  - python3
"""

    def ip_address(self, timeout: int = 300) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.runner.run(
                ["virsh", "domifaddr", self.name, "--source", "agent"], check=False, capture=True
            )
            for line in result.stdout.splitlines():
                fields = line.split()
                if len(fields) < 4 or "/" not in fields[-1]:
                    continue
                try:
                    address = ipaddress.ip_interface(fields[-1]).ip
                except ValueError:
                    continue
                if (
                    address.version == 4
                    and not address.is_loopback
                    and not address.is_link_local
                    and not address.is_multicast
                    and not address.is_unspecified
                ):
                    return str(address)
            time.sleep(3)
        raise AgentVMError(f"Timed out waiting for an address for {self.name}")

    def pin_host_key(self, address: str, timeout: int = 300) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.runner.run(
                ["ssh-keyscan", "-T", "10", "-H", address],
                check=False,
                capture=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                self.known_hosts.write_text(result.stdout, encoding="utf-8")
                os.chmod(self.known_hosts, 0o600)
                return
            time.sleep(5)
        raise AgentVMError(f"Timed out waiting for SSH host keys on {address}")

    def wait_for_ssh(self, address: str, private_key: Path, timeout: int = 300) -> None:
        user = self.config.guest["user"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.runner.run([
                "ssh", "-i", str(private_key), "-o", "BatchMode=yes",
                "-o", f"UserKnownHostsFile={self.known_hosts}", "-o", "StrictHostKeyChecking=yes",
                "-o", "ConnectTimeout=5", f"{user}@{address}", "cloud-init status --wait",
            ], check=False, capture=True)
            if result.returncode == 0:
                return
            time.sleep(5)
        raise AgentVMError(f"Timed out waiting for SSH/cloud-init on {address}")

    def destroy(self) -> None:
        if self.exists():
            self.runner.run(["virsh", "destroy", self.name], check=False)
            undefined = self.runner.run(
                ["virsh", "undefine", self.name, "--nvram"], check=False, capture=True
            )
            if undefined.returncode != 0:
                self.runner.run(["virsh", "undefine", self.name], check=False, capture=True)
            if not self.runner.dry_run and self.exists():
                raise AgentVMError(
                    f"Could not undefine {self.name!r}; guest files were left untouched"
                )
        for path in (self.disk, self.seed, self.known_hosts, self.state.directory / "user-data", self.state.directory / "meta-data"):
            path.unlink(missing_ok=True)

    def state_text(self) -> str:
        if not self.exists():
            return "absent"
        return self.runner.run(["virsh", "domstate", self.name], capture=True).stdout.strip()
