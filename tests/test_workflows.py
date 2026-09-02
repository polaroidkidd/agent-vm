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
        prompt = " ".join(self.steps["Refinement"]["prompt"].split())
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
        prompt = " ".join(self.steps["Review"]["prompt"].split())
        for text in (
            "BLOCKER",
            "SUGGESTION",
            "80%",
            "intended change-request target branch",
            "Never substitute the remote default branch",
            "merge-base",
            "git diff --name-status",
            "regardless of whether the worktree is dirty",
            "git diff --cached",
            "git ls-files --others --exclude-standard",
            "Union the intended task-related paths",
            "Any intended task change outside HEAD is a publication blocker",
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
        self.assertNotIn("If the worktree is clean", prompt)
        self.assertLess(prompt.index("merge-base"), prompt.index("git diff --cached"))

    def test_workflow_has_no_pr_agent_integration(self):
        self.assertNotIn("pr-agent", WORKFLOW_PATH.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
