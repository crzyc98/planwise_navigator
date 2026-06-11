"""Tests for part-time percentage census analysis (#093 / GitHub issue #282).

Covers the analyze_part_time_pct service method: column detection,
part-time counting (scheduled annual hours < 1,000), alias handling,
active-employee filtering, and the part_time_new_hire_pct config field.
"""

import csv
from pathlib import Path

import pytest

from planalign_api.services.file_service import FileService
from planalign_orchestrator.config.workforce import WorkforceSettings


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace directory structure."""
    workspace_id = "test-workspace"
    workspace_dir = tmp_path / workspace_id
    workspace_dir.mkdir()
    (workspace_dir / "data").mkdir()
    return tmp_path, workspace_id


@pytest.fixture
def file_service(tmp_workspace):
    """Create a FileService instance with the temp workspace root."""
    workspaces_root, _ = tmp_workspace
    return FileService(workspaces_root)


def _create_csv(
    workspace_root: Path, workspace_id: str, filename: str, columns: list, rows: list
) -> str:
    """Helper to create a CSV file, returning its workspace-relative path."""
    data_dir = workspace_root / workspace_id / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / filename
    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    return f"data/{filename}"


class TestAnalyzePartTimePct:
    """Test the analyze_part_time_pct service method."""

    def test_census_with_part_time_employees(self, file_service, tmp_workspace):
        """20 hrs/wk employees (1,040 annual hours) are NOT part-time under the <1,000 rule;
        15 hrs/wk employees (780 annual hours) are."""
        workspace_root, workspace_id = tmp_workspace
        rel_path = _create_csv(
            workspace_root,
            workspace_id,
            "census.csv",
            columns=["employee_id", "scheduled_hours_per_week"],
            rows=[
                ["EMP001", "40"],
                ["EMP002", "15"],  # 780 annual hours -> part-time
                ["EMP003", "20"],  # 1,040 annual hours -> not part-time
                ["EMP004", "10"],  # 520 annual hours -> part-time
            ],
        )

        result = file_service.analyze_part_time_pct(workspace_id, rel_path)

        assert result["column_present"] is True
        assert result["headcount"] == 4
        assert result["part_time_count"] == 2
        assert result["part_time_pct"] == 0.5

    def test_census_without_hours_column(self, file_service, tmp_workspace):
        """Census lacking a scheduled hours column returns column_present=False."""
        workspace_root, workspace_id = tmp_workspace
        rel_path = _create_csv(
            workspace_root,
            workspace_id,
            "census.csv",
            columns=["employee_id", "employee_gross_compensation"],
            rows=[["EMP001", "75000"], ["EMP002", "85000"]],
        )

        result = file_service.analyze_part_time_pct(workspace_id, rel_path)

        assert result["column_present"] is False
        assert result["headcount"] == 2
        assert result["part_time_count"] == 0
        assert result["part_time_pct"] == 0.0

    def test_hours_column_alias_detected(self, file_service, tmp_workspace):
        """Alias column names like hours_per_week are detected."""
        workspace_root, workspace_id = tmp_workspace
        rel_path = _create_csv(
            workspace_root,
            workspace_id,
            "census.csv",
            columns=["employee_id", "hours_per_week"],
            rows=[["EMP001", "40"], ["EMP002", "12"]],
        )

        result = file_service.analyze_part_time_pct(workspace_id, rel_path)

        assert result["column_present"] is True
        assert result["part_time_count"] == 1
        assert result["part_time_pct"] == 0.5

    def test_null_hours_treated_as_full_time(self, file_service, tmp_workspace):
        """Employees with no scheduled hours value are not counted as part-time."""
        workspace_root, workspace_id = tmp_workspace
        rel_path = _create_csv(
            workspace_root,
            workspace_id,
            "census.csv",
            columns=["employee_id", "scheduled_hours_per_week"],
            rows=[["EMP001", ""], ["EMP002", "15"]],
        )

        result = file_service.analyze_part_time_pct(workspace_id, rel_path)

        assert result["column_present"] is True
        assert result["headcount"] == 2
        assert result["part_time_count"] == 1

    def test_inactive_employees_excluded(self, file_service, tmp_workspace):
        """Inactive employees are excluded from the headcount and part-time count."""
        workspace_root, workspace_id = tmp_workspace
        rel_path = _create_csv(
            workspace_root,
            workspace_id,
            "census.csv",
            columns=["employee_id", "scheduled_hours_per_week", "active"],
            rows=[
                ["EMP001", "40", "true"],
                ["EMP002", "15", "true"],
                ["EMP003", "10", "false"],  # inactive: excluded
            ],
        )

        result = file_service.analyze_part_time_pct(workspace_id, rel_path)

        assert result["headcount"] == 2
        assert result["part_time_count"] == 1
        assert result["part_time_pct"] == 0.5

    def test_missing_file_raises_value_error(self, file_service):
        """A nonexistent file path raises ValueError."""
        with pytest.raises(ValueError, match="File not found"):
            file_service.analyze_part_time_pct("test-workspace", "data/nope.csv")


class TestPartTimeNewHireConfig:
    """Test the part_time_new_hire_pct config field."""

    def test_default_is_zero(self):
        assert WorkforceSettings().part_time_new_hire_pct == 0.0

    def test_valid_fraction_accepted(self):
        settings = WorkforceSettings(part_time_new_hire_pct=0.2)
        assert settings.part_time_new_hire_pct == 0.2

    def test_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            WorkforceSettings(part_time_new_hire_pct=1.5)
        with pytest.raises(ValueError):
            WorkforceSettings(part_time_new_hire_pct=-0.1)
