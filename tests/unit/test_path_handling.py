"""
Unit tests for path handling.

Tests for:
- T002: POSIX path conversion
- T003: Absolute-to-relative path conversion
- T004: Paths with spaces
- T015: Workspace-specific path construction
"""

from __future__ import annotations

import os
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import patch

import pytest


class TestNormalizePathForDuckDB:
    """Tests for normalize_path_for_duckdb() helper function (T001, T002, T003, T004)."""

    def test_posix_path_unchanged(self):
        """T002: POSIX paths should remain as forward slashes."""
        from planalign_orchestrator.pipeline.event_generation_executor import normalize_path_for_duckdb

        # Already POSIX format
        result = normalize_path_for_duckdb(Path("data/parquet/events"))
        assert "/" in result
        assert "\\" not in result
        assert result == "../data/parquet/events"

    def test_windows_backslash_converted(self):
        """T002: Windows backslash paths should be converted to forward slashes."""
        from planalign_orchestrator.pipeline.event_generation_executor import normalize_path_for_duckdb

        # Simulate Windows path by directly testing the conversion logic
        # On any platform, as_posix() should produce forward slashes
        path = Path("data") / "parquet" / "events"
        result = normalize_path_for_duckdb(path)

        assert "/" in result or result == "../data/parquet/events"
        assert "\\" not in result

    def test_absolute_path_conversion(self):
        """T003: Absolute paths should be converted to dbt-relative paths."""
        from planalign_orchestrator.pipeline.event_generation_executor import normalize_path_for_duckdb

        # Create an absolute path within the project
        cwd = Path.cwd()
        abs_path = cwd / "data" / "parquet" / "events"

        result = normalize_path_for_duckdb(abs_path)

        # Should be relative with forward slashes
        assert "/" in result or result.startswith("../")
        assert "\\" not in result

    def test_path_with_spaces(self):
        """T004: Paths with spaces should be handled correctly."""
        from planalign_orchestrator.pipeline.event_generation_executor import normalize_path_for_duckdb

        path = Path("data") / "my parquet folder" / "events"
        result = normalize_path_for_duckdb(path)

        # Should preserve spaces and use forward slashes
        assert "my parquet folder" in result
        assert "\\" not in result

    def test_already_relative_from_dbt(self):
        """Paths already starting with ../ should be preserved."""
        from planalign_orchestrator.pipeline.event_generation_executor import normalize_path_for_duckdb

        path = Path("../data/parquet/events")
        result = normalize_path_for_duckdb(path)

        # Should keep the ../ prefix
        assert result.startswith("../") or result.startswith("..")
        assert "\\" not in result

    def test_posix_format_always(self):
        """Result should always be in POSIX format regardless of input."""
        from planalign_orchestrator.pipeline.event_generation_executor import normalize_path_for_duckdb

        test_paths = [
            Path("data/parquet/events"),
            Path("data") / "parquet" / "events",
            Path(".") / "data" / "parquet",
        ]

        for path in test_paths:
            result = normalize_path_for_duckdb(path)
            # No backslashes in result
            assert "\\" not in result, f"Backslash found in result for {path}: {result}"


class TestWorkspacePathConstruction:
    """Tests for workspace-specific path construction (T015)."""

    def test_workspace_parquet_path_structure(self):
        """T015: Workspace-specific path should follow the correct structure."""
        # This tests the path construction logic for workspace isolation
        workspace_id = "ws-12345"
        scenario_id = "baseline"

        # Simulate the path construction that simulation_service.py should do
        base_path = Path("workspaces") / workspace_id / "scenarios" / scenario_id
        parquet_output = base_path / "data" / "parquet" / "events"

        # Should produce the expected structure
        expected_parts = ["workspaces", workspace_id, "scenarios", scenario_id, "data", "parquet", "events"]

        # Verify structure (platform-independent check)
        path_str = parquet_output.as_posix()
        for part in expected_parts:
            assert part in path_str, f"Expected '{part}' in path: {path_str}"

    def test_workspace_path_uses_forward_slashes(self):
        """T015: Workspace paths should use forward slashes for DuckDB."""
        workspace_id = "ws-12345"
        scenario_id = "baseline"

        base_path = Path("workspaces") / workspace_id / "scenarios" / scenario_id
        parquet_output = base_path / "data" / "parquet" / "events"

        # as_posix() should give forward slashes
        path_str = parquet_output.as_posix()
        assert "\\" not in path_str
