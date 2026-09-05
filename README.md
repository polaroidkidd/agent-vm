# Agent VM

This repository provisions one Ubuntu Server 24.04 VM for Kandev development.
Kandev, Pi, CLIProxyAPI, NetBird, Zsh, and Oh My Zsh run as native guest processes.
Docker Engine, Buildx, and Compose support repository workloads; Chromium supports
repository-pinned Playwright tests.

Model requests follow this path:

```text
Kandev → Pi → CLIProxyAPI → Codex OAuth subscription
```

Pi uses the `cliproxy` provider and the live CLIProxyAPI model catalog. Bifrost and
PR-Agent are retired. Full provisioning removes their services, packages,
configuration, credentials, and guest firewall rules after migrating Pi profiles.

## Supported platform

- Host: Ubuntu Linux, x86-64, KVM/QEMU, and system libvirt.
- Guest: Ubuntu Server 24.04 LTS, x86-64, with libvirt NAT and NetBird.
- Defaults: 4 vCPUs, 16 GiB RAM, and a 100 GiB sparse QCOW2 disk.
- Host dependencies: KVM/QEMU, libvirt, `virt-install`, QCOW2/cloud-image tooling,
  OpenSSH, OpenSSL, POSIX ACL tools, Ansible, and PyYAML. `create` checks these and
  available resources; it never installs host packages.
- The launcher uses Ubuntu's `/usr/bin/python3` so other Python environments cannot
  hide apt-installed PyYAML.

Run commands from the repository root. This host uses the system libvirt connection:

```bash
export LIBVIRT_DEFAULT_URI=qemu:///system
```

## First setup

1. Copy and protect the configuration:

   ```bash
   cp config/agent-vm.example.yaml config/agent-vm.yaml
   chmod 600 config/agent-vm.yaml
   ```

   Fill in NetBird enrollment, Stripe credentials, both console passwords, and the
   Git identity. Review resource sizes, ports, and the Kandev workspace name. All
   operational input lives in this ignored file; do not commit it.

2. Create and provision the VM:

   ```bash
   ./agent-vm create
   ```

3. Register the VM-specific public GitHub keys:

   ```bash
   ./agent-vm configure-github --show-only
   ```

   Add the SSH key as an Authentication Key and the armored GPG block as a GPG key
   in GitHub settings. The Git email must be verified on the account. Then run:

   ```bash
   ./agent-vm configure-github
   ```

   Git traffic uses SSH with GitHub's pinned Ed25519 host key. With
   `guest.git.sign_commits: true`, the guest signs commits noninteractively using
   its VM-specific key. Private keys remain in ignored state and the guest keyring.
   Use the connected GitHub integration for hosting workflows, never `gh`.

4. Complete CLIProxyAPI's interactive Codex OAuth login:

   ```bash
   ./agent-vm configure-cliproxy
   ./agent-vm configure-models
   ```

   Login temporarily stops CLIProxyAPI, forwards callback port 1455 over SSH, and
   restarts the service afterward. Open the displayed URL on the workstation.
   `configure-models` imports the live catalog directly into Pi, refreshes Kandev,
   and migrates old `bifrost/cliproxy/...` profile models to `cliproxy/...`.
   Repeat it after adding or reauthenticating a CLIProxyAPI Auth File.

5. Create the configured workspace in Kandev and connect its GitHub automation
   integration with read access to `polaroidkidd/agent-vm`. Register repositories,
   then run:

   ```bash
   ./agent-vm configure-kandev-workflow
   ./agent-vm provision
   ```

   Workflow Sync reads the configured remote branch and directory. A local YAML
   edit has no live effect until it is published there. The command requires
   `last_ok: true`, no error, and no warnings. Provisioning renames the manual
   duplicate to `Development (legacy)` and places the synced `Development` first.
   Existing tasks remain attached to their original workflow.

6. Configure the two private NetBird reverse proxies below, then verify:

   ```bash
   ./agent-vm doctor
   ```

   An optional model inference test consumes subscription capacity:

   ```bash
   ./agent-vm doctor --live-model-test
   ```

CLIProxyAPI is an unofficial compatibility bridge. Subscription access and API
access are separate products; compatibility can change independently of this VM.

## Kandev task environments

Provisioning manages scripts for repositories explicitly listed in configuration:

```yaml
services:
  node_major: 24
  corepack_version: 0.35.0
  node_versions: [24.7.0]
  kandev:
    repositories:
      - {name: whatsin.fyi, preset: whatsin-fyi}
      - {name: services, preset: compose}
```

Names must match registered repositories in the configured workspace. Missing
workspaces or repositories are reported as pending so first provisioning can finish.
The configured presets own the repository's setup/dev/cleanup fields; remove a
repository entry before maintaining those fields manually.

`agent-vm-task` reads the checkout's exact `.nvmrc` and `packageManager` pins. Add
required Node versions to `services.node_versions`; Corepack downloads the selected
pnpm version into the writable user cache. The default Node installation and
Corepack wrappers are also available to noninteractive Kandev sessions.

### whatsin.fyi

- **Setup:** Kandev copies `.env.development` from the source checkout. The helper
  runs frozen-lockfile installation, workspace generation, and installation of the
  repository's Playwright Chromium version. Setup does not contact a database.
- **Preview:** The helper starts one PostgreSQL 17 Compose project per worktree,
  with a generated password, a private named volume, and an ephemeral loopback
  port. It overrides `DIRECT_DATABASE_URL`, prepares that database, and starts
  Vite on another loopback port. Open the reported port through Kandev.
- The helper bypasses the root `web:dev` chain, which calls database push with
  `--accept-data-loss`. Schema preparation here never accepts destructive changes
  automatically. It does not start Stripe listeners or production Compose stacks.
