"""Tests for Git remote URL policy enforcement (SSRF hardening).

Covers the acceptance criteria for sync initialization: explicit scheme/host
policy, rejection of file/local/ext transports and malformed URLs, blocking of
loopback/private/link-local/metadata destinations unless explicitly enabled,
and credential redaction from strings surfaced to users.
"""

from __future__ import annotations

import logging
import os
import socket
import stat
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import planalign_api.config as api_config
from planalign_api.config import APISettings
from planalign_api.main import create_app
from planalign_api.services.remote_policy import (
    RemotePolicyError,
    redact_remote_url,
    validate_remote_url,
)
from planalign_cli.commands import sync as sync_command

pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides) -> APISettings:
    return APISettings(**overrides)


def _resolver(ip: str):
    """Build a getaddrinfo stub resolving every hostname to ``ip``."""

    def resolve(host, port, *args, **kwargs):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 0, "", (ip, 0))]

    return resolve


def _validate(url: str, monkeypatch, ip: str = "93.184.216.34", **policy) -> str:
    monkeypatch.setattr(
        "planalign_api.services.remote_policy.socket.getaddrinfo", _resolver(ip)
    )
    return validate_remote_url(url, _settings(**policy))


# ---------------------------------------------------------------------------
# Allowed remotes
# ---------------------------------------------------------------------------


class TestAllowedRemotes:
    def test_https_public_host_allowed(self, monkeypatch):
        url = "https://github.com/a/b.git"
        assert _validate(url, monkeypatch) == url

    def test_scp_style_ssh_allowed_and_kept_as_given(self, monkeypatch):
        url = "git@github.com:a/b.git"
        assert _validate(f"  {url}  ", monkeypatch) == url

    def test_ssh_scheme_allowed(self, monkeypatch):
        url = "ssh://git@git.example.com/team/repo.git"
        assert _validate(url, monkeypatch) == url

    def test_embedded_userinfo_allowed_and_preserved(self, monkeypatch):
        url = "https://user:token@github.com/user/repo.git"
        assert _validate(url, monkeypatch) == url

    def test_ipv4_mapped_public_address_allowed(self, monkeypatch):
        url = "https://github.com/a/b.git"
        assert _validate(url, monkeypatch, ip="::ffff:93.184.216.34") == url

    def test_http_allowed_via_opt_in(self, monkeypatch):
        url = "http://gitserver.internal/team/repo.git"
        assert _validate(url, monkeypatch, git_remote_allowed_schemes=["http"]) == url

    def test_private_destination_allowed_via_explicit_opt_in(self, monkeypatch):
        url = "https://192.168.1.50/team/repo.git"
        assert (
            _validate(
                url,
                monkeypatch,
                ip="192.168.1.50",
                git_remote_allow_private_networks=True,
            )
            == url
        )

    def test_suffix_wildcard_host_allowlist(self, monkeypatch):
        url = "https://git.corp.example.com/team/repo.git"
        assert (
            _validate(url, monkeypatch, git_remote_allowed_hosts=["example.com"]) == url
        )

    def test_exact_host_allowlist_match(self, monkeypatch):
        url = "ssh://git@github.com/user/repo.git"
        assert (
            _validate(url, monkeypatch, git_remote_allowed_hosts=["github.com"]) == url
        )


# ---------------------------------------------------------------------------
# Blocked protocols, local paths, malformed URLs
# ---------------------------------------------------------------------------


class TestBlockedProtocolsAndMalformedUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "file://localhost/tmp/repo.git",
            "ext::sh -c curl evil",
            "/etc/passwd",
            "./local/repo.git",
            "~/repo.git",
            "C:\\repos\\repo.git",
            "",
            "   ",
            "https://",
            "not a url at all",
            f"https://github.com/repo.git?x={'a' * 3000}",
            "ssh://github.com#@127.0.0.1/x",
            "ssh://github.com?@10.0.0.1:2222/x",
            "github.com#@127.0.0.1:x",
            "https://0177.0.0.1/x",
            "https://0x7f000001/x",
            "https://2130706433/x",
            "https://127.1/x",
            "ssh://-oProxyCommand=x@github.com/x",
            "ssh://-evil.example.com/x",
            "https://user:p@ss@github.com/x.git",
            "https://github.com/repo%20name.git",
            "https://github.com/repo\\name.git",
            "https://github.com/repo name.git",
        ],
    )
    def test_rejected_without_resolution(self, url, monkeypatch):
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            _resolver("93.184.216.34"),
        )
        with pytest.raises(RemotePolicyError):
            validate_remote_url(url, _settings())

    def test_control_characters_rejected(self, monkeypatch):
        with pytest.raises(RemotePolicyError):
            _validate("https://github.com\x0d/repo.git", monkeypatch)

    def test_scheme_not_in_allowlist_rejected(self, monkeypatch):
        for url in ["ftp://example.com/repo.git", "http://example.com/repo.git"]:
            with pytest.raises(RemotePolicyError):
                _validate(url, monkeypatch)

    def test_unresolvable_host_rejected(self, monkeypatch):
        def failing_resolver(host, port, *args, **kwargs):
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            failing_resolver,
        )
        with pytest.raises(RemotePolicyError):
            validate_remote_url("https://nonexistent.invalid/repo.git", _settings())

    def test_host_allowlist_mismatch_rejected(self, monkeypatch):
        with pytest.raises(RemotePolicyError):
            _validate(
                "https://evil.example.net/repo.git",
                monkeypatch,
                git_remote_allowed_hosts=["example.com"],
            )

    def test_subdomain_of_allowlist_entry_not_bypassable(self, monkeypatch):
        # evil-github.com must NOT match allowlist entry "github.com".
        with pytest.raises(RemotePolicyError):
            _validate(
                "https://evil-github.com/repo.git",
                monkeypatch,
                git_remote_allowed_hosts=["github.com"],
            )


