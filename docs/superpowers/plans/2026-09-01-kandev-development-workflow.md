# Kandev Development Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Git-synced Kandev Development workflow that parks new tasks in Backlog, performs automatic plan refinement behind a human approval gate, implements and publishes verified commits, reviews the branch, and ends after opening a ready change request.

**Architecture:** Store one portable version 1 Kandev workflow in `workflows/development.yaml` and make that file the Workflow Sync source of truth. Protect the state machine with empty terminal/parking event maps, human moves for approval, fresh auto-started sessions for active phases, and explicit completion signals for implementation and review. Validate the portable schema and critical prompt contracts with repository unit tests, then round-trip and smoke-test the definition in a disposable Kandev workspace before production migration.

**Tech Stack:** Kandev portable workflow YAML and Workflow Sync, Python 3.12 `unittest`, PyYAML, Pi Agent Skills, Superpowers, `ggs`, Git, connected hosting-provider integration.

**Spec:** `docs/superpowers/specs/2026-09-01-kandev-development-workflow-design.md`

## Global Constraints

- Use **Create without starting agent** for every newly parked task; Kandev's **Start task** action does not satisfy the Backlog requirement.
- Backlog-to-Refinement is a human process gate, not a security authorization boundary.
- Superpowers installation is external to this implementation and must not be added or changed here.
- Do not add a PR-Agent step, prompt, event, integration, or review gate.
- The shared Kandev task plan is authoritative; mirror it to `docs/plans/<task-id>.md` and commit it.
- A manual Refinement-to-In Progress move is approval and must not trigger another approval question.
- In Progress uses `ggs` to create atomic commits and push, but never opens a change request.
- Review returns only `BLOCKER` findings to In Progress; `SUGGESTION` findings are non-blocking.
- Review opens a ready-for-review pull or merge request through `ggs`; never create a draft.
- For GitHub hosting operations, use the connected Codex GitHub integration and never use `gh`.
- Set `auto_advance_requires_signal: true` and `cancel_triggers_turn_complete: false` on In Progress and Review.
- Preserve all unrelated work already present in the worktree; stage explicit paths only.
- Treat the installed Kandev version and a successful live round trip as authoritative over the unversioned public documentation.

---

## File Map

- Create `workflows/development.yaml`: portable Workflow Sync definition and all step prompts/events.
- Create `tests/test_workflows.py`: static schema, state-machine, and prompt-contract regression tests.
- Create `workflows/README.md`: Workflow Sync configuration, migration, rollback, and live-validation runbook.
- Keep `docs/superpowers/specs/2026-09-01-kandev-development-workflow-design.md` unchanged as the approved requirements source.
- Do not modify current PR-Agent provisioning files or other existing dirty files.

### Task 1: Define and test the portable workflow

**Files:**
- Create: `tests/test_workflows.py`
- Create: `workflows/development.yaml`

**Interfaces:**
- Consumes: Kandev portable workflow schema version `1` and the approved design specification.
- Produces: one workflow named `Development` with exact step names `Backlog`, `Refinement`, `In Progress`, `Review`, and `Done`; `WorkflowDefinitionTests.workflow` is the parsed workflow mapping used by every test.

- [ ] **Step 1: Write the failing workflow contract tests**

Create `tests/test_workflows.py` with this content:

