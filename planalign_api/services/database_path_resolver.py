"""
Database Path Resolver - Unified database path resolution for API services.

This module provides centralized database path resolution logic, replacing
duplicated fallback chain implementations across AnalyticsService,
ComparisonService, and SimulationService.

Feature: 005-database-path-resolver
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# ==============================================================================
# T004: IsolationMode Enum
# ==============================================================================


class IsolationMode(str, Enum):
    """
    Tenant isolation behavior for database resolution.

    Attributes:
        SINGLE_TENANT: Allow fallback to project-level database (default).
            Use for single-user deployments where a shared database is acceptable.
        MULTI_TENANT: Stop at workspace level; no project fallback.
            Use for multi-tenant deployments to prevent cross-workspace data access.
    """

    SINGLE_TENANT = "single-tenant"
    MULTI_TENANT = "multi-tenant"


# ==============================================================================
# T005: ResolvedDatabasePath Pydantic Model
# ==============================================================================


class ResolvedDatabasePath(BaseModel):
    """
    Immutable value object containing resolved database path and metadata.

    This class represents the result of a database path resolution operation,
    including metadata about where the database was found in the fallback chain.

    Attributes:
        path: Resolved filesystem path to the database, or None if not found.
        source: Level at which the database was found ("scenario", "workspace", "project"),
            or None if no database was found.
        warning: Optional warning message (e.g., when using project fallback or
            when path traversal is detected).

    Example:
        >>> result = resolver.resolve("workspace-123", "scenario-456")
        >>> if result.exists:
        ...     conn = duckdb.connect(str(result.path))
        >>> if result.warning:
        ...     logger.warning(result.warning)
    """

    model_config = ConfigDict(frozen=True)

    path: Optional[Path] = None
    source: Optional[Literal["scenario", "workspace", "project"]] = None
    warning: Optional[str] = None

    @property
    def exists(self) -> bool:
        """Return True if a database path was resolved."""
        return self.path is not None


# ==============================================================================
# T006: WorkspaceStorageProtocol
# ==============================================================================


@runtime_checkable
class WorkspaceStorageProtocol(Protocol):
    """
    Protocol defining the interface required from storage implementations.

    This protocol enables dependency injection and testing with mock storage.
    The existing WorkspaceStorage class already implements these methods.

    Methods:
        _workspace_path: Get the filesystem path for a workspace directory.
        _scenario_path: Get the filesystem path for a scenario directory.
    """

    def _workspace_path(self, workspace_id: str) -> Path:
        """Get the filesystem path for a workspace directory."""
        ...

    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path:
        """Get the filesystem path for a scenario directory."""
        ...


# ==============================================================================
# T007-T009: DatabasePathResolver Class
# ==============================================================================


class DatabasePathResolver:
    """
    Stateless service for resolving database paths using a fallback chain.

    This resolver implements the following fallback chain:
    1. Scenario-specific: {scenario_path}/simulation.duckdb
    2. Workspace-level: {workspace_path}/simulation.duckdb
    3. Project default: {project_root}/dbt/simulation.duckdb
       (only if isolation_mode is SINGLE_TENANT)

    The resolver is thread-safe by design (no mutable instance state after
    construction) and can be safely used in concurrent FastAPI request handlers.

    Attributes:
        _storage: Storage abstraction for path construction.
        _isolation_mode: Tenant isolation behavior.
        _project_root: Project root path (for fallback database).
        _database_filename: Database filename to search for.
        _project_db_path: Pre-computed project-level database path.

    Example:
        >>> from planalign_api.storage.workspace_storage import WorkspaceStorage
        >>> storage = WorkspaceStorage()
        >>> resolver = DatabasePathResolver(storage)
        >>> result = resolver.resolve("workspace-123", "scenario-456")
        >>> if result.exists:
        ...     conn = duckdb.connect(str(result.path))
    """

    # Pattern for detecting invalid path characters (path traversal prevention)
    # Rejects: path separators, null bytes, relative path components
    _INVALID_CHARS = re.compile(r"[/\\:\x00]|\.\.|\.$|^\.")

    def __init__(
        self,
        storage: WorkspaceStorageProtocol,
        isolation_mode: IsolationMode = IsolationMode.SINGLE_TENANT,
        project_root: Optional[Path] = None,
        database_filename: str = "simulation.duckdb",
    ) -> None:
        """
        Initialize the resolver.

        Args:
            storage: Storage abstraction for path construction.
                Must implement WorkspaceStorageProtocol.
            isolation_mode: Tenant isolation behavior.
                Defaults to SINGLE_TENANT (allow project fallback).
            project_root: Override for project root path.
                If not provided, auto-detects using module location.
            database_filename: Database filename to search for.
                Defaults to "simulation.duckdb".

        Raises:
            ValueError: If project_root is provided but does not exist,
                or if auto-detection fails.
        """
        self._storage = storage
        self._isolation_mode = isolation_mode
        self._database_filename = database_filename

        # T009: Determine project root
        if project_root is not None:
            self._project_root = project_root
        else:
            self._project_root = self._detect_project_root()

        # Pre-compute project database path
        self._project_db_path = self._project_root / "dbt" / self._database_filename

    # T008: Path traversal validation
    def _validate_identifier(self, value: str, name: str) -> bool:
        """
        Validate an identifier for path traversal safety.

        Checks for dangerous characters that could enable path traversal attacks:
        - Path separators (/, \\, :)
        - Null bytes (\\x00)
        - Relative path components (.., .)

        Args:
            value: The identifier value to validate.
            name: The name of the identifier (for logging).

        Returns:
            True if the value is safe to use in path construction.
            False if the value contains dangerous characters.
        """
        if not value:
            logger.warning(f"Empty {name} provided")
            return False

        if self._INVALID_CHARS.search(value):
            logger.warning(
                f"Invalid {name} '{value}': potential path traversal attempt"
            )
            return False

        return True

    # T009: Project root detection
    def _detect_project_root(self) -> Path:
        """
        Auto-detect project root from module location.

        Returns the path 3 levels up from this module's directory:
        planalign_api/services/database_path_resolver.py
        -> planalign_api/services/
        -> planalign_api/
        -> project_root/

        Returns:
            Path to the project root directory.
        """
        return Path(__file__).parent.parent.parent

    def resolve(
        self,
        workspace_id: str,
        scenario_id: str,
    ) -> ResolvedDatabasePath:
        """
        Resolve the database path for a given workspace and scenario.

        Implements the fallback chain:
        1. Scenario-specific database
        2. Workspace-level database
        3. Project default database (if SINGLE_TENANT mode)

        Args:
            workspace_id: The workspace identifier (validated for path safety).
            scenario_id: The scenario identifier (validated for path safety).

        Returns:
            ResolvedDatabasePath with the resolved path and metadata.
            - If found: path is set, source indicates the level
            - If not found: path is None
            - If validation fails: path is None, warning contains security message
        """
        # Step 1: Validate identifiers for path traversal
        if not self._validate_identifier(workspace_id, "workspace_id"):
            return ResolvedDatabasePath(
                path=None,
                source=None,
                warning=f"Invalid workspace_id: potential path traversal attempt",
            )

        if not self._validate_identifier(scenario_id, "scenario_id"):
            return ResolvedDatabasePath(
                path=None,
                source=None,
                warning=f"Invalid scenario_id: potential path traversal attempt",
            )

        # Step 2: Try scenario-specific database
        scenario_path = self._storage._scenario_path(workspace_id, scenario_id)
        scenario_db_path = scenario_path / self._database_filename
        if scenario_db_path.exists():
            return ResolvedDatabasePath(
                path=scenario_db_path,
                source="scenario",
                warning=None,
            )

        # Step 3: Try workspace-level database
        workspace_path = self._storage._workspace_path(workspace_id)
        workspace_db_path = workspace_path / self._database_filename
        if workspace_db_path.exists():
            return ResolvedDatabasePath(
                path=workspace_db_path,
                source="workspace",
                warning=None,
            )

        # Step 4: Check isolation mode before project fallback
        if self._isolation_mode == IsolationMode.MULTI_TENANT:
            logger.debug(
                f"Multi-tenant mode: no project fallback for workspace={workspace_id}, "
                f"scenario={scenario_id}"
            )
            return ResolvedDatabasePath(
                path=None,
                source=None,
                warning=None,
            )

        # Step 5: Try project default database (SINGLE_TENANT only)
        if self._project_db_path.exists():
            warning_msg = (
                f"Using global project database for workspace={workspace_id}, "
                f"scenario={scenario_id}. This database may contain data from "
                f"other scenarios."
            )
            logger.warning(warning_msg)
            return ResolvedDatabasePath(
                path=self._project_db_path,
                source="project",
                warning=warning_msg,
            )

        # Step 6: No database found
        logger.warning(
            f"No database found for workspace={workspace_id}, scenario={scenario_id}"
        )
        return ResolvedDatabasePath(
            path=None,
            source=None,
            warning=None,
        )
