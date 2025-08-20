#!/usr/bin/env python3
"""
Unit tests for the Eligibility Engine (Epic E022: Story S022-01).

Tests the core eligibility determination logic for DC plan participation
based on days of service since hire date.
"""

import os
import tempfile
from datetime import date, datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest
# Import the eligibility engine
from orchestrator_mvp.core.eligibility_engine import (
    EligibilityEngine, process_eligibility_for_year,
    validate_eligibility_engine)


class TestEligibilityEngine:
    """Test suite for EligibilityEngine class."""

    def test_initialization_with_valid_config(self):
        """Test EligibilityEngine initializes correctly with valid configuration."""
        config = {"eligibility": {"waiting_period_days": 365}}

        engine = EligibilityEngine(config)
        assert engine.waiting_period_days == 365
        assert engine.config == config

    def test_initialization_with_default_config(self):
        """Test EligibilityEngine uses default waiting period when not specified."""
        config = {}

        engine = EligibilityEngine(config)
        assert engine.waiting_period_days == 365  # Default

    def test_initialization_with_zero_waiting_period(self):
        """Test EligibilityEngine handles immediate eligibility (0 days)."""
        config = {"eligibility": {"waiting_period_days": 0}}

        engine = EligibilityEngine(config)
        assert engine.waiting_period_days == 0

    def test_initialization_invalid_waiting_period(self):
        """Test EligibilityEngine raises error for invalid waiting period."""
        config = {"eligibility": {"waiting_period_days": -1}}

        with pytest.raises(
            ValueError, match="waiting_period_days must be non-negative integer"
        ):
            EligibilityEngine(config)

    def test_initialization_non_integer_waiting_period(self):
        """Test EligibilityEngine raises error for non-integer waiting period."""
        config = {"eligibility": {"waiting_period_days": "invalid"}}

        with pytest.raises(
            ValueError, match="waiting_period_days must be non-negative integer"
        ):
            EligibilityEngine(config)

    @patch("orchestrator_mvp.core.eligibility_engine.get_connection")
    def test_determine_eligibility_basic_logic(self, mock_get_connection):
        """Test basic eligibility determination logic."""
        # Mock database connection and query result
        mock_conn = Mock()
        mock_get_connection.return_value = mock_conn

        # Mock DataFrame with test data
        test_data = pd.DataFrame(
            [
                {
                    "employee_id": "EMP001",
                    "employee_hire_date": date(2024, 1, 1),
                    "employment_status": "active",
                    "days_since_hire": 365,
                    "is_eligible": True,
                    "eligibility_reason": "eligible_service_met",
                },
                {
                    "employee_id": "EMP002",
                    "employee_hire_date": date(2024, 6, 1),
                    "employment_status": "active",
                    "days_since_hire": 180,
                    "is_eligible": False,
                    "eligibility_reason": "pending_service_requirement",
                },
            ]
        )

        mock_conn.execute.return_value.df.return_value = test_data

        config = {"eligibility": {"waiting_period_days": 365}}
        engine = EligibilityEngine(config)

        result = engine.determine_eligibility(2025)

        # Verify database query was called
        mock_conn.execute.assert_called_once()

        # Verify results
        assert len(result) == 2
        assert result.iloc[0]["employee_id"] == "EMP001"
        assert result.iloc[0]["is_eligible"] == True
        assert result.iloc[1]["employee_id"] == "EMP002"
        assert result.iloc[1]["is_eligible"] == False

    @patch("orchestrator_mvp.core.eligibility_engine.get_connection")
    def test_generate_eligibility_events_no_newly_eligible(self, mock_get_connection):
        """Test eligibility event generation with no newly eligible employees."""
        mock_conn = Mock()
        mock_get_connection.return_value = mock_conn

        # Mock empty DataFrame (no newly eligible employees)
        empty_data = pd.DataFrame(
            columns=[
                "employee_id",
                "employee_hire_date",
                "days_since_hire",
                "was_previously_eligible",
            ]
        )

        mock_conn.execute.return_value.df.return_value = empty_data

        config = {"eligibility": {"waiting_period_days": 365}}
        engine = EligibilityEngine(config)

        events = engine.generate_eligibility_events(2025)

        assert events == []

    @patch("orchestrator_mvp.core.eligibility_engine.get_connection")
    def test_generate_eligibility_events_with_newly_eligible(self, mock_get_connection):
        """Test eligibility event generation with newly eligible employees."""
        mock_conn = Mock()
        mock_get_connection.return_value = mock_conn

        # Mock DataFrame with newly eligible employees
        test_data = pd.DataFrame(
            [
                {
                    "employee_id": "EMP001",
                    "employee_hire_date": date(2024, 1, 1),
                    "days_since_hire": 365,
                    "was_previously_eligible": False,
                },
                {
                    "employee_id": "EMP002",
                    "employee_hire_date": date(2024, 2, 1),
                    "days_since_hire": 334,
                    "was_previously_eligible": False,
                },
            ]
        )

        mock_conn.execute.return_value.df.return_value = test_data

        config = {"eligibility": {"waiting_period_days": 365}}
        engine = EligibilityEngine(config)

        events = engine.generate_eligibility_events(2025)

        # Verify events were generated
        assert len(events) == 2

        # Verify event structure
        event = events[0]
        assert event["employee_id"] == "EMP001"
        assert event["event_type"] == "eligibility"
        assert event["simulation_year"] == 2025
        assert event["effective_date"] == date(2025, 1, 1)
        assert event["event_details"] == "eligible_after_365_days"
        assert event["event_category"] == "eligibility_determination"
        assert event["event_sequence"] == 6
        assert event["event_probability"] == 1.0
        assert event["parameter_source"] == "eligibility_engine"
        assert event["data_quality_flag"] == "VALID"

        # Verify compensation fields are None (not applicable)
        assert event["compensation_amount"] is None
        assert event["previous_compensation"] is None

    @patch("orchestrator_mvp.core.eligibility_engine.get_connection")
    def test_get_eligible_employees(self, mock_get_connection):
        """Test getting list of eligible employee IDs."""
        mock_conn = Mock()
        mock_get_connection.return_value = mock_conn

        # Mock DataFrame with eligibility data
        test_data = pd.DataFrame(
            [
                {"employee_id": "EMP001", "is_eligible": True},
                {"employee_id": "EMP002", "is_eligible": False},
                {"employee_id": "EMP003", "is_eligible": True},
            ]
        )

        mock_conn.execute.return_value.df.return_value = test_data

        config = {"eligibility": {"waiting_period_days": 365}}
        engine = EligibilityEngine(config)

        eligible_employees = engine.get_eligible_employees(2025)

        assert eligible_employees == ["EMP001", "EMP003"]

    def test_validate_configuration_valid(self):
        """Test configuration validation with valid settings."""
        config = {"eligibility": {"waiting_period_days": 365}}
        engine = EligibilityEngine(config)

        result = engine.validate_configuration()

        assert result["valid"] == True
        assert result["errors"] == []
        assert result["configuration_summary"]["waiting_period_days"] == 365
        assert result["configuration_summary"]["eligibility_type"] == "days_since_hire"
        assert result["configuration_summary"]["immediate_eligibility"] == False

    def test_validate_configuration_immediate_eligibility(self):
        """Test configuration validation with immediate eligibility."""
        config = {"eligibility": {"waiting_period_days": 0}}
        engine = EligibilityEngine(config)

        result = engine.validate_configuration()

        assert result["valid"] == True
        assert len(result["warnings"]) == 1
        assert "Immediate eligibility" in result["warnings"][0]
        assert result["configuration_summary"]["immediate_eligibility"] == True

    def test_validate_configuration_long_waiting_period(self):
        """Test configuration validation with long waiting period."""
        config = {"eligibility": {"waiting_period_days": 1200}}  # 3.3 years
        engine = EligibilityEngine(config)

        result = engine.validate_configuration()

        assert result["valid"] == True
        assert len(result["warnings"]) == 1
        assert "Long waiting period" in result["warnings"][0]


