import unittest
from pathlib import Path


class PlaybookTests(unittest.TestCase):
    def setUp(self):
        self.playbook = (Path(__file__).parents[1] / "ansible" / "playbook.yml").read_text(encoding="utf-8")

    def test_targeted_service_tags_start_their_services(self):
        for name, tag in (
            ("CLIProxyAPI", "cliproxy"),
            ("Bifrost", "bifrost"),
            ("Kandev", "kandev"),
        ):
            with self.subTest(service=name):
                task = self.playbook.split(f"- name: Enable {name} service", 1)[1].split("\n\n", 1)[0]
                self.assertIn("state: started", task)
                self.assertIn(f"tags: [services, {tag}]", task)

    def test_legacy_pi_package_is_removed_before_install(self):
        removal = self.playbook.index("- name: Remove legacy Pi package")
        install = self.playbook.index("- name: Install exact npm service releases")
        self.assertLess(removal, install)
        task = self.playbook[removal:install]
        self.assertIn('name: "@mariozechner/pi-coding-agent"', task)
        self.assertIn("state: absent", task)

    def test_kandev_can_write_npx_cache_for_acp_adapters(self):
        self.assertIn('- {path: "/home/{{ agent_user }}/.npm", mode: "0700"}', self.playbook)
        unit = (Path(__file__).parents[1] / "ansible" / "templates" / "kandev.service.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("ProtectHome=read-only", unit)
        self.assertIn("/home/{{ agent_user }}/.npm", unit.split("ReadWritePaths=", 1)[1])

    def test_agent_package_changes_restart_kandev_for_rediscovery(self):
        task = self.playbook.split("- name: Install exact npm service releases", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("services.pi.npm_package", task)
        self.assertIn("notify: Restart Kandev", task)

    def test_bifrost_recovers_interrupted_runtime_download_before_one_final_start(self):
        cleanup = self.playbook.index("- name: Remove interrupted Bifrost runtime downloads")
        flush = self.playbook.index("- name: Apply pending service restarts")
        enable = self.playbook.index("- name: Enable Bifrost service")
        self.assertLess(cleanup, flush)
        self.assertLess(flush, enable)
        task = self.playbook[cleanup:flush]
        self.assertIn("! -perm /111 -print -delete", task)
        self.assertIn("notify: Restart Bifrost", task)

    def test_bifrost_tag_installs_pi_model_catalog_synchronizer(self):
        task = self.playbook.split("- name: Install Pi model catalog synchronizer", 1)[1].split("\n\n", 1)[0]
        self.assertIn("agent-vm-sync-pi-models", task)
        self.assertIn("tags: [services, pi, bifrost]", task)

    def test_provision_does_not_overwrite_synchronized_pi_catalog(self):
        for name in ("Configure Pi provider through Bifrost", "Configure Pi defaults"):
            with self.subTest(task=name):
                task = self.playbook.split(f"- name: {name}", 1)[1].split("\n\n", 1)[0]
                self.assertIn("force: false", task)

    def test_global_pi_skills_are_copied_for_shared_agent_account(self):
        self.assertIn(
            '- {path: "/home/{{ agent_user }}/.agents/skills", mode: "0700"}',
            self.playbook,
        )
        task = self.playbook.split("- name: Install global Pi agent skills", 1)[1].split("\n\n", 1)[0]
        self.assertIn('src: "{{ item.source }}/"', task)
        self.assertIn('dest: "/home/{{ agent_user }}/.agents/skills/{{ item.name }}/"', task)
        self.assertIn("loop: \"{{ pi_skills }}\"", task)
        self.assertIn("tags: [services, pi, skills]", task)

    def test_agent_account_has_an_unlocked_console_password(self):
        task = self.playbook.split("- name: Ensure agent account configuration", 1)[1].split("\n\n", 1)[0]
        self.assertIn('password: "{{ agent_console_password_hash }}"', task)
        self.assertIn("password_lock: false", task)
        self.assertIn("update_password: always", task)
        self.assertIn("no_log: true", task)


if __name__ == "__main__":
    unittest.main()
