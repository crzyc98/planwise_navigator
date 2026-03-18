"""Termination rate suggestion service.

Calculates realistic termination rate suggestions based on census data,
replacing hardcoded 100% defaults with actual rate calculations.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from ..models.suggestion import TerminationRateSuggestion
from ..models.calculation import TerminationRateCalculation


logger = logging.getLogger(__name__)


class TerminationRateSuggestionService:
    """Service for calculating termination rate suggestions from census data."""

    def __init__(self):
        """Initialize the service."""
        pass

    def calculate_active_employee_count(
        self, census_data: list, scenario_id: str, year: int
    ) -> int:
        """
        Count active employees in census data.

        Args:
            census_data: List of census records
            scenario_id: Scenario identifier
            year: Year for filtering (if applicable)

        Returns:
            Count of employees with employment_status == 'ACTIVE'
        """
        if not census_data:
            return 0

        active_count = sum(
            1 for record in census_data
            if record.get("employment_status") == "ACTIVE"
        )
        return active_count

    def calculate_terminated_employee_count(
        self, census_data: list, scenario_id: str, year: int
    ) -> int:
        """
        Count terminated employees in census data for a specific year.

        Args:
            census_data: List of census records
            scenario_id: Scenario identifier
            year: Calendar year to filter terminations

        Returns:
            Count of employees with employment_status == 'TERMINATED' and
            termination_date in the specified year
        """
        if not census_data:
            return 0

        terminated_count = 0
        for record in census_data:
            if record.get("employment_status") != "TERMINATED":
                continue

            term_date = record.get("termination_date")
            if term_date is None:
                continue

            # Handle both date and string termination dates
            if isinstance(term_date, str):
                try:
                    term_date = date.fromisoformat(term_date)
                except (ValueError, TypeError):
                    continue
            elif not isinstance(term_date, date):
                continue

            # Check if termination occurred in the specified year
            if term_date.year == year:
                terminated_count += 1

        return terminated_count

    def suggest_termination_rate(
        self,
        census_data: list,
        scenario_id: str,
        plan_design_id: str,
        year: int,
        snapshot_date: Optional[date] = None,
    ) -> TerminationRateSuggestion:
        """
        Calculate termination rate suggestion from census data.

        This is the core fix for the bug where termination rates always returned 100%.

        Formula:
            termination_rate = (terminated_count / active_count) * 100

        Args:
            census_data: List of census records
            scenario_id: Scenario identifier
            plan_design_id: Benefit plan identifier
            year: Calendar year for calculation
            snapshot_date: Census snapshot date (defaults to today)

        Returns:
            TerminationRateSuggestion with:
            - suggested_rate: Calculated rate (0-99%), or None if error
            - confidence: HIGH/MEDIUM/LOW based on sample size
            - sample_size: Number of active employees
            - error_message: User-friendly error (if applicable)
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        # Calculate counts (NOT hardcoded 100%)
        active_count = self.calculate_active_employee_count(
            census_data, scenario_id, year
        )
        terminated_count = self.calculate_terminated_employee_count(
            census_data, scenario_id, year
        )

        # Step 1: Denominator validation (FIX FOR BUG)
        if active_count == 0:
            return TerminationRateSuggestion(
                scenario_id=scenario_id,
                plan_design_id=plan_design_id,
                snapshot_date=snapshot_date.isoformat(),
                suggested_rate=None,
                confidence=None,
                sample_size=0,
                error_message="Unable to calculate termination rate: no active employees found in census.",
            )

        # Step 2: Calculate rate using correct formula (NOT 100%)
        rate_decimal = Decimal(terminated_count) / Decimal(active_count)
        rate_percentage = rate_decimal * 100

        # Ensure rate is in valid range (0-99.9%)
        if rate_percentage >= 100:
            logger.warning(
                f"Termination rate >= 100% for {scenario_id}: "
                f"{terminated_count} terminated / {active_count} active"
            )
            # Cap at 99.9% (still indicates high turnover but distinguishes from bug)
            rate_percentage = Decimal("99.9")

        # Step 3: Determine confidence based on sample size
        confidence = self._determine_confidence(active_count)

        # Return valid suggestion (NOT 100%)
        return TerminationRateSuggestion(
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            snapshot_date=snapshot_date.isoformat(),
            suggested_rate=rate_percentage,
            confidence=confidence,
            sample_size=active_count,
            error_message=None,
        )

    def _determine_confidence(self, sample_size: int) -> str:
        """
        Determine confidence level based on sample size.

        Args:
            sample_size: Number of active employees

        Returns:
            'HIGH' (>100), 'MEDIUM' (10-100), or 'LOW' (<10)
        """
        if sample_size > 100:
            return "HIGH"
        elif sample_size >= 10:
            return "MEDIUM"
        else:
            return "LOW"

    def calculate_with_audit(
        self,
        census_data: list,
        scenario_id: str,
        plan_design_id: str,
        year: int,
        snapshot_date: Optional[date] = None,
    ) -> tuple[TerminationRateSuggestion, TerminationRateCalculation]:
        """
        Calculate termination rate with full audit trail.

        Useful for debugging and compliance. Returns both the user-facing
        suggestion and the detailed calculation state.

        Args:
            census_data: List of census records
            scenario_id: Scenario identifier
            plan_design_id: Benefit plan identifier
            year: Calendar year for calculation
            snapshot_date: Census snapshot date

        Returns:
            Tuple of (TerminationRateSuggestion, TerminationRateCalculation)
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        # Get counts
        active_count = self.calculate_active_employee_count(
            census_data, scenario_id, year
        )
        terminated_count = self.calculate_terminated_employee_count(
            census_data, scenario_id, year
        )

        # Get suggestion
        suggestion = self.suggest_termination_rate(
            census_data, scenario_id, plan_design_id, year, snapshot_date
        )

        # Build detailed calculation record
        calculation_status = "SUCCESS"
        error_message = None
        calculated_rate = None

        if active_count == 0:
            calculation_status = "DIVISION_BY_ZERO"
            error_message = "No active employees to use as denominator"
        else:
            calculated_rate = (Decimal(terminated_count) / Decimal(active_count)) * 100
            if calculated_rate >= 100:
                calculated_rate = Decimal("99.9")

        calculation = TerminationRateCalculation(
            calculation_id=uuid4(),
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            snapshot_date=snapshot_date.isoformat(),
            period_year=year,
            total_active_employees=active_count,
            total_terminated_employees=terminated_count,
            calculation_numerator=Decimal(terminated_count),
            calculation_denominator=Decimal(active_count),
            calculated_rate=calculated_rate,
            calculation_status=calculation_status,
            error_message=error_message,
        )

        return suggestion, calculation
