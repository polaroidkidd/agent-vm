from __future__ import annotations

import json
from dataclasses import dataclass, asdict

from .config import Config
from .process import Runner
from .state import State


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _remote(runner: Runner, config: Config, state: State, address: str, command: str):
    private_key = state.directory / "admin_ed25519"
    return runner.run([
        "ssh", "-i", str(private_key), "-o", "BatchMode=yes",
        "-o", f"UserKnownHostsFile={state.directory / 'known_hosts'}",
        "-o", "StrictHostKeyChecking=yes", f"{config.guest['user']}@{address}", command,
    ], check=False, capture=True)


def _has_models(output: str) -> bool:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and isinstance(data.get("data"), list) and bool(data["data"])


def _has_model(output: str, expected: str) -> bool:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False
    entries = data.get("data") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return False
    model_ids = {
        entry.get("id") for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    return expected in model_ids or any(model_id.endswith(f"/{expected}") for model_id in model_ids)


def _kandev_pi_capabilities(output: str) -> tuple[bool, str]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False, "Kandev Pi capability response was not valid JSON"
    if not isinstance(data, dict):
        return False, "Kandev Pi capability response was invalid"
    if data.get("status") != "ok":
        return False, str(data.get("error") or f"capability status is {data.get('status', 'unknown')}")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        return False, "Kandev Pi model catalog is empty"
    return True, f"Kandev ACP probe advertised {len(models)} model(s)"


def _kandev_pi_discovery(output: str) -> tuple[bool, str]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False, "Kandev agent discovery response was not valid JSON"
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, list):
        return False, "Kandev agent discovery response was invalid"
    pi = next(
        (agent for agent in agents if isinstance(agent, dict) and agent.get("name") == "pi-acp"),
        None,
    )
    if not pi or pi.get("available") is not True:
        return False, "Kandev did not discover the installed Pi agent"
    matched_path = str(pi.get("matched_path") or "Pi executable")
    return True, f"Kandev discovered Pi at {matched_path}"


