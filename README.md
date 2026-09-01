# Agent VM

This repository creates and provisions one disposable Ubuntu Server 24.04 x86-64 VM for agentic development. It runs Kandev, Pi, PR-Agent, Bifrost, CLIProxyAPI, NetBird, Zsh, and Oh My Zsh directly on the guest as native processes, and provides GitHub CLI plus Docker Engine with Buildx and Docker Compose for agent workloads.

Model requests follow one enforced path:

```text
Kandev / Pi / PR-Agent / OpenAI-compatible tools
                  |
                  v
          Bifrost virtual key
                  |
                  v
       CLIProxyAPI internal key
                  |
                  v
          Codex OAuth subscription
```

The CLIProxyAPI bridge is an unofficial compatibility layer. A ChatGPT/Codex subscription is not an OpenAI API account, and this arrangement may be affected by provider compatibility, terms, or account-policy changes.

## Supported platform

- Host: Ubuntu Linux, x86-64, KVM/QEMU, and libvirt.
- Guest: Ubuntu Server 24.04 LTS, x86-64.
- Networking: libvirt NAT plus NetBird.
- `create` verifies that KVM/QEMU, libvirt, `virt-install`, QCOW2 and cloud-image tooling, OpenSSH, OpenSSL, POSIX ACL tooling, Ansible, and PyYAML are available before creating anything. It never invokes a package manager.
- Hardware virtualization must still be enabled so `/dev/kvm` is available.
- The repository launcher deliberately uses Ubuntu's `/usr/bin/python3`, so an unrelated Homebrew or virtual-environment Python cannot hide the apt-installed PyYAML module.

The default VM is 4 vCPUs, 16 GiB RAM, and a 100 GiB sparse QCOW2 disk. All operational input—including NetBird enrollment—is kept in one ignored `config/agent-vm.yaml` file. These resource values are absolute; `create` fails before creating the VM if the host cannot currently satisfy them.

## First setup: run these commands in order

Run every command from the repository root.

1. Create the single ignored configuration file and restrict it:

   ```bash
   cp config/agent-vm.example.yaml config/agent-vm.yaml
   chmod 600 config/agent-vm.yaml
   ```

   Review the VM resources and service ports, choose the console recovery password, and fill all three required NetBird values:

   ```yaml
   NB_HOSTNAME: agent-vm
   NB_MANAGEMENT_URL: https://netbird.example.com
   NB_SETUP_KEY: replace-with-the-setup-key
   STRIPE_API_KEY: replace-with-a-stripe-api-key
   PR_AGENT_GITHUB_APP_ID: 123456
   PR_AGENT_GITHUB_PRIVATE_KEY: |-
     -----BEGIN RSA PRIVATE KEY-----
     replace-with-the-github-app-private-key
     -----END RSA PRIVATE KEY-----

   vm:
     vcpus: 4
     memory_gib: 16
     disk_gib: 100

   guest:
     console_agent_password: replace-with-an-agent-console-password
     console_root_password: replace-with-a-console-root-password
     git:
       sign_commits: true
       name: Replace With Your Name
       email: replace-with-your-verified-email@example.com

   services:
     nvm:
       version: v0.40.3
     uv:
       version: 0.12.7
     node_major: 24
     pi:
       npm_package: "@earendil-works/pi-coding-agent"
       superpowers_package: "@weiping/pi-superpowers"
       default_model: gpt-5.6-sol
     pr_agent:
       enabled: true
       pypi_package: pr-agent
       model: cliproxy/codex-auto-review
       fallback_model: cliproxy/gpt-5.6-sol
       workers: 2
   ```

   The populated file contains `NB_SETUP_KEY`, `STRIPE_API_KEY`, the GitHub App
   private key, and separate agent/root console passwords, is ignored by Git,
   and must remain mode `0600`. The two console passwords must be distinct. All
   configuration values are validated before any VM operation. `NB_SETUP_KEY`
   may be one-off or reusable. A rebuild creates a new NetBird peer and therefore
   needs another usable key. To omit PR-Agent, set `services.pr_agent.enabled` to
   `false`; its port and GitHub App values are then not required.

   Repository-owned Agent Skills live under `skills/<name>/`. `create`, `provision`,
   and `update` automatically copy every skill there to
   `/home/agent/.agents/skills/<name>`. Pi discovers that user-global location when
   Kandev starts a new agent session. Each immediate subdirectory of `skills/` must
   have a valid lowercase skill name and contain `SKILL.md`.

   Pi Superpowers is installed globally for the shared `agent` account using the
   exact npm release recorded during `create` or `update`. Its bootstrap extension,
   skills, and prompt templates are available to every new Pi session after Kandev
   restarts.

   Node.js is installed for `agent` through the pinned NVM release. The configured
   major selects the Node.js release line; NVM-managed `node`, `npm`, `npx`,
   `kandev`, and `pi` are also exposed through stable `/usr/local/bin` links for
   systemd services and non-interactive SSH commands.

   Python 3, `pip`, and `pipx` come from Ubuntu packages. The configured `uv`
   release is installed for `agent` through `pipx`; both `uv` and `uvx` are
   exposed through stable `/usr/local/bin` links for workloads and interactive
   shells.

