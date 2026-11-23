"""Sync service for workspace cloud synchronization using Git (E083).

This service provides Git-based synchronization for PlanAlign workspaces,
enabling cross-device access and version control of workspace configurations.
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

import yaml

if TYPE_CHECKING:
    from git import GitCommandError, InvalidGitRepositoryError, Remote, Repo

try:
    from git import GitCommandError, InvalidGitRepositoryError, Remote, Repo

    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    GitCommandError = Exception  # type: ignore[assignment,misc]
    InvalidGitRepositoryError = Exception  # type: ignore[assignment,misc]

from .remote_policy import RemotePolicyError, redact_remote_url, validate_remote_url
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

# Exclude runtime, build, and local sync state
dbt_project/
calibration_jobs/
runs/
target/
.planalign-sync.yaml
.planalign-sync-log.json
"""

# Sync config filename
SYNC_CONFIG_FILE = ".planalign-sync.yaml"
SYNC_LOG_FILE = ".planalign-sync-log.json"

# Explicit allowlist of workspace/scenario files eligible for sync staging.
_WORKSPACE_SYNC_FILES = ("workspace.json", "base_config.yaml")
_SCENARIO_SYNC_FILES = ("scenario.json", "overrides.yaml")

# Local-only sync state that must never be tracked in the sync repo.
_LOCAL_STATE_FILES = (SYNC_CONFIG_FILE, SYNC_LOG_FILE)

# Git transport protocols that are never permitted in sync repos.
_FORBIDDEN_GIT_PROTOCOLS = frozenset({"file", "ext", "local", "fd"})
_VALID_PROTOCOL_RE = re.compile(r"^[a-z][a-z0-9+.-]*$")


def _set_private_file_mode(path: Path) -> None:
    """Restrict ``path`` to mode 0600 on POSIX platforms."""
    if os.name != "posix":
        return
    try:
        if path.exists() and not path.is_symlink():
            os.chmod(path, 0o600)
    except OSError as exc:
        logger.warning("Failed to set 0600 permissions on %s: %s", path, exc)


def _write_private_text(path: Path, content: str) -> None:
    """Write text to ``path`` and enforce POSIX mode 0600."""
    if os.name == "posix":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        _set_private_file_mode(path)
    else:
        path.write_text(content, encoding="utf-8")


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


