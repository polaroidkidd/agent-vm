import unittest

from agent_vm.host import REQUIRED_COMMANDS


class HostTests(unittest.TestCase):
    def test_required_host_toolchain_is_complete(self):
        self.assertEqual(
            set(REQUIRED_COMMANDS),
            {
                "ansible-playbook",
                "virsh",
                "virt-install",
                "qemu-img",
                "cloud-localds",
                "ssh",
                "ssh-keygen",
                "ssh-keyscan",
                "gpg",
                "openssl",
                "setfacl",
            },
        )


if __name__ == "__main__":
    unittest.main()
