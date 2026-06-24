"""Tests for opt-out rate analysis from census data."""

import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from planalign_api.models.opt_out import (
    OptOutRateAnalysisResult,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write a list of dicts as a CSV file."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _hire_date(years_ago: float, anchor: date | None = None) -> str:
    """Return an ISO date string for a hire date N years in the past from anchor."""
    if anchor is None:
        anchor = date(2024, 6, 1)  # fixed anchor keeps tests deterministic
    return (anchor - timedelta(days=int(years_ago * 365))).isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def service(workspaces_root: Path):
    from planalign_api.services.opt_out_service import OptOutAnalysisService

    return OptOutAnalysisService(workspaces_root)


# ===========================================================================
# Phase 3 Tests (US1) — write BEFORE service implementation
# ===========================================================================


@pytest.mark.fast
class TestEnrollmentDetection:
    """T006: Enrolled employees are excluded from non-participant count."""

    def test_enrolled_excluded_from_non_participant_count(self, service, workspace_dir):
        """3 enrolled (deferral>0) + 2 non-enrolled (deferral=0) → non_participant_count=2."""
        rows = [
            {"hire_date": _hire_date(1), "deferral_rate": 0.06, "active": "true"},
            {"hire_date": _hire_date(1), "deferral_rate": 0.03, "active": "true"},
            {"hire_date": _hire_date(1), "deferral_rate": 0.10, "active": "true"},
            {"hire_date": _hire_date(1), "deferral_rate": 0.00, "active": "true"},
            {"hire_date": _hire_date(1), "deferral_rate": 0.00, "active": "true"},
        ]
        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=3
        )

        assert result.non_participant_count == 2
        assert result.eligible_count == 5
        assert result.suggested_rate == pytest.approx(0.4, abs=0.001)

    def test_null_deferral_treated_as_non_participant(self, service, workspace_dir):
        """T007: deferral_rate IS NULL counts as non-participant."""
        rows = [
            {"hire_date": _hire_date(1), "deferral_rate": None, "active": "true"},
        ]
        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=3
        )

        assert result.non_participant_count == 1
        assert result.eligible_count == 1
        assert result.suggested_rate == pytest.approx(1.0, abs=0.001)


@pytest.mark.fast
class TestEndpointContract:
    """T008: Integration test for the analyze-opt-out-rate endpoint."""

    def test_analyze_opt_out_rate_endpoint_success(self, service, workspace_dir):
        """Service returns a well-formed OptOutRateAnalysisResult for valid input."""
        rows = [
            {"hire_date": _hire_date(1), "deferral_rate": 0.06, "active": "true"},
            {"hire_date": _hire_date(1), "deferral_rate": 0.00, "active": "true"},
        ]
        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=3
        )

        assert isinstance(result, OptOutRateAnalysisResult)
        assert result.eligible_count == 2
        assert result.non_participant_count == 1
        assert result.suggested_rate == pytest.approx(0.5, abs=0.001)
        assert result.lookback_years == 3
        assert result.hire_date_column_used == "hire_date"
        assert result.source_file == str(csv_path)


# ===========================================================================
# Phase 4 Tests (US2) — lookback filtering
# ===========================================================================


@pytest.mark.fast
class TestLookbackFiltering:
    """T014, T015: Lookback filter and anchor behavior."""

    def test_lookback_filter_excludes_older_employees(self, service, workspace_dir):
        """T014: Employees hired before the lookback cutoff are excluded."""
        anchor = date(2024, 6, 1)
        rows = (
            # 5 employees hired 4 years ago (outside 2-year window)
            [
                {
                    "hire_date": _hire_date(4, anchor),
                    "deferral_rate": 0.00,
                    "active": "true",
                }
            ]
            * 5
            +
            # 3 employees hired 1 year ago (inside 2-year window)
            [
                {
                    "hire_date": _hire_date(1, anchor),
                    "deferral_rate": 0.00,
                    "active": "true",
                }
            ]
            * 3
        )
        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result_2yr = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=2
        )
        result_5yr = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=5
        )

        assert result_2yr.eligible_count == 3
        assert result_5yr.eligible_count == 8

    def test_lookback_anchor_uses_max_hire_date_not_today(self, service, workspace_dir):
        """T015: Lookback anchor is MAX(hire_date) in census, not today."""
        # All employees hired in 2019-2020 — a historical census
        rows = [
            {"hire_date": "2019-01-01", "deferral_rate": 0.00, "active": "true"},
            {"hire_date": "2019-06-15", "deferral_rate": 0.00, "active": "true"},
            {"hire_date": "2020-03-01", "deferral_rate": 0.00, "active": "true"},
        ]
        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        # MAX hire_date = 2020-03-01; lookback 3 yrs → cutoff ≈ 2017-03-01
        # All 3 employees are within 3 years of 2020-03-01 → eligible_count == 3
        result = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=3
        )

        assert result.eligible_count == 3, (
            "Lookback anchor must be MAX(hire_date) in census, not today's date. "
            f"Got eligible_count={result.eligible_count}"
        )