# ---------------------------------------------------------------------------
# Blocked network destinations
# ---------------------------------------------------------------------------


class TestBlockedDestinations:
    @pytest.mark.parametrize(
        ("url", "ip", "label"),
        [
            ("https://127.0.0.1/repo.git", "127.0.0.1", "loopback"),
            ("https://[::1]/repo.git", "::1", "loopback"),
            ("ssh://git@10.1.2.3/repo.git", "10.1.2.3", "private"),
            ("https://172.16.0.5/repo.git", "172.16.0.5", "private"),
            ("git@192.168.1.10:team/repo.git", "192.168.1.10", "private"),
            ("https://[fd00::1]/repo.git", "fd00::1", "private"),
            ("https://169.254.169.254/latest/meta-data", "169.254.169.254", "metadata"),
            (
                "https://fe80::1/repo.git".replace("fe80::1", "[fe80::1]"),
                "fe80::1",
                "link-local",
            ),
            ("https://0.0.0.0/repo.git", "0.0.0.0", "unspecified"),
            ("https://224.0.0.1/repo.git", "224.0.0.1", "multicast"),
            ("https://100.100.100.200/x", "100.100.100.200", "cgnat-metadata"),
            ("https://mapped.example.com/repo.git", "::ffff:127.0.0.1", "ipv4-mapped"),
            (
                "https://mapped-cgnat.example.com/repo.git",
                "::ffff:100.100.100.200",
                "ipv4-mapped-cgnat",
            ),
        ],
    )
    def test_blocked_addresses(self, monkeypatch, caplog, url, ip, label):
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo", _resolver(ip)
        )
        with caplog.at_level(
            logging.WARNING, logger="planalign_api.services.remote_policy"
        ):
            with pytest.raises(RemotePolicyError) as excinfo:
                validate_remote_url(url, _settings())
        message = str(excinfo.value)
        assert message == "Remote host is not an allowed destination"
        assert ip not in message
        assert ip in caplog.text

    def test_metadata_service_hostname_blocked(self, monkeypatch):
        # A hostile DNS answer pointing at the cloud metadata service.
        url = "https://metadata.internal.aws/repo.git"
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            _resolver("169.254.169.254"),
        )
        with pytest.raises(RemotePolicyError) as excinfo:
            validate_remote_url(url, _settings())
        assert "169.254.169.254" not in str(excinfo.value)

    def test_multi_address_response_blocks_if_any_is_private(self, monkeypatch, caplog):
        # Place the blocked IP first so server-side logging also verifies the
        # offending address (not the last address in the list) is recorded.
        responses = {
            "dual-homed.example.com": [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.9", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
            ]
        }

        def selective_resolver(host, port, *args, **kwargs):
            if host in responses:
                return responses[host]
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            selective_resolver,
        )
        with caplog.at_level(
            logging.WARNING, logger="planalign_api.services.remote_policy"
        ):
            with pytest.raises(RemotePolicyError) as excinfo:
                validate_remote_url(
                    "https://dual-homed.example.com/repo.git", _settings()
                )
        assert "10.0.0.9" not in str(excinfo.value)
        assert "93.184.216.34" not in str(excinfo.value)
        assert "10.0.0.9" in caplog.text

    def test_zone_id_link_local_blocked(self, monkeypatch):
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            _resolver("fe80::1%eth0"),
        )
        with pytest.raises(RemotePolicyError):
            validate_remote_url("https://gateway.local/repo.git", _settings())