```python
from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "development.yaml"


class WorkflowDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
        cls.workflow = cls.document["workflows"][0]
        cls.steps = {step["name"]: step for step in cls.workflow["steps"]}

    def test_portable_envelope_and_step_order(self):
        self.assertEqual(1, self.document["version"])
        self.assertEqual("kandev_workflow", self.document["type"])
        self.assertEqual(1, len(self.document["workflows"]))
        self.assertEqual("Development", self.workflow["name"])
        self.assertEqual(
            ["Backlog", "Refinement", "In Progress", "Review", "Done"],
            [step["name"] for step in self.workflow["steps"]],
        )
        self.assertEqual([0, 1, 2, 3, 4], [step["position"] for step in self.workflow["steps"]])
        self.assertEqual(1, sum(step["is_start_step"] for step in self.workflow["steps"]))

    def test_backlog_is_a_dormant_human_gate(self):
        step = self.steps["Backlog"]
        self.assertTrue(step["is_start_step"])
        self.assertEqual({}, step["events"])
        self.assertTrue(step["allow_manual_move"])
        self.assertFalse(step["show_in_command_panel"])
        self.assertFalse(step["auto_advance_requires_signal"])
        self.assertFalse(step["cancel_triggers_turn_complete"])
        self.assertNotIn("prompt", step)
        self.assertNotIn("pull_from_step_position", step)

    def test_refinement_resets_and_starts_without_auto_advancing(self):
        step = self.steps["Refinement"]
        self.assertEqual(
            [
                {"type": "reset_agent_context"},
                {"type": "auto_start_agent"},
            ],
            step["events"]["on_enter"],
        )
        self.assertNotIn("on_turn_complete", step["events"])
        self.assertEqual(3, step["wip_limit"])
        self.assertNotIn("pull_from_step_position", step)
        self.assertFalse(step["auto_advance_requires_signal"])
        self.assertFalse(step["cancel_triggers_turn_complete"])

    def test_in_progress_requires_signal_before_review(self):
        step = self.steps["In Progress"]
        self.assertEqual(
            [
                {"type": "reset_agent_context"},
                {"type": "auto_start_agent"},
            ],
            step["events"]["on_enter"],
        )
        self.assertEqual(
            [{"type": "move_to_step", "config": {"step_position": 3}}],
            step["events"]["on_turn_complete"],
        )
        self.assertTrue(step["auto_advance_requires_signal"])
        self.assertFalse(step["cancel_triggers_turn_complete"])

    def test_review_requires_signal_before_done(self):
        step = self.steps["Review"]
        self.assertEqual(
            [
                {"type": "reset_agent_context"},
                {"type": "auto_start_agent"},
            ],
            step["events"]["on_enter"],
        )
        self.assertEqual(
            [{"type": "move_to_step", "config": {"step_position": 4}}],
            step["events"]["on_turn_complete"],
        )
        self.assertTrue(step["auto_advance_requires_signal"])
        self.assertFalse(step["cancel_triggers_turn_complete"])

    def test_done_is_terminal(self):
        step = self.steps["Done"]
        self.assertEqual({}, step["events"])
        self.assertFalse(step["is_start_step"])
        self.assertFalse(step["show_in_command_panel"])
        self.assertFalse(step["auto_advance_requires_signal"])
        self.assertFalse(step["cancel_triggers_turn_complete"])
        self.assertNotIn("prompt", step)

    def test_refinement_prompt_contains_required_contracts(self):
        prompt = self.steps["Refinement"]["prompt"]
        for text in (
            "{{task_prompt}}",
            "Do not modify production code",
            "Superpowers",
            "brainstorm",
            "Which assumptions need to be true in order for your plan to be successful?",
            "create_task_plan_kandev",
            "get_task_plan_kandev",
            "update_task_plan_kandev",
            "docs/plans/<task-id>.md",
            "ggs",
            "Do not call `step_complete_kandev`",
        ):
            self.assertIn(text, prompt)

    def test_implementation_prompt_contains_required_contracts(self):
        prompt = self.steps["In Progress"]["prompt"]
        for text in (
            "get_task_plan_kandev",
            "docs/plans/<task-id>.md",
            "authoritative",
            "approved",
            "ggs",
            "push",
            "Do not open a pull or merge request",
            "step_complete_kandev",
        ):
            self.assertIn(text, prompt)

    def test_review_prompt_contains_required_contracts(self):
        prompt = self.steps["Review"]["prompt"]
        for text in (
            "BLOCKER",
            "SUGGESTION",
            "80%",
            "merge-base",
            "update_task_plan_kandev",
            "docs/plans/<task-id>.md",
            "move this task to In Progress",
            "ggs",
            "ready for review",
            "connected Codex GitHub integration",
            "Never use the GitHub CLI (`gh`)",
            "step_complete_kandev",
        ):
            self.assertIn(text, prompt)

    def test_workflow_has_no_pr_agent_integration(self):
        self.assertNotIn("pr-agent", WORKFLOW_PATH.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused tests and verify the missing definition fails**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_workflows -v
```