2. Validate the host, then create and provision the VM:

   ```bash
   ./agent-vm create
   ```

   This generates `.state/admin_ed25519`, `.state/github_ed25519`, an OpenPGP
   commit-signing key, application secrets, resolved versions, the QCOW2 overlay,
   and cloud-init data. `.state` is ignored and restricted locally.

   System libvirt runs QEMU as `libvirt-qemu`. `create` adds narrow POSIX ACL entries that grant this account traversal through otherwise-private parent directories and access only to the QCOW2 overlay, cloud-init seed, and verified base image. Other `.state` files remain inaccessible.

3. Register the generated SSH authentication key and OpenPGP signing key with
   GitHub. This command prints both public keys and their registration URLs:

   ```bash
   ./agent-vm configure-github --show-only
   ```

   Add the SSH key at **Settings → SSH and GPG keys → New SSH key** as an
   **Authentication Key**. Add the armored OpenPGP block at **New GPG key**. The
   configured Git email must be verified on the GitHub account.

   After registering both, import the private OpenPGP key into the guest, apply
   the Git configuration, and verify SSH authentication:

   ```bash
   ./agent-vm configure-github
   ```

   The VM accepts GitHub Git traffic through SSH only and pins GitHub's published
   Ed25519 host key. When `guest.git.sign_commits` is `true`, provisioning imports
   the generated private OpenPGP key into the shared `agent` account and configures
   Git to sign every commit—including Kandev commits—with its fingerprint. Set it
   to `false` to disable automatic signing. The unencrypted private key exists only
   in ignored mode-`0600` state and the guest's private GnuPG keyring so Kandev can
   sign non-interactively.

4. Complete the interactive Codex OAuth login:

   ```bash
   ./agent-vm configure-cliproxy
   ```

   The command stops the background CLIProxyAPI service for the login, forwards the standard local OAuth callback port over SSH, runs the no-browser login as `agent`, and restarts the service afterward. Open the displayed authorization URL on your workstation.

5. Reapply and validate Bifrost's declarative CLIProxyAPI-only routing:

   ```bash
   ./agent-vm configure-bifrost
   ```

   This also imports the live models from the CLIProxyAPI OAuth account, through
   Bifrost, into Pi and refreshes Kandev's model selector. Run it again after
   adding, removing, or reauthenticating a CLIProxyAPI Auth File.

6. Provision the PR-Agent GitHub App service:

   ```bash
   ./agent-vm configure-pr-agent
   ```

   PR-Agent uses a dedicated Bifrost virtual key that can access only
   `services.pr_agent.model` and `services.pr_agent.fallback_model`. Host-level
   settings restrict automatic behavior to `/review`, disable push-triggered
   runs and draft feedback, and enable PR-Agent restricted mode.

7. Create the three private NetBird Reverse Proxy services and the separate
   public PR-Agent webhook route described below.

8. Check the complete installation:

   ```bash
   ./agent-vm doctor
   ```

   To send one end-to-end Pi request through Bifrost and CLIProxyAPI as a final integration test, opt in explicitly:

   ```bash
   ./agent-vm doctor --live-model-test
   ```

   The live test consumes subscription capacity and is therefore never run by the default doctor command.

`create` installs and enrolls NetBird using the required YAML values. If those values change later, reapply the client configuration with:

```bash
./agent-vm configure-netbird
```

## NetBird Reverse Proxy setup

Server-side NetBird configuration is deliberately not automated. In the NetBird dashboard, create three HTTP Layer 7 services. For every service:

