# Open a Pull or Merge Request

Read [provider-routing.md](provider-routing.md) before interacting with the host.

## Prepare

1. Inspect the current branch, upstream, remotes, worktree, and commit range.
2. Detect and verify the target branch; do not assume the remote default is correct
   when the work is based on another feature branch.
3. Run the repository's required local verification.
4. Confirm commits are atomic and follow repository message conventions.
5. Locate the provider's pull or merge request template and read it in full.

Common template locations include `.github/pull_request_template.md`,
`.github/PULL_REQUEST_TEMPLATE.md`,
`.github/PULL_REQUEST_TEMPLATE/*.md`, and
`.gitlab/merge_request_templates/*.md`. Also inspect project instructions for custom
locations.

## Confirm Changeset Handling

Inspect repository conventions such as `.changeset/`, package scripts, release tooling,
or provider-specific release fragments. When the repository uses them and the request
does not already state a preference, ask the user whether to create one before pushing
or opening the change request.

If requested, create the changeset or release fragment using the repository convention,
validate it when a validator exists, and commit it before publication. If declined,
proceed and report that none was added. Do not introduce a changeset system into a
repository that does not already use one unless the user explicitly asks.

## Compose

Derive a leading ticket from the branch when present. Use a concise, imperative title:

```text
TICKET-1234: Add OAuth authentication
```

Do not add agent branding, issue labels, `[codex]`, `Codex:`, or similar prefixes to
the title.

When a project template exists, preserve its headings and instructions, fill only
relevant sections, and remove optional placeholders only when the template permits it.
Do not add custom sections or generator footers.

For a template containing `# Summary` and change-category sections:

- Fill `# Summary` with concrete details from the complete diff, commit history, and
  user request.
- Keep only applicable `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and
  `Security` sections, preserving their original order.
- Delete placeholder comments and empty category sections when the template permits.
- Do not add an `Unreleased` wrapper, Review Notes, Testing, Checklist, verification,
  or other sections unless the template contains them or the user asks.
- Keep the body factual. Do not invent issue links, tests, or manual validation.
- Keep verification details in the final response unless the template contains a place
  for them or the user asks to include them.

When no template exists, use only relevant Keep-a-Changelog categories:

```markdown
### Added
- Add OAuth authentication with PKCE.

### Changed
- Route login through the new authorization flow.

### Fixed
- Prevent stale sessions after token refresh; verify with session tests.
```

Explain cause and fix for substantive bug fixes. Base the description on the complete
diff and commit range, not only the latest commit.

## Publish

Push the current branch only when remote publication is within the request. Open the
change request through the selected provider interface and set the verified target.
Always create it ready for review. Do not create draft pull or merge requests,
including when a user requests one or repository policy normally requires one.

Apply labels, milestones, reviewers, and assignees only when requested or required by
repository policy. Do not carry GitLab-specific assignment conventions to other hosts.

Inspect remote checks after creation and report pending or failing checks.

## Report

In the final response, include the change request URL, target/base branch, source/head
branch, verification run, and current working-tree status. Mention conflicts resolved
and checks skipped or unable to run. Report the ready-for-review state and any
remaining required checks without claiming success for checks that were not observed.
