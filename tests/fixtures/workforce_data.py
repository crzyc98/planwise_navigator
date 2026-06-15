"""Test data generators for workforce simulations."""

import pytest
import pandas as pd
from datetime import date, timedelta
from typing import List, Dict


@pytest.fixture
def sample_employees() -> List[Dict]:
    """
    Generate 100 sample employees with realistic data.

    Returns list of employee dictionaries with fields:
    - employee_id: Unique identifier (EMP00000-EMP00099)
    - hire_date: Staggered hire dates
    - base_salary: Realistic salary distribution ($50k-$100k)
    - job_band: Level L1-L5
    - department: Engineering, Sales, Operations
    - is_active: Employment status

    Usage:
        @pytest.mark.fast
        def test_employee_processing(sample_employees):
            assert len(sample_employees) == 100
            assert all('employee_id' in emp for emp in sample_employees)
    """
    return [
        {
            "employee_id": f"EMP{i:05d}",
            "hire_date": date(2020, 1, 1) + timedelta(days=i * 10),
            "base_salary": 50000 + (i * 500),
            "job_band": f"L{(i % 5) + 1}",
            "department": ["Engineering", "Sales", "Operations"][i % 3],
            "is_active": True,
        }
        for i in range(100)
    ]


@pytest.fixture
def baseline_workforce_df(sample_employees) -> pd.DataFrame:
    """
    Baseline workforce as pandas DataFrame.

    Provides DataFrame representation of sample employees
    for data manipulation and analysis testing.

    Usage:
        @pytest.mark.fast
        def test_dataframe_operations(baseline_workforce_df):
            assert len(baseline_workforce_df) == 100
            assert 'employee_id' in baseline_workforce_df.columns
    """
    return pd.DataFrame(sample_employees)


@pytest.fixture
def sample_yearly_events() -> List[Dict]:
    """
    Generate sample hire/termination/promotion events.

    Creates 50 events distributed across event types:
    - hire: New employee events
    - termination: Employee departure events
    - promotion: Level advancement events

    Usage:
        @pytest.mark.fast
        def test_event_generation(sample_yearly_events):
            assert len(sample_yearly_events) == 50
            event_types = {e['event_type'] for e in sample_yearly_events}
            assert event_types == {'hire', 'termination', 'promotion'}
    """
    return [
        {
            "event_id": f"EVT{i:05d}",
            "employee_id": f"EMP{i:05d}",
            "event_type": ["hire", "termination", "promotion"][i % 3],
            "event_date": date(2025, 1, 1) + timedelta(days=i * 7),
            "simulation_year": 2025,
            "scenario_id": "baseline",
            "plan_design_id": "standard",
        }
        for i in range(50)
    ]


@pytest.fixture
def sample_census_data() -> List[Dict]:
    """
    Generate sample census data for termination rate testing.

    Creates 100 active employees with 5 terminated employees (5% turnover).

    Returns list of census records with fields:
    - employee_id: Unique identifier
    - employment_status: ACTIVE or TERMINATED
    - hire_date: Employee start date
    - termination_date: Separation date (null if ACTIVE)
    - annual_salary: Compensation
    - age: Current age
    - tenure_months: Months employed

    Expected rate: 5 terminated / 100 active = 0.05 (5%)

    Usage:
        @pytest.mark.fast
        def test_termination_rate_basic(sample_census_data):
            active = [e for e in sample_census_data if e['employment_status'] == 'ACTIVE']
            terminated = [e for e in sample_census_data if e['employment_status'] == 'TERMINATED']
            assert len(active) == 95
            assert len(terminated) == 5
            rate = len(terminated) / len(active)
            assert abs(rate - 0.05) < 0.01
    """
    today = date.today()
    census_data = []

    # Create 95 active employees
    for i in range(95):
        hire_date = date(2020, 1, 1) + timedelta(days=i * 10)
        census_data.append(
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE",
                "hire_date": hire_date,
                "termination_date": None,
                "annual_salary": 50000 + (i * 500),
                "age": 25 + (i % 40),
                "tenure_months": (today - hire_date).days / 30,
            }
        )

    # Create 5 terminated employees
    for i in range(95, 100):
        hire_date = date(2020, 1, 1) + timedelta(days=i * 10)
        term_date = date(2025, 6, 15) + timedelta(days=(i - 95) * 30)
        census_data.append(
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "TERMINATED",
                "hire_date": hire_date,
                "termination_date": term_date,
                "annual_salary": 50000 + (i * 500),
                "age": 25 + (i % 40),
                "tenure_months": (term_date - hire_date).days / 30,
            }
        )

    return census_data


