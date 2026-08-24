# Rebase Safely

## Prepare

1. Read applicable repository instructions.
2. Inspect `git status --short --branch`; do not hide or discard unrelated changes.
3. Determine the target from the request, the change request base, or the remote's
   symbolic default branch. Do not assume `main` or `master`.
4. Inspect the commit range and divergence before rewriting history.

Useful read-only checks:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD
git log --oneline --decorate --graph --max-count=20
git rev-list --left-right --count origin/target...HEAD
```

If the working tree is dirty, preserve it and stop unless the user has clearly
authorized a safe way to isolate or commit those changes.

## Rebase

```bash
git fetch origin target
git rebase origin/target
```

Resolve conflicts according to the intent of both sides, not by blindly choosing
`ours` or `theirs`. Remove conflict markers, stage each resolved path explicitly, and
continue:

```bash
git add path/to/resolved-file
git rebase --continue
```

Use `git rebase --abort` when resolution would require unsupported assumptions or
would risk losing user work.

## Verify and Publish

Run the repository's relevant tests, lint, type checks, and build after the rebase.
Review the rewritten range against the target. If publishing is within the user's
request and the branch was already pushed, use:

```bash
git push --force-with-lease
```

Never use `--force`. Route any subsequent check or change-request inspection through
[provider-routing.md](provider-routing.md).
