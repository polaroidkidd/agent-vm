# Kandev workflows

This directory is the Git source of truth for Kandev Workflow Sync. Immediate `.yaml`
and `.yml` files must use Kandev's portable version 1 `kandev_workflow` envelope.

## Development workflow

`development.yaml` defines the five-step Development workflow. New tasks must use
**Create without starting agent** so they park in Backlog. The **Start task** action
selects the first auto-starting step and therefore bypasses Backlog.

Required agent/runtime capabilities:

- Superpowers and `ggs` are available to every new task session.
- The profile can update Kandev plans, write and commit task worktrees, and push.
- GitHub publication uses the connected Codex GitHub integration, never `gh`.
- Other hosting providers expose the provider integration supported by `ggs`.

## Validate a proposed change

Use a disposable Kandev workspace before changing the active workflow. Configure
**Settings → Workspaces → Workflow Validation → Workflows → Workflow Sync** with:

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository owner | `polaroidkidd` |
| Repository name | `agent-vm` |
| Branch | the pushed validation branch from `git branch --show-current` |
| Directory | `workflows` |
| Auto-sync | disabled for the disposable test |
| Interval | `300` seconds |

The repository must be inside the workspace's effective scope. The workspace GitHub
automation connection needs Contents: read access to this private repository. Select
**Save**, then **Sync now**. Saving alone does not fetch definitions.
Inspect the response body and status card: HTTP success alone is insufficient. Require
`last_ok` to be true, `last_error` to be empty, and no warning for `development.yaml`.

Export the created Development workflow and compare its parsed YAML with
`workflows/development.yaml`. IDs, timestamps, sync ownership, and other documented
non-portable metadata are not part of the comparison.

Smoke-test the state machine in the disposable workspace:

1. **Create without starting agent** produces an idle Backlog task.
2. A manual Backlog-to-Refinement move starts a fresh refinement session.
3. An ordinary completed or cancelled Refinement turn remains in Refinement.
4. A manual Refinement-to-In Progress move starts a fresh implementation session and
   does not ask for plan approval again.
5. In Progress remains in place without `step_complete_kandev`; a valid completion
   signal moves it to Review.
6. Review blockers are written into both plan representations before a move back to
   In Progress.
7. Review remains in place if change-request publication fails.
8. A clean Review with a confirmed ready change request signals Done.
9. A message in Done does not move or restart the task.

Use a throwaway repository for steps that write plans or implementation commits. Use
the real connected hosting integration only for the final ready-change-request path;
never create a draft test request.

## Migrate the active workspace

Workflow Sync never adopts a manual workflow, even when the names match.

1. Confirm the committed workflow is present on the target branch and passed disposable
   validation.
2. Rename the current manual workflow to `Development (legacy)`.
3. Configure the active workspace's Workflow Sync with repository
   `polaroidkidd/agent-vm`, the protected target branch, directory `workflows`,
   Auto-sync enabled, and interval `300` seconds.
4. Save, select **Sync now**, and require a successful status with no warnings.
5. Use the synced `Development` workflow for new tasks.
6. Keep `Development (legacy)` while it owns tasks. Delete it only after those tasks
   have drained or after a separately reviewed task migration.

## Roll back

Select **Remove sync** to stop polling. Kandev releases the synced workflows to manual,
editable ownership and removes the sync configuration; it does not delete the workflows.
Do not remove or rename synced workflow definitions while they still own tasks without
first reviewing Kandev's reconciliation warnings and moving or archiving those tasks.

References:

- <https://kandev.ai/docs/workflow-sync>
- <https://kandev.ai/docs/workflow-import-export>
- <https://kandev.ai/docs/automation-and-mcp>
- <https://kandev.ai/docs/agents-and-profiles>
- <https://kandev.ai/docs/features/git-operations>