def run_doctor(
    runner: Runner,
    config: Config,
    state: State,
    address: str,
    *,
    live_model_test: bool = False,
) -> list[Check]:
    checks: list[Check] = []
    pr_agent = getattr(config, "pr_agent", None)
    services = ["docker", "kandev", "bifrost", "cliproxyapi", "netbird"]
    if pr_agent:
        services.append("pr-agent")
    for service in services:
        result = _remote(runner, config, state, address, f"systemctl is-active {service}")
        active = result.returncode == 0 and result.stdout.strip() == "active"
        checks.append(Check(f"service:{service}", "ready" if active else "failed", result.stdout.strip() or "inactive"))
    docker = _remote(
        runner,
        config,
        state,
        address,
        "docker version --format '{{.Server.Version}}'",
    )
    docker_version = docker.stdout.strip()
    checks.append(Check(
        "integration:docker",
        "ready" if docker.returncode == 0 and bool(docker_version) else "failed",
        f"Docker Engine {docker_version}" if docker_version else "agent cannot access the Docker daemon",
    ))
    for executable in ("gh", "pip", "pipx", "uv"):
        result = _remote(runner, config, state, address, f"{executable} --version 2>&1")
        detail = result.stdout.strip()
        checks.append(Check(
            f"tool:{executable}",
            "ready" if result.returncode == 0 and bool(detail) else "failed",
            detail or f"{executable} executable unavailable",
        ))
    endpoints = {
        "kandev": f"http://127.0.0.1:{config.ports['kandev']}/health",
        "bifrost": f"http://127.0.0.1:{config.ports['bifrost']}/health",
        "cliproxyapi": f"http://127.0.0.1:{config.ports['cliproxyapi']}/healthz",
    }
    if pr_agent:
        endpoints["pr-agent"] = f"http://127.0.0.1:{config.ports['pr_agent']}/"
    for name, url in endpoints.items():
        result = _remote(
            runner,
            config,
            state,
            address,
            "curl -fsS --retry 5 --retry-delay 2 --retry-connrefused "
            f"--retry-all-errors --max-time 5 {url}",
        )
        checks.append(Check(f"endpoint:{name}", "ready" if result.returncode == 0 else "failed", url))
    netbird = _remote(runner, config, state, address, "sudo netbird status --json")
    if netbird.returncode == 0:
        try:
            data = json.loads(netbird.stdout)
            detail = str(data.get("netbirdIp") or data.get("fqdn") or "connected")
        except json.JSONDecodeError:
            detail = "connected"
        checks.append(Check("integration:netbird", "ready", detail))
    else:
        checks.append(Check("integration:netbird", "pending", "client is not enrolled"))
    github = _remote(runner, config, state, address, "ssh -o BatchMode=yes -T git@github.com 2>&1")
    github_text = (github.stdout + github.stderr).strip()
    github_ok = "successfully authenticated" in github_text
    checks.append(Check("integration:github", "ready" if github_ok else "pending", "SSH key registered" if github_ok else "register the generated public key"))
    models = _remote(
        runner, config, state, address,
        "key=$(sed -n '/^api-keys:/{n;s/^[[:space:]]*-[[:space:]]*\"\\(.*\\)\"/\\1/p;}' ~/.config/cliproxyapi/config.yaml); "
        f"curl -fsS --max-time 10 -H \"Authorization: Bearer $key\" http://127.0.0.1:{config.ports['cliproxyapi']}/v1/models",
    )
    cliproxy_ready = models.returncode == 0 and _has_models(models.stdout)
    checks.append(Check(
        "integration:cliproxy-oauth",
        "ready" if cliproxy_ready else "pending",
        "nonempty model catalog available" if cliproxy_ready else "run configure-cliproxy",
    ))
    bifrost_models = _remote(
        runner,
        config,
        state,
        address,
        "set -a; . ~/.config/bifrost/bifrost.env; set +a; "
        f"curl -fsS --max-time 10 -H \"Authorization: Bearer $BIFROST_VIRTUAL_KEY\" http://127.0.0.1:{config.ports['bifrost']}/v1/models",
    )
    bifrost_ready = bifrost_models.returncode == 0 and _has_models(bifrost_models.stdout)
    checks.append(Check(
        "integration:bifrost-routing",
        "ready" if bifrost_ready else "pending",
        "virtual key reaches CLIProxyAPI models" if bifrost_ready else "complete OAuth, then run configure-bifrost",
    ))
    if pr_agent:
        pr_agent_model_ready = bifrost_ready and _has_model(bifrost_models.stdout, pr_agent["model"])
        checks.append(Check(
            "integration:pr-agent-bifrost",
            "ready" if pr_agent_model_ready else "pending",
            "configured review model is available through Bifrost"
            if pr_agent_model_ready else f"Bifrost does not advertise {pr_agent['model']}",
        ))
        github_app = _remote(
            runner,
            config,
            state,
            address,
            "/opt/pr-agent/current/venv/bin/python -c "
            "'from github import GithubIntegration; from pr_agent.config_loader import get_settings; "
            "s=get_settings(); GithubIntegration(s.github.app_id, s.github.private_key).get_app()'",
        )
        checks.append(Check(
            "integration:pr-agent-github",
            "ready" if github_app.returncode == 0 else "pending",
            "GitHub accepted the configured App identity"
            if github_app.returncode == 0 else "register or correct the GitHub App credentials",
        ))
    pi_version = _remote(runner, config, state, address, "pi --version 2>&1")
    checks.append(Check(
        "integration:pi",
        "ready" if pi_version.returncode == 0 else "failed",
        pi_version.stdout.strip() or "Pi executable unavailable",
    ))
    kandev_discovery = _remote(
        runner,
        config,
        state,
        address,
        f"curl -fsS --max-time 60 http://127.0.0.1:{config.ports['kandev']}/api/v1/agents/discovery",
    )
    discovery_ready, discovery_detail = _kandev_pi_discovery(kandev_discovery.stdout)
    if kandev_discovery.returncode != 0:
        discovery_ready = False
        discovery_detail = "Kandev agent discovery request failed"
    checks.append(Check(
        "integration:kandev-agent-discovery",
        "ready" if discovery_ready else "failed",
        discovery_detail,
    ))
    kandev_pi = _remote(
        runner,
        config,
        state,
        address,
        f"curl -fsS --max-time 60 'http://127.0.0.1:{config.ports['kandev']}/api/v1/agent-models/pi-acp?refresh=true'",
    )
    kandev_pi_ready, kandev_pi_detail = _kandev_pi_capabilities(kandev_pi.stdout)
    if kandev_pi.returncode != 0:
        kandev_pi_ready = False
        kandev_pi_detail = "Kandev Pi capability probe request failed"
    checks.append(Check(
        "integration:kandev-pi",
        "ready" if kandev_pi_ready else "failed",
        kandev_pi_detail,
    ))
    if live_model_test:
        model_test = _remote(
            runner,
            config,
            state,
            address,
            "pi --no-session --no-tools -p 'Reply with exactly OK.'",
        )
        checks.append(Check(
            "integration:pi-live-model",
            "ready" if model_test.returncode == 0 and bool(model_test.stdout.strip()) else "failed",
            "Pi completed a model request" if model_test.returncode == 0 and model_test.stdout.strip() else "model request failed",
        ))
    return checks


def print_checks(checks: list[Check], *, json_output: bool = False) -> bool:
    if json_output:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        width = max(len(check.name) for check in checks)
        for check in checks:
            print(f"{check.name:<{width}}  {check.status:<10} {check.detail}")
    return not any(check.status == "failed" for check in checks)