class SyncValidationError(SyncError):
    """Remote URL rejected by the remote policy (SSRF hardening)."""

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

    def _get_repo(self) -> Repo:
        """Get the Git repository, raising if not initialized.

        Callers must only invoke this after confirming ``is_initialized()``
        (or having just created the repo), so a ``None`` result here
        indicates a programming error rather than an expected state.
        """
        repo = self.repo
        assert repo is not None, "Repo accessed before sync was initialized"
        return repo

    def _get_sync_config_path(self) -> Path:
        """Get path to sync config file."""
        return self.workspaces_root / SYNC_CONFIG_FILE

    def _get_sync_log_path(self) -> Path:
        """Get path to sync log file."""
        return self.workspaces_root / SYNC_LOG_FILE

    def get_sync_config(self) -> SyncConfig:
        """Load sync configuration, rewriting it without credentials if needed."""
        config_path = self._get_sync_config_path()
        if not config_path.exists():
            return SyncConfig()
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            return SyncConfig()
        raw_remote = data.get("remote") if isinstance(data, dict) else None
        config = SyncConfig(**data)
        if isinstance(raw_remote, str) and raw_remote != config.remote:
            self.save_sync_config(config)
        return config

    def save_sync_config(self, config: SyncConfig) -> None:
        """Save sync configuration without credentials and with mode 0600."""
        config_path = self._get_sync_config_path()
        sanitized = config.model_copy(
            update={"remote": redact_remote_url(config.remote)}
        )
        rendered = yaml.dump(sanitized.model_dump(), default_flow_style=False)
        _write_private_text(config_path, rendered)

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
        logs: List[dict[str, Any]] = []

        if log_path.exists():
            try:
                with open(log_path, encoding="utf-8") as f:
                    logs = json.load(f)
            except (json.JSONDecodeError, IOError) as exc:
                logger.warning("Resetting unreadable sync log %s: %s", log_path, exc)
                logs = []

        entry = SyncLogEntry(
            timestamp=datetime.now(timezone.utc),
            operation=operation,  # type: ignore[arg-type]
            workspaces_affected=workspaces_affected,
            scenarios_affected=scenarios_affected,
            message=redact_remote_url(message),
            commit_sha=commit_sha,
            success=success,
        )

        logs.append(entry.model_dump(mode="json"))

        # Keep last 100 entries
        logs = logs[-100:]

        _write_private_text(log_path, json.dumps(logs, indent=2, default=str))

    def get_sync_log(self, limit: int = 20) -> List[SyncLogEntry]:
        """Get recent sync log entries."""
        log_path = self._get_sync_log_path()
        if not log_path.exists():
            return []

        try:
            with open(log_path, encoding="utf-8") as f:
                logs = json.load(f)
            return [SyncLogEntry(**entry) for entry in logs[-limit:]][::-1]
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to read sync log %s: %s", log_path, exc)
            return []

    def _protect_git_config(self, repo: Repo) -> None:
        """Restrict the sync repo's .git/config to mode 0600 on POSIX."""
        _set_private_file_mode(Path(repo.git_dir) / "config")

    def _allowed_git_protocols(self) -> List[str]:
        """Return Git transport protocols allowed by settings (never local/helper)."""
        protocols: List[str] = []
        for raw in get_settings().git_remote_allowed_schemes:
            scheme = raw.strip().lower()
            if (
                scheme
                and scheme not in _FORBIDDEN_GIT_PROTOCOLS
                and _VALID_PROTOCOL_RE.fullmatch(scheme)
                and scheme not in protocols
            ):
                protocols.append(scheme)
        return protocols

    def _hardened_git_config_items(self) -> List[Tuple[str, str]]:
        """Build Git config key/value pairs enforced on every sync repo operation."""
        items: List[Tuple[str, str]] = [
            ("core.symlinks", "false"),
            ("http.followRedirects", "false"),
            ("protocol.allow", "never"),
        ]
        for scheme in self._allowed_git_protocols():
            items.append((f"protocol.{scheme}.allow", "always"))
        return items

    def _hardened_git_env(self) -> Dict[str, str]:
        """Build process-level Git env overrides that cannot be undone by repo content."""
        items = self._hardened_git_config_items()
        env: Dict[str, str] = {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": str(len(items)),
        }
        for idx, (key, value) in enumerate(items):
            env[f"GIT_CONFIG_KEY_{idx}"] = key
            env[f"GIT_CONFIG_VALUE_{idx}"] = value
        return env

    def _harden_repo_config(self, repo: Repo) -> None:
        """Persist redirect, protocol, and symlink restrictions in local .git/config."""
        allowed_protocols = set(self._allowed_git_protocols())
        with repo.config_writer() as writer:
            writer.set_value("core", "symlinks", "false")
            writer.set_value("http", "followRedirects", "false")
            writer.set_value("protocol", "allow", "never")
            for section in list(writer.sections()):
                if section.startswith('protocol "') and section.endswith('"'):
                    scheme = section[len('protocol "') : -1].lower()
                    if scheme not in allowed_protocols:
                        writer.remove_section(section)
            for scheme in sorted(allowed_protocols):
                writer.set_value(f'protocol "{scheme}"', "allow", "always")
        self._protect_git_config(repo)

    def _get_origin_push_urls(self, repo: Repo) -> List[str]:
        """Return any explicit ``remote.origin.pushurl`` values in local config."""
        urls: List[str] = []
        with repo.config_reader() as reader:
            section = 'remote "origin"'
            if not (
                reader.has_section(section) and reader.has_option(section, "pushurl")
            ):
                return urls
            raw_values = reader.get_values(section, "pushurl")
            for val in raw_values:
                if isinstance(val, str) and val:
                    urls.append(val)
        return urls

    def _validate_origin_remote(self, repo: Repo) -> str:
        """Re-validate every configured origin URL against the remote policy."""
        try:
            origin = repo.remote("origin")
            urls = list(origin.urls)
        except ValueError as exc:
            raise SyncValidationError(
                "Remote URL rejected: Origin remote is not configured."
            ) from exc

        if not urls:
            raise SyncValidationError(
                "Remote URL rejected: Origin remote has no configured URL."
            )

        settings = get_settings()
        all_urls = [*urls, *self._get_origin_push_urls(repo)]
        normalized_primary = ""
        for idx, remote_url in enumerate(all_urls):
            try:
                normalized = validate_remote_url(remote_url, settings)
            except RemotePolicyError as exc:
                raise SyncValidationError(f"Remote URL rejected: {exc}") from exc
            if idx == 0:
                normalized_primary = normalized
        return normalized_primary

    def _ensure_gitignore(self, repo: Repo) -> None:
        """Create .gitignore, or add the local sync state entries it lacks."""
        gitignore_path = self.workspaces_root / ".gitignore"
        if gitignore_path.is_symlink():
            return
        if not gitignore_path.exists():
            gitignore_path.write_text(GITIGNORE_TEMPLATE, encoding="utf-8")
            repo.index.add([".gitignore"])
            return
        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
        missing = [name for name in _LOCAL_STATE_FILES if name not in lines]
        if missing:
            block = "\n# Local sync state\n" + "".join(f"{n}\n" for n in missing)
            with open(gitignore_path, "a", encoding="utf-8") as handle:
                handle.write(block)

    def _untrack_local_state(self, repo: Repo) -> None:
        """Remove local sync state files from the index (``git rm --cached``)."""
        tracked = {path for path, _stage in repo.index.entries}
        stale = [name for name in _LOCAL_STATE_FILES if name in tracked]
        if stale:
            repo.index.remove(stale)
            logger.info("Stopped tracking local sync state files: %s", stale)

    def _configure_origin_remote(self, repo: Repo, normalized_url: str) -> Remote:
        """Create or update the ``origin`` remote with the validated URL."""
        try:
            origin = repo.remote("origin")
            existing_urls = list(origin.urls)
            if not existing_urls or existing_urls[0] != normalized_url:
                repo.delete_remote("origin")  # type: ignore[arg-type]
                origin = repo.create_remote("origin", normalized_url)
        except ValueError:
            origin = repo.create_remote("origin", normalized_url)
        self._protect_git_config(repo)
        return origin

    def _sync_initial_branch(self, repo: Repo, origin: Remote, branch: str) -> None:
        """Fetch remote refs and either track the remote branch or make initial commit."""
        self._validate_origin_remote(repo)
        self._harden_repo_config(repo)
        try:
            with repo.git.custom_environment(**self._hardened_git_env()):
                origin.fetch()

            remote_branch = f"origin/{branch}"
            if remote_branch in [ref.name for ref in repo.refs]:
                if branch not in [h.name for h in repo.heads]:
                    repo.create_head(branch, remote_branch)
                repo.heads[branch].set_tracking_branch(repo.refs[remote_branch])
                self._protect_git_config(repo)
                with repo.git.custom_environment(**self._hardened_git_env()):
                    repo.heads[branch].checkout()
                self._remove_pulled_symlinks(
                    self._collect_changed_paths(repo, old_head=None)
                )
            else:
                self._create_initial_commit(repo, branch)
        except GitCommandError as e:
            if "Could not read from remote" in str(e):
                raise SyncAuthError(
                    "Failed to authenticate with remote. "
                    "Ensure SSH keys are configured or use HTTPS with credentials."
                ) from e
            logger.warning(
                "Initial fetch failed; creating a local initial commit: %s",
                redact_remote_url(str(e)),
            )
            self._create_initial_commit(repo, branch)

    def init(
        self,
        remote_url: str,
        branch: str = "main",
        auto_sync: bool = False,
    ) -> SyncStatus:
        """Initialize sync for the workspaces directory.

        Args:
            remote_url: Git remote URL (e.g., git@github.com:user/repo.git).
                Must pass the remote policy (scheme, host, and network
                destination checks); see planalign_api.services.remote_policy.
            branch: Branch to use (default: main)
            auto_sync: Enable auto-sync on changes

        Returns:
            SyncStatus after initialization
        """
        try:
            # Enforce the remote policy before any Git transport is created.
            try:
                normalized_url = validate_remote_url(remote_url, get_settings())
            except RemotePolicyError as e:
                raise SyncValidationError(f"Remote URL rejected: {e}") from e

            if not self.is_initialized():
                self._repo = Repo.init(self.workspaces_root)
                logger.info("Initialized Git repository at %s", self.workspaces_root)

            repo = self._get_repo()
            self._ensure_gitignore(repo)
            origin = self._configure_origin_remote(repo, normalized_url)
            self._harden_repo_config(repo)

            # Save sync config without credentials.
            redacted_url = redact_remote_url(normalized_url)
            config = SyncConfig(
                enabled=True,
                remote=redacted_url,
                branch=branch,
                auto_sync=auto_sync,
            )
            self.save_sync_config(config)

            self._sync_initial_branch(repo, origin, branch)
            self._protect_git_config(repo)

            workspaces, scenarios = self._count_content()
            self._log_operation(
                "init",
                f"Sync initialized with {redacted_url}",
                workspaces_affected=workspaces,
                scenarios_affected=scenarios,
            )
            return self.get_status()

        except (SyncValidationError, SyncAuthError):
            raise
        except Exception as e:
            detail = redact_remote_url(str(e))
            logger.error("Failed to initialize sync: %s", detail)
            self._log_operation(
                "init",
                f"Failed to initialize sync: {detail}",
                success=False,
            )
            raise SyncError(f"Failed to initialize sync: {detail}") from e

    def _create_initial_commit(self, repo: Repo, branch: str) -> None:
        """Create initial commit if repo is empty."""
        if not repo.head.is_valid():
            repo.git.symbolic_ref("HEAD", f"refs/heads/{branch}")
        elif branch not in [h.name for h in repo.heads]:
            repo.head.reference = repo.create_head(branch)

        self._untrack_local_state(repo)
        self._stage_syncable_files(repo)

        if self._has_staged_changes(repo):
            repo.index.commit("Initial PlanAlign workspace sync")

    def _is_safe_regular_file(self, path: Path, root_resolved: Path) -> bool:
        """Return True if ``path`` is a regular file with no symlinks under root."""
        if path.is_symlink():
            return False
        try:
            rel = path.relative_to(self.workspaces_root)
        except ValueError:
            return False
        current = self.workspaces_root
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                return False
        try:
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode):
                return False
            resolved = path.resolve(strict=True)
        except OSError:
            return False
        return resolved.is_relative_to(root_resolved) and resolved != root_resolved

    def _iter_workspace_sync_files(
        self, workspace_dir: Path, root_resolved: Path
    ) -> List[Path]:
        """Collect allowlisted syncable files for one workspace directory."""
        files: List[Path] = []
        for filename in _WORKSPACE_SYNC_FILES:
            candidate = workspace_dir / filename
            if self._is_safe_regular_file(candidate, root_resolved):
                files.append(candidate)

        scenarios_dir = workspace_dir / "scenarios"
        if scenarios_dir.is_symlink() or not scenarios_dir.is_dir():
            return files

        for scenario_dir in sorted(scenarios_dir.iterdir()):
            if (
                scenario_dir.name.startswith(".")
                or scenario_dir.is_symlink()
                or not scenario_dir.is_dir()
            ):
                continue
            for filename in _SCENARIO_SYNC_FILES:
                candidate = scenario_dir / filename
                if self._is_safe_regular_file(candidate, root_resolved):
                    files.append(candidate)
        return files

    def _stage_syncable_files(self, repo: Repo) -> int:
        """Stage allowlisted workspace configuration files (never symlinks).

        Returns:
            Number of workspace/scenario config files staged.
        """
        count = 0
        root_resolved = self.workspaces_root.resolve()

        for workspace_dir in sorted(self.workspaces_root.iterdir()):
            if (
                workspace_dir.name.startswith(".")
                or workspace_dir.is_symlink()
                or not workspace_dir.is_dir()
            ):
                continue
            for filepath in self._iter_workspace_sync_files(
                workspace_dir, root_resolved
            ):
                rel_path = filepath.relative_to(self.workspaces_root)
                try:
                    repo.index.add([str(rel_path)])
                    count += 1
                except Exception as exc:
                    logger.warning("Failed to stage %s: %s", rel_path, exc)

        gitignore_path = self.workspaces_root / ".gitignore"
        if self._is_safe_regular_file(gitignore_path, root_resolved):
            try:
                repo.index.add([".gitignore"])
            except Exception as exc:
                logger.warning("Failed to stage .gitignore: %s", exc)

        return count

    def _has_staged_changes(self, repo: Repo) -> bool:
        """Return whether the index has changes relative to HEAD."""
        if repo.head.is_valid():
            return bool(repo.index.diff("HEAD"))
        return bool(repo.index.entries)

    def _has_unpushed_commits(self, repo: Repo, branch: str) -> bool:
        """Return whether HEAD has commits not yet present on ``origin/<branch>``."""
        if not repo.head.is_valid():
            return False
        remote_ref = f"origin/{branch}"
        if remote_ref not in [ref.name for ref in repo.refs]:
            return True
        return any(True for _ in repo.iter_commits(f"{remote_ref}..HEAD", max_count=1))

    def _collect_changed_paths(self, repo: Repo, old_head: Optional[str]) -> List[str]:
        """Collect relative file paths touched by a pull or initial checkout."""
        if not repo.head.is_valid():
            return []
        paths: List[str] = []
        seen: set[str] = set()
        if old_head:
            for diff_item in repo.commit(old_head).diff(repo.head.commit):
                for candidate in (diff_item.a_path, diff_item.b_path):
                    if candidate and candidate not in seen:
                        seen.add(candidate)
                        paths.append(candidate)
            return paths

        for item in repo.head.commit.tree.traverse():
            item_path = getattr(item, "path", None)
            if isinstance(item_path, str) and item_path not in seen:
                seen.add(item_path)
                paths.append(item_path)
        return paths

    def _remove_pulled_symlinks(self, rel_paths: Iterable[str]) -> int:
        """Walk pulled paths and remove (and log) any symlink found on disk."""
        removed = 0
        checked: set[Path] = set()
        for rel_str in rel_paths:
            rel = Path(rel_str)
            if rel.is_absolute() or ".." in rel.parts:
                continue
            current = self.workspaces_root
            for part in rel.parts:
                current = current / part
                if current in checked:
                    continue
                checked.add(current)
                if not current.is_symlink():
                    continue
                try:
                    current.unlink()
                    removed += 1
                    logger.warning(
                        "Removed symlink checked out during sync pull: %s",
                        current.relative_to(self.workspaces_root),
                    )
                except OSError as exc:
                    logger.warning(
                        "Failed to remove symlink %s: %s",
                        current.relative_to(self.workspaces_root),
                        exc,
                    )
                break
        return removed

    def _count_pull_changes(
        self, repo: Repo, old_head: Optional[str]
    ) -> Tuple[int, int, int]:
        """Count (updated, added, removed) files across a pull."""
        files_updated = 0
        files_added = 0
        files_removed = 0
        if not repo.head.is_valid():
            return files_updated, files_added, files_removed

        if old_head:
            for diff_item in repo.commit(old_head).diff(repo.head.commit):
                if diff_item.new_file:
                    files_added += 1
                elif diff_item.deleted_file:
                    files_removed += 1
                else:
                    files_updated += 1
            return files_updated, files_added, files_removed

        files_added = sum(
            1
            for item in repo.head.commit.tree.traverse()
            if getattr(item, "type", None) == "blob"
        )
        return files_updated, files_added, files_removed

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

        repo = self._get_repo()
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
                except Exception as exc:
                    logger.debug("Could not compute ahead/behind counts: %s", exc)

            # Get last sync time from log
            logs = self.get_sync_log(limit=1)
            last_sync = logs[0].timestamp if logs and logs[0].success else None

            return SyncStatus(
                is_initialized=True,
                remote_url=redact_remote_url(config.remote),
                branch=config.branch,
                local_changes=local_changes,
                ahead=ahead,
                behind=behind,
                last_sync=last_sync,
            )

        except Exception as e:
            detail = redact_remote_url(str(e))
            logger.error("Failed to get sync status: %s", detail)
            return SyncStatus(
                is_initialized=True,
                remote_url=redact_remote_url(config.remote) if config else None,
                branch=config.branch if config else "main",
                error=detail,
            )

    def _push_to_origin(self, repo: Repo, branch: str) -> None:
        """Execute ``git push`` under hardened transport and protocol controls."""
        try:
            origin = repo.remote("origin")
            with repo.git.custom_environment(**self._hardened_git_env()):
                push_info = origin.push(branch)
            for info in push_info:
                if info.flags & info.ERROR:
                    raise SyncError(f"Push failed: {redact_remote_url(info.summary)}")
        except GitCommandError as e:
            if "Could not read from remote" in str(e):
                raise SyncAuthError(
                    "Failed to authenticate with remote. "
                    "Check your SSH keys or credentials."
                ) from e
            raise

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
            repo = self._get_repo()
            self._validate_origin_remote(repo)
            self._harden_repo_config(repo)
            self._ensure_gitignore(repo)
            config = self.get_sync_config()

            self._untrack_local_state(repo)
            files_staged = self._stage_syncable_files(repo)
            has_staged = self._has_staged_changes(repo)
            has_unpushed = self._has_unpushed_commits(repo, config.branch)

            if not has_staged and not has_unpushed:
                return SyncPushResult(
                    success=True,
                    files_pushed=0,
                    message="Nothing to push. Workspaces are up to date.",
                )

            workspaces, scenarios = self._count_content()
            if has_staged:
                commit_msg = (
                    message
                    if message is not None
                    else f"Sync {workspaces} workspace(s), {scenarios} scenario(s)"
                )
                commit = repo.index.commit(commit_msg)
                commit_sha = commit.hexsha[:8]
            else:
                commit_sha = repo.head.commit.hexsha[:8]

            self._push_to_origin(repo, config.branch)

            self._log_operation(
                "push",
                f"Pushed {files_staged} file(s) to {redact_remote_url(config.remote)}",
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
            detail = redact_remote_url(str(e))
            logger.error("Push failed: %s", detail)
            self._log_operation(
                "push",
                f"Push failed: {detail}",
                success=False,
            )
            return SyncPushResult(
                success=False,
                message=f"Push failed: {detail}",
            )

    def _pull_with_stash(self, repo: Repo, config: SyncConfig) -> Tuple[int, int, int]:
        """Stash local edits, pull, restore them, and keep the local sync config."""
        stashed = False
        if repo.is_dirty():
            repo.git.stash("push", "-m", "planalign-sync-stash")
            stashed = True
        try:
            counts = self._fetch_and_pull(repo, config.branch)
        finally:
            if stashed:
                self._pop_stash(repo)
        # A pull can delete a sync config that an older version tracked.
        if not self._get_sync_config_path().exists():
            self.save_sync_config(config)
        return counts

    def _fetch_and_pull(self, repo: Repo, branch: str) -> Tuple[int, int, int]:
        """Fetch/pull under hardened Git config and scrub symlinks.

        Callers validate the origin URL and re-assert the repo hardening first.
        """
        origin = repo.remote("origin")
        old_head = repo.head.commit.hexsha if repo.head.is_valid() else None

        with repo.git.custom_environment(**self._hardened_git_env()):
            origin.fetch()
            origin.pull(branch)

        changed_paths = self._collect_changed_paths(repo, old_head)
        self._remove_pulled_symlinks(changed_paths)
        return self._count_pull_changes(repo, old_head)

    def _pop_stash(self, repo: Repo) -> None:
        """Restore a stashed working tree under hardened Git config."""
        try:
            with repo.git.custom_environment(**self._hardened_git_env()):
                repo.git.stash("pop")
        except GitCommandError as exc:
            conflicts = self._get_conflict_files(repo)
            if conflicts:
                self._log_operation(
                    "conflict",
                    f"Conflicts in {len(conflicts)} file(s)",
                    success=False,
                )
                raise SyncConflictError(
                    f"Conflicts detected in {len(conflicts)} file(s)",
                    conflicting_files=conflicts,
                ) from exc
            logger.warning("Stash pop failed without conflict list: %s", exc)

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
            repo = self._get_repo()
            self._validate_origin_remote(repo)
            self._harden_repo_config(repo)
            config = self.get_sync_config()
            files_updated, files_added, files_removed = self._pull_with_stash(
                repo, config
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
                message=(
                    f"Updated {files_updated}, added {files_added}, "
                    f"removed {files_removed} file(s)"
                ),
            )

        except SyncConflictError as e:
            return SyncPullResult(
                success=False,
                conflicts=e.conflicting_files,
                message=str(e),
            )
        except SyncError:
            raise
        except GitCommandError as e:
            if "Could not read from remote" in str(e):
                raise SyncAuthError(
                    "Failed to authenticate with remote. "
                    "Check your SSH keys or credentials."
                ) from e
            raise SyncError(f"Pull failed: {redact_remote_url(str(e))}") from e
        except Exception as e:
            detail = redact_remote_url(str(e))
            logger.error("Pull failed: %s", detail)
            self._log_operation(
                "pull",
                f"Pull failed: {detail}",
                success=False,
            )
            return SyncPullResult(
                success=False,
                message=f"Pull failed: {detail}",
            )

    def _get_conflict_files(self, repo: Repo) -> List[str]:
        """Get list of files with merge conflicts."""
        conflicts: List[str] = []
        try:
            unmerged = repo.index.unmerged_blobs()
            conflicts = [str(path) for path in unmerged.keys()]
        except Exception as exc:
            logger.warning("Failed to inspect unmerged blobs: %s", exc)
        return conflicts

    def disconnect(self) -> bool:
        """Disconnect sync (remove remote, keep local files).

        Returns:
            True if disconnected successfully
        """
        if not self.is_initialized():
            return False

        try:
            repo = self._get_repo()

            try:
                repo.delete_remote("origin")  # type: ignore[arg-type]
            except Exception as exc:
                logger.warning(
                    "Could not remove origin remote during disconnect: %s", exc
                )
            self._protect_git_config(repo)

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
            logger.error("Failed to disconnect sync: %s", e)
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
                        1
                        for d in scenarios_dir.iterdir()
                        if d.is_dir() and (d / "scenario.json").exists()
                    )

                # Check for local changes
                has_changes = False
                repo = self.repo
                if repo:
                    rel_path = workspace_dir.relative_to(self.workspaces_root)
                    # Check if any files in this workspace are modified
                    for item in repo.untracked_files:
                        if item.startswith(str(rel_path)):
                            has_changes = True
                            break
                    if not has_changes:
                        for diff in repo.index.diff(None):
                            if diff.a_path and diff.a_path.startswith(str(rel_path)):
                                has_changes = True
                                break

                infos.append(
                    WorkspaceSyncInfo(
                        workspace_id=data["id"],
                        workspace_name=data["name"],
                        scenario_count=scenario_count,
                        has_local_changes=has_changes,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to get sync info for {workspace_dir}: {e}")

        return infos
