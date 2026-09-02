import importlib.util
from importlib.machinery import SourceFileLoader
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "ansible"
    / "files"
    / "agent-vm-configure-kandev-workflow-sync"
)
SPEC = importlib.util.spec_from_loader(
    "agent_vm_configure_kandev_workflow_sync",
    SourceFileLoader("agent_vm_configure_kandev_workflow_sync", str(SCRIPT)),
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


DESIRED = {
    "provider": "github",
    "repo_owner": "polaroidkidd",
    "repo_name": "agent-vm",
    "branch": "master",
    "path": "workflows",
    "interval_seconds": 300,
    "poll_enabled": True,
}


class FakeRequester:
    def __init__(self, current=None, sync_response=None):
        self.current = current
        self.sync_response = sync_response
        self.calls = []

    def __call__(self, base_url, path, *, method="GET", payload=None):
        self.calls.append((base_url, path, method, payload))
        if path == "/api/v1/workspaces":
            return 200, {"workspaces": [{"id": "workspace-id", "name": "Default"}]}
        if path.startswith("/api/v1/workflow-sync/config"):
            if method == "POST":
                self.current = {**payload}
                return 200, self.current
            return (200, self.current) if self.current is not None else (204, None)
        if path.startswith("/api/v1/workflow-sync/sync"):
            return 200, self.sync_response
        raise AssertionError(path)


class KandevWorkflowSyncTests(unittest.TestCase):
    def test_workspace_name_must_match_exactly_once(self):
        self.assertEqual(
            "workspace-id",
            MODULE.workspace_id([{"id": "workspace-id", "name": "Default"}], "Default"),
        )
        for payload in (
            [],
            [{"id": "one", "name": "Default"}, {"id": "two", "name": "Default"}],
            {"unexpected": []},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    MODULE.workspace_id(payload, "Default")

    def test_apply_upserts_configuration_without_forcing_sync(self):
        requester = FakeRequester()

        result, ok = MODULE.reconcile(
            "http://localhost:38429",
            "Default",
            DESIRED,
            mode="apply",
            requester=requester,
        )

        self.assertTrue(ok)
        self.assertTrue(result["changed"])
        self.assertEqual("pending", result["status"])
        self.assertEqual(3, len(requester.calls))
        self.assertEqual("POST", requester.calls[-1][2])
        self.assertEqual(DESIRED, requester.calls[-1][3])

    def test_apply_is_idempotent_when_configuration_matches(self):
        requester = FakeRequester(current={**DESIRED})

        result, ok = MODULE.reconcile(
            "http://localhost:38429",
            "Default",
            DESIRED,
            mode="apply",
            requester=requester,
        )

        self.assertTrue(ok)
        self.assertFalse(result["changed"])
        self.assertEqual(2, len(requester.calls))

    def test_check_requires_success_without_error_or_warnings(self):
        ready = {
            **DESIRED,
            "last_synced_at": "2026-09-02T12:00:00Z",
            "last_ok": True,
            "last_error": "",
            "last_warnings": [],
        }
        requester = FakeRequester(current=ready)

        result, ok = MODULE.reconcile(
            "http://localhost:38429",
            "Default",
            DESIRED,
            mode="check",
            requester=requester,
        )

        self.assertTrue(ok)
        self.assertEqual("ready", result["status"])

        for update in (
            {"last_ok": False, "last_error": "repository unavailable"},
            {"last_warnings": ["development.yaml was skipped"]},
        ):
            with self.subTest(update=update):
                requester = FakeRequester(current={**ready, **update})
                result, ok = MODULE.reconcile(
                    "http://localhost:38429",
                    "Default",
                    DESIRED,
                    mode="check",
                    requester=requester,
                )
                self.assertFalse(ok)
                self.assertEqual("failed", result["status"])

    def test_force_sync_inspects_json_error_despite_http_success(self):
        requester = FakeRequester(
            current={**DESIRED},
            sync_response={
                "config": {**DESIRED, "last_ok": False},
                "error": "GitHub automation connection is unavailable",
            },
        )

        result, ok = MODULE.reconcile(
            "http://localhost:38429",
            "Default",
            DESIRED,
            mode="sync",
            requester=requester,
        )

        self.assertFalse(ok)
        self.assertEqual("failed", result["status"])
        self.assertIn("automation connection", result["detail"])

    def test_force_sync_accepts_only_clean_success(self):
        synced = {
            **DESIRED,
            "last_synced_at": "2026-09-02T12:00:00Z",
            "last_ok": True,
            "last_error": "",
            "last_warnings": [],
        }
        requester = FakeRequester(
            current={**DESIRED},
            sync_response={"config": synced, "result": {"unchanged": ["Development"]}},
        )

        result, ok = MODULE.reconcile(
            "http://localhost:38429",
            "Default",
            DESIRED,
            mode="sync",
            requester=requester,
        )

        self.assertTrue(ok)
        self.assertEqual("ready", result["status"])


if __name__ == "__main__":
    unittest.main()