class TestProcessEligibilityForYear:
    """Test suite for process_eligibility_for_year convenience function."""

    @patch("orchestrator_mvp.core.eligibility_engine.EligibilityEngine")
    def test_process_eligibility_with_config(self, mock_engine_class):
        """Test process_eligibility_for_year with provided configuration."""
        # Mock EligibilityEngine
        mock_engine = Mock()
        mock_engine.generate_eligibility_events.return_value = [
            {"employee_id": "EMP001", "event_type": "eligibility"}
        ]
        mock_engine_class.return_value = mock_engine

        config = {"eligibility": {"waiting_period_days": 180}}

        events = process_eligibility_for_year(2025, config)

        # Verify engine was created with config
        mock_engine_class.assert_called_once_with(config)

        # Verify events were generated
        mock_engine.generate_eligibility_events.assert_called_once_with(2025)
        assert len(events) == 1

    @patch("orchestrator_mvp.core.eligibility_engine.EligibilityEngine")
    def test_process_eligibility_without_config(self, mock_engine_class):
        """Test process_eligibility_for_year with default configuration."""
        # Mock EligibilityEngine
        mock_engine = Mock()
        mock_engine.generate_eligibility_events.return_value = []
        mock_engine_class.return_value = mock_engine

        events = process_eligibility_for_year(2025)

        # Verify engine was created with default config
        expected_config = {"eligibility": {"waiting_period_days": 365}}
        mock_engine_class.assert_called_once_with(expected_config)

        # Verify events were generated
        mock_engine.generate_eligibility_events.assert_called_once_with(2025)
        assert events == []