# ===========================================================================
# Phase 5 Tests (US3) — error paths
# ===========================================================================


@pytest.mark.fast
class TestErrorPaths:
    """T018-T021: Missing file, missing columns, endpoint 400 response."""

    def test_missing_file_raises_value_error(self, service, workspace_dir):
        """T018: Non-existent file path raises ValueError with 'not found'."""
        with pytest.raises(ValueError, match="(?i)not found"):
            service.analyze_opt_out_rate(
                "test-ws", str(workspace_dir / "nonexistent.csv"), lookback_years=3
            )

    def test_missing_hire_date_column_raises_value_error(self, service, workspace_dir):
        """T019: CSV with no hire_date column raises ValueError listing expected names."""
        rows = [{"deferral_rate": 0.06, "active": "true"}]
        csv_path = workspace_dir / "no_hire.csv"
        _write_csv(csv_path, rows)

        with pytest.raises(ValueError, match="hire"):
            service.analyze_opt_out_rate("test-ws", str(csv_path), lookback_years=3)

    def test_missing_deferral_column_raises_value_error(self, service, workspace_dir):
        """T020: CSV with hire_date but no deferral column raises ValueError listing expected names."""
        rows = [{"hire_date": _hire_date(1), "active": "true"}]
        csv_path = workspace_dir / "no_deferral.csv"
        _write_csv(csv_path, rows)

        with pytest.raises(ValueError, match="deferral"):
            service.analyze_opt_out_rate("test-ws", str(csv_path), lookback_years=3)

    def test_endpoint_returns_400_for_missing_file(self, tmp_path, monkeypatch):
        """T021: POST endpoint returns HTTP 400 when file does not exist."""
        from fastapi.testclient import TestClient
        from planalign_api.main import app
        from planalign_api import config as api_config

        workspaces_root = tmp_path / "workspaces"
        workspaces_root.mkdir()
        (workspaces_root / "test-ws").mkdir()

        monkeypatch.setattr(api_config.settings, "workspaces_root", workspaces_root)

        client = TestClient(app)
        response = client.post(
            "/api/workspaces/test-ws/analyze-opt-out-rate",
            json={"file_path": str(tmp_path / "nonexistent.csv"), "lookback_years": 3},
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()


# ===========================================================================
# Phase 6 Tests (Polish) — edge cases
# ===========================================================================


@pytest.mark.fast
class TestEdgeCases:
    """T027, T028: Empty window and null hire dates."""

    def test_empty_lookback_window_returns_null_rate_with_message(
        self, service, workspace_dir
    ):
        """T027: When no active employees have valid hire dates, suggested_rate is None with message."""
        # All employees are inactive — the active filter excludes them → eligible_count = 0
        rows = [
            {"hire_date": _hire_date(1), "deferral_rate": 0.00, "active": "false"},
            {"hire_date": _hire_date(2), "deferral_rate": 0.00, "active": "N"},
        ]
        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=3
        )

        assert result.suggested_rate is None
        assert result.eligible_count == 0
        assert result.message is not None and len(result.message) > 0

    def test_null_hire_date_excluded_and_counted(self, service, workspace_dir):
        """T028: Employees with NULL hire_date are excluded and counted in excluded_null_tenure."""
        rows = [
            {"hire_date": _hire_date(1), "deferral_rate": 0.00, "active": "true"},
            {"hire_date": None, "deferral_rate": 0.00, "active": "true"},  # excluded
            {"hire_date": "", "deferral_rate": 0.00, "active": "true"},  # excluded
        ]
        csv_path = workspace_dir / "census.csv"
        _write_csv(csv_path, rows)

        result = service.analyze_opt_out_rate(
            "test-ws", str(csv_path), lookback_years=3
        )

        assert result.eligible_count == 1
        assert result.excluded_null_tenure == 2
