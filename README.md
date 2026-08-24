# Agent VM

This repository creates and provisions one disposable Ubuntu Server 24.04 x86-64 VM for agentic development. It runs Kandev, Pi, Bifrost, CLIProxyAPI, NetBird, Zsh, and Oh My Zsh directly on the guest as native processes, and provides Docker Engine with Buildx and Docker Compose for agent workloads.

Model requests follow one enforced path:

```text
Kandev / Pi / OpenAI-compatible tools
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

   vm:
     vcpus: 4
     memory_gib: 16
     disk_gib: 100

   guest:
     console_agent_password: replace-with-an-agent-console-password
     console_root_password: replace-with-a-console-root-password

   services:
     nvm:
       version: v0.40.3
     node_major: 24
   ```

   The populated file contains `NB_SETUP_KEY` and separate agent/root console passwords, is ignored by Git, and must remain mode `0600`. The two console passwords must be distinct. All configuration values are validated before any VM operation. `NB_SETUP_KEY` may be one-off or reusable. A rebuild creates a new NetBird peer and therefore needs another usable key.

   Repository-owned Agent Skills live under `skills/<name>/`. `create`, `provision`,
   and `update` automatically copy every skill there to
   `/home/agent/.agents/skills/<name>`. Pi discovers that user-global location when
   Kandev starts a new agent session. Each immediate subdirectory of `skills/` must
   have a valid lowercase skill name and contain `SKILL.md`.

   Node.js is installed for `agent` through the pinned NVM release. The configured
   major selects the Node.js release line; NVM-managed `node`, `npm`, `npx`,
   `kandev`, and `pi` are also exposed through stable `/usr/local/bin` links for
   systemd services and non-interactive SSH commands.

2. Validate the host, then create and provision the VM:

   ```bash
   ./agent-vm create
   ```

   This generates `.state/admin_ed25519`, `.state/github_ed25519`, application secrets, resolved versions, the QCOW2 overlay, and cloud-init data. `.state` is ignored and restricted locally.

   System libvirt runs QEMU as `libvirt-qemu`. `create` adds narrow POSIX ACL entries that grant this account traversal through otherwise-private parent directories and access only to the QCOW2 overlay, cloud-init seed, and verified base image. Other `.state` files remain inaccessible.

3. Register the generated GitHub public key at <https://github.com/settings/keys>:

   ```bash
   ./agent-vm configure-github --show-only
   ```

   After registering it, verify SSH authentication:

   ```bash
   ./agent-vm configure-github
   ```

   The VM accepts GitHub Git traffic through SSH only and pins GitHub's published Ed25519 host key.

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

6. Create the three NetBird Reverse Proxy services described below.

7. Check the complete installation:

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

## Credentials and tool configuration

Generated secrets are stored in `.state/secrets.json` with mode `0600`. The CLI never prints them during normal operation. Inspect only the value you need, for example:

```bash
jq -r .bifrost_virtual_key .state/secrets.json
jq -r .bifrost_admin_password .state/secrets.json
jq -r .cliproxy_management_secret .state/secrets.json
```

For a tool that accepts an OpenAI-compatible base URL:

```bash
export OPENAI_BASE_URL=https://bifrost.intra.dle.dev/v1
export OPENAI_API_KEY="$(jq -r .bifrost_virtual_key .state/secrets.json)"
```

Inside the VM, use `http://127.0.0.1:8080/v1`. The requested model must be present in CLIProxyAPI's `/v1/models` response. Change `services.pi.default_model` in the YAML and rerun `configure-bifrost` to select a different default from the live catalog.

Pi is installed and preconfigured with the Bifrost provider. Changes to the
managed Pi package restart Kandev so its local-agent discovery is refreshed. In
Kandev, open **Settings → Agents**, rescan the local host, select Pi, and review
the generated local profile before starting work. Kandev runs Pi as the same
`agent` account and uses local workspaces only.

The guest's Zsh configuration is a headless, portable adaptation of `polaroidkidd/regolith-dot-files`. It installs every real custom plugin found in the requested workstation inventory (the Oh My Zsh `example` placeholder is excluded), enables the portable active subset, and omits Kitty and workstation-only graphical helpers.

SSH tunnel fallbacks are available even before the NetBird proxies are configured:

```bash
ssh -L 8080:127.0.0.1:8080 agent@<netbird-address>
ssh -L 8317:127.0.0.1:8317 agent@<netbird-address>
```

Then open `http://127.0.0.1:8080` or `http://127.0.0.1:8317/management.html`.

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
- Services: `sudo systemctl status docker kandev bifrost cliproxyapi netbird`
- Logs: `sudo journalctl -u <service> -n 200 --no-pager`
- NetBird: `sudo netbird status` and `ip addr show wt0`
- Docker: `docker version`, `docker compose version`, and `docker info`
- Firewall: `sudo ufw status verbose`
- CLIProxyAPI health: `curl http://127.0.0.1:8317/healthz`
- Bifrost health: `curl http://127.0.0.1:8080/health`
- Kandev health: `curl http://127.0.0.1:38429/health`

`doctor` reports provisioning failures separately from pending GitHub registration, Codex OAuth, and NetBird enrollment. Server-side Reverse Proxy services are out of scope and are not probed automatically.

## Development checks

Run the dependency-free unit suite and syntax checks with:

```bash
make check
```
