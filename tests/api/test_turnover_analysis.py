"""Tests for turnover rate analysis service."""

import csv
from datetime import date, timedelta
from pathlib import Path

import duckdb
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


def _write_census(workspace_dir: Path, rows: list[dict], suffix: str) -> str:
    """Write the same synthetic census as CSV or Parquet."""
    csv_path = workspace_dir / "census.csv"
    _write_csv(csv_path, rows)
    if suffix == ".parquet":
        with duckdb.connect(":memory:") as conn:
            conn.read_csv(str(csv_path)).write_parquet(
                str(csv_path.with_suffix(suffix))
            )
    return f"census{suffix}"


class TestTurnoverAnalysisService:
    """Tests for TurnoverAnalysisService.analyze_turnover_rates."""

    @pytest.mark.parametrize("suffix", [".csv", ".parquet"])
    def test_historical_new_hire_termination_stays_in_cohort(
        self, service, workspace_dir, suffix
    ):
        rows = [
            {"hire_date": "2023-01-01", "termination_date": "2023-04-01"},
            {"hire_date": "2024-10-01", "termination_date": ""},
        ]
        file_name = _write_census(workspace_dir, rows, suffix)
        for as_of in (date(2024, 12, 31), date(2026, 12, 31)):
            result = service.analyze_turnover_rates("test-ws", file_name, as_of)
            assert result.total_employees == 2
            assert result.total_terminated == 1
            assert result.experienced_rate is None
            assert result.new_hire_rate is not None
            assert result.new_hire_rate.terminated_count == 1
            # The active employee ages into the experienced cohort later.
            expected_size = 2 if as_of.year == 2024 else 1
            assert result.new_hire_rate.sample_size == expected_size
            assert result.new_hire_rate.rate == 1 / expected_size
            assert result.as_of_date == as_of
            assert result.as_of_date_source == "provided"
            assert result == service.analyze_turnover_rates("test-ws", file_name, as_of)

    @pytest.mark.parametrize("suffix", [".csv", ".parquet"])
    @pytest.mark.parametrize("as_of", [date(2021, 1, 1), date(2024, 12, 31)])
    def test_termination_tenure_one_year_boundary(
        self, service, workspace_dir, suffix, as_of
    ):
        # Preserve the service's days / 365.25 threshold on either side.
        rows = [
            {"hire_date": "2020-01-01", "termination_date": "2020-12-31"},
            {"hire_date": "2020-01-01", "termination_date": "2021-01-01"},
        ]
        file_name = _write_census(workspace_dir, rows, suffix)
        result = service.analyze_turnover_rates("test-ws", file_name, as_of)
        assert result.experienced_rate is not None
        assert result.new_hire_rate is not None
        for rate in (result.experienced_rate, result.new_hire_rate):
            assert rate.sample_size == 1
            assert rate.terminated_count == 1
            assert rate.rate == 1.0

    @pytest.mark.parametrize("suffix", [".csv", ".parquet"])
    @pytest.mark.parametrize("status", [{"active": "false"}, {"status": "terminated"}])
    def test_status_only_termination_uses_as_of_tenure(
        self, service, workspace_dir, suffix, status
    ):
        file_name = _write_census(
            workspace_dir, [{"hire_date": "2023-01-01", **status}], suffix
        )
        early = service.analyze_turnover_rates("test-ws", file_name, date(2023, 4, 1))
        later = service.analyze_turnover_rates("test-ws", file_name, date(2024, 12, 31))
        assert early.new_hire_rate is not None
        assert early.new_hire_rate.terminated_count == 1
        assert later.new_hire_rate is None
        assert later.experienced_rate is not None
        assert later.experienced_rate.terminated_count == 1

    @pytest.mark.parametrize("suffix", [".csv", ".parquet"])
    @pytest.mark.parametrize(
        "termination_date", ["", " ", "invalid", "2022-12-31", "2025-01-01"]
    )
    def test_termination_date_precedence_and_validation(
        self, service, workspace_dir, suffix, termination_date
    ):
        file_name = _write_census(
            workspace_dir,
            [
                {
                    "hire_date": "2023-01-01",
                    "termination_date": termination_date,
                    "active": "false",
                }
            ],
            suffix,
        )
        if termination_date in ("invalid", "2022-12-31"):
            with pytest.raises(
                ValueError, match="invalid termination date.*on or after hire"
            ):
                service.analyze_turnover_rates("test-ws", file_name, date(2024, 12, 31))
            return
        result = service.analyze_turnover_rates(
            "test-ws", file_name, date(2024, 12, 31)
        )
        assert result.total_employees == 1
        assert result.new_hire_rate is None
        if termination_date == "2025-01-01":
            assert result.total_terminated == 0
            assert result.experienced_rate is None
        else:
            assert result.total_terminated == 1
            assert result.experienced_rate is not None
            assert result.experienced_rate.terminated_count == 1

    @pytest.mark.parametrize("suffix", [".csv", ".parquet"])
    @pytest.mark.parametrize(
        "flags",
        [
            {"active": "true"},
            {"active": "false"},
            {"status": "active"},
            {"status": "terminated"},
            {"active": "false", "status": "active"},
            {},
        ],
    )
    def test_future_termination_excluded_and_as_of_boundary_included(
        self, service, workspace_dir, suffix, flags
    ):
        file_name = _write_census(
            workspace_dir,
            [
                {"hire_date": "2020-01-01", "termination_date": "2026-01-01", **flags},
                {"hire_date": "2020-01-01", "termination_date": "", **flags},
            ],
            suffix,
        )
        before = service.analyze_turnover_rates(
            "test-ws", file_name, date(2025, 12, 31)
        )
        on_date = service.analyze_turnover_rates("test-ws", file_name, date(2026, 1, 1))
        fallback_count = int(
            flags.get("active") == "false"
            or ("active" not in flags and flags.get("status") == "terminated")
        )
        assert before.total_employees == on_date.total_employees == 2
        assert before.total_terminated == fallback_count
        assert on_date.total_terminated == 1 + fallback_count
        assert on_date.experienced_rate.rate == (1 + fallback_count) / 2
        if fallback_count == 0:
            assert before.experienced_rate is None
        else:
            assert before.experienced_rate.rate == 0.5
        for result, expected_date in (
            (before, date(2025, 12, 31)),
            (on_date, date(2026, 1, 1)),
        ):
            assert result.as_of_date == expected_date
            assert result.as_of_date_source == "provided"
        inferred = service.analyze_turnover_rates("test-ws", file_name)
        assert inferred.as_of_date == date(2026, 12, 31)
        assert inferred.as_of_date_source == "inferred"
        assert inferred.total_terminated == 1 + fallback_count

    def test_normal_case_with_terminations(self, service, workspace_dir):
        """Test analysis with a mix of active and terminated employees."""
        today = date.today()
        rows = []

        # 80 experienced active employees (tenure >= 1 year)
        for i in range(80):
            rows.append(
                {
                    "employee_id": f"EXP_A_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "employee_termination_date": "",
                    "active": "true",
                }
            )

        # 10 experienced terminated employees
        for i in range(10):
            rows.append(
                {
                    "employee_id": f"EXP_T_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "employee_termination_date": (
                        today - timedelta(days=30 + i)
                    ).isoformat(),
                    "active": "false",
                }
            )

        # 8 new hire active employees (tenure < 1 year)
        for i in range(8):
            rows.append(
                {
                    "employee_id": f"NH_A_{i}",
                    "employee_hire_date": (today - timedelta(days=100 + i)).isoformat(),
                    "employee_termination_date": "",
                    "active": "true",
                }
            )

        # 2 new hire terminated employees
        for i in range(2):
            rows.append(
                {
                    "employee_id": f"NH_T_{i}",
                    "employee_hire_date": (today - timedelta(days=100 + i)).isoformat(),
                    "employee_termination_date": (
                        today - timedelta(days=10 + i)
                    ).isoformat(),
                    "active": "false",
                }
            )

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates(
            "test-ws", "census.csv", as_of_date=today
        )

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
            rows.append(
                {
                    "employee_id": f"EMP_{i}",
                    "employee_hire_date": (
                        today - timedelta(days=365 * 2 + i)
                    ).isoformat(),
                    "active": "true",
                }
            )

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates(
            "test-ws", "census.csv", as_of_date=today
        )

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
            rows.append(
                {
                    "employee_id": f"A_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "active": "true",
                }
            )

        # Terminated employees (active=false)
        for i in range(10):
            rows.append(
                {
                    "employee_id": f"T_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "active": "false",
                }
            )

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates(
            "test-ws", "census.csv", as_of_date=today
        )

        assert result.total_terminated == 10
        assert result.experienced_rate is not None
        assert result.experienced_rate.rate == 10 / 50

    def test_no_new_hires_in_census(self, service, workspace_dir):
        """Test when all employees have tenure > 1 year."""
        today = date.today()
        rows = []

        # All experienced
        for i in range(40):
            rows.append(
                {
                    "employee_id": f"A_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "employee_termination_date": "",
                    "active": "true",
                }
            )

        for i in range(10):
            rows.append(
                {
                    "employee_id": f"T_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "employee_termination_date": (
                        today - timedelta(days=30)
                    ).isoformat(),
                    "active": "false",
                }
            )

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
            rows.append(
                {
                    "employee_id": f"A_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "active": "true",
                }
            )

        for i in range(50):
            rows.append(
                {
                    "employee_id": f"T_{i}",
                    "employee_hire_date": (today - timedelta(days=730 + i)).isoformat(),
                    "active": "false",
                }
            )

        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_turnover_rates(
            "test-ws", "census.csv", as_of_date=today
        )

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
