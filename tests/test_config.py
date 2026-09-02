import copy
import tempfile
import unittest
from pathlib import Path

from agent_vm.config import Config
from agent_vm.errors import AgentVMError


VALID = {
    "schema_version": 1,
    "vm": {
        "name": "agent-vm",
        "architecture": "x86_64",
        "vcpus": 4,
        "memory_gib": 16,
        "disk_gib": 100,
        "image": {"url": "https://example.test/image.qcow2", "checksum_url": "https://example.test/SHA256SUMS"},
    },
    "guest": {
        "user": "agent",
        "workspace_dir": "/home/agent/workspaces",
        "console_agent_password": "agent-console-secret",
        "console_root_password": "console-secret",
        "git": {
            "sign_commits": True,
            "name": "Agent User",
            "email": "agent@example.test",
        },
    },
    "ports": {"kandev": 38429, "bifrost": 8080, "cliproxyapi": 8317},
    "NB_HOSTNAME": "agent-vm",
    "NB_MANAGEMENT_URL": "https://netbird.example.com",
    "NB_SETUP_KEY": "test-setup-key",
    "STRIPE_API_KEY": "sk_test_example",
    "services": {
        "nvm": {"version": "v0.40.3"},
        "uv": {"version": "0.12.7"},
        "node_major": 24,
        "kandev": {
            "npm_package": "kandev",
            "workflow_sync": {
                "enabled": True,
                "provider": "github",
                "workspace_name": "Default",
                "repo_owner": "polaroidkidd",
                "repo_name": "agent-vm",
                "branch": "master",
                "path": "workflows",
                "interval_seconds": 300,
                "poll_enabled": True,
            },
        },
        "pi": {
            "npm_package": "@earendil-works/pi-coding-agent",
            "superpowers_package": "@weiping/pi-superpowers",
            "default_model": "model",
        },
        "bifrost": {"npm_package": "bifrost"},
        "cliproxyapi": {"github_repository": "owner/repo", "asset_pattern": "linux"},
    },
}