# ---------------------------------------------------------------------------
# Credential redaction
# ---------------------------------------------------------------------------


class TestCredentialRedaction:
    @pytest.mark.parametrize(
        ("raw", "expected", "must_not_contain"),
        [
            (
                "https://ghp_secretToken123@github.com/org/repo.git",
                "https://github.com/org/repo.git",
                ["ghp_secretToken123"],
            ),
            (
                "https://user:s3cret@github.com/repo.git",
                "https://github.com/repo.git",
                ["user", "s3cret"],
            ),
            (
                "https://user:pa/ss@github.com/org/repo.git",
                "https://github.com/org/repo.git",
                ["user", "pa/ss"],
            ),
            (
                "https://user:p@ss@github.com/org/repo.git",
                "https://github.com/org/repo.git",
                ["user", "p@ss"],
            ),
            (
                "https://user:p@s/s@github.com/org/repo.git",
                "https://github.com/org/repo.git",
                ["user", "p@s/s"],
            ),
            (
                "Push failed: fatal: unable to access 'https://bob:pw123@host/x.git'",
                "Push failed: fatal: unable to access 'https://host/x.git'",
                ["bob", "pw123"],
            ),
            (
                "fatal: Authentication failed for 'https://tok_999@git.example.com/a/b.git/'",
                "fatal: Authentication failed for 'https://git.example.com/a/b.git/'",
                ["tok_999"],
            ),
            (
                "git@github.com:user/repo.git",
                "git@github.com:user/repo.git",
                [],
            ),
        ],
    )
    def test_redaction_table(self, raw, expected, must_not_contain):
        redacted = redact_remote_url(raw)
        assert redacted == expected
        for secret in must_not_contain:
            assert secret not in redacted

    def test_none_passthrough(self):
        assert redact_remote_url(None) is None

    def test_validation_error_never_contains_credentials(self, monkeypatch):
        with pytest.raises(RemotePolicyError) as excinfo:
            _validate("file:///tmp/x", monkeypatch)
        assert "s3cret" not in str(excinfo.value)

    def test_cli_status_redacts_embedded_remote_password(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            sync_command,
            "console",
            sync_command.Console(file=output, force_terminal=False),
        )
        monkeypatch.setattr(
            sync_command,
            "_get_sync_service",
            lambda: SimpleNamespace(
                get_status=lambda: SimpleNamespace(
                    is_initialized=True,
                    remote_url="https://alice:secret@example.com/repo.git",
                    branch="main",
                    local_changes=0,
                    ahead=0,
                    behind=0,
                    last_sync=None,
                    conflicts=[],
                    error=None,
                ),
                get_workspace_sync_info=lambda: [],
            ),
        )

        sync_command.sync_status()

        rendered = output.getvalue()
        assert "secret" not in rendered
        assert "alice" not in rendered
        assert "https://example.com/repo.git" in rendered


# ---------------------------------------------------------------------------
# Service integration
# ---------------------------------------------------------------------------


class TestSyncServicePolicyIntegration:
    def test_init_rejects_local_path_before_creating_repo(self, tmp_path, monkeypatch):
        pytest.importorskip("git")
        from planalign_api.services.sync_service import (
            SyncService,
            SyncValidationError,
        )

        service = SyncService(workspaces_root=tmp_path / "workspaces")
        with pytest.raises(SyncValidationError):
            service.init(remote_url="/etc/passwd")
        # Validation happens before any repository state is created.
        assert not (tmp_path / "workspaces" / ".git").exists()

    def test_init_rejects_ext_transport_with_credentials(self, tmp_path, monkeypatch):
        pytest.importorskip("git")
        from planalign_api.services.sync_service import (
            SyncService,
            SyncValidationError,
        )

        service = SyncService(workspaces_root=tmp_path / "workspaces")
        with pytest.raises(SyncValidationError) as excinfo:
            service.init(remote_url="ext::sh -c touch /tmp/pwned")
        assert "not allowed" in str(excinfo.value)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def _api_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)
    return TestClient(create_app(), raise_server_exceptions=False)


