"""Tests for per-segment deferral rate analysis from census data (issue #650)."""

import csv
from datetime import date
from pathlib import Path

import pytest

from planalign_api.services.deferral_segment_service import (
    LOW_CONFIDENCE_THRESHOLD,
    DeferralSegmentAnalysisService,
)

AS_OF = date(2024, 12, 31)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _birth_date_for_age(age: int) -> str:
    """Birth date that yields exactly `age` at AS_OF under the service's formula."""
    return date(AS_OF.year - age, AS_OF.month, AS_OF.day).isoformat()


def _employee(age: int, compensation: float, deferral_rate: float, **overrides) -> dict:
    row = {
        "employee_id": overrides.pop("employee_id", "EMP"),
        "employee_birth_date": _birth_date_for_age(age),
        "employee_hire_date": "2020-01-01",
        "employee_gross_compensation": compensation,
        "employee_deferral_rate": deferral_rate,
    }
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
def service(workspaces_root: Path) -> DeferralSegmentAnalysisService:
    return DeferralSegmentAnalysisService(workspaces_root)


def _analyze(service, workspace_dir, rows, as_of=AS_OF):
    for index, row in enumerate(rows):
        row.setdefault("employee_id", f"EMP{index:04d}")
        row["employee_id"] = f"EMP{index:04d}"
    _write_csv(workspace_dir / "census.csv", rows)
    return service.analyze_deferral_segments("test-ws", "census.csv", as_of_date=as_of)


def _segment(result, key):
    return next((s for s in result.segments if s.segment == key), None)


@pytest.mark.fast
class TestSegmentBoundaries:
    """Age and income cut points must match int_voluntary_enrollment_decision.sql."""

    @pytest.mark.parametrize(
        "age,expected",
        [
            (30, "young"),
            (31, "mid_career"),
            (45, "mid_career"),
            (46, "mature"),
            (55, "mature"),
            (56, "senior"),
        ],
    )
    def test_age_boundaries(self, service, workspace_dir, age, expected):
        result = _analyze(service, workspace_dir, [_employee(age, 60_000, 0.05)])
        assert _segment(result, f"{expected}_moderate") is not None

    @pytest.mark.parametrize(
        "compensation,expected",
        [
            (49_999, "low"),
            (50_000, "moderate"),
            (99_999, "moderate"),
            (100_000, "high"),
            (199_999, "high"),
            (200_000, "executive"),
        ],
    )
    def test_income_boundaries(self, service, workspace_dir, compensation, expected):
        result = _analyze(service, workspace_dir, [_employee(40, compensation, 0.05)])
        assert _segment(result, f"mid_career_{expected}") is not None


@pytest.mark.fast
class TestParticipantAveraging:
    def test_averages_only_participants(self, service, workspace_dir):
        """Non-participants are counted but excluded from the average.

        The configured rate is conditional on enrolling, so averaging zeros in
        would double-count non-participation.
        """
        result = _analyze(
            service,
            workspace_dir,
            [
                _employee(40, 60_000, 0.06),
                _employee(40, 60_000, 0.10),
                _employee(40, 60_000, 0.0),
                _employee(40, 60_000, 0.0),
            ],
        )
        segment = _segment(result, "mid_career_moderate")
        assert segment.average_deferral_rate == pytest.approx(0.08)
        assert segment.participant_count == 2
        assert segment.employee_count == 4

    def test_segment_without_participants_has_no_suggestion(
        self, service, workspace_dir
    ):
        result = _analyze(service, workspace_dir, [_employee(40, 60_000, 0.0)])
        segment = _segment(result, "mid_career_moderate")
        assert segment.average_deferral_rate is None
        assert segment.participant_count == 0
        assert segment.employee_count == 1

    def test_segments_are_independent(self, service, workspace_dir):
        result = _analyze(
            service,
            workspace_dir,
            [
                _employee(25, 40_000, 0.02),
                _employee(60, 250_000, 0.14),
            ],
        )
        assert _segment(result, "young_low").average_deferral_rate == pytest.approx(
            0.02
        )
        assert _segment(
            result, "senior_executive"
        ).average_deferral_rate == pytest.approx(0.14)

    def test_overall_average_covers_participants_only(self, service, workspace_dir):
        result = _analyze(
            service,
            workspace_dir,
            [
                _employee(25, 40_000, 0.04),
                _employee(60, 250_000, 0.08),
                _employee(40, 60_000, 0.0),
            ],
        )
        assert result.overall_average_deferral_rate == pytest.approx(0.06)
        assert result.total_participants == 2
        assert result.total_employees_analyzed == 3


@pytest.mark.fast
class TestExclusions:
    def test_percent_encoded_deferral_is_excluded(self, service, workspace_dir):
        """A rate above 1.0 is percent-encoded or corrupt, not a 600% deferral."""
        result = _analyze(
            service,
            workspace_dir,
            [_employee(40, 60_000, 0.06), _employee(40, 60_000, 6.0)],
        )
        segment = _segment(result, "mid_career_moderate")
        assert segment.average_deferral_rate == pytest.approx(0.06)
        assert segment.employee_count == 1
        assert result.excluded_count == 1

    def test_missing_values_are_excluded(self, service, workspace_dir):
        result = _analyze(
            service,
            workspace_dir,
            [
                _employee(40, 60_000, 0.06),
                _employee(40, 60_000, 0.06, employee_birth_date=""),
                _employee(40, 60_000, 0.06, employee_gross_compensation=""),
                _employee(40, 60_000, 0.06, employee_deferral_rate=""),
            ],
        )
        assert result.total_employees_analyzed == 1
        assert result.excluded_count == 3

    def test_inactive_employees_are_excluded(self, service, workspace_dir):
        result = _analyze(
            service,
            workspace_dir,
            [
                _employee(40, 60_000, 0.06, active="Active"),
                _employee(40, 60_000, 0.20, active="Terminated"),
            ],
        )
        assert result.total_employees_analyzed == 1
        assert _segment(
            result, "mid_career_moderate"
        ).average_deferral_rate == pytest.approx(0.06)


