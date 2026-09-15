import unittest
from unittest.mock import Mock, patch

from agent_vm.cli import App, parser


class CLITests(unittest.TestCase):
    @patch("agent_vm.cli.resolve_all")
    def test_update_installs_and_records_resolved_codex_release(self, resolve):
        app = App.__new__(App)
        app.config = Mock()
        app.state = Mock()
        app._provision = Mock()
        releases = {"codex": {"version": "0.155.0", "source": "npm:@openai/codex"}}
        resolve.return_value = releases

        app.update()

        resolve.assert_called_once_with(app.config)
        app._provision.assert_called_once_with(versions=releases, perform_update=True)
        app.state.write_json.assert_called_once_with(app.state.versions_path, releases)

    def test_configure_kandev_workflow_command_is_registered(self):
        args = parser().parse_args(["configure-kandev-workflow"])
        self.assertEqual("configure-kandev-workflow", args.command)


if __name__ == "__main__":
    unittest.main()
