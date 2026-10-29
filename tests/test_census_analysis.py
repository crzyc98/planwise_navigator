"""Tests for pre-simulation census analysis (Census Analysis page)."""

import csv
from datetime import date
from pathlib import Path

import pytest

from planalign_api.services.census_analysis_service import CensusAnalysisService
from planalign_api.services.compensation_solver import CompensationSolver

AS_OF = date(2024, 12, 31)


@pytest.mark.fast
@pytest.mark.parametrize("as_of", [None, date(2023, 12, 31)])
def test_pre_coverage_hce_is_unknown(service, workspace_dir, as_of):
    rows = [_employee(hire_date="2023-01-01", compensation=200000, department="Eng")]
    result = _analyze(service, workspace_dir, rows, as_of=as_of)

    assert result.as_of_date == date(2023, 12, 31)
    assert result.as_of_date_source == ("inferred" if as_of is None else "provided")
    assert result.hce_compensation_threshold is None
    assert result.overall.hce_count is None
    assert all(segment.hce_count is None for segment in result.segments)
    assert "hce_status" not in result.available_segment_dimensions
    assert result.model_dump(mode="json")["overall"]["hce_count"] is None
    assert result.overall.enrolled_count == 1


@pytest.mark.fast
def test_missing_irs_seed_preserves_unknown_hce(
    service, workspace_dir, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "planalign_api.services.census_analysis_service.IRS_LIMITS_SEED",
        tmp_path / "missing.csv",
    )
    result = _analyze(service, workspace_dir, [_employee(compensation=200000)])

    assert result.as_of_date == AS_OF
    assert result.hce_compensation_threshold is None
    assert result.overall.hce_count is None
    assert "hce_status" not in result.available_segment_dimensions
    assert result.overall.participation_rate == 1.0


@pytest.mark.fast
def test_explicit_covered_date_restores_hce_without_changing_other_metrics(
    service, workspace_dir
):
    rows = [_employee(hire_date="2023-01-01", compensation=200000)]
    inferred = _analyze(service, workspace_dir, rows, as_of=None)
    covered = _analyze(service, workspace_dir, rows, as_of=AS_OF)

    assert covered.as_of_date_source == "provided"
    assert covered.hce_compensation_threshold == 155000
    assert covered.overall.hce_count == 1
    assert covered.overall.model_dump(
        exclude={"hce_count"}
    ) == inferred.overall.model_dump(exclude={"hce_count"})


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.fast
def test_compensation_solver_uses_shared_active_filter(tmp_path):
    path = tmp_path / "census.csv"
    _write_csv(
        path,
        [
            {"active": active, "employee_gross_compensation": 100000}
            for active in (None, " employed ", "1.0", " Y ", "t", "no")
        ],
    )

    _, average_compensation, headcount = CompensationSolver(
        tmp_path
    ).analyze_workforce_for_solver("unused", str(path))

    assert headcount == 5
    assert average_compensation == 100000


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

    def test_total_compensation_includes_active_eligible_employees(
        self, service, workspace_dir
    ):
        rows = [
            _employee(
                compensation=120000,
                department="Eng",
                eligibility_entry_date="2020-01-01",
            ),
            _employee(
                compensation=80000,
                department="Sales",
                eligibility_entry_date="2020-01-01",
            ),
            _employee(
                compensation=60000,
                department="Eng",
                eligibility_entry_date="2025-01-01",
            ),
            _employee(
                compensation=50000,
                department="Sales",
                active="false",
                eligibility_entry_date="2020-01-01",
            ),
        ]
        result = _analyze(service, workspace_dir, rows)

        assert result.overall.total_eligible_compensation == pytest.approx(200000)
        department_segments = {
            segment.value: segment
            for segment in result.segments
            if segment.dimension == "department"
        }
        assert department_segments["Eng"].total_eligible_compensation == pytest.approx(
            120000
        )
        assert department_segments[
            "Sales"
        ].total_eligible_compensation == pytest.approx(80000)

    def test_inactive_employees_excluded(self, service, workspace_dir):
        rows = [
            _employee(active="true"),
            _employee(active="false"),
        ]
        result = _analyze(service, workspace_dir, rows)

        assert result.total_employees == 2
        assert result.active_employees == 1
        assert result.overall.employee_count == 1

    def test_average_employer_contribution_and_total_savings_rate(
        self, service, workspace_dir
    ):
        rows = [
            _employee(compensation=120000, deferral_rate=0.06, match=3600, core=1200),
            _employee(compensation=60000, deferral_rate=0, match=0, core=0),
            _employee(compensation=200000, deferral_rate=0.10, match=7000, core=2000),
            _employee(compensation=50000, deferral_rate=None, match=0, core=0),
        ]
        result = _analyze(service, workspace_dir, rows)

        # Per-employee employer rate: 0.04, 0.0, 0.045, 0.0 -> mean 0.02125
        assert result.overall.average_employer_contribution_rate == pytest.approx(
            0.02125
        )
        # Per-employee total savings (deferral + employer rate): 0.10, 0.0, 0.145, 0.0
        # -> mean 0.06125
        assert result.overall.average_total_savings_rate == pytest.approx(0.06125)

    def test_savings_rate_none_without_compensation(self, service, workspace_dir):
        rows = [_employee(compensation="", deferral_rate=0.06)]
        result = _analyze(service, workspace_dir, rows)

        assert result.overall.average_employer_contribution_rate is None
        assert result.overall.average_total_savings_rate is None