@pytest.mark.fast
class TestConfidenceAndMetadata:
    def test_low_confidence_flagged_below_threshold(self, service, workspace_dir):
        result = _analyze(service, workspace_dir, [_employee(40, 60_000, 0.06)])
        segment = _segment(result, "mid_career_moderate")
        assert segment.low_confidence is True
        assert result.low_confidence_threshold == LOW_CONFIDENCE_THRESHOLD
        assert "mid_career_moderate" in result.message

    def test_sufficient_participants_not_flagged(self, service, workspace_dir):
        rows = [_employee(40, 60_000, 0.06) for _ in range(LOW_CONFIDENCE_THRESHOLD)]
        result = _analyze(service, workspace_dir, rows)
        assert _segment(result, "mid_career_moderate").low_confidence is False
        assert result.message is None

    def test_provided_as_of_date_is_reported(self, service, workspace_dir):
        result = _analyze(service, workspace_dir, [_employee(40, 60_000, 0.06)])
        assert result.as_of_date == AS_OF
        assert result.as_of_date_source == "provided"

    def test_as_of_date_inferred_from_census(self, service, workspace_dir):
        result = _analyze(
            service,
            workspace_dir,
            [_employee(40, 60_000, 0.06, employee_hire_date="2023-04-01")],
            as_of=None,
        )
        assert result.as_of_date == date(2023, 12, 31)
        assert result.as_of_date_source == "inferred"

    def test_empty_census_reports_no_usable_employees(self, service, workspace_dir):
        result = _analyze(
            service,
            workspace_dir,
            [_employee(40, 60_000, 0.06, employee_birth_date="")],
        )
        assert result.segments == []
        assert result.total_employees_analyzed == 0
        assert "No employees with usable" in result.message


@pytest.mark.fast
class TestRequiredColumns:
    @pytest.mark.parametrize(
        "missing,label",
        [
            ("employee_birth_date", "birth date"),
            ("employee_gross_compensation", "compensation"),
            ("employee_deferral_rate", "deferral rate"),
        ],
    )
    def test_missing_required_column_raises(
        self, service, workspace_dir, missing, label
    ):
        row = _employee(40, 60_000, 0.06)
        del row[missing]
        _write_csv(workspace_dir / "census.csv", [row])
        with pytest.raises(ValueError, match=f"No {label} column found"):
            service.analyze_deferral_segments("test-ws", "census.csv", as_of_date=AS_OF)

    def test_missing_file_raises(self, service):
        with pytest.raises(ValueError, match="File not found"):
            service.analyze_deferral_segments("test-ws", "nope.csv", as_of_date=AS_OF)


@pytest.mark.fast
class TestEndpoint:
    """The HTTP contract the Studio Match Census button depends on."""

    def _client(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from planalign_api import config as api_config
        from planalign_api.main import app

        workspaces_root = tmp_path / "workspaces"
        workspaces_root.mkdir()
        (workspaces_root / "test-ws").mkdir()
        monkeypatch.setattr(api_config.settings, "workspaces_root", workspaces_root)
        return TestClient(app), workspaces_root / "test-ws"

    def test_returns_segment_averages(self, tmp_path, monkeypatch):
        client, workspace_dir = self._client(tmp_path, monkeypatch)
        _write_csv(
            workspace_dir / "census.csv",
            [
                _employee(25, 40_000, 0.04, employee_id="E1"),
                _employee(25, 40_000, 0.06, employee_id="E2"),
                _employee(60, 250_000, 0.12, employee_id="E3"),
            ],
        )

        response = client.post(
            "/api/workspaces/test-ws/analyze-deferral-segments",
            json={"file_path": "census.csv", "as_of_date": AS_OF.isoformat()},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["as_of_date"] == AS_OF.isoformat()
        assert body["total_participants"] == 3
        segments = {s["segment"]: s for s in body["segments"]}
        assert segments["young_low"]["average_deferral_rate"] == pytest.approx(0.05)
        assert segments["senior_executive"]["average_deferral_rate"] == pytest.approx(
            0.12
        )

    def test_returns_400_for_missing_file(self, tmp_path, monkeypatch):
        client, _ = self._client(tmp_path, monkeypatch)
        response = client.post(
            "/api/workspaces/test-ws/analyze-deferral-segments",
            json={"file_path": "nonexistent.csv"},
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_returns_400_for_census_missing_required_column(
        self, tmp_path, monkeypatch
    ):
        client, workspace_dir = self._client(tmp_path, monkeypatch)
        row = _employee(40, 60_000, 0.06)
        del row["employee_deferral_rate"]
        _write_csv(workspace_dir / "census.csv", [row])

        response = client.post(
            "/api/workspaces/test-ws/analyze-deferral-segments",
            json={"file_path": "census.csv", "as_of_date": AS_OF.isoformat()},
        )
        assert response.status_code == 400
        assert "deferral rate column" in response.json()["detail"]
