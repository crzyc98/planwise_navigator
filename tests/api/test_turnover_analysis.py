"""Tests for turnover rate analysis service."""

import csv
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from planalign_api.services.turnover_service import TurnoverAnalysisService


@pytest.fixture
def workspaces_root(tmp_path):
    """Create a temporary workspaces root directory."""
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture
def workspace_dir(workspaces_root):
    """Create a workspace directory."""
    ws = workspaces_root / "test-ws"
    ws.mkdir()
    return ws


@pytest.fixture
def service(workspaces_root):
    """Create a TurnoverAnalysisService instance."""
    return TurnoverAnalysisService(workspaces_root)


def _write_csv(path: Path, rows: list[dict]):
    """Helper to write CSV census files."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestTurnoverAnalysisService:
    """Tests for TurnoverAnalysisService.analyze_turnover_rates."""

    def test_normal_case_with_terminations(self, service, workspace_dir):
        """Test analysis with a mix of active and terminated employees."""
        today = date.today()
        rows = []

        # 80 experienced active employees (tenure >= 1 year)
        for i in range(80):
            rows.append({
                "employee_id": f"EXP_A_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "employee_termination_date": "",
                "active": "true",
            })

        # 10 experienced terminated employees
        for i in range(10):
            rows.append({
                "employee_id": f"EXP_T_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "employee_termination_date": (today - timedelta(days=30 + i)).isoformat(),
                "active": "false",
            })

        # 8 new hire active employees (tenure < 1 year)
        for i in range(8):
            rows.append({
                "employee_id": f"NH_A_{i}",
                "employee_hire_date": (today - timedelta(days=100 + i)).isoformat(),
                "employee_termination_date": "",
                "active": "true",
            })

        # 2 new hire terminated employees
        for i in range(2):
            rows.append({
                "employee_id": f"NH_T_{i}",
                "employee_hire_date": (today - timedelta(days=100 + i)).isoformat(),
                "employee_termination_date": (today - timedelta(days=10 + i)).isoformat(),
                "active": "false",
            })

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates("test-ws", "census.csv")

        assert result.total_employees == 100
        assert result.total_terminated == 12

        # Experienced rate: 10 / 90 ≈ 0.1111
        assert result.experienced_rate is not None
        assert abs(result.experienced_rate.rate - 10 / 90) < 0.01
        assert result.experienced_rate.sample_size == 90
        assert result.experienced_rate.terminated_count == 10
        assert result.experienced_rate.confidence == "moderate"

        # New hire rate: 2 / 10 = 0.2
        assert result.new_hire_rate is not None
        assert abs(result.new_hire_rate.rate - 2 / 10) < 0.01
        assert result.new_hire_rate.sample_size == 10
        assert result.new_hire_rate.terminated_count == 2
        assert result.new_hire_rate.confidence == "low"

    def test_no_terminated_employees(self, service, workspace_dir):
        """Test when all employees are active."""
        today = date.today()
        rows = []
        for i in range(50):
            rows.append({
                "employee_id": f"EMP_{i}",
                "employee_hire_date": (today - timedelta(days=365 * 2 + i)).isoformat(),
                "active": "true",
            })

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates("test-ws", "census.csv")

        assert result.total_employees == 50
        assert result.total_terminated == 0
        assert result.experienced_rate is None
        assert result.new_hire_rate is None
        assert result.message is not None
        assert "No terminated employees" in result.message

    def test_active_column_only(self, service, workspace_dir):
        """Test with active column but no termination date column."""
        today = date.today()
        rows = []

        # Active employees
        for i in range(40):
            rows.append({
                "employee_id": f"A_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "active": "true",
            })

        # Terminated employees (active=false)
        for i in range(10):
            rows.append({
                "employee_id": f"T_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "active": "false",
            })

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates("test-ws", "census.csv")

        assert result.total_terminated == 10
        assert result.experienced_rate is not None
        assert result.experienced_rate.rate == 10 / 50

    def test_no_new_hires_in_census(self, service, workspace_dir):
        """Test when all employees have tenure > 1 year."""
        today = date.today()
        rows = []

        # All experienced
        for i in range(40):
            rows.append({
                "employee_id": f"A_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "employee_termination_date": "",
                "active": "true",
            })

        for i in range(10):
            rows.append({
                "employee_id": f"T_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "employee_termination_date": (today - timedelta(days=30)).isoformat(),
                "active": "false",
            })

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates("test-ws", "census.csv")

        assert result.experienced_rate is not None
        assert result.new_hire_rate is None
        assert result.message is not None
        assert "tenure < 1 year" in result.message

    def test_high_confidence_with_large_sample(self, service, workspace_dir):
        """Test confidence is 'high' with >= 30 terminated employees."""
        today = date.today()
        rows = []

        for i in range(200):
            rows.append({
                "employee_id": f"A_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "active": "true",
            })

        for i in range(50):
            rows.append({
                "employee_id": f"T_{i}",
                "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                "active": "false",
            })

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates("test-ws", "census.csv")

        assert result.experienced_rate is not None
        assert result.experienced_rate.confidence == "high"
        assert result.experienced_rate.terminated_count == 50

    def test_missing_hire_date_column(self, service, workspace_dir):
        """Test error when census has no hire date column."""
        rows = [
            {"employee_id": "1", "name": "Alice", "active": "true"},
            {"employee_id": "2", "name": "Bob", "active": "false"},
        ]

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        with pytest.raises(ValueError, match="hire date column"):
            service.analyze_turnover_rates("test-ws", "census.csv")

    def test_missing_termination_data(self, service, workspace_dir):
        """Test error when census has no way to identify terminated employees."""
        rows = [
            {"employee_id": "1", "employee_hire_date": "2020-01-01", "name": "Alice"},
            {"employee_id": "2", "employee_hire_date": "2021-01-01", "name": "Bob"},
        ]

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        with pytest.raises(ValueError, match="termination data"):
            service.analyze_turnover_rates("test-ws", "census.csv")

    def test_file_not_found(self, service):
        """Test error when census file doesn't exist."""
        with pytest.raises(ValueError, match="File not found"):
            service.analyze_turnover_rates("test-ws", "nonexistent.csv")

    def test_termination_date_column_variants(self, service, workspace_dir):
        """Test with alternative column name: termination_date."""
        today = date.today()
        rows = [
            {
                "employee_id": "1",
                "hire_date": (today - timedelta(days=730)).isoformat(),
                "termination_date": "",
                "active": "true",
            },
            {
                "employee_id": "2",
                "hire_date": (today - timedelta(days=730)).isoformat(),
                "termination_date": (today - timedelta(days=30)).isoformat(),
                "active": "false",
            },
        ]

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates("test-ws", "census.csv")

        assert result.total_employees == 2
        assert result.total_terminated == 1