@pytest.fixture
def edge_case_census_data() -> Dict[str, List[Dict]]:
    """
    Generate edge case census data for robust testing.

    Returns dictionary with scenarios:
    - 'zero_active': No active employees (should error)
    - 'single_employee': 1 active, 0 terminated (expect 0%)
    - 'no_terminations': 100 active, 0 terminated (expect 0%)
    - 'all_terminated': 0 active, 5 terminated (should error)
    - 'missing_fields': Records with null status/dates (should handle gracefully)

    Usage:
        @pytest.mark.fast
        def test_edge_cases(edge_case_census_data):
            zero_active = edge_case_census_data['zero_active']
            assert len(zero_active) == 0

            single = edge_case_census_data['single_employee']
            assert len([e for e in single if e['employment_status'] == 'ACTIVE']) == 1
    """
    today = date.today()

    return {
        "zero_active": [],  # No employees
        "single_employee": [
            {
                "employee_id": "EMP00001",
                "employment_status": "ACTIVE",
                "hire_date": date(2023, 1, 1),
                "termination_date": None,
                "annual_salary": 75000,
                "age": 35,
                "tenure_months": (today - date(2023, 1, 1)).days / 30,
            }
        ],
        "no_terminations": [
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE",
                "hire_date": date(2020, 1, 1) + timedelta(days=i * 10),
                "termination_date": None,
                "annual_salary": 50000 + (i * 500),
                "age": 25 + (i % 40),
                "tenure_months": (
                    today - (date(2020, 1, 1) + timedelta(days=i * 10))
                ).days
                / 30,
            }
            for i in range(100)
        ],
        "all_terminated": [
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "TERMINATED",
                "hire_date": date(2020, 1, 1) + timedelta(days=i * 10),
                "termination_date": date(2024, 12, 31),
                "annual_salary": 50000 + (i * 500),
                "age": 25 + (i % 40),
                "tenure_months": (
                    date(2024, 12, 31) - (date(2020, 1, 1) + timedelta(days=i * 10))
                ).days
                / 30,
            }
            for i in range(5)
        ],
        "mixed_population": [
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE" if i < 50 else "TERMINATED",
                "hire_date": date(2020, 1, 1) + timedelta(days=i * 10),
                "termination_date": None if i < 50 else date(2025, 3, 1),
                "annual_salary": 50000 + (i * 500),
                "age": 25 + (i % 40),
                "tenure_months": (
                    date(2025, 3, 1) - (date(2020, 1, 1) + timedelta(days=i * 10))
                ).days
                / 30
                if i >= 50
                else (today - (date(2020, 1, 1) + timedelta(days=i * 10))).days / 30,
            }
            for i in range(100)
        ],
    }


def assert_valid_termination_rate(response_dict: Dict) -> None:
    """
    Helper function to validate termination rate suggestion response format.

    Checks:
    - suggested_rate is not 100% (the bug we're fixing)
    - If error_message is present, suggested_rate must be null
    - If suggested_rate is present, error_message must be null
    - Confidence level is one of HIGH/MEDIUM/LOW (if present)
    - sample_size is a non-negative integer

    Usage:
        def test_endpoint(client):
            response = client.get("/api/scenarios/test/termination-rate-suggestion")
            assert_valid_termination_rate(response.json())

    Raises:
        AssertionError: If validation fails
    """
    assert isinstance(response_dict, dict), "Response must be a dictionary"

    rate = response_dict.get("suggested_rate")
    error = response_dict.get("error_message")
    confidence = response_dict.get("confidence")
    sample_size = response_dict.get("sample_size", 0)

    # Main bug fix: Never return 100%
    if rate is not None:
        assert rate != 100.0, "BUG: Suggested rate cannot be 100%"
        assert rate != 1.0, "BUG: Suggested rate (as decimal) cannot be 1.0 (100%)"
        assert 0.0 <= rate < 100.0, f"Rate must be 0-99.9%, got {rate}"

    # Error consistency check
    if error is not None:
        assert rate is None, "If error_message is present, suggested_rate must be None"
        assert isinstance(error, str), "error_message must be a string"
        assert len(error) > 0, "error_message cannot be empty"
    else:
        assert rate is not None, "If no error_message, suggested_rate must be present"

    # Confidence checks
    if confidence is not None:
        assert confidence in [
            "HIGH",
            "MEDIUM",
            "LOW",
        ], f"Invalid confidence: {confidence}"

    # Sample size checks
    assert isinstance(sample_size, int), "sample_size must be an integer"
    assert sample_size >= 0, "sample_size cannot be negative"
