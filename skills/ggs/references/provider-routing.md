# Provider Routing

Treat the hosting provider as an adapter around native Git workflows.

## Detect the Provider

Inspect all configured remotes and the selected upstream:

```bash
git remote -v
git remote get-url origin
git branch -vv
```

Recognize both HTTPS and SSH forms. A custom hostname may be a self-hosted GitHub,
GitLab, Bitbucket, or other installation; inspect repository guidance before choosing
a provider tool. Do not send credentials or private remote URLs to unrelated services.

## Select the Interface

### GitHub

Use the relevant available Codex GitHub skill and connected GitHub integration for
repository, pull request, issue, review, comment, check, and Actions operations. Never
use the GitHub CLI (`gh`). If the integration cannot perform a requested operation,
state that limitation and ask the user how to proceed.

### GitLab

Prefer a connected GitLab integration when available. Otherwise, check that `glab` is
installed and authenticated before using it:

```bash
glab auth status
```

Use `glab mr`, `glab ci`, and related commands only for GitLab remotes. Do not run an
interactive login unless the user asks.

### Bitbucket and Other Hosts

Use a connected integration or a repository-approved provider tool when available.
If none is available, continue with native local Git work and explain which remote
operation cannot be completed. Do not substitute a different provider's CLI.

## Normalize Concepts

Use **change request** generically in reasoning and map it at the interface boundary:

- GitHub and Bitbucket: pull request (PR)
- GitLab: merge request (MR)
- Draft, ready, reviewer, thread, check, and pipeline capabilities vary by provider

Do not assume every provider supports draft state, thread resolution, auto-assignment,
labels, milestones, or a ready transition. Apply those actions only when supported and
consistent with project policy.