class TestValidateEligibilityEngine:
    """Test suite for validate_eligibility_engine function."""

    def test_validate_eligibility_engine_valid_config(self):
        """Test validation with valid configuration."""
        config = {"eligibility": {"waiting_period_days": 365}}

        result = validate_eligibility_engine(config)

        assert result["valid"] == True
        assert result["errors"] == []

    def test_validate_eligibility_engine_invalid_config(self):
        """Test validation with invalid configuration."""
        config = {"eligibility": {"waiting_period_days": -1}}

        result = validate_eligibility_engine(config)

        assert result["valid"] == False
        assert len(result["errors"]) == 1
        assert "Configuration error" in result["errors"][0]


class TestEligibilityEnginePerformance:
    """Test suite for eligibility engine performance characteristics."""

    @patch("orchestrator_mvp.core.eligibility_engine.get_connection")
    def test_performance_with_large_dataset(self, mock_get_connection):
        """Test eligibility engine performs well with large datasets."""
        mock_conn = Mock()
        mock_get_connection.return_value = mock_conn

        # Simulate large dataset (10K employees)
        large_dataset = pd.DataFrame(
            {
                "employee_id": [f"EMP{i:06d}" for i in range(10000)],
                "employee_hire_date": [date(2024, 1, 1)] * 10000,
                "days_since_hire": [365] * 10000,
                "was_previously_eligible": [False] * 10000,
            }
        )

        mock_conn.execute.return_value.df.return_value = large_dataset

        config = {"eligibility": {"waiting_period_days": 365}}
        engine = EligibilityEngine(config)

        import time

        start_time = time.time()
        events = engine.generate_eligibility_events(2025)
        end_time = time.time()

        # Performance target: <5 seconds for 10K employees
        processing_time = end_time - start_time
        assert (
            processing_time < 5.0
        ), f"Processing took {processing_time:.2f} seconds, expected <5 seconds"

        # Verify all events were generated
        assert len(events) == 10000

    @patch("orchestrator_mvp.core.eligibility_engine.get_connection")
    def test_memory_efficiency(self, mock_get_connection):
        """Test eligibility engine memory efficiency."""
        mock_conn = Mock()
        mock_get_connection.return_value = mock_conn

        # Mock moderate dataset
        test_data = pd.DataFrame(
            [
                {
                    "employee_id": f"EMP{i:04d}",
                    "employee_hire_date": date(2024, 1, 1),
                    "days_since_hire": 365,
                    "was_previously_eligible": False,
                }
                for i in range(1000)
            ]
        )

        mock_conn.execute.return_value.df.return_value = test_data

        config = {"eligibility": {"waiting_period_days": 365}}
        engine = EligibilityEngine(config)

        # Test that we can generate events without memory issues
        events = engine.generate_eligibility_events(2025)

        # Verify expected number of events
        assert len(events) == 1000

        # Verify memory usage is reasonable (events should be lightweight)
        import sys

        event_size = sys.getsizeof(events[0])
        total_size = sys.getsizeof(events) + len(events) * event_size

        # Should be less than 1MB for 1000 events
        assert (
            total_size < 1024 * 1024
        ), f"Event storage uses {total_size} bytes, expected <1MB"


@pytest.fixture
def sample_config():
    """Fixture providing sample eligibility configuration."""
    return {
        "eligibility": {"waiting_period_days": 365},
        "start_year": 2025,
        "end_year": 2029,
        "random_seed": 42,
    }


@pytest.fixture
def sample_employee_data():
    """Fixture providing sample employee data for testing."""
    return pd.DataFrame(
        [
            {
                "employee_id": "EMP001",
                "employee_hire_date": date(2024, 1, 1),
                "employment_status": "active",
                "days_since_hire": 365,
                "is_eligible": True,
                "eligibility_reason": "eligible_service_met",
            },
            {
                "employee_id": "EMP002",
                "employee_hire_date": date(2024, 6, 1),
                "employment_status": "active",
                "days_since_hire": 180,
                "is_eligible": False,
                "eligibility_reason": "pending_service_requirement",
            },
            {
                "employee_id": "EMP003",
                "employee_hire_date": date(2023, 1, 1),
                "employment_status": "active",
                "days_since_hire": 730,
                "is_eligible": True,
                "eligibility_reason": "eligible_service_met",
            },
        ]
    )
