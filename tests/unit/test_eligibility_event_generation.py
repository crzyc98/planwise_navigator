#!/usr/bin/env python3
"""
Unit tests for eligibility event generation at hire time.

Tests that eligibility events are properly generated when employees are hired,
with correct eligibility dates based on the waiting period configuration.
"""

import json
from datetime import date, timedelta

import pytest
from orchestrator_mvp.core.event_emitter import generate_hiring_events


class TestEligibilityEventGeneration:
    """Test eligibility event generation at hire time."""

    def test_eligibility_event_created_with_hire(self):
        """Test that hiring generates both hire and eligibility events."""
        # Configuration with 365-day waiting period
        config = {"eligibility": {"waiting_period_days": 365}}

        # Generate hiring events
        events = generate_hiring_events(
            num_hires=1, simulation_year=2025, random_seed=42, config=config
        )

        # Should have 2 events: hire and eligibility
        assert len(events) == 2

        # First event should be hire
        hire_event = events[0]
        assert hire_event["event_type"] == "hire"
        assert hire_event["simulation_year"] == 2025

        # Second event should be eligibility
        eligibility_event = events[1]
        assert eligibility_event["event_type"] == "eligibility"
        assert eligibility_event["simulation_year"] == 2025
        assert eligibility_event["employee_id"] == hire_event["employee_id"]

        # Parse event details
        details = json.loads(eligibility_event["event_details"])
        assert details["determination_type"] == "initial"
        assert details["waiting_period_days"] == 365
        assert details["eligibility_status"] == "pending"

        # Check eligibility date is hire date + 365 days
        hire_date = hire_event["effective_date"]
        expected_eligibility_date = (hire_date + timedelta(days=365)).isoformat()
        assert details["eligibility_date"] == expected_eligibility_date

    def test_immediate_eligibility(self):
        """Test immediate eligibility (0 days waiting period)."""
        config = {"eligibility": {"waiting_period_days": 0}}

        events = generate_hiring_events(
            num_hires=1, simulation_year=2025, random_seed=42, config=config
        )

        # Get eligibility event
        eligibility_event = next(e for e in events if e["event_type"] == "eligibility")
        details = json.loads(eligibility_event["event_details"])

        # Should be immediately eligible
        assert details["waiting_period_days"] == 0
        assert details["eligibility_status"] == "immediate"

        # Eligibility date should be same as hire date
        hire_event = next(e for e in events if e["event_type"] == "hire")
        assert details["eligibility_date"] == hire_event["effective_date"].isoformat()

    def test_multiple_hires_generate_eligibility_events(self):
        """Test that multiple hires each get eligibility events."""
        config = {"eligibility": {"waiting_period_days": 90}}

        events = generate_hiring_events(
            num_hires=5, simulation_year=2025, random_seed=42, config=config
        )

        # Should have 10 events: 5 hires + 5 eligibility
        assert len(events) == 10

        # Count event types
        hire_count = sum(1 for e in events if e["event_type"] == "hire")
        eligibility_count = sum(1 for e in events if e["event_type"] == "eligibility")

        assert hire_count == 5
        assert eligibility_count == 5

        # Verify each hire has a corresponding eligibility event
        hire_ids = {e["employee_id"] for e in events if e["event_type"] == "hire"}
        eligibility_ids = {
            e["employee_id"] for e in events if e["event_type"] == "eligibility"
        }
        assert hire_ids == eligibility_ids

    def test_eligibility_date_calculation(self):
        """Test various waiting periods calculate correct eligibility dates."""
        test_cases = [
            (0, "immediate"),  # Immediate eligibility
            (30, "pending"),  # 30 days
            (90, "pending"),  # 90 days
            (180, "pending"),  # 6 months
            (365, "pending"),  # 1 year
            (730, "pending"),  # 2 years
        ]

        for waiting_days, expected_status in test_cases:
            config = {"eligibility": {"waiting_period_days": waiting_days}}

            events = generate_hiring_events(
                num_hires=1, simulation_year=2025, random_seed=42, config=config
            )

            hire_event = next(e for e in events if e["event_type"] == "hire")
            eligibility_event = next(
                e for e in events if e["event_type"] == "eligibility"
            )
            details = json.loads(eligibility_event["event_details"])

            # Check status
            assert details["eligibility_status"] == expected_status

            # Check eligibility date calculation
            hire_date = hire_event["effective_date"]
            expected_date = (hire_date + timedelta(days=waiting_days)).isoformat()
            assert details["eligibility_date"] == expected_date

    def test_no_config_uses_default(self):
        """Test that missing config uses default 365-day waiting period."""
        # No config provided
        events = generate_hiring_events(
            num_hires=1, simulation_year=2025, random_seed=42, config=None
        )

        eligibility_event = next(e for e in events if e["event_type"] == "eligibility")
        details = json.loads(eligibility_event["event_details"])

        # Should use default 365 days
        assert details["waiting_period_days"] == 365
        assert details["eligibility_status"] == "pending"

    def test_eligibility_event_fields(self):
        """Test that eligibility events have all required fields."""
        config = {"eligibility": {"waiting_period_days": 180}}

        events = generate_hiring_events(
            num_hires=1, simulation_year=2025, random_seed=42, config=config
        )

        eligibility_event = next(e for e in events if e["event_type"] == "eligibility")

        # Check all required fields are present
        required_fields = [
            "employee_id",
            "employee_ssn",
            "event_type",
            "simulation_year",
            "effective_date",
            "event_details",
            "compensation_amount",
            "previous_compensation",
            "employee_age",
            "employee_tenure",
            "level_id",
            "age_band",
            "tenure_band",
            "event_probability",
            "event_category",
            "event_sequence",
            "created_at",
            "parameter_scenario_id",
            "parameter_source",
            "data_quality_flag",
        ]

        for field in required_fields:
            assert field in eligibility_event

        # Check specific values
        assert eligibility_event["event_category"] == "eligibility_determination"
        assert eligibility_event["event_sequence"] == 2  # Same as hire events
        assert eligibility_event["event_probability"] == 1.0
        assert eligibility_event["data_quality_flag"] == "VALID"

        # Check event_details is valid JSON
        details = json.loads(eligibility_event["event_details"])
        assert "determination_type" in details
        assert "eligibility_date" in details
        assert "waiting_period_days" in details
        assert "eligibility_status" in details


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
