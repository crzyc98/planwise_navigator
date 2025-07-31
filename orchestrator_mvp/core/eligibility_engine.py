#!/usr/bin/env python3
"""
Eligibility Engine for DC Plan Participation (Epic E022: Story S022-01)

A simple, configurable eligibility determination engine that evaluates employee
eligibility for DC plan participation based on days of service since hire date.
This MVP focuses on the most common eligibility pattern: waiting period after hire.

Features:
- Days-based eligibility calculation using SQL for performance
- Configurable waiting period (0 = immediate, 365 = 1 year wait)
- ELIGIBILITY event generation for newly eligible employees
- Integration with existing event sourcing architecture
- Performance target: <30 seconds for 100K employees

Usage:
    # Create engine with configuration
    config = load_config()
    engine = EligibilityEngine(config)

    # Generate eligibility events for a simulation year
    events = engine.generate_eligibility_events(2025)

    # Store events using existing infrastructure
    store_events_in_database(events, "fct_yearly_events")

Integration:
    This engine integrates with the MVP orchestrator multi-year framework
    at step 4 (event_generation) via the existing event_emitter.py patterns.
"""

from typing import Dict, Any, List, Optional
from datetime import date, datetime
import pandas as pd
from decimal import Decimal

from .database_manager import get_connection


class EligibilityEngine:
    """
    Simple eligibility determination engine based on days since hire.

    This MVP implementation focuses on the most common eligibility pattern:
    employees become eligible for plan participation after a configurable
    waiting period measured in days since their hire date.

    Configuration:
        waiting_period_days: int - Days to wait after hire (0 = immediate, 365 = 1 year)

    Performance:
        - SQL-based calculation for 100K employees in <30 seconds
        - Minimal memory footprint using streaming operations
        - Year-aware logic for multi-year simulations
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize eligibility engine with configuration.

        Args:
            config: Simulation configuration dictionary with eligibility section
        """
        self.config = config
        # Get waiting period from config with debug logging
        eligibility_config = config.get('eligibility', {})
        self.waiting_period_days = eligibility_config.get('waiting_period_days', 365)

        # Debug logging for troubleshooting
        print(f"🔍 EligibilityEngine DEBUG: Config keys: {list(config.keys())}")
        print(f"🔍 EligibilityEngine DEBUG: Eligibility section: {eligibility_config}")
        print(f"🔍 EligibilityEngine DEBUG: Using waiting_period_days: {self.waiting_period_days}")

        # Validate configuration
        if not isinstance(self.waiting_period_days, int) or self.waiting_period_days < 0:
            raise ValueError(f"waiting_period_days must be non-negative integer, got: {self.waiting_period_days}")

    def determine_eligibility(self, simulation_year: int) -> pd.DataFrame:
        """
        Determine eligibility status for all active employees in a simulation year.

        This method calculates whether each active employee meets the days-based
        service requirement for plan participation eligibility.

        Args:
            simulation_year: Year to evaluate eligibility for

        Returns:
            DataFrame with columns:
                - employee_id: Employee identifier
                - employee_hire_date: Original hire date
                - employment_status: Current employment status
                - days_since_hire: Days from hire to start of simulation year
                - is_eligible: Boolean eligibility status
                - eligibility_reason: Reason for eligibility status

        Performance:
            Uses SQL for vectorized calculation of days since hire.
            Processes 100K employees in <30 seconds.
        """
        conn = get_connection()
        try:
            query = f"""
            SELECT
                employee_id,
                employee_hire_date,
                employment_status,
                DATEDIFF('day', employee_hire_date, '{simulation_year}-01-01'::DATE) as days_since_hire,
                DATEDIFF('day', employee_hire_date, '{simulation_year}-01-01'::DATE) >= {self.waiting_period_days} as is_eligible,
                CASE
                    WHEN DATEDIFF('day', employee_hire_date, '{simulation_year}-01-01'::DATE) >= {self.waiting_period_days}
                    THEN 'eligible_service_met'
                    ELSE 'pending_service_requirement'
                END as eligibility_reason
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
            ORDER BY employee_id
            """

            return conn.execute(query).df()

        finally:
            conn.close()

    def generate_eligibility_events(self, simulation_year: int) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Eligibility events are now generated at hire time.

        This method is kept for backward compatibility but returns an empty list.
        Eligibility events are now created when employees are hired, with the
        eligibility date calculated as hire_date + waiting_period_days.

        Args:
            simulation_year: Year to generate events for (ignored)

        Returns:
            Empty list - eligibility events are generated at hire time
        """
        print(f"📋 Note: Eligibility events are now generated at hire time in event_emitter.py")
        return []

    def get_eligible_employees(self, simulation_year: int) -> List[str]:
        """
        Get list of employee IDs who are eligible for plan participation.

        This is a convenience method for filtering other operations (like
        enrollment or contribution events) to only eligible employees.

        Args:
            simulation_year: Year to check eligibility for

        Returns:
            List of employee IDs who are eligible

        Usage:
            eligible_employees = engine.get_eligible_employees(2025)
            # Use eligible_employees list to filter enrollment events
        """
        eligibility_df = self.determine_eligibility(simulation_year)
        eligible_df = eligibility_df[eligibility_df['is_eligible'] == True]
        return eligible_df['employee_id'].tolist()

    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate eligibility engine configuration and return diagnostics.

        Returns:
            Dictionary with validation results and configuration summary
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'configuration_summary': {
                'waiting_period_days': self.waiting_period_days,
                'eligibility_type': 'days_since_hire',
                'immediate_eligibility': self.waiting_period_days == 0
            }
        }

        # Validate waiting period
        if self.waiting_period_days < 0:
            validation_result['valid'] = False
            validation_result['errors'].append(f"waiting_period_days cannot be negative: {self.waiting_period_days}")

        # Add warnings for edge cases
        if self.waiting_period_days == 0:
            validation_result['warnings'].append("Immediate eligibility (0 days) - all active employees eligible")
        elif self.waiting_period_days > 1095:  # 3 years
            validation_result['warnings'].append(f"Long waiting period ({self.waiting_period_days} days / {self.waiting_period_days/365:.1f} years)")

        return validation_result


def process_eligibility_for_year(
    simulation_year: int,
    config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    DEPRECATED: Eligibility events are now generated at hire time.

    This function is kept for backward compatibility but returns an empty list.
    Eligibility events are now created when employees are hired in the
    event_emitter.generate_hiring_events() function.

    Args:
        simulation_year: Year for simulation (ignored)
        config: Configuration dictionary (ignored)

    Returns:
        Empty list - eligibility events are generated at hire time
    """
    return []


def validate_eligibility_engine(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate eligibility engine configuration without generating events.

    Args:
        config: Configuration to validate

    Returns:
        Validation results dictionary
    """
    try:
        engine = EligibilityEngine(config)
        return engine.validate_configuration()
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Configuration error: {str(e)}"],
            'warnings': [],
            'configuration_summary': {}
        }