@pytest.mark.fast
class TestDeferralDistribution:
    def test_buckets_cover_full_range(self, service, workspace_dir):
        rows = [
            _employee(deferral_rate=0),
            _employee(deferral_rate=0.06),
            _employee(deferral_rate=0.12),
        ]
        result = _analyze(service, workspace_dir, rows)

        buckets = {b.bucket: b for b in result.deferral_rate_distribution}
        assert len(result.deferral_rate_distribution) == 11
        assert buckets["0%"].count == 1
        assert buckets["6%"].count == 1
        assert buckets["10%+"].count == 1
        assert buckets["6%"].percentage == pytest.approx(33.33, abs=0.01)

    def test_null_deferral_counted_as_zero_bucket(self, service, workspace_dir):
        rows = [_employee(deferral_rate=None), _employee(deferral_rate=0.02)]
        result = _analyze(service, workspace_dir, rows)

        buckets = {b.bucket: b for b in result.deferral_rate_distribution}
        assert buckets["0%"].count == 1
        assert buckets["2%"].count == 1

    def test_empty_without_deferral_column(self, service, workspace_dir):
        rows = [_employee()]
        for row in rows:
            row.pop("employee_deferral_rate", None)
        _write_csv(workspace_dir / "census.csv", rows)
        result = service.analyze("test-ws", "census.csv", as_of_date=AS_OF)

        assert result.deferral_rate_distribution == []


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

    @pytest.mark.parametrize("compensation", ["", "unparseable"])
    def test_missing_or_invalid_compensation_has_unknown_hce_status(
        self, service, workspace_dir, compensation
    ):
        rows = [_employee(compensation=200000), _employee(compensation=compensation)]
        result = _analyze(service, workspace_dir, rows)

        hce_segments = [s for s in result.segments if s.dimension == "hce_status"]
        assert result.active_employees == 2
        assert result.overall.hce_count == 1
        assert [(s.value, s.employee_count) for s in hce_segments] == [("HCE", 1)]

    @pytest.mark.parametrize("active", [None, " employed ", "1.0", " Y "])
    def test_shared_active_aliases_are_included(self, service, workspace_dir, active):
        result = _analyze(service, workspace_dir, [_employee(active=active)])
        assert result.active_employees == 1

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


@pytest.mark.fast
@pytest.mark.parametrize(
    "status,count,compensation",
    [("all", 2, 180000), ("active", 1, 80000), ("terminated", 1, 100000)],
)
def test_population_filter(service, workspace_dir, status, count, compensation):
    _write_csv(
        workspace_dir / "census.csv",
        [
            _employee(
                employee_id="A", active="employed", compensation=80000, department="Eng"
            ),
            _employee(
                employee_id="T", active="false", compensation=100000, department="Eng"
            ),
        ],
    )
    result = service.analyze("test-ws", "census.csv", AS_OF, employee_status=status)
    assert result.total_employees == 2
    assert result.active_employees == 1
    assert result.overall.employee_count == count
    assert result.overall.total_eligible_compensation == compensation
    assert sum(b.count for b in result.deferral_rate_distribution) == count
    assert (
        next(s for s in result.segments if s.dimension == "department").employee_count
        == count
    )


@pytest.mark.fast
def test_terminated_population_without_status_is_empty(service, workspace_dir):
    row = _employee()
    del row["active"]
    _write_csv(workspace_dir / "census.csv", [row])
    result = service.analyze(
        "test-ws", "census.csv", AS_OF, employee_status="terminated"
    )
    assert result.overall.employee_count == 0
    assert result.message == "No employees found in the selected population."


@pytest.mark.fast
@pytest.mark.parametrize("status", ["all", "active", "terminated"])
def test_workforce_rates_use_full_census_and_receipts_use_selected_population(
    service, workspace_dir, status
):
    rows = [
        _employee(
            employee_id="A",
            hire_date="2020-01-01",
            employee_termination_date="",
            match=100,
            core=0,
        ),
        _employee(
            employee_id="B",
            hire_date="2024-03-01",
            employee_termination_date="",
            match=0,
            core=100,
        ),
        _employee(
            employee_id="C",
            hire_date="2020-01-01",
            employee_termination_date="2024-06-01",
            active="false",
            match=100,
            core=100,
        ),
        _employee(
            employee_id="D",
            hire_date="2025-01-01",
            employee_termination_date="",
            match=0,
            core=0,
        ),
    ]
    _write_csv(workspace_dir / "census.csv", rows)
    result = service.analyze("test-ws", "census.csv", AS_OF, employee_status=status)
    assert result.workforce_rate_start == date(2023, 12, 31)
    assert result.workforce_average_headcount == 2
    assert result.new_hire_rate == 0.5
    assert result.termination_rate == 0.5
    expected = {"all": 0.5, "active": 1 / 3, "terminated": 1.0}[status]
    assert result.match_receipt_rate == pytest.approx(expected)
    assert result.core_receipt_rate == pytest.approx(expected)


@pytest.mark.fast
def test_missing_columns_do_not_imply_zero_rates(service, workspace_dir):
    row = _employee()
    del row["employer_match_contribution"]
    del row["employer_core_contribution"]
    result = _analyze(service, workspace_dir, [row])
    assert result.match_receipt_rate is None
    assert result.core_receipt_rate is None
    assert result.new_hire_rate is None
    assert result.termination_rate is None


@pytest.mark.fast
def test_workforce_dates_reject_invalid_and_exclude_boundary_and_future_events(
    service, workspace_dir
):
    rows = [
        _employee(hire_date="2023-12-31", employee_termination_date="2025-01-01"),
        _employee(hire_date="2024-12-31", employee_termination_date=""),
    ]
    result = _analyze(service, workspace_dir, rows)
    assert result.new_hire_rate == pytest.approx(1 / 1.5)
    assert result.termination_rate == 0
    rows[0]["employee_termination_date"] = "invalid"
    result = _analyze(service, workspace_dir, rows)
    assert result.termination_rate is None
    assert result.new_hire_rate is None
