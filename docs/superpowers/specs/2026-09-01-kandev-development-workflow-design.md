# Kandev Development Workflow Design

Date: 2026-09-01
Status: Approved

## Problem

The current Kandev `Development` workflow starts work too eagerly, does not provide a
strict human refinement gate, and does not preserve an approved plan as a committed
repository artifact. Implementation, review, publication, and terminal behavior also
need explicit completion guards so incomplete or cancelled agent turns cannot advance a
task.

## Current Behavior

The current workflow contains Backlog, Refinement, In Progress, Review, and Done.
Backlog immediately advances on turn start, Refinement does not auto-start, In Progress
can advance after an ordinary completed turn, Review moves backward on turn start, and
Done sends a task back to In Progress on turn start. Review uses only a local review
prompt and does not own publication of the change request.

## Desired Behavior

```text
Create without starting agent
            |
            v
         Backlog --human move--> Refinement --human approval/move--> In Progress
                                                                      ^       |
                                                                      |       | completion signal
                                                                      |       v
                                                                      +---- Review
                                                                    blockers   |
                                                                               | ready PR/MR + signal
                                                                               v
                                                                              Done
```

Backlog is a dormant parking state. A human manually moves a task into Refinement.
Refinement starts automatically in a fresh context, resolves ambiguity, and produces an
approved, committed plan. Moving the task from Refinement to In Progress is the approval
signal. In Progress starts automatically in another fresh context, implements the plan,
commits and pushes the work, and signals completion. Review starts in a fresh context,
returns blocker findings to In Progress, or opens a ready-for-review change request and
signals Done. Done is terminal.

## Documented Kandev Constraints

- Tasks must be created with **Create without starting agent**. Kandev's **Start task**
  action selects the first positional step with `auto_start_agent`, which would bypass
  Backlog and start Refinement.
- `allow_manual_move` is a board affordance rather than an authorization boundary. The
  human-only gate is therefore a process guarantee: Backlog has no running agent or
  transition events, while privileged external task APIs may still move a task.
- Refinement must not use `pull_from_step_position`, because pull behavior could promote
  Backlog tasks without a human move.
- Automatic In Progress and Review transitions use
  `auto_advance_requires_signal: true`. Explicit cancellation does not count as
  completion because `cancel_triggers_turn_complete` is false.
- Workflow Sync matches synced workflows by source path and name and does not adopt a
  manual workflow with the same name.
- The workflow YAML cannot install agent-native skills or supply a hosting integration.
  Those are runtime prerequisites of the selected agent profile.

## Source of Truth and Migration

The portable version 1 workflow definition will live at:

```text
workflows/development.yaml
```

Kandev Workflow Sync will read the `workflows` directory from the configured branch of
`polaroidkidd/agent-vm`. The synced definition is authoritative and intentionally
read-only in Kandev's workflow editor.

`services.kandev.workflow_sync` in the private agent-vm configuration declares the
target workspace, repository, branch, directory, polling interval, and polling state.
Normal provisioning idempotently saves that configuration after Kandev starts. The
separate `configure-kandev-workflow` command forces the first reconciliation after the
workspace GitHub automation connection exists and rejects errors or warnings. Doctor
checks the same stored configuration and last-sync status.

Migration must preserve the existing manual workflow and its tasks:

1. Validate the synced workflow in a disposable Kandev workspace.
2. Rename the current manual workflow to `Development (legacy)`.
3. Run the declarative Workflow Sync configurator so it creates the synced
   `Development` workflow.
4. Use the synced workflow for new tasks.
5. Leave the legacy workflow in place until its tasks have drained or been moved safely.
6. Delete the legacy workflow only through a separately approved cleanup action.

## Step Design

### Backlog

- Position 0 and the sole start step.
- No prompt or workflow events.
- Manual movement enabled.
- Hidden from the command panel.
- No WIP feeder or automatic advancement.
- Tasks arrive here only through **Create without starting agent**.

### Refinement

- Position 1 with a WIP limit of three and no pull source.
- On entry, reset agent context and then auto-start the agent.
- Do not enable Kandev plan mode because refinement must write and commit the Markdown
  plan; the prompt itself forbids production-code changes.
- Do not define a turn-complete transition. The task remains awaiting human approval.
- On exit, no automatic action is required.

