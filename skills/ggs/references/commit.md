# Create or Amend Commits

## Inspect and Partition

1. Run `git status --short --branch`.
2. Read unstaged and staged diffs, including untracked files relevant to the request.
3. Inspect recent subjects with `git log -5 --format='%h %s'` to learn local style.
4. Partition the intended work into atomic commits. Keep tightly coupled code and
   small tests together; split unrelated fixes, features, or refactors.
5. Preserve unrelated changes and user-staged content. Do not rewrite the previous
   commit unless the user explicitly asks to amend it.

## Derive the Message

Get the current branch with `git branch --show-current`. When it begins with a ticket
matching `[A-Z][A-Z0-9]*-[0-9]+`, use that exact ticket as the prefix. For example,
`TIMDO-1234--oauth` yields `TIMDO-1234`.

Use the repository's established format. When no stricter convention exists:

```text
TICKET-1234: Add OAuth authentication

### Added
- Add the authorization-code flow with PKCE.

### Fixed
- Prevent stale sessions after token refresh.
```

Omit the ticket prefix when neither the branch nor repository policy provides one.
Keep the subject imperative, capitalized, concise, and without a trailing period.
Include a body only when it adds useful context. Wrap prose near 72 characters and
use only relevant `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or `Security`
sections when that category style matches repository history.

Never include secrets, generated attribution, or `Co-Authored-By` lines unless the
user explicitly requests them.

## Stage and Commit

Stage explicit paths, using patch mode when only part of a file belongs in the commit:

```bash
git add path/to/file path/to/test
git add -p path/to/partially-related-file
git diff --staged --check
git diff --staged
git commit
```

Never use `git add .`, `git add -A`, or `git add -u`. If a hook changes files or
rejects the commit, inspect the result, make only in-scope fixes, explicitly re-stage,
rerun relevant verification, and retry.

For an explicitly requested amend, inspect `git show --stat --oneline HEAD` and the
existing message before using `git commit --amend`. Update the message only when the
amended content changes what it claims.

After each commit, verify `git status --short --branch` and show the resulting commit
with `git log -1 --format='%h %s'`.
