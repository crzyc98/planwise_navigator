"""
Contract: DatabasePathResolver Interface

This file defines the public interface contract for the DatabasePathResolver.
It serves as the specification for implementation and test doubles.

Feature: 005-database-path-resolver
Date: 2025-12-12
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

# ==============================================================================
# Enums
# ==============================================================================


class IsolationMode(str, Enum):
    """Tenant isolation behavior for database resolution."""

    SINGLE_TENANT = "single-tenant"  # Allow fallback to project-level database
    MULTI_TENANT = "multi-tenant"  # Stop at workspace level; no project fallback


# ==============================================================================
# Value Objects
# ==============================================================================


class ResolvedDatabasePath(BaseModel):
    """
    Immutable value object containing resolved database path and metadata.

    Attributes:
        path: Resolved filesystem path to the database, or None if not found.
        source: Level at which the database was found.
        warning: Optional warning message (e.g., when using project fallback).
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
# Protocols
# ==============================================================================


@runtime_checkable
class WorkspaceStorageProtocol(Protocol):
    """
    Protocol defining the interface required from storage implementations.

    The existing WorkspaceStorage class already implements these methods.
    """

    def _workspace_path(self, workspace_id: str) -> Path:
        """Get the filesystem path for a workspace directory."""
        ...

    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path:
        """Get the filesystem path for a scenario directory."""
        ...


# ==============================================================================
# Service Class Interface
# ==============================================================================


class DatabasePathResolverInterface(Protocol):
    """
    Protocol defining the public interface for DatabasePathResolver.

    This protocol can be used for type hints and test doubles.
    """

    def resolve(
        self,
        workspace_id: str,
        scenario_id: str,
    ) -> ResolvedDatabasePath:
        """
        Resolve the database path for a given workspace and scenario.

        The resolution follows this fallback chain:
        1. Scenario-specific: {scenario_path}/simulation.duckdb
        2. Workspace-level: {workspace_path}/simulation.duckdb
        3. Project default: {project_root}/dbt/simulation.duckdb
           (only if isolation_mode is SINGLE_TENANT)

        Args:
            workspace_id: The workspace identifier (validated for path safety).
            scenario_id: The scenario identifier (validated for path safety).

        Returns:
            ResolvedDatabasePath with the resolved path and metadata.
            If no database is found, path will be None.
            If inputs fail validation, path will be None with a warning.
        """
        ...


# ==============================================================================
# Implementation Skeleton (for reference)
# ==============================================================================


class DatabasePathResolver:
    """
    Stateless service for resolving database paths.

    Thread-safe by design (no mutable instance state).

    Example:
        >>> from planalign_api.storage.workspace_storage import WorkspaceStorage
        >>> storage = WorkspaceStorage()
        >>> resolver = DatabasePathResolver(storage)
        >>> result = resolver.resolve("workspace-123", "scenario-456")
        >>> if result.exists:
        ...     conn = duckdb.connect(str(result.path))
    """

    # Pattern for detecting invalid path characters
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
            isolation_mode: Tenant isolation behavior (default: SINGLE_TENANT).
            project_root: Override for project root path (default: auto-detect).
            database_filename: Database filename to search for.

        Raises:
            ValueError: If project_root cannot be determined.
        """
        self._storage = storage
        self._isolation_mode = isolation_mode
        self._database_filename = database_filename

        # Determine project root
        if project_root is not None:
            self._project_root = project_root
        else:
            self._project_root = self._detect_project_root()

        # Pre-compute project database path
        self._project_db_path = self._project_root / "dbt" / self._database_filename

    def resolve(
        self,
        workspace_id: str,
        scenario_id: str,
    ) -> ResolvedDatabasePath:
        """Resolve database path using fallback chain."""
        # Implementation details in actual source file
        raise NotImplementedError("See planalign_api/services/database_path_resolver.py")

    def _validate_identifier(self, value: str, name: str) -> bool:
        """
        Validate an identifier for path traversal safety.

        Returns False if the value contains dangerous characters.
        """
        if not value:
            return False
        return self._INVALID_CHARS.search(value) is None

    def _detect_project_root(self) -> Path:
        """
        Auto-detect project root from module location.

        Returns the path 3 levels up from the services directory.
        """
        return Path(__file__).parent.parent.parent
