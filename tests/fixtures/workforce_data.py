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
            "hire_date": date(2020, 1, 1) + timedelta(days=i*10),
            "base_salary": 50000 + (i * 500),
            "job_band": f"L{(i % 5) + 1}",
            "department": ["Engineering", "Sales", "Operations"][i % 3],
            "is_active": True
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
            "event_date": date(2025, 1, 1) + timedelta(days=i*7),
            "simulation_year": 2025,
            "scenario_id": "baseline",
            "plan_design_id": "standard"
        }
        for i in range(50)
    ]
