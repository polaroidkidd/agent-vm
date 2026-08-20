from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import Config
from .errors import AgentVMError


PRERELEASE_RE = re.compile(r"(?:^|[.\-+])(alpha|beta|rc|pre|preview|dev|nightly|snapshot)(?:[.\-+]|$)", re.I)


@dataclass(frozen=True)
class Release:
    version: str
    source: str
    url: str | None = None
    sha256: str | None = None
    asset: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _json(url: str, *, accept: str = "application/json") -> dict:
    request = Request(url, headers={"Accept": accept, "User-Agent": "agent-vm/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except Exception as exc:
        raise AgentVMError(f"Unable to resolve release metadata from {url}: {exc}") from exc


def npm_latest(package: str) -> Release:
    data = _json(
        f"https://registry.npmjs.org/{quote(package, safe='')}/latest",
        accept="application/json",
    )
    version = str(data.get("version", ""))
    if not version or PRERELEASE_RE.search(version):
        raise AgentVMError(f"npm latest for {package} is missing or a development version: {version!r}")
    return Release(version=version, source=f"npm:{package}")


def github_latest(repository: str, asset_pattern: str) -> Release:
    data = _json(
        f"https://api.github.com/repos/{repository}/releases/latest",
        accept="application/vnd.github+json",
    )
    tag = str(data.get("tag_name", ""))
    if not tag or data.get("draft") or data.get("prerelease") or PRERELEASE_RE.search(tag):
        raise AgentVMError(f"Latest GitHub release for {repository} is not stable: {tag!r}")
    pattern = re.compile(asset_pattern)
    matches = [asset for asset in data.get("assets", []) if pattern.search(str(asset.get("name", "")))]
    if len(matches) != 1:
        raise AgentVMError(f"Expected one Linux amd64 asset for {repository}; found {len(matches)}")
    asset = matches[0]
    digest = str(asset.get("digest") or "")
    sha256 = digest.split(":", 1)[1] if digest.startswith("sha256:") else None
    if sha256 is None:
        checksum_assets = [item for item in data.get("assets", []) if item.get("name") == "checksums.txt"]
        if len(checksum_assets) == 1:
            request = Request(checksum_assets[0]["browser_download_url"], headers={"User-Agent": "agent-vm/0.1"})
            try:
                with urlopen(request, timeout=30) as response:
                    checksum_text = response.read().decode("utf-8")
            except Exception as exc:
                raise AgentVMError(f"Unable to download checksums for {repository}: {exc}") from exc
            for line in checksum_text.splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[-1].lstrip("*") == asset["name"]:
                    sha256 = fields[0]
                    break
    if sha256 is None or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise AgentVMError(f"Release asset {asset.get('name')} has no usable SHA-256 checksum")
    return Release(
        version=tag.removeprefix("v"),
        source=f"github:{repository}",
        url=str(asset["browser_download_url"]),
        sha256=sha256.lower(),
        asset=str(asset["name"]),
    )


def resolve_all(config: Config) -> dict:
    services = config.services
    values = {
        "kandev": npm_latest(services["kandev"]["npm_package"]).to_dict(),
        "pi": npm_latest(services["pi"]["npm_package"]).to_dict(),
        "bifrost": npm_latest(services["bifrost"]["npm_package"]).to_dict(),
        "cliproxyapi": github_latest(
            services["cliproxyapi"]["github_repository"],
            services["cliproxyapi"]["asset_pattern"],
        ).to_dict(),
    }
    return values
