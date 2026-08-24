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
    },
    "ports": {"kandev": 38429, "bifrost": 8080, "cliproxyapi": 8317},
    "NB_HOSTNAME": "agent-vm",
    "NB_MANAGEMENT_URL": "https://netbird.example.com",
    "NB_SETUP_KEY": "test-setup-key",
    "services": {
        "nvm": {"version": "v0.40.3"},
        "node_major": 24,
        "kandev": {"npm_package": "kandev"},
        "pi": {"npm_package": "@earendil-works/pi-coding-agent", "default_model": "model"},
        "bifrost": {"npm_package": "bifrost"},
        "cliproxyapi": {"github_repository": "owner/repo", "asset_pattern": "linux"},
    },
}


class ConfigTests(unittest.TestCase):
    def config(self, raw=None):
        return Config(path=Path("config.yaml"), root=Path("/tmp/repo"), raw=copy.deepcopy(raw or VALID))

    def test_valid_configuration(self):
        self.config().validate()

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

    def test_ports_must_be_unique(self):
        raw = copy.deepcopy(VALID)
        raw["ports"]["bifrost"] = raw["ports"]["kandev"]
        with self.assertRaisesRegex(AgentVMError, "unique"):
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
