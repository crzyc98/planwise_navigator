"""
Tests for the SyncService (E083 - Workspace Cloud Synchronization).

These tests verify the Git-based workspace synchronization functionality.
"""

from __future__ import annotations

import json
import logging
import os
import pytest
import socket
import stat
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

# Check if GitPython is available
try:
    import git
    from git import Repo

    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    git = None
    Repo = None


# Skip all tests if GitPython is not installed
pytestmark = pytest.mark.skipif(
    not GIT_AVAILABLE, reason="GitPython is required for sync tests"
)


@pytest.fixture
def temp_workspaces_dir():
    """Create a temporary directory for workspaces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_workspace(temp_workspaces_dir):
    """Create a sample workspace structure."""
    workspace_id = "test-workspace-123"
    workspace_dir = temp_workspaces_dir / workspace_id
    workspace_dir.mkdir(parents=True)

    # Create workspace.json
    workspace_json = workspace_dir / "workspace.json"
    workspace_json.write_text(
        json.dumps(
            {
                "id": workspace_id,
                "name": "Test Workspace",
                "description": "A test workspace",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )

    # Create base_config.yaml
    base_config = workspace_dir / "base_config.yaml"
    base_config.write_text("simulation:\n  years: [2025, 2026]\n")

    # Create scenarios directory with a scenario
    scenarios_dir = workspace_dir / "scenarios"
    scenarios_dir.mkdir()

    scenario_id = "test-scenario-456"
    scenario_dir = scenarios_dir / scenario_id
    scenario_dir.mkdir()

    scenario_json = scenario_dir / "scenario.json"
    scenario_json.write_text(
        json.dumps(
            {
                "id": scenario_id,
                "workspace_id": workspace_id,
                "name": "Test Scenario",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )

    return workspace_dir


@pytest.fixture
def sync_service(temp_workspaces_dir):
    """Create a SyncService with a temporary workspaces directory."""
    from planalign_api.services.sync_service import SyncService

    return SyncService(workspaces_root=temp_workspaces_dir)


class TestSyncModels:
    """Test sync model creation and validation."""

    def test_sync_config_defaults(self):
        """Test SyncConfig default values."""
        from planalign_api.models.sync import SyncConfig

        config = SyncConfig()
        assert config.version == 1
        assert config.enabled is False
        assert config.remote is None
        assert config.branch == "main"
        assert config.auto_sync is False
        assert config.conflict_strategy == "last-write-wins"

    def test_sync_config_custom_values(self):
        """Test SyncConfig with custom values."""
        from planalign_api.models.sync import SyncConfig

        config = SyncConfig(
            enabled=True,
            remote="git@github.com:user/repo.git",
            branch="develop",
            auto_sync=True,
            conflict_strategy="keep-local",
        )
        assert config.enabled is True
        assert config.remote == "git@github.com:user/repo.git"
        assert config.branch == "develop"
        assert config.auto_sync is True
        assert config.conflict_strategy == "keep-local"

    def test_sync_status_model(self):
        """Test SyncStatus model."""
        from planalign_api.models.sync import SyncStatus

        status = SyncStatus(
            is_initialized=True,
            remote_url="git@github.com:user/repo.git",
            branch="main",
            local_changes=5,
            ahead=2,
            behind=1,
        )
        assert status.is_initialized is True
        assert status.local_changes == 5
        assert status.ahead == 2
        assert status.behind == 1

    def test_sync_log_entry_model(self):
        """Test SyncLogEntry model."""
        from planalign_api.models.sync import SyncLogEntry

        entry = SyncLogEntry(
            timestamp=datetime.now(timezone.utc),
            operation="push",
            workspaces_affected=3,
            scenarios_affected=10,
            message="Pushed changes",
            commit_sha="abc1234",
        )
        assert entry.operation == "push"
        assert entry.workspaces_affected == 3
        assert entry.success is True

    def test_sync_push_result_model(self):
        """Test SyncPushResult model."""
        from planalign_api.models.sync import SyncPushResult

        result = SyncPushResult(
            success=True,
            commit_sha="abc1234",
            files_pushed=15,
            message="Push successful",
        )
        assert result.success is True
        assert result.files_pushed == 15

    def test_sync_pull_result_model(self):
        """Test SyncPullResult model."""
        from planalign_api.models.sync import SyncPullResult

        result = SyncPullResult(
            success=True,
            files_updated=5,
            files_added=3,
            files_removed=1,
            message="Pull successful",
        )
        assert result.success is True
        assert result.files_updated == 5
        assert len(result.conflicts) == 0


class TestSyncServiceInitialization:
    """Test SyncService initialization."""

    def test_service_creation(self, sync_service, temp_workspaces_dir):
        """Test SyncService can be created."""
        assert sync_service.workspaces_root == temp_workspaces_dir
        assert sync_service.workspaces_root.exists()

    def test_not_initialized_by_default(self, sync_service):
        """Test sync is not initialized by default."""
        assert sync_service.is_initialized() is False

    def test_get_status_not_initialized(self, sync_service):
        """Test getting status when not initialized."""
        status = sync_service.get_status()
        assert status.is_initialized is False
        assert status.remote_url is None


class TestSyncServiceConfig:
    """Test sync configuration management."""

    def test_get_default_config(self, sync_service):
        """Test getting default config when none exists."""
        config = sync_service.get_sync_config()
        assert config.enabled is False
        assert config.remote is None

    def test_save_and_load_config(self, sync_service):
        """Test saving and loading sync config."""
        from planalign_api.models.sync import SyncConfig

        config = SyncConfig(
            enabled=True,
            remote="git@github.com:user/repo.git",
            branch="develop",
        )
        sync_service.save_sync_config(config)

        loaded = sync_service.get_sync_config()
        assert loaded.enabled is True
        assert loaded.remote == "git@github.com:user/repo.git"
        assert loaded.branch == "develop"


class TestSyncServiceOperations:
    """Test sync operations (init, push, pull)."""

    def test_init_creates_git_repo(
        self, sync_service, temp_workspaces_dir, monkeypatch
    ):
        """Test that init creates a Git repository."""
        # Resolve the remote to a public address without real DNS
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            lambda host, port, *a, **kw: [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("140.82.121.4", 0))
            ],
        )
        # Mock the remote operations
        with patch.object(sync_service, "_create_initial_commit"):
            # Init will fail on remote operations, but should create local repo
            try:
                sync_service.init(
                    remote_url="git@github.com:user/test-repo.git",
                    branch="main",
                )
            except Exception:
                pass  # Expected to fail on remote operations

            # Check if git repo was created
            git_dir = temp_workspaces_dir / ".git"
            # The repo should have been initialized
            assert sync_service.repo is not None or git_dir.exists()

    def test_push_without_init_fails(self, sync_service):
        """Test that push fails when sync is not initialized."""
        result = sync_service.push()
        assert result.success is False
        assert "not initialized" in result.message.lower()

    def test_pull_without_init_fails(self, sync_service):
        """Test that pull fails when sync is not initialized."""
        result = sync_service.pull()
        assert result.success is False
        assert "not initialized" in result.message.lower()


class TestSyncServiceLogging:
    """Test sync operation logging."""

    def test_log_operation(self, sync_service):
        """Test logging a sync operation."""
        sync_service._log_operation(
            operation="push",
            message="Test push",
            workspaces_affected=2,
            scenarios_affected=5,
            commit_sha="abc1234",
        )

        logs = sync_service.get_sync_log(limit=10)
        assert len(logs) == 1
        assert logs[0].operation == "push"
        assert logs[0].message == "Test push"
        assert logs[0].workspaces_affected == 2

    def test_log_limit(self, sync_service):
        """Test log limit is respected."""
        # Create 10 log entries
        for i in range(10):
            sync_service._log_operation(
                operation="push",
                message=f"Push {i}",
            )

        logs = sync_service.get_sync_log(limit=5)
        assert len(logs) == 5

    def test_empty_log(self, sync_service):
        """Test getting empty log."""
        logs = sync_service.get_sync_log()
        assert len(logs) == 0


class TestSyncServiceWorkspaceInfo:
    """Test workspace sync information."""

    def test_get_workspace_info_empty(self, sync_service):
        """Test getting workspace info when no workspaces exist."""
        infos = sync_service.get_workspace_sync_info()
        assert len(infos) == 0

    def test_get_workspace_info_with_workspace(self, sync_service, sample_workspace):
        """Test getting workspace info with a sample workspace."""
        infos = sync_service.get_workspace_sync_info()
        assert len(infos) == 1
        assert infos[0].workspace_name == "Test Workspace"
        assert infos[0].scenario_count == 1

    def test_count_content(self, sync_service, sample_workspace):
        """Test counting workspaces and scenarios."""
        workspaces, scenarios = sync_service._count_content()
        assert workspaces == 1
        assert scenarios == 1


class TestGitignoreTemplate:
    """Test .gitignore template."""

    def test_gitignore_excludes_duckdb(self):
        """Test .gitignore template excludes DuckDB files."""
        from planalign_api.services.sync_service import GITIGNORE_TEMPLATE

        assert "*.duckdb" in GITIGNORE_TEMPLATE

    def test_gitignore_excludes_xlsx(self):
        """Test .gitignore template excludes Excel files."""
        from planalign_api.services.sync_service import GITIGNORE_TEMPLATE

        assert "*.xlsx" in GITIGNORE_TEMPLATE

    def test_gitignore_keeps_json(self):
        """Test .gitignore template keeps JSON files."""
        from planalign_api.services.sync_service import GITIGNORE_TEMPLATE

        # The template should have negation patterns for JSON
        assert "!**/workspace.json" in GITIGNORE_TEMPLATE
        assert "!**/scenario.json" in GITIGNORE_TEMPLATE


class TestSyncExceptions:
    """Test sync exception classes."""

    def test_sync_error(self):
        """Test SyncError exception."""
        from planalign_api.services.sync_service import SyncError

        error = SyncError("Test error")
        assert str(error) == "Test error"

    def test_sync_auth_error(self):
        """Test SyncAuthError exception."""
        from planalign_api.services.sync_service import SyncAuthError

        error = SyncAuthError("Auth failed")
        assert str(error) == "Auth failed"
        assert isinstance(error, Exception)

    def test_sync_conflict_error(self):
        """Test SyncConflictError exception."""
        from planalign_api.services.sync_service import SyncConflictError

        error = SyncConflictError("Conflict detected", ["file1.json", "file2.yaml"])
        assert "Conflict detected" in str(error)
        assert error.conflicting_files == ["file1.json", "file2.yaml"]


@pytest.mark.fast
class TestSyncModelsValidation:
    """Fast unit tests for sync model validation."""

    def test_sync_config_conflict_strategy_validation(self):
        """Test that invalid conflict strategies are rejected."""
        from planalign_api.models.sync import SyncConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SyncConfig(conflict_strategy="invalid-strategy")

    def test_sync_log_entry_operation_validation(self):
        """Test that invalid operations are rejected."""
        from planalign_api.models.sync import SyncLogEntry
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SyncLogEntry(
                timestamp=datetime.now(timezone.utc),
                operation="invalid-op",
                message="Test",
            )


def _configure_test_git_identity(repo: Repo) -> None:
    with repo.config_writer() as writer:
        writer.set_value("user", "name", "PlanAlign Test")
        writer.set_value("user", "email", "test@example.com")


def _make_bare_remote(tmp_path: Path) -> tuple[Path, Repo]:
    remote_dir = tmp_path / "remote.git"
    bare = Repo.init(remote_dir, bare=True)
    return remote_dir, bare


@pytest.mark.fast
class TestSyncHardening:
    """Tests for credential handling, staging allowlist, re-validation, and Git safety."""

    def test_config_rewrites_legacy_credentials_on_load_with_0600(self, tmp_path):
        from planalign_api.services.sync_service import SYNC_CONFIG_FILE, SyncService

        service = SyncService(workspaces_root=tmp_path / "workspaces")
        cfg_path = service.workspaces_root / SYNC_CONFIG_FILE
        cfg_path.write_text(
            "enabled: true\n"
            "remote: https://alice:legacySecret@github.com/org/repo.git\n"
            "branch: main\n",
            encoding="utf-8",
        )
        if os.name == "posix":
            os.chmod(cfg_path, 0o644)

        loaded = service.get_sync_config()

        assert loaded.remote == "https://github.com/org/repo.git"
        disk_text = cfg_path.read_text(encoding="utf-8")
        assert "legacySecret" not in disk_text
        assert "alice" not in disk_text
        assert "https://github.com/org/repo.git" in disk_text
        if os.name == "posix":
            assert stat.S_IMODE(cfg_path.stat().st_mode) == 0o600

    def test_staging_allowlist_and_no_symlinks(
        self, sample_workspace, temp_workspaces_dir
    ):
        from planalign_api.services.sync_service import SYNC_CONFIG_FILE, SyncService

        service = SyncService(workspaces_root=temp_workspaces_dir)
        repo = Repo.init(temp_workspaces_dir)
        _configure_test_git_identity(repo)

        # Write allowlisted files
        scenario_dir = sample_workspace / "scenarios" / "test-scenario-456"
        (scenario_dir / "overrides.yaml").write_text(
            "compensation:\n  cola_rate: 0.03\n"
        )

        # Write excluded files that previously matched **/*.json or **/*.yaml
        target_manifest = sample_workspace / "target" / "manifest.json"
        target_manifest.parent.mkdir(parents=True)
        target_manifest.write_text('{"metadata": {}}')

        root_target = temp_workspaces_dir / "target" / "manifest.json"
        root_target.parent.mkdir(parents=True)
        root_target.write_text('{"metadata": {}}')

        cal_request = sample_workspace / "calibration_jobs" / "x" / "request.json"
        cal_request.parent.mkdir(parents=True)
        cal_request.write_text('{"job": "x"}')

        root_cal = temp_workspaces_dir / "calibration_jobs" / "x" / "request.json"
        root_cal.parent.mkdir(parents=True)
        root_cal.write_text('{"job": "x"}')

        dbt_file = sample_workspace / "dbt_project" / "dbt_project.yml"
        dbt_file.parent.mkdir(parents=True)
        dbt_file.write_text("name: test\n")

        run_file = scenario_dir / "runs" / "r1" / "run_metadata.json"
        run_file.parent.mkdir(parents=True)
        run_file.write_text('{"run_id": "r1"}')

        ckpt_file = sample_workspace / "checkpoints" / "cp.json"
        ckpt_file.parent.mkdir(parents=True)
        ckpt_file.write_text("{}")

        # Sync config must not be staged either
        (temp_workspaces_dir / SYNC_CONFIG_FILE).write_text("enabled: true\n")

        # Symlink in an allowlisted slot must never be staged
        outside = temp_workspaces_dir.parent / "outside_secret.yaml"
        outside.write_text("secret: true\n")
        sym_scenario = sample_workspace / "scenarios" / "sym-scenario"
        sym_scenario.mkdir()
        (sym_scenario / "config.yaml").symlink_to(outside)

        staged_count = service._stage_syncable_files(repo)
        staged_paths = {path for path, _stage in repo.index.entries}

        assert staged_count == 4
        assert staged_paths == {
            "test-workspace-123/workspace.json",
            "test-workspace-123/base_config.yaml",
            "test-workspace-123/scenarios/test-scenario-456/scenario.json",
            "test-workspace-123/scenarios/test-scenario-456/overrides.yaml",
        }
        assert all("manifest.json" not in p for p in staged_paths)
        assert all("calibration_jobs" not in p for p in staged_paths)
        assert all("sym-scenario" not in p for p in staged_paths)
        assert SYNC_CONFIG_FILE not in staged_paths

    def test_init_passes_normalized_url_and_sets_hardened_git_config(
        self, tmp_path, monkeypatch
    ):
        from planalign_api.services.sync_service import SyncService

        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            lambda host, port, *a, **kw: [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("140.82.121.4", 0))
            ],
        )

        service = SyncService(workspaces_root=tmp_path / "workspaces")
        with patch.object(
            SyncService,
            "_sync_initial_branch",
            lambda self, repo, origin, branch: None,
        ):
            service.init(remote_url="  git@github.com:org/repo.git  ", branch="main")

        repo = Repo(service.workspaces_root)
        assert list(repo.remote("origin").urls) == ["git@github.com:org/repo.git"]
        assert repo.git.config("--local", "--get", "core.symlinks") == "false"
        assert repo.git.config("--local", "--get", "http.followRedirects") == "false"
        assert repo.git.config("--local", "--get", "protocol.allow") == "never"
        assert repo.git.config("--local", "--get", "protocol.https.allow") == "always"
        assert repo.git.config("--local", "--get", "protocol.ssh.allow") == "always"

        env = service._hardened_git_env()
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert "GIT_CONFIG_COUNT" in env
        assert service._allowed_git_protocols() == ["https", "ssh"]

    def test_hardened_git_env_blocks_file_transport_and_honors_extra_schemes(
        self, tmp_path, monkeypatch
    ):
        from planalign_api.config import APISettings
        from planalign_api.services.sync_service import SyncService

        remote_dir, _ = _make_bare_remote(tmp_path)
        service = SyncService(workspaces_root=tmp_path / "workspaces")
        repo = Repo.init(service.workspaces_root)
        repo.create_remote("origin", str(remote_dir))
        service._harden_repo_config(repo)

        with pytest.raises(git.GitCommandError):
            with repo.git.custom_environment(**service._hardened_git_env()):
                repo.remote("origin").fetch()

        # Extra network schemes from settings are added, while file/ext stay excluded.
        custom_settings = APISettings(
            workspaces_root=service.workspaces_root,
            git_remote_allowed_schemes=["https", "ssh", "git", "file", "ext"],
        )
        monkeypatch.setattr(
            "planalign_api.services.sync_service.get_settings", lambda: custom_settings
        )
        assert service._allowed_git_protocols() == ["https", "ssh", "git"]

    def test_push_and_pull_revalidate_stored_origin_url(self, tmp_path, monkeypatch):
        from planalign_api.services.sync_service import (
            SyncService,
            SyncValidationError,
        )

        workspaces_root = tmp_path / "workspaces"
        service = SyncService(workspaces_root=workspaces_root)
        repo = Repo.init(workspaces_root)
        _configure_test_git_identity(repo)
        repo.create_remote("origin", "https://git.example.com/org/repo.git")
        service.save_sync_config(
            service.get_sync_config().model_copy(
                update={
                    "enabled": True,
                    "remote": "https://git.example.com/org/repo.git",
                    "branch": "main",
                }
            )
        )

        # Remote now resolves to a private address -> both push and pull must refuse.
        monkeypatch.setattr(
            "planalign_api.services.remote_policy.socket.getaddrinfo",
            lambda host, port, *a, **kw: [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))
            ],
        )

        with pytest.raises(SyncValidationError) as push_exc:
            service.push()
        assert "Remote host is not an allowed destination" in str(push_exc.value)
        assert "127.0.0.1" not in str(push_exc.value)

        with pytest.raises(SyncValidationError) as pull_exc:
            service.pull()
        assert "Remote host is not an allowed destination" in str(pull_exc.value)
        assert "127.0.0.1" not in str(pull_exc.value)

    def test_pull_checks_out_symlinks_as_plain_files_and_scrubs_on_disk_symlinks(
        self, tmp_path, monkeypatch, caplog
    ):
        from planalign_api.services.sync_service import SyncService

        remote_dir, _ = _make_bare_remote(tmp_path)

        # Seed a bare remote with an initial commit and a second commit containing a symlink.
        seed_dir = tmp_path / "seed"
        seed = Repo.init(seed_dir)
        _configure_test_git_identity(seed)
        ws_seed = seed_dir / "ws-1"
        ws_seed.mkdir()
        (ws_seed / "workspace.json").write_text('{"id": "ws-1", "name": "WS"}')
        seed.index.add(["ws-1/workspace.json"])
        seed.index.commit("initial")
        seed.create_remote("origin", str(remote_dir))
        seed.remote("origin").push("HEAD:refs/heads/main")

        # Initialize sync repo against the local bare remote (allowing local file
        # transport only inside this test while keeping core.symlinks=false active).
        workspaces_root = tmp_path / "workspaces"
        service = SyncService(workspaces_root=workspaces_root)
        monkeypatch.setattr(
            "planalign_api.services.sync_service.validate_remote_url",
            lambda url, _settings=None: url,
        )
        monkeypatch.setattr(
            SyncService, "_allowed_git_protocols", lambda self: ["file"]
        )
        service.init(remote_url=str(remote_dir), branch="main")

        # Push a commit containing a git symlink (mode 120000) to the bare remote.
        link_path = ws_seed / "link.yaml"
        link_path.symlink_to("/etc/passwd")
        seed.index.add(["ws-1/link.yaml"])
        seed.index.commit("add symlink")
        seed.remote("origin").push("HEAD:refs/heads/main")

        pull_result = service.pull()
        assert pull_result.success is True
        pulled_link = workspaces_root / "ws-1" / "link.yaml"
        assert pulled_link.exists()
        assert not pulled_link.is_symlink()
        assert pulled_link.is_file()

        # Defense-in-depth post-pull walk removes any symlink present on disk and logs it.
        extra_link = workspaces_root / "ws-1" / "on_disk_symlink.yaml"
        extra_link.symlink_to("/etc/passwd")
        with caplog.at_level(
            logging.WARNING, logger="planalign_api.services.sync_service"
        ):
            removed = service._remove_pulled_symlinks(["ws-1/on_disk_symlink.yaml"])
        assert removed == 1
        assert not extra_link.is_symlink()
        assert not extra_link.exists()
        assert "on_disk_symlink.yaml" in caplog.text

    def test_push_and_pull_roundtrip_against_bare_remote(self, tmp_path, monkeypatch):
        from planalign_api.services.sync_service import SYNC_CONFIG_FILE, SyncService

        remote_dir, bare = _make_bare_remote(tmp_path)
        workspaces_root = tmp_path / "workspaces"
        ws_dir = workspaces_root / "ws-alpha"
        ws_dir.mkdir(parents=True)
        (ws_dir / "workspace.json").write_text('{"id": "ws-alpha", "name": "Alpha"}')
        (ws_dir / "base_config.yaml").write_text("simulation:\n  seed: 42\n")
        (ws_dir / "target").mkdir()
        (ws_dir / "target" / "manifest.json").write_text("{}")

        service = SyncService(workspaces_root=workspaces_root)
        monkeypatch.setattr(
            "planalign_api.services.sync_service.validate_remote_url",
            lambda url, _settings=None: url,
        )
        monkeypatch.setattr(
            SyncService, "_allowed_git_protocols", lambda self: ["file"]
        )

        # Configure git author on the sync repo after Repo.init
        orig_init = Repo.init

        def _init_with_identity(*args, **kwargs):
            r = orig_init(*args, **kwargs)
            _configure_test_git_identity(r)
            return r

        monkeypatch.setattr(
            "planalign_api.services.sync_service.Repo.init", _init_with_identity
        )

        service.init(remote_url=str(remote_dir), branch="main")
        push_res = service.push(message="Initial push")
        assert push_res.success is True

        # Verify bare remote contains allowlisted files only (no sync config or target/manifest.json)
        remote_blobs = {
            item.path
            for item in bare.commit("main").tree.traverse()
            if getattr(item, "type", None) == "blob"
        }
        assert "ws-alpha/workspace.json" in remote_blobs
        assert "ws-alpha/base_config.yaml" in remote_blobs
        assert SYNC_CONFIG_FILE not in remote_blobs
        assert "ws-alpha/target/manifest.json" not in remote_blobs

        # A change pushed from another clone arrives through pull.
        other = Repo.clone_from(str(remote_dir), tmp_path / "other", branch="main")
        _configure_test_git_identity(other)
        (tmp_path / "other" / "ws-alpha" / "base_config.yaml").write_text(
            "simulation:\n  seed: 7\n"
        )
        other.index.add(["ws-alpha/base_config.yaml"])
        other.index.commit("Change seed")
        other.remote("origin").push("main")

        pull_res = service.pull()
        assert pull_res.success is True
        assert "seed: 7" in (ws_dir / "base_config.yaml").read_text()

    def test_push_untracks_legacy_sync_config(self, tmp_path, monkeypatch):
        from planalign_api.services.sync_service import (
            SYNC_CONFIG_FILE,
            GITIGNORE_TEMPLATE,
            SyncService,
        )

        remote_dir, bare = _make_bare_remote(tmp_path)
        workspaces_root = tmp_path / "workspaces"
        ws_dir = workspaces_root / "ws-alpha"
        ws_dir.mkdir(parents=True)
        (ws_dir / "workspace.json").write_text('{"id": "ws-alpha", "name": "Alpha"}')

        # An older install committed the sync config and has an old .gitignore.
        repo = Repo.init(workspaces_root)
        _configure_test_git_identity(repo)
        repo.create_remote("origin", str(remote_dir))
        (workspaces_root / ".gitignore").write_text("*.duckdb\n")
        (workspaces_root / SYNC_CONFIG_FILE).write_text("enabled: true\n")
        repo.index.add([".gitignore", SYNC_CONFIG_FILE, "ws-alpha/workspace.json"])
        repo.index.commit("Old sync")
        repo.git.branch("-M", "main")

        service = SyncService(workspaces_root=workspaces_root)
        monkeypatch.setattr(
            "planalign_api.services.sync_service.validate_remote_url",
            lambda url, _settings=None: url,
        )
        monkeypatch.setattr(
            SyncService, "_allowed_git_protocols", lambda self: ["file"]
        )

        assert service.push().success is True

        remote_blobs = {
            item.path
            for item in bare.commit("main").tree.traverse()
            if getattr(item, "type", None) == "blob"
        }
        assert SYNC_CONFIG_FILE not in remote_blobs
        assert "ws-alpha/workspace.json" in remote_blobs
        assert (workspaces_root / SYNC_CONFIG_FILE).exists()
        gitignore = (workspaces_root / ".gitignore").read_text().splitlines()
        assert SYNC_CONFIG_FILE in gitignore
        assert SYNC_CONFIG_FILE in GITIGNORE_TEMPLATE