Expected: `ERROR` from `FileNotFoundError` for `workflows/development.yaml`.

- [ ] **Step 3: Add the exact portable workflow definition**

Create `workflows/development.yaml` with this content:

```yaml
version: 1
type: kandev_workflow
workflows:
  - name: Development
    description: Refine, approve, implement, review, and publish development tasks.
    steps:
      - name: Backlog
        position: 0
        color: bg-neutral-400
        events: {}
        is_start_step: true
        show_in_command_panel: false
        allow_manual_move: true
        auto_advance_requires_signal: false
        cancel_triggers_turn_complete: false

      - name: Refinement
        position: 1
        color: bg-slate-500
        prompt: |-
          {{task_prompt}}

          Refine this task into an implementation-ready specification.

          Do not modify production code. You may inspect the repository, update the
          Kandev task plan, write its Markdown mirror, and commit only that plan file.

          Skill loading:

          1. Inspect the active skill catalog for Superpowers. Load only the skills
             required for the current refinement phase.
          2. If Superpowers is unavailable, report that prerequisite as a blocker and
             remain in Refinement. Do not claim the plan is complete.
          3. If the task description is light or underspecified, ask the user whether
             the task should be brainstormed further before refinement continues. Wait
             for the answer. If approved, follow the Superpowers brainstorming flow.
          4. Continue with the applicable Superpowers planning flow after requirements
             and design decisions are approved.

          During refinement:

          1. Determine whether the requested behavior is still relevant to the current
             codebase.
          2. Locate the affected applications, packages, modules, callers, tests, and
             existing implementation.
          3. Identify ambiguities, missing requirements, edge cases, dependencies, and
             architectural decisions.
          4. Ask one focused question at a time whenever a product, UX, architectural,
             or behavioral decision cannot be inferred safely.
          5. Propose a concrete implementation approach with acceptance criteria and a
             test strategy.
          6. Include a Markdown section headed exactly:

             ## Which assumptions need to be true in order for your plan to be successful?

             Answer it with concrete runtime, repository, integration, credential, and
             behavioral assumptions. Do not merely repeat requirements.

          Plan persistence:

          1. Discover the canonical create_task_plan_kandev,
             get_task_plan_kandev, and update_task_plan_kandev tools in the active
             Kandev task server.
          2. Create or update the single shared Kandev task plan. This plan is the
             authoritative representation.
          3. Obtain the current Kandev task ID from task context and mirror the exact
             authoritative Markdown to docs/plans/<task-id>.md in the task worktree.
          4. Use the ggs skill to inspect Git state, stage only the Markdown plan, review
             the staged diff, and commit it atomically. Do not push and do not open a
             pull or merge request.
          5. If either plan representation cannot be updated or the plan commit fails,
             report the blocker and remain in Refinement.

          When sufficiently specified, summarize:

          - Problem
          - Current behavior
          - Desired behavior
          - Proposed implementation
          - Acceptance criteria
          - Test strategy
          - Which assumptions need to be true in order for your plan to be successful?
          - Open questions

          The task must remain awaiting human approval. Do not call
          `step_complete_kandev`; a manual move to In Progress is the approval signal.
        events:
          on_enter:
            - type: reset_agent_context
            - type: auto_start_agent
        is_start_step: false
        show_in_command_panel: true
        allow_manual_move: true
        auto_advance_requires_signal: false
        cancel_triggers_turn_complete: false
        wip_limit: 3

      - name: In Progress
        position: 2
        color: bg-blue-500
        prompt: |-
          {{task_prompt}}

          The human move into In Progress approves the current plan. Do not ask for
          plan approval again. Start implementation automatically.

          1. Discover and call get_task_plan_kandev, then read the complete shared
             Kandev task plan before changing code.
          2. Read docs/plans/<task-id>.md. The Kandev task plan is authoritative. If a
             user edited it in Kandev, mirror the exact current plan to the Markdown
             file and use ggs to make a plan-only commit before implementation.
          3. Lazily load the applicable Superpowers execution skills when available and
             implement the approved plan task by task.
          4. Add or update the specified tests. Run verification proportional to risk
             and confirm the actual command output before claiming success.
          5. Preserve unrelated work. Use ggs to stage explicit paths, inspect staged
             diffs, and create atomic commits that follow repository conventions.
          6. Use ggs to push every implementation and plan-sync commit to the configured
             repository and verify the remote branch.
          7. Do not open a pull or merge request from In Progress.

          If implementation, verification, commit, or push is incomplete or blocked,
          explain the blocker and remain in In Progress. Do not signal completion merely
          because the turn or context is ending.

          Only after the approved plan is fully implemented, required verification has
          passed, all intended changes are committed, and the push has succeeded,
          discover and call step_complete_kandev with a concise implementation and
          verification summary. That signal advances the task to Review.
        events:
          on_enter:
            - type: reset_agent_context
            - type: auto_start_agent
          on_turn_complete:
            - type: move_to_step
              config:
                step_position: 3
        is_start_step: false
        show_in_command_panel: true
        allow_manual_move: true
        auto_advance_requires_signal: true
        cancel_triggers_turn_complete: false

      - name: Review
        position: 3
        color: bg-yellow-500
        prompt: |-
          Review the changed files in the current Git worktree. Do not modify production
          code during review.

          Determine the review range:

          - If there are uncommitted or staged changes, review those changed files.
          - If the worktree is clean, detect the remote default branch, set BASE_REF to
            its remote-tracking ref, compute `git merge-base "$BASE_REF" HEAD`, and
            review only the cumulative branch commits and diff after that merge-base.
          - Never diff directly against an outdated default-branch tip.
          - Read every changed file in full and inspect relevant callers, interfaces,
            tests, and git blame context.
          - Report issues only on code modified by this changeset, using the rest of the
            repository only as context.

          Review architectural fit, state and data modeling, security, correctness,
          concurrency, performance, resource lifetime, and maintainability. Ignore
          pre-existing issues, intentional task behavior, lint-only failures, pedantic
          preferences, and vague requests for more tests.

          Report only findings with at least 80% confidence. Use these sections and omit
          empty ones:

          ## BLOCKER

          Must be fixed before publication: architectural boundary violations,
          security vulnerabilities, data-loss risks, crashes, or broken behavior.

          ## SUGGESTION

          Concrete non-blocking architecture, performance, maintainability, or targeted
          test improvements.

          Every finding must include file and line, what is wrong, why it matters, and
          how to fix it.

          If BLOCKER findings exist:

          1. Discover get_task_plan_kandev and update_task_plan_kandev.
          2. Append a review-fix phase containing the exact blocker findings to the
             authoritative Kandev task plan.
          3. Mirror the resulting plan exactly to docs/plans/<task-id>.md and use ggs to
             commit only that plan update.
          4. Discover the available Kandev task-lifecycle move tool and move this task to In Progress
             as the final action of the review turn.
          5. Do not open a pull or merge request and do not call
             step_complete_kandev.

          If there are no BLOCKER findings, SUGGESTION findings do not prevent
          publication:

          1. Load ggs and follow its open-change-request workflow.
          2. Detect an existing change request for the current branch and reuse it rather
             than creating a duplicate.
          3. Open or confirm exactly one change request in ready for review state. Never
             create a draft.
          4. For GitHub, use the connected Codex GitHub integration. Never use the
             GitHub CLI (`gh`). For another provider, follow ggs provider routing.
          5. If no supported provider integration is available or publication fails,
             report the blocker and remain in Review.
          6. Confirm the change-request URL, base branch, head branch, ready state, and
             current checks.
          7. Discover and call step_complete_kandev with the verdict, non-blocking
             suggestions, verification summary, and confirmed URL. This signal advances
             the task to Done.
        events:
          on_enter:
            - type: reset_agent_context
            - type: auto_start_agent
          on_turn_complete:
            - type: move_to_step
              config:
                step_position: 4
        is_start_step: false
        show_in_command_panel: true
        allow_manual_move: true
        auto_advance_requires_signal: true
        cancel_triggers_turn_complete: false

      - name: Done
        position: 4
        color: bg-green-500
        events: {}
        is_start_step: false
        show_in_command_panel: false
        allow_manual_move: true
        auto_advance_requires_signal: false
        cancel_triggers_turn_complete: false
```