class TestSyncInitEndpoint:
    def test_init_rejects_file_remote_with_400(self, tmp_path, monkeypatch):
        pytest.importorskip("git")
        client = _api_client(tmp_path, monkeypatch)
        response = client.post(
            "/api/sync/init", json={"remote_url": "file:///tmp/repo.git"}
        )
        assert response.status_code == 400
        body = response.text
        assert "file" in body

    def test_init_rejects_loopback_remote_with_400(self, tmp_path, monkeypatch):
        pytest.importorskip("git")

        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            _resolver("127.0.0.1"),
        )
        client = _api_client(tmp_path, monkeypatch)
        response = client.post(
            "/api/sync/init",
            json={"remote_url": "https://user:s3cret@internal.local/repo.git"},
        )
        assert response.status_code == 400
        assert "s3cret" not in response.text

    def test_init_accepts_public_https_remote_shape(self, tmp_path, monkeypatch):
        pytest.importorskip("git")
        from planalign_api.services.sync_service import SyncService

        monkeypatch.setenv("GIT_AUTHOR_NAME", "PlanAlign Test")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
        monkeypatch.setenv("GIT_COMMITTER_NAME", "PlanAlign Test")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            _resolver("140.82.121.4"),
        )
        # Keep the test fully offline by stubbing the remote fetch step.
        with patch.object(
            SyncService,
            "_sync_initial_branch",
            lambda self, repo, origin, branch: self._create_initial_commit(
                repo, branch
            ),
        ):
            client = _api_client(tmp_path, monkeypatch)
            response = client.post(
                "/api/sync/init", json={"remote_url": "https://github.com/u/r.git"}
            )
        assert response.status_code == 200

    def test_sync_config_endpoint_and_disk_files_have_no_secret(
        self, tmp_path, monkeypatch
    ):
        pytest.importorskip("git")
        from git import Repo
        from planalign_api.services.sync_service import (
            SYNC_CONFIG_FILE,
            SYNC_LOG_FILE,
            SyncService,
        )

        monkeypatch.setenv("GIT_AUTHOR_NAME", "PlanAlign Test")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
        monkeypatch.setenv("GIT_COMMITTER_NAME", "PlanAlign Test")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            _resolver("140.82.121.4"),
        )
        secret_token = "ghp_superSecretToken98765"
        remote_with_secret = f"https://alice:{secret_token}@github.com/org/repo.git"

        with patch.object(
            SyncService,
            "_sync_initial_branch",
            lambda self, repo, origin, branch: self._create_initial_commit(
                repo, branch
            ),
        ):
            client = _api_client(tmp_path, monkeypatch)
            init_resp = client.post(
                "/api/sync/init", json={"remote_url": remote_with_secret}
            )
            assert init_resp.status_code == 200
            assert secret_token not in init_resp.text

            cfg_resp = client.get("/api/sync/config")
            assert cfg_resp.status_code == 200
            assert secret_token not in cfg_resp.text
            assert cfg_resp.json()["remote"] == "https://github.com/org/repo.git"

        workspaces_root = tmp_path / "workspaces"
        sync_cfg_path = workspaces_root / SYNC_CONFIG_FILE
        sync_log_path = workspaces_root / SYNC_LOG_FILE
        git_cfg_path = workspaces_root / ".git" / "config"

        assert secret_token not in sync_cfg_path.read_text(encoding="utf-8")
        assert secret_token not in sync_log_path.read_text(encoding="utf-8")
        assert secret_token in git_cfg_path.read_text(encoding="utf-8")

        repo = Repo(workspaces_root)
        committed = [
            item.path
            for item in repo.head.commit.tree.traverse()
            if getattr(item, "type", None) == "blob"
        ]
        assert SYNC_CONFIG_FILE not in committed
        assert SYNC_CONFIG_FILE in (workspaces_root / ".gitignore").read_text(
            encoding="utf-8"
        )

        if os.name == "posix":
            for private_file in (sync_cfg_path, sync_log_path, git_cfg_path):
                mode = stat.S_IMODE(private_file.stat().st_mode)
                assert (
                    mode == 0o600
                ), f"Expected 0600 on {private_file}, got {oct(mode)}"

    def test_push_and_pull_endpoints_reject_invalid_stored_remote(
        self, tmp_path, monkeypatch
    ):
        pytest.importorskip("git")
        from git import Repo
        from planalign_api.models.sync import SyncConfig
        from planalign_api.services.sync_service import SyncService

        workspaces_root = tmp_path / "workspaces"
        service = SyncService(workspaces_root=workspaces_root)
        repo = Repo.init(workspaces_root)
        repo.create_remote("origin", "https://git.example.com/org/repo.git")
        service.save_sync_config(
            SyncConfig(
                enabled=True,
                remote="https://git.example.com/org/repo.git",
                branch="main",
            )
        )

        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            _resolver("100.100.100.200"),
        )
        client = _api_client(tmp_path, monkeypatch)

        push_resp = client.post("/api/sync/push")
        assert push_resp.status_code == 400
        assert "Remote host is not an allowed destination" in push_resp.text
        assert "100.100.100.200" not in push_resp.text

        pull_resp = client.post("/api/sync/pull")
        assert pull_resp.status_code == 400
        assert "Remote host is not an allowed destination" in pull_resp.text
        assert "100.100.100.200" not in pull_resp.text
