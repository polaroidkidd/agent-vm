import unittest
from unittest.mock import patch

from agent_vm.errors import AgentVMError
from agent_vm.releases import github_latest, npm_latest


class ReleaseTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