- Select the peer named by `NB_HOSTNAME` in `config/agent-vm.yaml`.
- Select HTTP as the target protocol.
- Enable TLS termination.
- Enable NetBird-Only Access and restrict it to the trusted user/peer group.
- Enable host-header forwarding and redirect rewriting when the application requires them.
- Wait for the service to become `active`.

| Public hostname | Peer target port | Purpose |
|---|---:|---|
| `kandev.intra.dle.dev` | `38429` | Kandev board, API, and WebSocket traffic |
| `bifrost.intra.dle.dev` | `8080` | Bifrost dashboard and OpenAI-compatible API |
| `cliapiproxy.intra.dle.dev` | `8317` | CLIProxyAPI API and management UI |

The ports come from `config/agent-vm.yaml`; use the configured values if you changed them. The guest firewall accepts these ports only over loopback and `wt0`, not over the libvirt LAN.

NetBird Reverse Proxy is currently beta. Self-hosted deployments must provide the NetBird proxy/Traefik infrastructure required by the [official Reverse Proxy guide](https://docs.netbird.io/manage/reverse-proxy).

After configuration, use:

- Kandev: <https://kandev.intra.dle.dev>
- Bifrost: <https://bifrost.intra.dle.dev>
- CLIProxyAPI: <https://cliapiproxy.intra.dle.dev/management.html>

CLIProxyAPI's UI and APIs share port 8317. Bifrost and CLIProxyAPI still require their own credentials after NetBird admits the connection.
Plugin installation is enabled in the management UI, with artifacts stored under
`~/.config/cliproxyapi/plugins`. CLIProxyAPI plugins are trusted native libraries
loaded into the service process, so install only plugins whose source and release
artifacts you trust.

## PR-Agent GitHub App and webhook

Create a dedicated GitHub App following the
[official self-hosted PR-Agent guide](https://docs.pr-agent.ai/installation/github/#run-as-a-github-app).
Grant only these repository permissions:

- Pull requests: read and write
- Issues: read and write
- Metadata: read-only
- Contents: read-only

Subscribe only to `Pull request`. Do not subscribe to `Issue comment`,
`Pull request review comment`, or `Push`: this review-only deployment does not
accept interactive `/improve` commands and deliberately disables automatic
push-triggered reviews. Generate an App private key, put its ID and PEM value in
the ignored YAML configuration, install the App only on the repositories it may
review, and rerun `./agent-vm configure-pr-agent`.

GitHub cannot reach a NetBird-only hostname. Publish only
`POST /api/v1/github_webhooks` through a separate public HTTPS reverse proxy,
forwarding over NetBird to guest port `3000` (or the configured
`ports.pr_agent`). Do not expose Bifrost, CLIProxyAPI, Kandev, SSH, or PR-Agent's
other paths through that public listener. Configure the GitHub App with:

- Webhook URL: `https://<public-review-host>/api/v1/github_webhooks`
- Webhook secret: `jq -r .pr_agent_webhook_secret .state/secrets.json`

The guest firewall accepts the PR-Agent port only on `wt0`; the public edge is
an independently operated ingress boundary and is not created by this repository.
PR-Agent verifies every webhook signature and rejects requests when its secret
is absent or incorrect.

## Credentials and tool configuration

Generated secrets are stored in `.state/secrets.json` with mode `0600`. The CLI never prints them during normal operation. Inspect only the value you need, for example:

```bash
jq -r .bifrost_virtual_key .state/secrets.json
jq -r .bifrost_admin_password .state/secrets.json
jq -r .cliproxy_management_secret .state/secrets.json
jq -r .pr_agent_webhook_secret .state/secrets.json
```

For a tool that accepts an OpenAI-compatible base URL:

```bash
export OPENAI_BASE_URL=https://bifrost.intra.dle.dev/v1
export OPENAI_API_KEY="$(jq -r .bifrost_virtual_key .state/secrets.json)"
```

Inside the VM, use `http://127.0.0.1:8080/v1`. The requested model must be present in CLIProxyAPI's `/v1/models` response. Change `services.pi.default_model` in the YAML and rerun `configure-bifrost` to select a different Pi default from the live catalog. Change the two `services.pr_agent` model values and rerun `configure-pr-agent` to change PR-Agent's Bifrost allowlist.

Pi is installed and preconfigured with the Bifrost provider. Changes to the
managed Pi package restart Kandev so its local-agent discovery is refreshed. In
Kandev, open **Settings → Agents**, rescan the local host, select Pi, and review
the generated local profile before starting work. Kandev runs Pi as the same
`agent` account and uses local workspaces only.

`STRIPE_API_KEY` comes from the ignored, mode-`0600` VM configuration. Provisioning
writes it to a mode-`0600` agent environment file used by Kandev and direct Zsh
sessions, so Pi and workspace processes inherit it without storing the value in
tracked files.

The guest's Zsh configuration is a headless, portable adaptation of `polaroidkidd/regolith-dot-files`. It installs every real custom plugin found in the requested workstation inventory (the Oh My Zsh `example` placeholder is excluded), enables the portable active subset, and omits Kitty and workstation-only graphical helpers.

SSH tunnel fallbacks are available even before the NetBird proxies are configured:

```bash
ssh -L 8080:127.0.0.1:8080 agent@<netbird-address>
ssh -L 8317:127.0.0.1:8317 agent@<netbird-address>
ssh -L 3000:127.0.0.1:3000 agent@<netbird-address>
```

Then open `http://127.0.0.1:8080`, `http://127.0.0.1:8317/management.html`, or
`http://127.0.0.1:3000/` for PR-Agent's health response.

## Routine operations

```bash
./agent-vm status       # VM state, address, and recorded versions
./agent-vm doctor       # service and non-billable integration readiness
./agent-vm provision    # idempotently reapply recorded versions
./agent-vm update       # resolve and install the latest stable releases
```

`provision` never performs an application upgrade. `update` excludes alpha, beta, release-candidate, nightly, preview, development, and draft releases. CLIProxyAPI release artifacts and the Ubuntu image are SHA-256 verified.
For Node.js, `provision` retains the installed release when it already matches
`services.node_major`, while `update` installs the newest release in that major.
Changing `services.nvm.version` or `services.node_major` and running `provision`
applies the explicitly configured NVM or Node.js line.
Changing `services.uv.version` and running `provision` similarly installs that
exact `uv` release.

Every full `create`, `provision`, and `update` run installs Ubuntu's Docker
Engine, Buildx, and Docker Compose packages, starts the Docker daemon, and adds
`agent` to the `docker` group. Reconnect any shell that was already open when
Docker was first provisioned so it picks up the new group membership. Docker
group membership is effectively root-equivalent inside the VM because it grants
access to the privileged Docker daemon.

The destructive rebuild command is intentionally separate:

```bash
./agent-vm rebuild --yes-destroy
```

It deletes the libvirt domain, QCOW2 overlay, application state, workspaces, OAuth state, and generated identities. Push all work first. Nothing is restored automatically, and GitHub/NetBird/Codex must be enrolled again.

The `agent` console password comes from `guest.console_agent_password` in the ignored, mode-`0600` configuration file. It is applied during `create`, `provision`, and `update`, so changing it takes effect on the next provisioning run. The console recovery root password comes from `guest.console_root_password` and only changes during `create` or the destructive `rebuild`. Both passwords are hashed through standard input, so neither is exposed in OpenSSL process arguments. Root SSH and all SSH password authentication remain disabled.

## Troubleshooting

- VM console: `virsh console agent-vm` (log in as `agent` with `guest.console_agent_password`; detach with `Ctrl+]`)
- VM details: `virsh dominfo agent-vm` and `virsh domifaddr agent-vm --source agent`
- Services: `sudo systemctl status docker kandev pr-agent bifrost cliproxyapi netbird`
- Logs: `sudo journalctl -u <service> -n 200 --no-pager`
- NetBird: `sudo netbird status` and `ip addr show wt0`
- GitHub CLI: `gh --version`
- Docker: `docker version`, `docker compose version`, and `docker info`
- Python tooling: `pip --version`, `pipx --version`, and `uv --version`
- Firewall: `sudo ufw status verbose`
- CLIProxyAPI health: `curl http://127.0.0.1:8317/healthz`
- Bifrost health: `curl http://127.0.0.1:8080/health`
- Kandev health: `curl http://127.0.0.1:38429/health`
- PR-Agent health: `curl http://127.0.0.1:3000/`

`doctor` reports provisioning failures separately from pending GitHub registration, Codex OAuth, and NetBird enrollment. Server-side Reverse Proxy services are out of scope and are not probed automatically.

## Development checks

Run the dependency-free unit suite and syntax checks with:

```bash
make check
```
