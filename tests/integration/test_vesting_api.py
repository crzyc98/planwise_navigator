"""Integration tests for vesting API endpoints (T022, T042)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client for API tests."""
    from planalign_api.main import app
    return TestClient(app)


class TestVestingSchedulesEndpoint:
    """Tests for GET /api/vesting/schedules endpoint."""

    def test_list_schedules_returns_all_schedules(self, client):
        """GET /api/vesting/schedules returns all 8 schedule types."""
        response = client.get("/api/vesting/schedules")
        assert response.status_code == 200
        data = response.json()
        assert "schedules" in data
        assert len(data["schedules"]) == 8

    def test_schedule_has_required_fields(self, client):
        """Each schedule has schedule_type, name, description, percentages."""
        response = client.get("/api/vesting/schedules")
        assert response.status_code == 200
        schedules = response.json()["schedules"]

        for schedule in schedules:
            assert "schedule_type" in schedule
            assert "name" in schedule
            assert "description" in schedule
            assert "percentages" in schedule

    def test_schedule_types_are_valid(self, client):
        """All returned schedule types are valid enum values."""
        response = client.get("/api/vesting/schedules")
        schedules = response.json()["schedules"]

        valid_types = {
            "immediate", "cliff_2_year", "cliff_3_year", "cliff_4_year",
            "qaca_2_year", "graded_3_year", "graded_4_year", "graded_5_year"
        }
        returned_types = {s["schedule_type"] for s in schedules}
        assert returned_types == valid_types


class TestVestingAnalysisEndpoint:
    """Tests for POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting."""

    @pytest.fixture
    def valid_request_body(self):
        """Valid vesting analysis request body."""
        return {
            "current_schedule": {
                "schedule_type": "graded_5_year",
                "name": "5-Year Graded"
            },
            "proposed_schedule": {
                "schedule_type": "cliff_3_year",
                "name": "3-Year Cliff"
            }
        }

    def test_invalid_workspace_returns_404(self, client, valid_request_body):
        """Non-existent workspace returns 404."""
        response = client.post(
            "/api/workspaces/nonexistent_ws/scenarios/baseline/analytics/vesting",
            json=valid_request_body
        )
        # Should return 404 for non-existent workspace
        assert response.status_code in [404, 422]

    def test_invalid_schedule_type_returns_422(self, client):
        """Invalid schedule type returns validation error."""
        invalid_body = {
            "current_schedule": {
                "schedule_type": "invalid_schedule",  # Not a valid type
                "name": "Invalid"
            },
            "proposed_schedule": {
                "schedule_type": "cliff_3_year",
                "name": "3-Year Cliff"
            }
        }
        response = client.post(
            "/api/workspaces/test_ws/scenarios/baseline/analytics/vesting",
            json=invalid_body
        )
        assert response.status_code == 422  # Validation error

    def test_hours_threshold_validation(self, client):
        """Hours threshold must be 0-2080."""
        invalid_body = {
            "current_schedule": {
                "schedule_type": "graded_5_year",
                "name": "5-Year Graded",
                "require_hours_credit": True,
                "hours_threshold": 5000  # Invalid: > 2080
            },
            "proposed_schedule": {
                "schedule_type": "cliff_3_year",
                "name": "3-Year Cliff"
            }
        }
        response = client.post(
            "/api/workspaces/test_ws/scenarios/baseline/analytics/vesting",
            json=invalid_body
        )
        assert response.status_code == 422

    def test_simulation_year_validation(self, client):
        """Simulation year must be 2020-2050 if provided."""
        invalid_body = {
            "current_schedule": {
                "schedule_type": "graded_5_year",
                "name": "5-Year Graded"
            },
            "proposed_schedule": {
                "schedule_type": "cliff_3_year",
                "name": "3-Year Cliff"
            },
            "simulation_year": 1990  # Invalid: < 2020
        }
        response = client.post(
            "/api/workspaces/test_ws/scenarios/baseline/analytics/vesting",
            json=invalid_body
        )
        assert response.status_code == 422


class TestVestingAnalysisResponseStructure:
    """Tests for vesting analysis response structure."""

    def test_response_has_required_fields(self):
        """Response should have scenario_id, scenario_name, summary, by_tenure_band, employee_details."""
        # This test validates the response model structure
        from planalign_api.models.vesting import (
            VestingAnalysisResponse,
            VestingAnalysisSummary,
            VestingScheduleConfig,
            VestingScheduleType,
        )
        from decimal import Decimal

        # Create a minimal valid response
        response = VestingAnalysisResponse(
            scenario_id="baseline",
            scenario_name="Baseline Scenario",
            current_schedule=VestingScheduleConfig(
                schedule_type=VestingScheduleType.GRADED_5_YEAR,
                name="5-Year Graded"
            ),
            proposed_schedule=VestingScheduleConfig(
                schedule_type=VestingScheduleType.CLIFF_3_YEAR,
                name="3-Year Cliff"
            ),
            summary=VestingAnalysisSummary(
                analysis_year=2027,
                terminated_employee_count=0,
                total_employer_contributions=Decimal("0"),
                current_total_vested=Decimal("0"),
                current_total_forfeited=Decimal("0"),
                proposed_total_vested=Decimal("0"),
                proposed_total_forfeited=Decimal("0"),
                forfeiture_variance=Decimal("0"),
                forfeiture_variance_pct=Decimal("0")
            ),
            by_tenure_band=[],
            employee_details=[]
        )

        assert response.scenario_id == "baseline"
        assert response.summary.analysis_year == 2027
        assert response.by_tenure_band == []
        assert response.employee_details == []