- [ ] **Step 4: Run the focused tests and verify the definition passes**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_workflows -v
```

Expected: all ten `WorkflowDefinitionTests` tests pass.

- [ ] **Step 5: Run YAML and whitespace validation**

Run:

```bash
/usr/bin/python3 -c 'import pathlib, yaml; p=pathlib.Path("workflows/development.yaml"); d=yaml.safe_load(p.read_text()); assert d["version"] == 1 and d["type"] == "kandev_workflow" and len(d["workflows"]) == 1'
git diff --check -- workflows/development.yaml tests/test_workflows.py
```

Expected: both commands exit `0` with no output.

- [ ] **Step 6: Commit the workflow and its regression tests atomically**

Use `ggs` and run:

```bash
git add workflows/development.yaml tests/test_workflows.py
git diff --staged --check
git diff --staged
git commit -m "Add Git-synced Kandev development workflow"
```

Expected: one commit containing only the workflow definition and its tests.

### Task 2: Document Workflow Sync rollout and rollback

**Files:**
- Create: `workflows/README.md`

**Interfaces:**
- Consumes: `workflows/development.yaml`, GitHub repository `polaroidkidd/agent-vm`, and Kandev Workflow Sync.
- Produces: an operator runbook with exact development, validation, migration, and rollback settings.

- [ ] **Step 1: Add the Workflow Sync runbook**

Create `workflows/README.md` with this content:

```markdown
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
6. Review blockers are written into both plan representations before a move back to In
   Progress.
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
```

- [ ] **Step 2: Validate the runbook against the committed definition**

Run:

```bash
test -f workflows/development.yaml
test -f workflows/README.md
rg -n "Create without starting agent|polaroidkidd|agent-vm|Workflow Validation|last_ok|Development \\(legacy\\)|Remove sync" workflows/README.md
git diff --check -- workflows/README.md
```

Expected: every required operational marker is printed by `rg`; the other commands exit
`0` with no output.

- [ ] **Step 3: Run the complete repository verification**

Run:

```bash
make check
```

Expected: the complete unit suite passes, Python compilation succeeds, and
`git diff --check` reports no whitespace errors.

- [ ] **Step 4: Commit the runbook separately**

Use `ggs` and run:

```bash
git add workflows/README.md
git diff --staged --check
git diff --staged
git commit -m "Document Kandev workflow sync operations"
```

Expected: one documentation-only commit containing `workflows/README.md`.

### Task 3: Publish and round-trip the workflow in disposable Kandev

**Files:**
- Verify: `workflows/development.yaml`
- Verify: `workflows/README.md`
- Verify: `tests/test_workflows.py`

**Interfaces:**
- Consumes: the connected workspace GitHub automation connection and the current pushed Git branch.
- Produces: a successful Kandev Workflow Sync status and an exported portable definition equivalent to the committed YAML.

- [ ] **Step 1: Verify the implementation branch before publication**

Use `ggs` to inspect the current branch, upstream, remotes, commits, and worktree. The
implementation must run from the isolated worktree created at execution time; unrelated
changes from the original checkout must not appear.

Run:

```bash
git status --short --branch
git remote -v
git log --oneline --decorate -5
make check
```

Expected: the intended workflow commits are present, `make check` passes, and the
implementation worktree is clean.

- [ ] **Step 2: Push the implementation branch with `ggs`**

Stage nothing. Use native Git through the `ggs` push workflow and establish the upstream
only when it is absent:

```bash
git push -u origin HEAD
```

Expected: the push succeeds and `git status --short --branch` shows the local branch
tracking its remote with no divergence.

- [ ] **Step 3: Configure disposable Workflow Sync**

In Kandev, create or select the disposable workspace named `Workflow Validation`. Give
its GitHub automation connection Contents: read access to `polaroidkidd/agent-vm`.
Configure Workflow Sync exactly as documented in `workflows/README.md`, using the pushed
branch reported by `git branch --show-current`, directory `workflows`, polling disabled,
and interval `300`.

Expected after **Save** and **Sync now**:

- one sync-owned workflow named `Development` is created or updated;
- `config.last_ok` is true;
- `config.last_error` is empty;
- `development.yaml` has no warning;
- the workflow is read-only in Kandev's normal workflow editor.

Do not proceed on HTTP `200` alone because Kandev can return a completed sync response
whose JSON contains `error`.

- [ ] **Step 4: Export and compare the round-tripped workflow**

Export only the disposable synced `Development` workflow from Kandev. Save the result
outside the repository as `/tmp/kandev-development-export.yaml`, then run:

```bash
/usr/bin/python3 - <<'PY'
from pathlib import Path
import yaml

