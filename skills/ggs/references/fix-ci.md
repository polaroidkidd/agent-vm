# Diagnose or Fix CI

Read [provider-routing.md](provider-routing.md) before inspecting remote checks.

## Diagnose

1. Determine whether the user asked for diagnosis only or authorized a fix.
2. Fetch the failing check, pipeline, workflow, job, and logs through the selected
   provider interface.
3. Record the exact command, error, environment, and first meaningful failure. Do not
   treat later cascade errors as independent root causes.
4. Read the repository's CI configuration and local scripts to identify the canonical
   reproduction command.
5. Reproduce locally when safe. Separate code failures from flaky tests, environment
   differences, missing secrets, permissions, and provider outages.

For GitHub, use the connected Codex GitHub integration and never `gh`. For GitLab,
prefer a connected integration; otherwise authenticated `glab ci` commands may inspect
pipeline status and traces.

## Fix

When a fix is authorized, make the smallest change that addresses the root cause. Run
the focused failing check first, then the repository's broader required verification.
Review the diff and follow [commit.md](commit.md) when a commit is requested.

Push only when remote publication is within scope. After pushing, monitor the new run
through the provider interface and report each required check's current status. Do not
mark a change request ready while required checks are pending or failing.

If logs or rerun controls are unavailable through the approved integration, explain
the limitation and ask the user how to proceed instead of switching to a prohibited
CLI or scraping private CI pages.
