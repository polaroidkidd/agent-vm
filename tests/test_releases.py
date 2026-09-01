import unittest
from pathlib import Path
from unittest.mock import patch

from agent_vm.config import Config
from agent_vm.errors import AgentVMError
from agent_vm.releases import github_latest, npm_latest, pypi_latest, resolve_all

from tests.test_config import VALID


class ReleaseTests(unittest.TestCase):
    @patch("agent_vm.releases._json")
    def test_pypi_latest_selects_checksum_verified_universal_wheel(self, metadata):
        metadata.return_value = {
            "info": {"version": "0.44.0"},
            "releases": {
                "0.44.0": [{
                    "filename": "pr_agent-0.44.0-py3-none-any.whl",
                    "url": "https://files.pythonhosted.org/pr_agent.whl",
                    "digests": {"sha256": "a" * 64},
                }],
            },
        }

        release = pypi_latest("pr-agent")

        self.assertEqual("0.44.0", release.version)
        self.assertEqual("a" * 64, release.sha256)
        metadata.assert_called_once_with(
            "https://pypi.org/pypi/pr-agent/json",
            accept="application/json",
        )

    @patch("agent_vm.releases._json")
    def test_pypi_latest_rejects_wheel_without_checksum(self, metadata):
        metadata.return_value = {
            "info": {"version": "0.44.0"},
            "releases": {
                "0.44.0": [{
                    "filename": "pr_agent-0.44.0-py3-none-any.whl",
                    "url": "https://files.pythonhosted.org/pr_agent.whl",
                    "digests": {},
                }],
            },
        }
        with self.assertRaisesRegex(AgentVMError, "no usable SHA-256"):
            pypi_latest("pr-agent")

    @patch("agent_vm.releases._json")
    def test_npm_latest_accepts_stable(self, metadata):
        metadata.return_value = {"version": "1.2.3"}
        self.assertEqual(npm_latest("package").version, "1.2.3")
        metadata.assert_called_once_with(
            "https://registry.npmjs.org/package/latest",
            accept="application/json",
        )

    @patch("agent_vm.releases._json")
    def test_npm_latest_rejects_development_versions(self, metadata):
        for version in ("1.2.3-alpha.1", "1.2.3-beta", "1.2.3-rc.1", "2.0.0-nightly.1"):
            metadata.return_value = {"version": version}
            with self.subTest(version=version), self.assertRaises(AgentVMError):
                npm_latest("package")

    @patch("agent_vm.releases._json")
    def test_github_release_requires_one_digest_verified_asset(self, metadata):
        metadata.return_value = {
            "tag_name": "v7.1.0",
            "draft": False,
            "prerelease": False,
            "assets": [{
                "name": "CLIProxyAPI_7.1.0_linux_amd64.tar.gz",
                "browser_download_url": "https://example.test/asset",
                "digest": "sha256:" + "a" * 64,
            }],
        }
        release = github_latest("owner/repo", r"linux_amd64\.tar\.gz$")
        self.assertEqual(release.version, "7.1.0")
        self.assertEqual(release.sha256, "a" * 64)
        metadata.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/releases/latest",
            accept="application/vnd.github+json",
        )

    @patch("agent_vm.releases._json")
    def test_github_release_rejects_missing_digest(self, metadata):
        metadata.return_value = {
            "tag_name": "v7.1.0", "draft": False, "prerelease": False,
            "assets": [{"name": "app_linux_amd64.tar.gz", "browser_download_url": "https://example.test/asset"}],
        }
        with self.assertRaisesRegex(AgentVMError, "no usable SHA-256"):
            github_latest("owner/repo", r"linux_amd64\.tar\.gz$")

    @patch("agent_vm.releases._json")
    def test_resolve_all_records_exact_pi_superpowers_release(self, metadata):
        def response(url, *, accept):
            if url.startswith("https://registry.npmjs.org/"):
                return {"version": "5.1.0"}
            return {
                "tag_name": "v7.1.0",
                "draft": False,
                "prerelease": False,
                "assets": [{
                    "name": "CLIProxyAPI_7.1.0_linux_amd64.tar.gz",
                    "browser_download_url": "https://example.test/asset",
                    "digest": "sha256:" + "a" * 64,
                }],
            }

        metadata.side_effect = response
        config = Config(path=Path("config.yaml"), root=Path("/tmp/repo"), raw=VALID)

        releases = resolve_all(config)

        self.assertIn("pi_superpowers", releases)
        self.assertEqual(
            releases["pi_superpowers"],
            {
                "version": "5.1.0",
                "source": "npm:@weiping/pi-superpowers",
                "url": None,
                "sha256": None,
                "asset": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
