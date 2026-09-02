import unittest
from pathlib import Path


class PlaybookTests(unittest.TestCase):
    def setUp(self):
        self.playbook = (Path(__file__).parents[1] / "ansible" / "playbook.yml").read_text(encoding="utf-8")

    def test_targeted_service_tags_start_their_services(self):
        for name, tag in (
            ("CLIProxyAPI", "cliproxy"),
            ("Bifrost", "bifrost"),
            ("PR-Agent", "pr-agent"),
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

    def test_node_is_provisioned_for_agent_with_pinned_nvm(self):
        self.assertNotIn("Configure NodeSource repository", self.playbook)
        removal = self.playbook.split("- name: Remove legacy system Node.js package", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("name: nodejs", removal)
        self.assertIn("state: absent", removal)

        archive = self.playbook.split("- name: Download pinned NVM release archive", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn(
            "https://github.com/nvm-sh/nvm/archive/refs/tags/{{ services.nvm.version }}.tar.gz",
            archive,
        )
        self.assertNotIn("GIT_CONFIG_GLOBAL", archive)

        nvm = self.playbook.split("- name: Install pinned NVM", 1)[1].split("\n\n", 1)[0]
        self.assertIn("ansible.builtin.unarchive", nvm)
        self.assertIn("remote_src: true", nvm)
        self.assertIn("--strip-components=1", nvm)
        self.assertIn('.agent-vm-{{ services.nvm.version }}', nvm)
        self.assertIn('become_user: "{{ agent_user }}"', nvm)

        node = self.playbook.split("- name: Install configured Node.js with NVM", 1)[1].split(
            "\n    - name: Resolve active NVM Node.js binary", 1
        )[0]
        self.assertIn('nvm install "{{ node_major }}"', node)
        self.assertIn('nvm version "{{ node_major }}" 2>/dev/null || true', node)
        self.assertIn('become_user: "{{ agent_user }}"', node)
        self.assertIn("perform_update", node)

    def test_nvm_node_tools_and_agent_clis_are_available_without_shell_startup(self):
        core = self.playbook.split("- name: Activate NVM-managed Node.js tools", 1)[1].split(
            "\n\n", 1
        )[0]
        for executable in ("node", "npm", "npx"):
            self.assertIn(f"- {executable}", core)

        agents = self.playbook.split("- name: Activate NVM-managed agent CLIs", 1)[1].split(
            "\n\n", 1
        )[0]
        for executable in ("kandev", "pi"):
            self.assertIn(f"- {executable}", agents)

        unit = (Path(__file__).parents[1] / "ansible" / "templates" / "kandev.service.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("ExecStart=/usr/local/bin/kandev", unit)

    def test_kandev_can_write_npx_cache_for_acp_adapters(self):
        self.assertIn('- {path: "/home/{{ agent_user }}/.npm", mode: "0700"}', self.playbook)
        unit = (Path(__file__).parents[1] / "ansible" / "templates" / "kandev.service.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("ProtectHome=read-only", unit)
        self.assertIn("/home/{{ agent_user }}/.npm", unit.split("ReadWritePaths=", 1)[1])

    def test_git_commit_signing_imports_generated_openpgp_key(self):
        packages = self.playbook.split("- name: Install base packages", 1)[1].split("\n\n", 1)[0]
        self.assertIn("- gnupg", packages)

        imported = self.playbook.split("- name: Import Git commit signing key", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("--import", imported)
        self.assertIn('stdin: "{{ git_signing_private_key }}"', imported)
        self.assertIn("no_log: true", imported)

        task = self.playbook.split("- name: Configure Git commit signing identity", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn('name: "{{ item.name }}"', task)
        self.assertIn('value: "{{ item.value }}"', task)
        self.assertIn("name: gpg.format", task)
        self.assertIn("value: openpgp", task)
        self.assertIn("name: user.name", task)
        self.assertIn("name: user.email", task)
        self.assertIn("value: \"{{ git_signing_fingerprint }}\"", task)
        self.assertIn("when: git_sign_commits", task)
        self.assertIn('become_user: "{{ agent_user }}"', task)
        self.assertIn("tags: [base, git]", task)

        automatic = self.playbook.split("- name: Configure automatic Git commit signing", 1)[
            1
        ].split("\n\n", 1)[0]
        self.assertIn("name: commit.gpgsign", automatic)
        self.assertIn("git_sign_commits | ternary('true', 'false')", automatic)

    def test_stripe_api_key_is_provisioned_for_workloads_and_shells(self):
        task = self.playbook.split("- name: Configure agent workload environment", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("src: agent-vm.env.j2", task)
        self.assertIn('mode: "0600"', task)
        self.assertIn("no_log: true", task)
        self.assertIn("notify: Restart Kandev", task)

        environment = (
            Path(__file__).parents[1] / "ansible" / "templates" / "agent-vm.env.j2"
        ).read_text(encoding="utf-8")
        self.assertEqual(environment, "STRIPE_API_KEY={{ stripe_api_key | to_json }}\n")

        unit = (Path(__file__).parents[1] / "ansible" / "templates" / "kandev.service.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("EnvironmentFile=/home/{{ agent_user }}/.config/agent-vm.env", unit)

        zshrc = (Path(__file__).parents[1] / "ansible" / "templates" / "zshrc.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("export STRIPE_API_KEY", zshrc)
        self.assertIn('source "$HOME/.config/agent-vm.env"', zshrc)

    def test_cliproxyapi_plugins_are_enabled_in_a_persistent_directory(self):
        self.assertIn(
            '- {path: "/home/{{ agent_user }}/.config/cliproxyapi/plugins", mode: "0700"}',
            self.playbook,
        )
        config = (
            Path(__file__).parents[1]
            / "ansible"
            / "templates"
            / "cliproxyapi-config.yaml.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("plugins:\n  enabled: true", config)
        self.assertIn('dir: "/home/{{ agent_user }}/.config/cliproxyapi/plugins"', config)

    def test_agent_package_changes_restart_kandev_for_rediscovery(self):
        task = self.playbook.split("- name: Install exact npm service releases", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("services.pi.npm_package", task)
        self.assertIn("notify: Restart Kandev", task)

    def test_exact_global_pi_superpowers_package_is_installed_for_agent(self):
        self.assertIn("- name: Install exact global Pi packages", self.playbook)
        task = self.playbook.split("- name: Install exact global Pi packages", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("/usr/local/bin/pi", task)
        self.assertIn("install", task)
        self.assertIn("services.pi.superpowers_package", task)
        self.assertIn("versions.pi_superpowers.version", task)
        self.assertIn('become_user: "{{ agent_user }}"', task)
        self.assertIn('HOME: "/home/{{ agent_user }}"', task)
        self.assertIn("pi_global_packages.stdout", task)
        self.assertNotIn("pi_global_packages.stdout_lines", task)
        self.assertIn("pi_superpowers_manifest_content.content", task)
        self.assertIn("notify: Restart Kandev", task)
        self.assertIn("tags: [services, pi, skills]", task)

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

    def test_provision_applies_declarative_kandev_workflow_sync_configuration(self):
        install = self.playbook.split(
            "- name: Install Kandev Workflow Sync configurator", 1
        )[1].split("\n\n", 1)[0]
        self.assertIn("agent-vm-configure-kandev-workflow-sync", install)
        self.assertIn("mode: \"0755\"", install)
        self.assertIn("tags: [services, kandev, kandev-workflow]", install)

        configure = self.playbook.split(
            "- name: Apply declarative Kandev Workflow Sync configuration", 1
        )[1].split("\n\n", 1)[0]
        for argument in (
            "--workspace-name",
            "--repo-owner",
            "--repo-name",
            "--branch",
            "--path",
            "--interval-seconds",
            "--poll-enabled",
        ):
            self.assertIn(argument, configure)
        self.assertNotIn("--sync", configure)
        self.assertIn("become_user", configure)
        self.assertIn("changed_when", configure)

    def test_pr_agent_uses_verified_release_and_dedicated_bifrost_key(self):
        for name in (
            "Resolve active NVM Node.js binary",
            "Record active NVM Node.js binary directory",
        ):
            with self.subTest(task=name):
                task = self.playbook.split(f"- name: {name}", 1)[1].split("\n\n", 1)[0]
                self.assertIn("tags: [services, pr-agent]", task)

        download = self.playbook.split("- name: Download verified PR-Agent wheel", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("versions.pr_agent.url", download)
        self.assertIn('checksum: "sha256:{{ versions.pr_agent.sha256 }}"', download)

        secrets = (
            Path(__file__).parents[1] / "ansible" / "templates" / "pr-agent-secrets.toml.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("generated_secrets.pr_agent_bifrost_virtual_key", secrets)
        self.assertIn('api_base = "http://127.0.0.1:{{ ports.bifrost }}/v1"', secrets)
        self.assertIn("pr_agent.github_app_id | string | to_json", secrets)
        self.assertIn("[config]", secrets)
        self.assertIn("fallback_models = {{ [pr_agent.fallback_model] | to_json }}", secrets)

        bifrost = (
            Path(__file__).parents[1] / "ansible" / "templates" / "bifrost-config.json.j2"
        ).read_text(encoding="utf-8")
        self.assertIn('"id": "vk-pr-agent"', bifrost)
        self.assertIn("pr_agent.bifrost_model | to_json", bifrost)
        self.assertIn("pr_agent.bifrost_fallback_model | to_json", bifrost)

    def test_pr_agent_is_restricted_to_review_only_automation(self):
        environment = (
            Path(__file__).parents[1] / "ansible" / "templates" / "pr-agent.env.j2"
        ).read_text(encoding="utf-8")
        self.assertIn('GITHUB_APP__PR_COMMANDS=["/review"]', environment)
        self.assertIn("GITHUB_APP__HANDLE_PUSH_TRIGGER=false", environment)
        self.assertIn("CONFIG__RESTRICTED_MODE=true", environment)
        self.assertIn("CONFIG__MAX_MODEL_TOKENS=200000", environment)
        self.assertIn("CONFIG__TEMPERATURE=1", environment)
        self.assertIn("CONFIG__LOG_LEVEL=INFO", environment)
        self.assertNotIn("CONFIG__FALLBACK_MODELS", environment)
        self.assertIn("LITELLM__CUSTOM_LLM_PROVIDER=openai", environment)

        unit = (
            Path(__file__).parents[1] / "ansible" / "templates" / "pr-agent.service.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("Requires=bifrost.service", unit)
        self.assertIn("python:pr_agent.servers.gunicorn_config", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ProtectHome=read-only", unit)

        disabled = self.playbook.split(
            "- name: Disable PR-Agent service when not configured", 1
        )[1].split("\n\n", 1)[0]
        self.assertIn("enabled: false", disabled)
        self.assertIn("state: stopped", disabled)

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

    def test_provision_installs_docker_for_agent_account(self):
        install = self.playbook.split("- name: Install Docker Engine and Compose", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("- docker.io", install)
        self.assertIn("- docker-buildx", install)
        self.assertIn("- docker-compose-v2", install)
        self.assertIn("state: present", install)

        account = self.playbook.split("- name: Ensure agent account configuration", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("groups: sudo,docker", account)
        self.assertIn("append: true", account)

        service = self.playbook.split("- name: Enable Docker service", 1)[1].split("\n\n", 1)[0]
        self.assertIn("enabled: true", service)
        self.assertIn("state: started", service)
        self.assertIn("tags: [base, docker]", service)

    def test_provision_installs_github_cli(self):
        packages = self.playbook.split("- name: Install base packages", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("- gh", packages)

    def test_python_tooling_is_provisioned_for_agent_and_workloads(self):
        install = self.playbook.split("- name: Install Python package tooling", 1)[1].split(
            "\n\n", 1
        )[0]
        self.assertIn("- python3-pip", install)
        self.assertIn("- pipx", install)
        self.assertIn("state: present", install)

        uv = self.playbook.split("- name: Install configured uv with pipx", 1)[1].split(
            "\n    - name: Activate pipx-managed uv tools", 1
        )[0]
        self.assertIn('uv=={{ services.uv.version }}', uv)
        self.assertIn('become_user: "{{ agent_user }}"', uv)

        activation = self.playbook.split("- name: Activate pipx-managed uv tools", 1)[1].split(
            "\n\n", 1
        )[0]
        for executable in ("uv", "uvx"):
            self.assertIn(f"- {executable}", activation)
        self.assertIn('dest: "/usr/local/bin/{{ item }}"', activation)


if __name__ == "__main__":
    unittest.main()