class ConfigTests(unittest.TestCase):
    def config(self, raw=None):
        return Config(path=Path("config.yaml"), root=Path("/tmp/repo"), raw=copy.deepcopy(raw or VALID))

    def test_valid_configuration(self):
        config = self.config()
        config.validate()
        self.assertEqual(
            {
                "provider": "github",
                "workspace_name": "Default",
                "repo_owner": "polaroidkidd",
                "repo_name": "agent-vm",
                "branch": "master",
                "path": "workflows",
                "interval_seconds": 300,
                "poll_enabled": True,
            },
            config.kandev_workflow_sync,
        )

    def test_kandev_workflow_sync_can_be_disabled(self):
        raw = copy.deepcopy(VALID)
        raw["services"]["kandev"]["workflow_sync"] = {"enabled": False}
        config = self.config(raw)

        config.validate()

        self.assertIsNone(config.kandev_workflow_sync)

    def test_kandev_workflow_sync_is_required(self):
        raw = copy.deepcopy(VALID)
        del raw["services"]["kandev"]["workflow_sync"]
        with self.assertRaisesRegex(AgentVMError, "services.kandev.workflow_sync"):
            self.config(raw).validate()

    def test_kandev_workflow_sync_rejects_unsafe_repository_values(self):
        cases = (
            ("provider", "gitlab", "provider must be github"),
            ("repo_owner", "owner/name", "cannot contain slashes or spaces"),
            ("repo_name", "agent vm", "cannot contain slashes or spaces"),
            ("path", "../workflows", "safe repository directory"),
            ("interval_seconds", 59, "between 60 and 2592000"),
            ("poll_enabled", "yes", "must be a boolean"),
        )
        for key, value, message in cases:
            with self.subTest(key=key):
                raw = copy.deepcopy(VALID)
                raw["services"]["kandev"]["workflow_sync"][key] = value
                with self.assertRaisesRegex(AgentVMError, message):
                    self.config(raw).validate()

    def test_resources_must_be_positive_absolute_values(self):
        raw = copy.deepcopy(VALID)
        raw["vm"]["memory_gib"] = 0
        with self.assertRaisesRegex(AgentVMError, "greater than zero"):
            self.config(raw).validate()

    def test_workspace_must_be_absolute(self):
        raw = copy.deepcopy(VALID)
        raw["guest"]["workspace_dir"] = "workspaces"
        with self.assertRaisesRegex(AgentVMError, "must be absolute"):
            self.config(raw).validate()

    def test_console_root_password_is_required(self):
        raw = copy.deepcopy(VALID)
        del raw["guest"]["console_root_password"]
        with self.assertRaisesRegex(AgentVMError, "guest.console_root_password"):
            self.config(raw).validate()

    def test_console_root_password_must_be_one_line(self):
        raw = copy.deepcopy(VALID)
        raw["guest"]["console_root_password"] = "first\nsecond"
        with self.assertRaisesRegex(AgentVMError, "single-line"):
            self.config(raw).validate()

    def test_console_agent_password_is_required(self):
        raw = copy.deepcopy(VALID)
        del raw["guest"]["console_agent_password"]
        with self.assertRaisesRegex(AgentVMError, "guest.console_agent_password"):
            self.config(raw).validate()

    def test_console_agent_password_must_be_one_line(self):
        raw = copy.deepcopy(VALID)
        raw["guest"]["console_agent_password"] = "first\nsecond"
        with self.assertRaisesRegex(AgentVMError, "guest.console_agent_password.*single-line"):
            self.config(raw).validate()

    def test_console_passwords_must_be_distinct(self):
        raw = copy.deepcopy(VALID)
        raw["guest"]["console_agent_password"] = raw["guest"]["console_root_password"]
        with self.assertRaisesRegex(AgentVMError, "console passwords must be distinct"):
            self.config(raw).validate()

    def test_git_commit_signing_is_configurable(self):
        config = self.config()
        config.validate()
        self.assertTrue(config.git_sign_commits)

        raw = copy.deepcopy(VALID)
        del raw["guest"]["git"]
        config = self.config(raw)
        config.validate()
        self.assertFalse(config.git_sign_commits)

    def test_git_commit_signing_must_be_boolean(self):
        raw = copy.deepcopy(VALID)
        raw["guest"]["git"]["sign_commits"] = "yes"
        with self.assertRaisesRegex(AgentVMError, "guest.git.sign_commits must be a boolean"):
            self.config(raw).validate()

    def test_enabled_git_commit_signing_requires_identity(self):
        for key in ("name", "email"):
            with self.subTest(key=key):
                raw = copy.deepcopy(VALID)
                del raw["guest"]["git"][key]
                with self.assertRaisesRegex(AgentVMError, f"guest.git.{key}"):
                    self.config(raw).validate()

    def test_git_commit_signing_email_must_be_valid(self):
        raw = copy.deepcopy(VALID)
        raw["guest"]["git"]["email"] = "not-an-email"
        with self.assertRaisesRegex(AgentVMError, "guest.git.email must be an email address"):
            self.config(raw).validate()

    def test_ports_must_be_unique(self):
        raw = copy.deepcopy(VALID)
        raw["ports"]["bifrost"] = raw["ports"]["kandev"]
        with self.assertRaisesRegex(AgentVMError, "unique"):
            self.config(raw).validate()

    def test_enabled_pr_agent_requires_unique_port_and_github_app_identity(self):
        raw = copy.deepcopy(VALID)
        raw["ports"]["pr_agent"] = 3000
        raw["services"]["pr_agent"] = {
            "enabled": True,
            "pypi_package": "pr-agent",
            "model": "cliproxy/codex-auto-review",
            "fallback_model": "cliproxy/gpt-5.6-sol",
            "workers": 2,
        }
        raw["PR_AGENT_GITHUB_APP_ID"] = 123456
        raw["PR_AGENT_GITHUB_PRIVATE_KEY"] = (
            "-----BEGIN RSA PRIVATE KEY-----\nkey\n-----END RSA PRIVATE KEY-----"
        )

        config = self.config(raw)
        config.validate()

        self.assertEqual("cliproxy/codex-auto-review", config.pr_agent["model"])
        self.assertEqual(123456, config.pr_agent["github_app_id"])
        self.assertEqual("codex-auto-review", config.pr_agent["bifrost_model"])
        self.assertEqual("gpt-5.6-sol", config.pr_agent["bifrost_fallback_model"])

    def test_disabled_pr_agent_does_not_require_credentials(self):
        raw = copy.deepcopy(VALID)
        raw["services"]["pr_agent"] = {"enabled": False}
        config = self.config(raw)
        config.validate()
        self.assertIsNone(config.pr_agent)

    def test_enabled_pr_agent_rejects_invalid_private_key(self):
        raw = copy.deepcopy(VALID)
        raw["ports"]["pr_agent"] = 3000
        raw["services"]["pr_agent"] = {
            "enabled": True,
            "pypi_package": "pr-agent",
            "model": "model",
            "fallback_model": "fallback",
            "workers": 2,
        }
        raw["PR_AGENT_GITHUB_APP_ID"] = 123456
        raw["PR_AGENT_GITHUB_PRIVATE_KEY"] = "not a key"
        with self.assertRaisesRegex(AgentVMError, "PEM key"):
            self.config(raw).validate()

    def test_netbird_hostname_is_validated(self):
        raw = copy.deepcopy(VALID)
        raw["NB_HOSTNAME"] = "bad host"
        with self.assertRaisesRegex(AgentVMError, "invalid"):
            self.config(raw).validate()

    def test_netbird_values_are_required(self):
        for name in ("NB_HOSTNAME", "NB_MANAGEMENT_URL", "NB_SETUP_KEY"):
            with self.subTest(name=name):
                raw = copy.deepcopy(VALID)
                raw[name] = ""
                with self.assertRaisesRegex(AgentVMError, name):
                    self.config(raw).validate()

    def test_netbird_management_url_must_be_http(self):
        raw = copy.deepcopy(VALID)
        raw["NB_MANAGEMENT_URL"] = "netbird.example.com"
        with self.assertRaisesRegex(AgentVMError, "http"):
            self.config(raw).validate()

    def test_stripe_api_key_is_required(self):
        raw = copy.deepcopy(VALID)
        del raw["STRIPE_API_KEY"]
        with self.assertRaisesRegex(AgentVMError, "STRIPE_API_KEY"):
            self.config(raw).validate()

    def test_stripe_api_key_must_be_one_line(self):
        raw = copy.deepcopy(VALID)
        raw["STRIPE_API_KEY"] = "first\nsecond"
        with self.assertRaisesRegex(AgentVMError, "STRIPE_API_KEY.*single-line"):
            self.config(raw).validate()

    def test_config_file_must_be_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent-vm.yaml"
            path.write_text("schema_version: 1\n", encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaisesRegex(AgentVMError, "mode 0600"):
                Config.load(path, Path(directory))

    def test_only_x86_64_is_supported(self):
        raw = copy.deepcopy(VALID)
        raw["vm"]["architecture"] = "aarch64"
        with self.assertRaisesRegex(AgentVMError, "x86_64"):
            self.config(raw).validate()

    def test_local_state_cannot_escape_repository(self):
        raw = copy.deepcopy(VALID)
        raw["local"] = {"state_dir": "../outside"}
        with self.assertRaisesRegex(AgentVMError, "inside the repository"):
            self.config(raw).validate()

    def test_vm_and_guest_names_are_safe(self):
        raw = copy.deepcopy(VALID)
        raw["guest"]["user"] = "bad user"
        with self.assertRaisesRegex(AgentVMError, "Unix account"):
            self.config(raw).validate()

    def test_boolean_resources_are_rejected(self):
        raw = copy.deepcopy(VALID)
        raw["vm"]["vcpus"] = True
        with self.assertRaisesRegex(AgentVMError, "int"):
            self.config(raw).validate()

    def test_nvm_version_must_be_an_exact_release_tag(self):
        for version in ("0.40.3", "main", "v0.40", "v0.40.3; touch /tmp/bad"):
            with self.subTest(version=version):
                raw = copy.deepcopy(VALID)
                raw["services"]["nvm"]["version"] = version
                with self.assertRaisesRegex(AgentVMError, "services.nvm.version"):
                    self.config(raw).validate()

    def test_uv_version_must_be_an_exact_release(self):
        for version in ("", "v0.12.7", "0.12", "latest", "0.12.7rc1"):
            with self.subTest(version=version):
                raw = copy.deepcopy(VALID)
                raw["services"]["uv"]["version"] = version
                with self.assertRaisesRegex(AgentVMError, "services.uv.version"):
                    self.config(raw).validate()

    def test_node_major_must_be_positive(self):
        raw = copy.deepcopy(VALID)
        raw["services"]["node_major"] = 0
        with self.assertRaisesRegex(AgentVMError, "services.node_major"):
            self.config(raw).validate()

    def test_legacy_pi_package_is_rejected(self):
        raw = copy.deepcopy(VALID)
        raw["services"]["pi"]["npm_package"] = "@mariozechner/pi-coding-agent"
        with self.assertRaisesRegex(AgentVMError, "Kandev Pi ACP compatibility"):
            self.config(raw).validate()

    def test_pi_superpowers_package_is_required(self):
        raw = copy.deepcopy(VALID)
        del raw["services"]["pi"]["superpowers_package"]
        with self.assertRaisesRegex(AgentVMError, "services.pi.superpowers_package"):
            self.config(raw).validate()

    def test_pi_superpowers_package_is_pinned_to_supported_distribution(self):
        raw = copy.deepcopy(VALID)
        raw["services"]["pi"]["superpowers_package"] = "other-package"
        with self.assertRaisesRegex(AgentVMError, "@weiping/pi-superpowers"):
            self.config(raw).validate()

    def test_repository_pi_skills_are_discovered_for_ansible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "skills" / "ggs"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(
                "---\nname: ggs\ndescription: Git workflows\n---\n",
                encoding="utf-8",
            )
            config = Config(path=root / "config.yaml", root=root, raw=copy.deepcopy(VALID))

            config.validate()

            self.assertEqual(config.pi_skills, [{"name": "ggs", "source": str(source.absolute())}])

    def test_repository_pi_skill_must_contain_skill_md(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skills" / "ggs").mkdir(parents=True)
            config = Config(path=root / "config.yaml", root=root, raw=copy.deepcopy(VALID))
            with self.assertRaisesRegex(AgentVMError, "skill 'ggs' must contain SKILL.md"):
                config.validate()

    def test_repository_pi_skill_name_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "skills" / "Bad Skill"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("skill", encoding="utf-8")
            config = Config(path=root / "config.yaml", root=root, raw=copy.deepcopy(VALID))
            with self.assertRaisesRegex(AgentVMError, "lowercase letters"):
                config.validate()


if __name__ == "__main__":
    unittest.main()