The refinement prompt must:

1. Inspect the repository and determine whether the request still applies.
2. Discover Superpowers from the active agent's skill catalog and load only the skills
   required for the current phase.
3. If Superpowers is missing, report the blocker and remain in Refinement.
4. If the task description is light, ask whether the user wants to brainstorm it first
   and wait for the answer before continuing.
5. When brainstorming is requested, follow the Superpowers brainstorming flow before
   continuing into planning.
6. Locate affected code, dependencies, edge cases, and architectural decisions without
   modifying production code.
7. Ask one focused question at a time when a material decision cannot be inferred.
8. Include a section headed exactly:
   **Which assumptions need to be true in order for your plan to be successful?**
9. Create or update the single shared Kandev task plan.
10. Mirror the authoritative Kandev plan exactly to
    `docs/plans/<task-id>.md` in the task worktree.
11. Use `ggs` to commit only the plan artifact. Do not push or open a change request.
12. Remain in Refinement after summarizing the problem, current and desired behavior,
    approach, acceptance criteria, test strategy, assumptions, and open questions.

### In Progress

- Position 2.
- On entry, reset agent context and then auto-start the agent.
- On turn completion, move to Review only after `step_complete_kandev` is received.
- Explicit cancellation never advances the task.

The implementation prompt must:

1. Read the shared Kandev task plan before changing code.
2. Read `docs/plans/<task-id>.md` and treat the Kandev plan as authoritative.
3. If the plans differ because of UI edits, synchronize the Markdown plan and make a
   plan-only `ggs` commit before implementation.
4. Treat the manual move into In Progress as approval; do not request approval again.
5. Load the applicable Superpowers execution skills lazily when they are available.
6. Implement the approved plan, including its tests and verification.
7. Preserve unrelated work and use `ggs` for explicit-path, atomic commits.
8. Push all implementation commits to the configured repository.
9. Never open a pull or merge request from In Progress.
10. Call `step_complete_kandev` only when required verification passes, intended changes
    are committed, the push succeeds, and no implementation blocker remains.

### Review

- Position 3.
- On entry, reset agent context and then auto-start the agent.
- On turn completion, move to Done only after `step_complete_kandev` is received.
- Explicit cancellation never advances the task.

The review prompt must:

1. Load `ggs`, read the authoritative task plan, and resolve the intended
   change-request target from an existing change request, an explicit approved-plan or
   task target, or user confirmation. The remote default is not a substitute for a
   confirmed target.
2. Refresh the target's remote-tracking ref and always review the merge-base-to-HEAD
   committed range, even when the worktree is dirty.
3. Separately inspect staged, unstaged, and untracked changes; union task-related
   contents with the committed review set while preserving and excluding unrelated
   working-tree changes.
4. Treat intended task changes outside HEAD as publication blockers because they are
   absent from the pushed change-request branch.
5. Read each changed file and relevant callers, interfaces, tests, and blame context.
6. Report only issues introduced by the changeset with at least 80 percent confidence.
7. Classify findings as `BLOCKER` or `SUGGESTION`; suggestions are non-blocking.
8. Include file and line, impact, and a concrete fix for every finding.
9. Never modify production code while reviewing.
10. When blockers exist, append a review-fix phase containing the exact blockers to the
   shared Kandev task plan, mirror it to the Markdown plan, commit only that plan update
   with `ggs`, and use the available Kandev task lifecycle tool to move the task to In
   Progress. Do not emit the completion signal or open a change request.
11. When no blockers exist, use `ggs` and the connected hosting-provider integration to
   open a ready-for-review pull or merge request. Never use PR-Agent or create a draft.
12. If target resolution, target refresh, publication, or provider access fails, remain
    in Review and report the blocker.
13. After confirming the ready change request and its URL, call
    `step_complete_kandev` with a concise review and publication summary.

For GitHub, `ggs` must use the connected Codex GitHub integration and must never invoke
the GitHub CLI. Other providers follow the provider routing defined by `ggs`.

### Done

- Position 4.
- No prompt or events.
- Hidden from the command panel.
- Terminal: user messages do not restart implementation or move the task.

## Failure Handling

- Missing Superpowers, `ggs`, Kandev task tools, Git credentials, push access, or a
  supported hosting integration prevents the current gated step from completing.