expected = yaml.safe_load(Path("workflows/development.yaml").read_text(encoding="utf-8"))
actual = yaml.safe_load(Path("/tmp/kandev-development-export.yaml").read_text(encoding="utf-8"))
assert actual == expected, "Kandev export differs from the committed portable workflow"
print("Kandev workflow round trip matches")
PY
```

Expected: `Kandev workflow round trip matches`.

If Kandev omits a field that the public docs claim is portable, stop and reconcile the
definition with the installed Kandev version. Do not weaken the comparison silently.

### Task 4: Exercise workflow transitions and failure gates

**Files:**
- Verify: `workflows/development.yaml`
- Verify: `/tmp/kandev-development-export.yaml`

**Interfaces:**
- Consumes: the disposable synced `Development` workflow, a throwaway Git repository with a pushable remote, a Kandev-capable agent profile exposing Superpowers and `ggs`, and Kandev task MCP tools.
- Produces: an operator record showing the installed Kandev runtime obeys every transition and stop condition.

- [ ] **Step 1: Verify Backlog parking and the human gate**

Create a task with **Create without starting agent** in the disposable workspace and
attach only the throwaway repository.

Expected:

- the task starts in Backlog;
- no agent session starts;
- waiting does not change the step;
- only the manual board move to Refinement begins the next phase.

- [ ] **Step 2: Verify Refinement auto-start and approval behavior**

Use this light task description:

```text
Add a harmless smoke-test text file to the throwaway repository.
```

Move the task manually to Refinement.

Expected:

- a fresh agent session starts automatically;
- it asks whether to brainstorm before continuing;
- the task remains in Refinement while awaiting the answer;
- answering `no` continues refinement without brainstorming;
- the final Kandev plan includes the exact assumptions heading;
- `docs/plans/<task-id>.md` matches the Kandev plan and is committed;
- the agent does not change production files, push, signal completion, or leave
  Refinement.

- [ ] **Step 3: Verify In Progress signal and cancellation gates**

Manually move the task to In Progress.

Expected:

- a new agent session starts automatically with a fresh context;
- it treats the move as approval and does not ask for approval again;
- it reads the Kandev plan before implementation;
- it creates only the harmless planned text file and its specified verification;
- it commits and pushes through `ggs` without opening a change request;
- cancelling a trial turn before completion leaves the task in In Progress;
- a subsequent successful run calls `step_complete_kandev` and moves to Review.

- [ ] **Step 4: Verify Review publication failure remains gated**

Because the throwaway repository has no supported hosted change-request integration,
allow Review to run through its analysis.

Expected:

- a fresh review session starts automatically;
- no production file is modified;
- publication reports the missing provider integration;
- `step_complete_kandev` is not called;
- the task remains in Review.

- [ ] **Step 5: Verify blocker handoff independently**

In a second throwaway task, use an intentionally incomplete implementation whose task
acceptance criterion has a deterministic failing test. Move it through Refinement and In
Progress without permitting a completion signal until the failure is present, then move
it manually to Review solely for this negative-path test.

Expected:

- Review reports the failing changed behavior as a `BLOCKER` with file, line, impact,
  and fix;
- Review appends the exact blocker to the Kandev plan;
- the mirrored Markdown plan is committed;
- the Kandev task lifecycle tool moves the task to In Progress;
- no change request is opened and no Review completion signal is sent.

Archive the disposable tasks after recording the expected outcomes. Remove their
throwaway repositories only with explicit approval. Do not delete the synced workflow
while it still owns tasks.

### Task 5: Open the implementation pull request and prepare production migration

**Files:**
- Verify: `workflows/development.yaml`
- Verify: `workflows/README.md`
- Verify: `tests/test_workflows.py`
- Verify: `docs/superpowers/specs/2026-09-01-kandev-development-workflow-design.md`
- Verify: `docs/superpowers/plans/2026-09-01-kandev-development-workflow.md`

**Interfaces:**
- Consumes: successful local checks, successful Kandev round trip, recorded smoke-test outcomes, and the connected Codex GitHub integration.
- Produces: one ready-for-review GitHub pull request and a post-merge migration checklist for the active Kandev workspace.

- [ ] **Step 1: Perform verification before completion**

Load `superpowers:verification-before-completion`, then run:

```bash
make check
git status --short --branch
git log --oneline --decorate origin/master..HEAD
git diff --stat origin/master...HEAD
```

Expected: all checks pass, the implementation worktree is clean, and the branch contains
only the approved specification, plan, workflow, tests, and runbook changes. If the
remote default branch is no longer `master`, detect it and replace `origin/master` in
the two inspection commands.

- [ ] **Step 2: Open a ready-for-review pull request with `ggs`**

Load `ggs`, read its provider-routing and open-change-request references, and use the
connected Codex GitHub integration. Never invoke `gh`. Detect and honor any pull request
template. Open exactly one ready-for-review pull request from the implementation branch
to the verified default branch.

The title must be:

```text
Add Git-synced Kandev development workflow
```

The description must summarize:

- the Backlog human gate;
- automatic Superpowers refinement and committed task plans;
- approved implementation with `ggs` commits and pushes;
- blocker-only review loops and ready change-request publication;
- removal of PR-Agent from this workflow;
- local test results, Kandev round-trip result, and smoke-test outcomes.

Expected: the integration returns the pull-request URL and confirms it is ready for
review, not draft.

- [ ] **Step 3: Hand off the post-merge production migration**

Report the exact checklist from `workflows/README.md`:

1. Merge the reviewed workflow pull request.
2. Rename the manual workflow to `Development (legacy)`.
3. Configure the active workspace to sync `polaroidkidd/agent-vm`, the protected default
   branch, and directory `workflows`, with polling enabled at `300` seconds.
4. Run **Sync now** and require `last_ok`, no error, and no warning.
5. Use synced `Development` for new tasks created without starting an agent.
6. Retain the legacy workflow until its existing tasks drain.

Do not rename, delete, or migrate the active workflow as part of opening the pull request;
those are post-merge operational changes.
