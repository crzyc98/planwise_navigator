"""Tests for pre-simulation census analysis (Census Analysis page)."""

import csv
from datetime import date
from pathlib import Path

import pytest

from planalign_api.services.census_analysis_service import CensusAnalysisService

AS_OF = date(2024, 12, 31)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _birth_date_for_age(age: int) -> str:
    return date(AS_OF.year - age, AS_OF.month, AS_OF.day).isoformat()


def _employee(
    *,
    age: int = 40,
    hire_date: str = "2020-01-01",
    compensation: float = 80000,
    deferral_rate: str | float | None = 0.06,
    active: str = "true",
    department: str | None = None,
    match: float = 0,
    core: float = 0,
    **overrides,
) -> dict:
    row = {
        "employee_id": overrides.pop("employee_id", "EMP"),
        "employee_birth_date": _birth_date_for_age(age),
        "employee_hire_date": hire_date,
        "employee_gross_compensation": compensation,
        "employee_deferral_rate": deferral_rate if deferral_rate is not None else "",
        "active": active,
        "employer_match_contribution": match,
        "employer_core_contribution": core,
    }
    if department is not None:
        row["department"] = department
    row.update(overrides)
    return row


@pytest.fixture
def workspaces_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture
def workspace_dir(workspaces_root: Path) -> Path:
    ws = workspaces_root / "test-ws"
    ws.mkdir()
    return ws


@pytest.fixture
def service(workspaces_root: Path) -> CensusAnalysisService:
    return CensusAnalysisService(workspaces_root)


def _analyze(service, workspace_dir, rows, as_of=AS_OF):
    for index, row in enumerate(rows):
        row["employee_id"] = f"EMP{index:04d}"
    _write_csv(workspace_dir / "census.csv", rows)
    return service.analyze("test-ws", "census.csv", as_of_date=as_of)


@pytest.mark.fast
class TestOverallMetrics:
    def test_participation_and_savings_rate(self, service, workspace_dir):
        rows = [
            _employee(deferral_rate=0.06, department="Eng"),
            _employee(deferral_rate=0.10, department="Eng"),
            _employee(deferral_rate=0, department="Sales"),
            _employee(deferral_rate=None, department="Sales"),
        ]
        result = _analyze(service, workspace_dir, rows)

        assert result.overall.employee_count == 4
        assert result.overall.eligible_count == 4
        assert result.overall.enrolled_count == 2
        assert result.overall.participation_rate == pytest.approx(0.5)
        assert result.overall.zero_deferral_count == 2
        assert result.overall.average_deferral_rate == pytest.approx(0.08)

    def test_employer_cost_proxy(self, service, workspace_dir):
        rows = [
            _employee(match=3000, core=1000),
            _employee(match=2000, core=500),
        ]
        result = _analyze(service, workspace_dir, rows)

        assert result.overall.total_employer_match == pytest.approx(5000)
        assert result.overall.total_employer_core == pytest.approx(1500)
        assert result.overall.total_employer_cost == pytest.approx(6500)

    def test_inactive_employees_excluded(self, service, workspace_dir):
        rows = [
            _employee(active="true"),
            _employee(active="false"),
        ]
        result = _analyze(service, workspace_dir, rows)

        assert result.total_employees == 2
        assert result.active_employees == 1
        assert result.overall.employee_count == 1


@pytest.mark.fast
class TestSegments:
    def test_department_segment(self, service, workspace_dir):
        rows = [
            _employee(department="Eng", deferral_rate=0.10),
            _employee(department="Eng", deferral_rate=0.10),
            _employee(department="Sales", deferral_rate=0),
        ]
        result = _analyze(service, workspace_dir, rows)

        assert "department" in result.available_segment_dimensions
        dept_segments = {
            s.value: s for s in result.segments if s.dimension == "department"
        }
        assert dept_segments["Eng"].employee_count == 2
        assert dept_segments["Eng"].participation_rate == pytest.approx(1.0)
        assert dept_segments["Sales"].participation_rate == pytest.approx(0.0)

    def test_hce_status_segment(self, service, workspace_dir):
        rows = [
            _employee(compensation=200000),  # HCE for 2024 threshold (155000)
            _employee(compensation=60000),
        ]
        result = _analyze(service, workspace_dir, rows)

        assert result.hce_compensation_threshold == pytest.approx(155000)
        hce_segments = {
            s.value: s for s in result.segments if s.dimension == "hce_status"
        }
        assert hce_segments["HCE"].employee_count == 1
        assert hce_segments["NHCE"].employee_count == 1

    def test_age_and_tenure_bands_present(self, service, workspace_dir):
        rows = [_employee(age=25), _employee(age=55)]
        result = _analyze(service, workspace_dir, rows)

        assert "age_band" in result.available_segment_dimensions
        assert "tenure_band" in result.available_segment_dimensions
        assert (
            sum(s.employee_count for s in result.segments if s.dimension == "age_band")
            == 2
        )

    def test_no_department_column_omits_dimension(self, service, workspace_dir):
        rows = [_employee(), _employee()]
        result = _analyze(service, workspace_dir, rows)

        assert "department" not in result.available_segment_dimensions
        assert not any(s.dimension == "department" for s in result.segments)


@pytest.mark.fast
class TestDataQuality:
    def test_duplicate_employee_id_flagged(self, service, workspace_dir):
        rows = [_employee(employee_id="DUP"), _employee(employee_id="DUP")]
        _write_csv(workspace_dir / "census.csv", rows)
        result = service.analyze("test-ws", "census.csv", as_of_date=AS_OF)

        dupe_issues = [
            i
            for i in result.data_quality_issues
            if i.issue_type == "duplicate_employee_id"
        ]
        assert len(dupe_issues) == 1
        assert dupe_issues[0].count == 1

    def test_missing_compensation_flagged(self, service, workspace_dir):
        rows = [_employee(), _employee(compensation="")]
        result = _analyze(service, workspace_dir, rows)

        missing = [
            i
            for i in result.data_quality_issues
            if i.issue_type == "missing_required_field"
            and i.field == "employee_gross_compensation"
        ]
        assert len(missing) == 1
        assert missing[0].count == 1

    def test_out_of_range_deferral_rate_flagged(self, service, workspace_dir):
        rows = [_employee(deferral_rate=0.06), _employee(deferral_rate=1.5)]
        result = _analyze(service, workspace_dir, rows)

        out_of_range = [
            i
            for i in result.data_quality_issues
            if i.issue_type == "out_of_range_value"
            and i.field == "employee_deferral_rate"
        ]
        assert len(out_of_range) == 1
        assert out_of_range[0].count == 1

    def test_clean_census_has_no_issues(self, service, workspace_dir):
        rows = [_employee(), _employee()]
        result = _analyze(service, workspace_dir, rows)

        assert result.data_quality_issues == []


@pytest.mark.fast
class TestFileHandling:
    def test_missing_file_raises_value_error(self, service, workspace_dir):
        with pytest.raises(ValueError, match="File not found"):
            service.analyze("test-ws", "does-not-exist.csv", as_of_date=AS_OF)

    def test_as_of_date_provided_is_echoed(self, service, workspace_dir):
        rows = [_employee()]
        result = _analyze(service, workspace_dir, rows, as_of=date(2025, 6, 30))

        assert result.as_of_date == date(2025, 6, 30)
        assert result.as_of_date_source == "provided"