- A failed plan commit keeps the task in Refinement or In Progress as applicable.
- Failed verification or push keeps the task in In Progress.
- Review blockers are persisted in both plan representations before the task moves.
- Failed change-request creation keeps the task in Review.
- Cancellation never executes a completion transition.
- Agents must not call the completion signal merely because their turn or context is
  ending.

## Assumptions Required for Success

- Users create tasks with **Create without starting agent**.
- The selected agent profile exposes Superpowers and `ggs` in new sessions.
- The profile can write the worktree and Git metadata and can push the task branch.
- Supported sessions expose Kandev's shared-plan, task-lifecycle, and completion-signal
  tools.
- GitHub tasks use an agent with the connected Codex GitHub integration; `gh` is not a
  fallback.
- The Workflow Sync integration can read the repository, configured branch, and
  `workflows` directory.
- The private agent-vm configuration names exactly one target workspace and contains
  the expected GitHub Workflow Sync fields.
- Task IDs are safe to use as Markdown filenames.
- The repository permits a `docs/plans` directory and plan-only commits.

## Acceptance Criteria

- A task created without starting an agent appears in Backlog and no agent runs.
- Nothing automatically promotes a Backlog task.
- A manual move to Refinement starts a fresh refinement session.
- Light descriptions cause the brainstorm question before planning continues.
- Refinement exposes the required assumptions section and commits synchronized Kandev
  and Markdown plans without changing production code.
- Refinement never advances on turn completion or cancellation.
- A manual move to In Progress starts a fresh implementation session without another
  approval prompt.
- UI plan edits are committed to the Markdown plan before implementation.
- In Progress cannot reach Review without successful verification, commits, push, and
  the explicit completion signal.
- Review starts with a fresh context and returns blockers to In Progress with a
  persisted handoff.
- Review always covers the confirmed target's merge-base-to-HEAD diff, even when
  unrelated worktree changes exist, and includes intended staged, unstaged, or
  untracked contents.
- A missing or ambiguous target and intended task changes outside HEAD prevent
  publication.
- Suggestions alone do not prevent publication.
- A clean review opens exactly one ready-for-review change request through `ggs` and
  then advances to Done.
- Failed publication remains in Review.
- Done has no automatic exit or restart behavior.
- No workflow prompt, event, or step references PR-Agent.

## Validation Strategy

### Static validation

- Parse the YAML as a version 1 `kandev_workflow` document.
- Assert unique contiguous positions and exactly one start step.
- Assert Backlog and Done have empty event maps.
- Assert Refinement has no turn-complete move and no pull source.
- Assert In Progress and Review require completion signals and reject cancellation as
  completion.
- Assert only recognized portable event types and valid step positions are used.
- Assert prompts contain the required skill, plan, Git, review, and publication guards.
- Assert the workflow contains no PR-Agent references.
- Validate the config-to-Ansible Workflow Sync path, idempotent API reconciliation,
  clean forced-sync result, and doctor status parser.

### Kandev integration validation

1. Configure Workflow Sync in a disposable workspace.
2. Confirm the synced workflow is read-only and export it.
3. Compare all round-tripped fields with the committed YAML.
4. Exercise task creation and every manual and automatic transition.
5. Verify an ordinary completed turn and an explicit cancellation cannot advance gated
   steps.
6. Verify a missing skill, failed plan commit, failed test, failed push, and failed
   publication each leave the task in the correct step.
7. Exercise both Review paths: blocker return and ready change-request publication.
8. Confirm Done remains terminal after a user message.

The installed Kandev version is authoritative for the live smoke test. The public docs
describe current `main`, so successful static validation alone is not sufficient.

## Kandev Documentation References

- [Tasks and workflows](https://kandev.ai/docs/core-concepts/tasks)
- [Workflow Import and Export](https://kandev.ai/docs/workflow-import-export)
- [Workflow Sync](https://kandev.ai/docs/workflow-sync)
- [Automation and MCP](https://kandev.ai/docs/automation-and-mcp)
- [Agents and Profiles](https://kandev.ai/docs/agents-and-profiles)
- [Git Operations](https://kandev.ai/docs/features/git-operations)

## Open Questions

None. Superpowers installation is intentionally outside this plan and will be completed
separately by the user.
