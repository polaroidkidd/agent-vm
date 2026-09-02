import unittest

from agent_vm.cli import parser


class CLITests(unittest.TestCase):
    def test_configure_kandev_workflow_command_is_registered(self):
        args = parser().parse_args(["configure-kandev-workflow"])
        self.assertEqual("configure-kandev-workflow", args.command)


if __name__ == "__main__":
    unittest.main()
