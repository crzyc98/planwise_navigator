"""Sync service for workspace cloud synchronization using Git (E083).

This service provides Git-based synchronization for PlanAlign workspaces,
enabling cross-device access and version control of workspace configurations.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

try:
    import git
    from git import Repo, GitCommandError, InvalidGitRepositoryError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    git = None
    Repo = None
    GitCommandError = Exception
    InvalidGitRepositoryError = Exception

from ..config import get_settings
from ..models.sync import (
    SyncConfig,
    SyncStatus,
    SyncLogEntry,
    SyncPushResult,
    SyncPullResult,
    WorkspaceSyncInfo,
)

logger = logging.getLogger(__name__)


# Default .gitignore content for workspace sync
GITIGNORE_TEMPLATE = """# PlanAlign Workspace Sync - Auto-generated
# Exclude large/regenerable files
*.duckdb
*.duckdb.wal
*.xlsx
*.parquet
*.csv

# Exclude temporary files
*.tmp
*.lock
*.log
__pycache__/
.DS_Store

# Exclude checkpoints (can be large)
checkpoints/

# Keep important metadata files
!**/workspace.json
!**/scenario.json
!**/run_metadata.json
!**/*.yaml
!**/*.yml
"""

# Sync config filename
SYNC_CONFIG_FILE = ".planalign-sync.yaml"
SYNC_LOG_FILE = ".planalign-sync-log.json"


class SyncError(Exception):
    """Base exception for sync operations."""
    pass


class SyncAuthError(SyncError):
    """Authentication failed with remote."""
    pass


class SyncConflictError(SyncError):
    """Conflict detected during sync."""
    def __init__(self, message: str, conflicting_files: List[str]):
        super().__init__(message)
        self.conflicting_files = conflicting_files


class SyncNetworkError(SyncError):
    """Network error during sync."""
    pass


class SyncService:
    """Service for Git-based workspace synchronization."""

    def __init__(self, workspaces_root: Optional[Path] = None):
        """Initialize the sync service.

        Args:
            workspaces_root: Root directory for workspaces. Defaults to settings.
        """
        if not GIT_AVAILABLE:
            raise ImportError(
                "GitPython is required for sync functionality. "
                "Install it with: pip install GitPython"
            )

        self.workspaces_root = workspaces_root or get_settings().workspaces_root
        self.workspaces_root.mkdir(parents=True, exist_ok=True)
        self._repo: Optional[Repo] = None

    @property
    def repo(self) -> Optional[Repo]:
        """Get the Git repository for the workspaces directory."""
        if self._repo is None:
            try:
                self._repo = Repo(self.workspaces_root)
            except InvalidGitRepositoryError:
                self._repo = None
        return self._repo

    def is_initialized(self) -> bool:
        """Check if sync is initialized (Git repo exists)."""
        return self.repo is not None

    def _get_sync_config_path(self) -> Path:
        """Get path to sync config file."""
        return self.workspaces_root / SYNC_CONFIG_FILE

    def _get_sync_log_path(self) -> Path:
        """Get path to sync log file."""
        return self.workspaces_root / SYNC_LOG_FILE

    def get_sync_config(self) -> SyncConfig:
        """Load sync configuration."""
        config_path = self._get_sync_config_path()
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)
                return SyncConfig(**data) if data else SyncConfig()
        return SyncConfig()

    def save_sync_config(self, config: SyncConfig) -> None:
        """Save sync configuration."""
        config_path = self._get_sync_config_path()
        with open(config_path, "w") as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)

    def _log_operation(
        self,
        operation: str,
        message: str,
        workspaces_affected: int = 0,
        scenarios_affected: int = 0,
        commit_sha: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """Log a sync operation."""
        log_path = self._get_sync_log_path()
        logs: List[dict] = []

        if log_path.exists():
            try:
                with open(log_path) as f:
                    logs = json.load(f)
            except (json.JSONDecodeError, IOError):
                logs = []

        entry = SyncLogEntry(
            timestamp=datetime.utcnow(),
            operation=operation,
            workspaces_affected=workspaces_affected,
            scenarios_affected=scenarios_affected,
            message=message,
            commit_sha=commit_sha,
            success=success,
        )

        logs.append(entry.model_dump(mode="json"))

        # Keep last 100 entries
        logs = logs[-100:]

        with open(log_path, "w") as f:
            json.dump(logs, f, indent=2, default=str)

    def get_sync_log(self, limit: int = 20) -> List[SyncLogEntry]:
        """Get recent sync log entries."""
        log_path = self._get_sync_log_path()
        if not log_path.exists():
            return []

        try:
            with open(log_path) as f:
                logs = json.load(f)
            return [SyncLogEntry(**entry) for entry in logs[-limit:]][::-1]
        except (json.JSONDecodeError, IOError):
            return []

    def init(
        self,
        remote_url: str,
        branch: str = "main",
        auto_sync: bool = False,
    ) -> SyncStatus:
        """Initialize sync for the workspaces directory.

        Args:
            remote_url: Git remote URL (e.g., git@github.com:user/repo.git)
            branch: Branch to use (default: main)
            auto_sync: Enable auto-sync on changes

        Returns:
            SyncStatus after initialization
        """
        try:
            # Initialize or get existing repo
            if not self.is_initialized():
                self._repo = Repo.init(self.workspaces_root)
                logger.info(f"Initialized Git repository at {self.workspaces_root}")

            repo = self.repo

            # Create .gitignore if it doesn't exist
            gitignore_path = self.workspaces_root / ".gitignore"
            if not gitignore_path.exists():
                with open(gitignore_path, "w") as f:
                    f.write(GITIGNORE_TEMPLATE)
                repo.index.add([".gitignore"])

            # Add remote if not exists
            try:
                origin = repo.remote("origin")
                # Update URL if different
                if list(origin.urls)[0] != remote_url:
                    repo.delete_remote("origin")
                    origin = repo.create_remote("origin", remote_url)
            except ValueError:
                origin = repo.create_remote("origin", remote_url)

            # Save sync config
            config = SyncConfig(
                enabled=True,
                remote=remote_url,
                branch=branch,
                auto_sync=auto_sync,
            )
            self.save_sync_config(config)

            # Try to fetch from remote
            try:
                origin.fetch()

                # Check if remote branch exists
                remote_branch = f"origin/{branch}"
                if remote_branch in [ref.name for ref in repo.refs]:
                    # Remote has content - set up tracking
                    if branch not in [h.name for h in repo.heads]:
                        repo.create_head(branch, remote_branch)
                    repo.heads[branch].set_tracking_branch(repo.refs[remote_branch])
                    repo.heads[branch].checkout()
                else:
                    # Remote is empty - create initial commit
                    self._create_initial_commit(repo, branch)

            except GitCommandError as e:
                if "Could not read from remote" in str(e):
                    raise SyncAuthError(
                        "Failed to authenticate with remote. "
                        "Ensure SSH keys are configured or use HTTPS with credentials."
                    )
                # Remote might not exist yet - create initial commit
                self._create_initial_commit(repo, branch)

            # Count workspaces and scenarios for logging
            workspaces, scenarios = self._count_content()

            self._log_operation(
                "init",
                f"Sync initialized with {remote_url}",
                workspaces_affected=workspaces,
                scenarios_affected=scenarios,
            )

            return self.get_status()

        except Exception as e:
            logger.error(f"Failed to initialize sync: {e}")
            self._log_operation(
                "init",
                f"Failed to initialize sync: {e}",
                success=False,
            )
            raise SyncError(f"Failed to initialize sync: {e}") from e

    def _create_initial_commit(self, repo: Repo, branch: str) -> None:
        """Create initial commit if repo is empty."""
        if branch not in [h.name for h in repo.heads]:
            repo.head.reference = repo.create_head(branch)

        # Stage all syncable files
        self._stage_syncable_files(repo)

        # Only commit if there are staged changes
        if repo.index.diff("HEAD", staged=True) if repo.head.is_valid() else repo.index.entries:
            repo.index.commit("Initial PlanAlign workspace sync")

    def _stage_syncable_files(self, repo: Repo) -> int:
        """Stage all syncable files (JSON, YAML).

        Returns:
            Number of files staged
        """
        count = 0
        for pattern in ["**/*.json", "**/*.yaml", "**/*.yml"]:
            for filepath in self.workspaces_root.glob(pattern):
                if filepath.is_file() and not str(filepath).startswith("."):
                    rel_path = filepath.relative_to(self.workspaces_root)
                    # Skip excluded paths
                    if any(
                        part.startswith(".")
                        for part in rel_path.parts
                        if part != "." and not part.startswith(".planalign")
                    ):
                        continue
                    try:
                        repo.index.add([str(rel_path)])
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to stage {rel_path}: {e}")

        # Also add sync config and gitignore
        for special_file in [".gitignore", SYNC_CONFIG_FILE]:
            special_path = self.workspaces_root / special_file
            if special_path.exists():
                try:
                    repo.index.add([special_file])
                except Exception:
                    pass

        return count

    def _count_content(self) -> Tuple[int, int]:
        """Count workspaces and scenarios.

        Returns:
            Tuple of (workspace_count, scenario_count)
        """
        workspaces = 0
        scenarios = 0

        for workspace_dir in self.workspaces_root.iterdir():
            if workspace_dir.is_dir() and not workspace_dir.name.startswith("."):
                workspace_json = workspace_dir / "workspace.json"
                if workspace_json.exists():
                    workspaces += 1
                    scenarios_dir = workspace_dir / "scenarios"
                    if scenarios_dir.exists():
                        for scenario_dir in scenarios_dir.iterdir():
                            if scenario_dir.is_dir():
                                scenarios += 1

        return workspaces, scenarios

    def get_status(self) -> SyncStatus:
        """Get current sync status."""
        if not self.is_initialized():
            return SyncStatus(
                is_initialized=False,
                remote_url=None,
                branch="main",
            )

        repo = self.repo
        config = self.get_sync_config()

        try:
            # Count local changes (untracked + modified)
            local_changes = len(repo.untracked_files) + len(repo.index.diff(None))

            # Get ahead/behind counts
            ahead = 0
            behind = 0
            if repo.head.is_valid() and config.remote:
                try:
                    tracking = repo.head.reference.tracking_branch()
                    if tracking:
                        commits_ahead = list(
                            repo.iter_commits(f"{tracking.name}..HEAD")
                        )
                        commits_behind = list(
                            repo.iter_commits(f"HEAD..{tracking.name}")
                        )
                        ahead = len(commits_ahead)
                        behind = len(commits_behind)
                except Exception:
                    pass

            # Get last sync time from log
            logs = self.get_sync_log(limit=1)
            last_sync = logs[0].timestamp if logs and logs[0].success else None

            return SyncStatus(
                is_initialized=True,
                remote_url=config.remote,
                branch=config.branch,
                local_changes=local_changes,
                ahead=ahead,
                behind=behind,
                last_sync=last_sync,
            )

        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return SyncStatus(
                is_initialized=True,
                remote_url=config.remote if config else None,
                branch=config.branch if config else "main",
                error=str(e),
            )

    def push(self, message: Optional[str] = None) -> SyncPushResult:
        """Push local changes to remote.

        Args:
            message: Optional commit message. Auto-generated if not provided.

        Returns:
            SyncPushResult with operation details
        """
        if not self.is_initialized():
            return SyncPushResult(
                success=False,
                message="Sync not initialized. Run 'planalign sync init' first.",
            )

        try:
            repo = self.repo
            config = self.get_sync_config()

            # Stage all syncable files
            files_staged = self._stage_syncable_files(repo)

            # Check if there are changes to commit
            if not repo.is_dirty(untracked_files=True):
                return SyncPushResult(
                    success=True,
                    files_pushed=0,
                    message="Nothing to push. Workspaces are up to date.",
                )

            # Create commit message
            workspaces, scenarios = self._count_content()
            if message is None:
                message = f"Sync {workspaces} workspace(s), {scenarios} scenario(s)"

            # Commit changes
            commit = repo.index.commit(message)
            commit_sha = commit.hexsha[:8]

            # Push to remote
            try:
                origin = repo.remote("origin")
                push_info = origin.push(config.branch)

                # Check push result
                for info in push_info:
                    if info.flags & info.ERROR:
                        raise SyncError(f"Push failed: {info.summary}")

            except GitCommandError as e:
                if "Could not read from remote" in str(e):
                    raise SyncAuthError(
                        "Failed to authenticate with remote. "
                        "Check your SSH keys or credentials."
                    )
                raise

            self._log_operation(
                "push",
                f"Pushed {files_staged} file(s) to {config.remote}",
                workspaces_affected=workspaces,
                scenarios_affected=scenarios,
                commit_sha=commit_sha,
            )

            return SyncPushResult(
                success=True,
                commit_sha=commit_sha,
                files_pushed=files_staged,
                message=f"Pushed {files_staged} file(s). Commit: {commit_sha}",
            )

        except SyncError:
            raise
        except Exception as e:
            logger.error(f"Push failed: {e}")
            self._log_operation(
                "push",
                f"Push failed: {e}",
                success=False,
            )
            return SyncPushResult(
                success=False,
                message=f"Push failed: {e}",
            )

    def pull(self) -> SyncPullResult:
        """Pull remote changes.

        Returns:
            SyncPullResult with operation details
        """
        if not self.is_initialized():
            return SyncPullResult(
                success=False,
                message="Sync not initialized. Run 'planalign sync init' first.",
            )

        try:
            repo = self.repo
            config = self.get_sync_config()

            # Stash local changes if any
            stashed = False
            if repo.is_dirty():
                repo.git.stash("push", "-m", "planalign-sync-stash")
                stashed = True

            try:
                # Fetch and merge
                origin = repo.remote("origin")
                fetch_info = origin.fetch()

                # Get current HEAD before merge
                old_head = repo.head.commit.hexsha if repo.head.is_valid() else None

                # Pull changes
                origin.pull(config.branch)

                # Count changes
                files_updated = 0
                files_added = 0
                files_removed = 0

                if old_head and repo.head.is_valid():
                    diff = repo.head.commit.diff(old_head)
                    for d in diff:
                        if d.new_file:
                            files_added += 1
                        elif d.deleted_file:
                            files_removed += 1
                        else:
                            files_updated += 1

            finally:
                # Restore stashed changes
                if stashed:
                    try:
                        repo.git.stash("pop")
                    except GitCommandError as e:
                        # Conflict during stash pop
                        conflicts = self._get_conflict_files(repo)
                        if conflicts:
                            self._log_operation(
                                "conflict",
                                f"Conflicts in {len(conflicts)} file(s)",
                                success=False,
                            )
                            return SyncPullResult(
                                success=False,
                                files_updated=files_updated,
                                files_added=files_added,
                                files_removed=files_removed,
                                conflicts=conflicts,
                                message=f"Conflicts detected in {len(conflicts)} file(s)",
                            )

            workspaces, scenarios = self._count_content()
            self._log_operation(
                "pull",
                f"Pulled {files_updated + files_added} file(s)",
                workspaces_affected=workspaces,
                scenarios_affected=scenarios,
            )

            total_changes = files_updated + files_added + files_removed
            if total_changes == 0:
                return SyncPullResult(
                    success=True,
                    message="Already up to date.",
                )

            return SyncPullResult(
                success=True,
                files_updated=files_updated,
                files_added=files_added,
                files_removed=files_removed,
                message=f"Updated {files_updated}, added {files_added}, removed {files_removed} file(s)",
            )

        except GitCommandError as e:
            if "Could not read from remote" in str(e):
                raise SyncAuthError(
                    "Failed to authenticate with remote. "
                    "Check your SSH keys or credentials."
                )
            raise SyncError(f"Pull failed: {e}") from e
        except Exception as e:
            logger.error(f"Pull failed: {e}")
            self._log_operation(
                "pull",
                f"Pull failed: {e}",
                success=False,
            )
            return SyncPullResult(
                success=False,
                message=f"Pull failed: {e}",
            )

    def _get_conflict_files(self, repo: Repo) -> List[str]:
        """Get list of files with merge conflicts."""
        conflicts = []
        try:
            unmerged = repo.index.unmerged_blobs()
            conflicts = list(unmerged.keys())
        except Exception:
            pass
        return conflicts

    def disconnect(self) -> bool:
        """Disconnect sync (remove remote, keep local files).

        Returns:
            True if disconnected successfully
        """
        if not self.is_initialized():
            return False

        try:
            repo = self.repo

            # Remove remote
            try:
                repo.delete_remote("origin")
            except Exception:
                pass

            # Update config
            config = self.get_sync_config()
            config.enabled = False
            config.remote = None
            self.save_sync_config(config)

            self._log_operation(
                "disconnect",
                "Sync disconnected. Local workspaces preserved.",
            )

            return True

        except Exception as e:
            logger.error(f"Failed to disconnect sync: {e}")
            return False

    def get_workspace_sync_info(self) -> List[WorkspaceSyncInfo]:
        """Get sync information for all workspaces."""
        infos = []

        for workspace_dir in sorted(self.workspaces_root.iterdir()):
            if not workspace_dir.is_dir() or workspace_dir.name.startswith("."):
                continue

            workspace_json = workspace_dir / "workspace.json"
            if not workspace_json.exists():
                continue

            try:
                with open(workspace_json) as f:
                    data = json.load(f)

                # Count scenarios
                scenarios_dir = workspace_dir / "scenarios"
                scenario_count = 0
                if scenarios_dir.exists():
                    scenario_count = sum(
                        1 for d in scenarios_dir.iterdir()
                        if d.is_dir() and (d / "scenario.json").exists()
                    )

                # Check for local changes
                has_changes = False
                if self.repo:
                    rel_path = workspace_dir.relative_to(self.workspaces_root)
                    # Check if any files in this workspace are modified
                    for item in self.repo.untracked_files:
                        if item.startswith(str(rel_path)):
                            has_changes = True
                            break
                    if not has_changes:
                        for diff in self.repo.index.diff(None):
                            if diff.a_path and diff.a_path.startswith(str(rel_path)):
                                has_changes = True
                                break

                infos.append(WorkspaceSyncInfo(
                    workspace_id=data["id"],
                    workspace_name=data["name"],
                    scenario_count=scenario_count,
                    has_local_changes=has_changes,
                ))

            except Exception as e:
                logger.warning(f"Failed to get sync info for {workspace_dir}: {e}")

        return infos