- **Cleanup:** Stop the preview in Kandev first. Cleanup stops only that worktree's
  Compose project and preserves its database volume for resuming work. It never
  prunes Docker data or removes another worktree's services.

Task ownership and credentials live under
`~/.local/state/agent-vm/tasks/kandev-<path-hash>/` in private files. A single preview
per worktree is enforced with a lock. Wrangler logs and the Miniflare worker
registry also live in this task directory. Database volumes persist after cleanup;
remove an obsolete task's specifically named volume only when its data is no longer
needed. The preset supplies a local database, not production seed data or external
image/payment services.

### services

Setup verifies the pinned pnpm version and Docker Compose. This infrastructure
repository has no automatic dev server. Follow its repository instructions and
validate only the changed stack with `docker compose ... config -q`; provisioning
and the task helper do not start, stop, or prune its stacks.

## Shell and runtime tools

The headless shell enables Git, Docker/Compose, fuzzy history, directory navigation,
archive extraction, colored manuals, safe paste, command suggestions, additional
completions, and syntax highlighting. NetBird and pnpm completions are guarded by
command availability. Shell history and completion caches live in writable XDG
locations; Oh My Zsh does not update itself during shell startup.

The VM includes `rg`, `fd`, `fzf`, `sqlite3`, `tmux`, `vim`, `tree`, Python/pip/pipx,
`uv`, Docker/Compose, and stable Node/Corepack/pnpm/Yarn entry points. Kandev's
systemd unit permits writes to workspaces, Pi configuration, npm/XDG caches, local
user data, and the GPG keyring. These paths are shared by trusted agents in this
single-user VM; they are not task isolation boundaries. Task databases and preview
ports are isolated separately.

Superpowers remains installed for explicit use. The Development workflow does not
require or invoke it unless the user asks. Kandev remains the plan authority, with
the committed `docs/plans/<task-id>.md` mirror and the existing review gates.

## NetBird reverse proxies

Server-side NetBird configuration is managed separately. Create HTTP services for
the configured peer, enable TLS termination and NetBird-only access, and restrict
access to the trusted group. Support WebSocket traffic for Kandev.

| Hostname | Peer port | Purpose |
|---|---:|---|
| `kandev.intra.dle.dev` | `38429` | Kandev board, API, and WebSockets |
| `cliapiproxy.intra.dle.dev` | `8317` | CLIProxyAPI API and management UI |

Use the configured ports if different. Guest ingress permits these services only
on `wt0`, plus normal loopback access. CLIProxyAPI still requires its credentials.
Its management UI is at `/management.html`; plugin artifacts live in
`~/.config/cliproxyapi/plugins`.

For an existing installation, retire the Bifrost dashboard proxy and public
PR-Agent webhook route in their separately managed infrastructure. Disable the
retired GitHub App webhook/installation where appropriate. Guest provisioning
cannot remove these external resources and does not change Kandev's independent
GitHub connection.

SSH tunnel fallback:

```bash
ssh -L 38429:127.0.0.1:38429 -L 8317:127.0.0.1:8317 agent@<netbird-address>
```

## Credentials

Generated credentials live in `.state/secrets.json` with mode `0600`. For tools
supporting an OpenAI-compatible endpoint:

```bash
export OPENAI_BASE_URL=https://cliapiproxy.intra.dle.dev/v1
export OPENAI_API_KEY="$(jq -r .cliproxy_api_key .state/secrets.json)"
```

Inside the VM, the base URL is `http://127.0.0.1:8317/v1`. Use a model ID returned
by `/v1/models`. The CLIProxyAPI management secret is separate from its API key.
`STRIPE_API_KEY` is loaded into Kandev and interactive shells from a private guest
environment file. Avoid printing full service environments, configuration, or logs.

## Routine operations

```bash
./agent-vm status       # recorded VM metadata and versions
./agent-vm doctor       # non-billable service and integration checks
./agent-vm provision    # reapply recorded releases and configured settings
./agent-vm configure-models
./agent-vm configure-kandev-workflow  # force and verify remote Workflow Sync
./agent-vm configure-netbird
./agent-vm update       # resolve and install latest stable application releases
```

Full provisioning reconciles Workflow Sync settings without forcing a fetch; its
poller reads the remote source. It also applies repository presets and removes
retired components. `provision` retains recorded application releases and a Node
release matching `node_major`; `update` advances them. Explicit NVM, uv, Corepack,
and additional Node pins are applied by provisioning. CLIProxyAPI artifacts and
the Ubuntu image are SHA-256 checked.

Docker group membership grants root-equivalent control within the guest. Reconnect
shells after the first Docker installation to acquire the new group membership.

The separate destructive command `./agent-vm rebuild --yes-destroy` deletes the VM,
workspaces, application/OAuth state, and generated identities. Nothing is restored
automatically. The agent console password is reapplied by provisioning; the root
recovery password changes only at creation or rebuild. Root SSH and SSH password
authentication remain disabled.

## Troubleshooting and validation

Use `virsh -c qemu:///system dominfo agent-vm` and `domifaddr agent-vm --source agent`
for live VM state. `virsh -c qemu:///system console agent-vm` provides console access
(detach with `Ctrl+]`). In the guest:

```bash
sudo systemctl status docker kandev cliproxyapi netbird
sudo journalctl -u kandev -n 100 --no-pager
sudo netbird status
sudo ufw status verbose
curl -f http://127.0.0.1:38429/health
curl -f http://127.0.0.1:8317/healthz
```

`doctor` distinguishes infrastructure failures from pending GitHub registration,
OAuth, and NetBird enrollment. External reverse proxies are not probed. Run local
unit and syntax checks with `make check`. See [workflows/README.md](workflows/README.md)
for the workflow state-machine validation procedure.
