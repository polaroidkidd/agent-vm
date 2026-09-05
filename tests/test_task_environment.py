import copy
import importlib.util
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


def load_script(name):
    path = Path(__file__).parents[1] / "ansible/files" / name
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TASK = load_script("agent-vm-task")
CONFIGURE = load_script("agent-vm-configure-kandev")


class TaskEnvironmentTests(unittest.TestCase):
    def test_worktree_services_have_distinct_names_and_only_loopback_database_ingress(self):
        first, second = TASK.task_name(Path("/worktrees/one")), TASK.task_name(Path("/worktrees/two"))
        self.assertNotEqual(first, second)
        compose = TASK.compose_config({"project": first, "password": "test-only"})
        self.assertNotIn("name", compose)
        self.assertNotIn("container_name", compose["services"]["db"])
        self.assertEqual([{"target": 5432, "published": "0", "host_ip": "127.0.0.1"}],
                         compose["services"]["db"]["ports"])

    def test_infrastructure_setup_never_starts_containers_or_installs_unlocked_dependencies(self):
        with patch.object(TASK, "run") as run:
            TASK.setup(Path("/repo"), "compose", {})
        commands = [call.args[2:] for call in run.call_args_list]
        self.assertEqual([("pnpm", "--version"), ("docker", "compose", "version")], commands)

    def test_cleanup_is_scoped_to_worktree_project_and_preserves_volumes(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(TASK.Path, "home", return_value=Path(home)), patch.object(TASK, "run") as run:
                root = Path(home) / "worktree"
                directory, state = TASK.task_state(root)
                TASK.cleanup(root, {})
                command = run.call_args.args[2:]
                self.assertEqual(("docker", "compose", "--project-name", TASK.task_name(root)), command[:4])
                self.assertEqual("down", command[-1])
                self.assertNotIn("--volumes", command)
                self.assertTrue((directory / "state.json").exists())
                self.assertEqual(0o600, (directory / "compose.json").stat().st_mode & 0o777)

    def test_cleanup_without_owned_state_does_nothing(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(TASK.Path, "home", return_value=Path(home)), patch.object(TASK, "run") as run:
                TASK.cleanup(Path(home) / "unmanaged", {})
                run.assert_not_called()

    def test_foreign_task_state_is_rejected_before_cleanup(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(TASK.Path, "home", return_value=Path(home)), patch.object(TASK, "run") as run:
                root = Path(home) / "worktree"
                directory, state = TASK.task_state(root)
                state["project"] = "production"
                (directory / "state.json").write_text(json.dumps(state))
                with self.assertRaisesRegex(ValueError, "does not belong"):
                    TASK.cleanup(root, {})
                run.assert_not_called()


class KandevConfigurationTests(unittest.TestCase):
    def test_mutations_load_and_send_the_current_settings_token(self):
        responses = []
        for value in ({"interimSettingsInterlockToken": "boot-token"}, {}):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(value).encode()
            responses.append(response)
        with patch.object(CONFIGURE, "urlopen", side_effect=responses) as request:
            CONFIGURE.api("http://localhost", "/agent-profiles/pi", method="PATCH", data={"model": "cliproxy/sol"})
        self.assertEqual(2, request.call_count)
        boot, mutation = [call.args[0] for call in request.call_args_list]
        self.assertTrue(boot.full_url.endswith("/app-state?path=%2Fsettings%2Fagents"))
        self.assertEqual("boot-token", dict(mutation.header_items())["X-kandev-interim-settings-interlock"])

    def test_migration_does_not_change_profiles_when_direct_models_are_unavailable(self):
        responses = [
            {"agents": [{"name": "pi-acp", "profiles": [{"id": "pi", "name": "sol", "model": "bifrost/cliproxy/sol"}]}]},
            {"status": "ok", "models": []},
        ]
        with patch.object(CONFIGURE, "api", side_effect=responses) as api:
            with self.assertRaisesRegex(ValueError, "absent"):
                CONFIGURE.reconcile("http://localhost", {"workspace_name": "dle"})
        self.assertEqual(2, api.call_count)
        self.assertFalse(any(call.kwargs.get("method") == "PATCH" for call in api.call_args_list))

    def test_migration_only_changes_retired_model_prefix(self):
        self.assertEqual("cliproxy/model", CONFIGURE.migrated_model("bifrost/cliproxy/model"))
        self.assertEqual("other/model", CONFIGURE.migrated_model("other/model"))
        self.assertIsNone(CONFIGURE.migrated_model(None))

    def test_reconciliation_preserves_tasks_unrelated_profiles_and_is_idempotent(self):
        data = {
            "/agent-models/pi-acp?refresh=true": {"status": "ok", "models": [{"id": "cliproxy/sol"}]},
            "/agents": {"agents": [
                {"name": "pi-acp", "profiles": [{"id": "pi", "name": "sol", "model": "bifrost/cliproxy/sol",
                                                   "mode": "high", "auto_approve": True, "fallback_model": None}]},
                {"name": "other", "profiles": [{"id": "other", "model": "other/model"}]},
            ]},
            "/workspaces": {"workspaces": [{"id": "ws", "name": "dle"}]},
            "/workspaces/ws/workflows": {"workflows": [
                {"id": "old", "name": "Development", "source": "manual", "sort_order": 0},
                {"id": "new", "name": "Development", "source": "github", "sort_order": 1,
                 "source_path": "workflows/development.yaml"},
            ]},
            "/workspaces/ws/repositories": {"repositories": [
                {"id": "repo", "name": "services", "default_branch": "master", "setup_script": ""},
            ]},
        }
        writes = []

        def api(base, path, method="GET", data=None):
            if method == "GET":
                return copy.deepcopy(responses[path])
            writes.append((path, copy.deepcopy(data)))
            if path == "/agent-profiles/pi":
                responses["/agents"]["agents"][0]["profiles"][0].update(data)
            elif path == "/workflows/old":
                responses["/workspaces/ws/workflows"]["workflows"][0].update(data)
            elif path.endswith("/reorder"):
                for workflow in responses["/workspaces/ws/workflows"]["workflows"]:
                    workflow["sort_order"] = data["workflow_ids"].index(workflow["id"])
            elif path == "/repositories/repo":
                responses["/workspaces/ws/repositories"]["repositories"][0].update(data)
            else:
                self.fail(f"Unexpected write: {path}")
            return {}

        responses = data
        config = {"workspace_name": "dle", "repositories": [{"name": "services", "preset": "compose"}]}
        with patch.object(CONFIGURE, "api", side_effect=api):
            first = CONFIGURE.reconcile("http://localhost", config)
            count = len(writes)
            second = CONFIGURE.reconcile("http://localhost", config)
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(count, len(writes))
        self.assertEqual(("/agent-profiles/pi", {"model": "cliproxy/sol"}), writes[0])
        self.assertEqual("high", responses["/agents"]["agents"][0]["profiles"][0]["mode"])
        self.assertEqual("master", responses["/workspaces/ws/repositories"]["repositories"][0]["default_branch"])
        self.assertFalse(any("tasks" in path for path, _ in writes))


if __name__ == "__main__":
    unittest.main()
