---
name: ggs
description: "Global Git Skills: platform-agnostic workflows for inspecting Git repositories, creating atomic commits, handling repository changeset conventions, deriving ticket-aware messages, rebasing safely, opening or updating pull/merge requests, addressing review feedback, and diagnosing CI. Use for Git work across GitHub, GitLab, Bitbucket, and other hosting platforms; route hosting actions through the repository's connected integration or supported provider tool."
---

# Global Git Skills

Apply consistent Git practices without assuming a hosting platform, default branch,
ticket prefix, package manager, or CI system.

## Establish Context

1. Read applicable `AGENTS.md` files and repository contribution guidance.
2. Inspect `git status`, the current branch, remotes, recent history, and relevant diffs.
3. Detect the hosting platform from `git remote get-url origin`; do not infer it from
   local directory names.
4. Detect repository conventions from hooks, history, templates, and project docs.
5. Preserve unrelated user changes and stop before destructive or ambiguous actions.

## Route Hosting Actions

- Use native `git` for local history, staging, commits, fetches, rebases, and pushes.
- For GitHub repositories, use the relevant Codex GitHub skill and connected GitHub
  integration for pull requests, issues, reviews, comments, and checks. Never use `gh`.
- For GitLab repositories, use an available connected integration; otherwise use
  authenticated `glab` when installed and allowed.
- For other hosts, prefer an available connected integration or supported host tool.
  If no capable integration exists, explain the limitation before attempting a
  different interface.
- Follow project and user instructions when they impose a stricter tool policy.

Read [references/provider-routing.md](references/provider-routing.md) before any
remote hosting action.

## Apply Global Rules

- Make one logical change per commit.
- Stage explicit paths. Never use `git add .`, `git add -A`, or `git add -u`.
- Review `git diff --staged` immediately before committing.
- Derive a leading ticket such as `ABC-123` from the branch when present; never
  hardcode a project prefix. If absent, follow repository history or stated policy.
- Use imperative, capitalized subjects with no trailing period. Honor stricter local
  length and body conventions.
- Never add generated attribution or `Co-Authored-By` lines unless the user asks.
- Detect the default or target branch; do not assume `main` or `master`.
- Use `--force-with-lease`, never `--force`, when rewriting a published branch.
- Run the repository's own verification commands before pushing or requesting review.
- Before opening a change request, detect repository changeset or release-fragment
  conventions and resolve whether the current change needs one before pushing.
- Always create change requests ready for review. Do not create draft pull or merge
  requests, including when a user requests one or repository policy normally requires
  one.
- Use the repository's pull or merge request template exactly when one exists. Remove
  irrelevant optional sections and do not add custom generator footers.
- Never add agent branding such as `[codex]`, `Codex:`, or similar labels to change
  request titles.
- Address review feedback before replying or resolving. Preserve review context by
  preferring follow-up commits once review has started.

## Select a Workflow

- Create or amend commits: read [references/commit.md](references/commit.md).
- Rebase onto a target branch: read [references/rebase.md](references/rebase.md).
- Open a pull or merge request: read
  [references/open-change-request.md](references/open-change-request.md).
- Update a pull or merge request or address feedback: read
  [references/update-change-request.md](references/update-change-request.md).
- Diagnose or fix CI: read [references/fix-ci.md](references/fix-ci.md).

Load only the reference needed for the requested workflow, plus provider routing when
the workflow touches the hosting platform.
