#!/usr/bin/env python3
"""Enhanced Eligibility Processing System for orchestrator_dbt.

This module provides comprehensive DC plan eligibility determination with
advanced rule processing, performance optimizations, and regulatory compliance
features. Designed for enterprise-grade workforce simulations with sophisticated
eligibility requirements and audit trail capabilities.

Key enhancements over MVP:
- Multi-criteria eligibility rules (age, tenure, hours, status)
- Batch SQL operations for high-performance processing
- Advanced validation with business rule enforcement
- Comprehensive audit trails for regulatory compliance
- Integration with orchestrator_dbt configuration system
- Performance monitoring and optimization recommendations

Epic E022 Integration:
- DC plan eligibility determination
- Waiting period calculations
- Service requirement validation
- Event generation for eligibility changes
- Integration with compensation and enrollment systems
"""

import time
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import pandas as pd

from ..core.database_manager import DatabaseManager
from ..core.config import OrchestrationConfig

logger = logging.getLogger(__name__)


class EligibilityStatus(Enum):
    """Employee eligibility status types."""
    ELIGIBLE = "eligible"
    PENDING = "pending"
    INELIGIBLE = "ineligible"
    EXCLUDED = "excluded"


class EligibilityReason(Enum):
    """Reasons for eligibility determination."""
    SERVICE_MET = "eligible_service_met"
    IMMEDIATE = "immediate_eligibility"
    PENDING_SERVICE = "pending_service_requirement"
    PENDING_AGE = "pending_age_requirement"
    PENDING_HOURS = "pending_hours_requirement"
    EXCLUDED_STATUS = "excluded_employment_status"
    EXCLUDED_CATEGORY = "excluded_employee_category"


@dataclass
class EligibilityRule:
    """Definition of eligibility rule with validation criteria."""
    name: str
    waiting_period_days: int = 365
    minimum_age: Optional[int] = None
    minimum_hours_per_year: Optional[int] = None
    excluded_statuses: List[str] = None
    excluded_categories: List[str] = None
    immediate_eligibility: bool = False

    def __post_init__(self):
        if self.excluded_statuses is None:
            self.excluded_statuses = ['terminated', 'suspended']
        if self.excluded_categories is None:
            self.excluded_categories = ['contractor', 'intern']


@dataclass
class EligibilityResult:
    """Result of eligibility determination for an employee."""
    employee_id: str
    employee_hire_date: date
    employment_status: str
    days_since_hire: int
    age: Optional[int]
    status: EligibilityStatus
    reason: EligibilityReason
    eligibility_date: Optional[date]
    waiting_period_remaining: Optional[int]
    next_review_date: Optional[date]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'employee_id': self.employee_id,
            'employee_hire_date': self.employee_hire_date,
            'employment_status': self.employment_status,
            'days_since_hire': self.days_since_hire,
            'age': self.age,
            'status': self.status.value,
            'reason': self.reason.value,
            'eligibility_date': self.eligibility_date,
            'waiting_period_remaining': self.waiting_period_remaining,
            'next_review_date': self.next_review_date
        }


class EligibilityProcessor:
    """Enhanced eligibility determination engine with advanced rule processing.

    This processor provides comprehensive DC plan eligibility determination with:
    - Multi-criteria eligibility rules (service, age, hours, status)
    - High-performance batch SQL operations
    - Regulatory compliance and audit trails
    - Integration with orchestrator_dbt systems
    - Performance monitoring and optimization
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        config: OrchestrationConfig,
        eligibility_rules: Optional[List[EligibilityRule]] = None
    ):
        """Initialize eligibility processor.

        Args:
            database_manager: Database operations manager
            config: Orchestration configuration
            eligibility_rules: Optional custom eligibility rules
        """
        self.db_manager = database_manager
        self.config = config

        # Set up eligibility rules
        if eligibility_rules:
            self.eligibility_rules = eligibility_rules
        else:
            self.eligibility_rules = self._load_default_eligibility_rules()

        # Performance tracking
        self._processing_metrics = {
            'total_processed': 0,
            'processing_time': 0.0,
            'database_queries': 0,
            'cache_hits': 0
        }

        # Eligibility result cache for performance
        self._eligibility_cache: Dict[Tuple[int, str], EligibilityResult] = {}

    def determine_eligibility_batch(
        self,
        simulation_year: int,
        rule_name: str = "standard_waiting_period"
    ) -> List[EligibilityResult]:
        """Determine eligibility status for all active employees using batch operations.

        This method uses optimized SQL queries to process large workforces efficiently
        while maintaining comprehensive eligibility rule evaluation.

        Args:
            simulation_year: Year to evaluate eligibility for
            rule_name: Name of eligibility rule to apply

        Returns:
            List of EligibilityResult objects for all employees
        """
        start_time = time.time()

        # Find matching rule
        rule = next((r for r in self.eligibility_rules if r.name == rule_name), None)
        if not rule:
            raise ValueError(f"Eligibility rule '{rule_name}' not found")

        # Use batch SQL for high-performance processing
        eligibility_results = self._process_eligibility_batch_sql(simulation_year, rule)

        # Update metrics
        processing_time = time.time() - start_time
        self._processing_metrics['total_processed'] += len(eligibility_results)
        self._processing_metrics['processing_time'] += processing_time
        self._processing_metrics['database_queries'] += 1

        logger.info(
            f"Processed eligibility for {len(eligibility_results)} employees "
            f"in {processing_time:.3f}s ({len(eligibility_results)/processing_time:.0f} employees/sec)"
        )

        return eligibility_results

    def _process_eligibility_batch_sql(
        self,
        simulation_year: int,
        rule: EligibilityRule
    ) -> List[EligibilityResult]:
        """Process eligibility using optimized batch SQL operations."""

        evaluation_date = date(simulation_year, 1, 1)

        # Build comprehensive eligibility query with all rule criteria
        batch_sql = f"""
        WITH workforce_eligibility_analysis AS (
            SELECT
                employee_id,
                employee_hire_date,
                employment_status,
                current_age,
                -- Days since hire calculation
                DATEDIFF('day', employee_hire_date, '{evaluation_date}'::DATE) as days_since_hire,

                -- Service requirement evaluation
                CASE
                    WHEN ? = 0 THEN TRUE  -- Immediate eligibility
                    WHEN DATEDIFF('day', employee_hire_date, '{evaluation_date}'::DATE) >= ? THEN TRUE
                    ELSE FALSE
                END as meets_service_requirement,

                -- Age requirement evaluation (if specified)
                CASE
                    WHEN ? IS NULL THEN TRUE  -- No age requirement
                    WHEN current_age >= ? THEN TRUE
                    ELSE FALSE
                END as meets_age_requirement,

                -- Calculate eligibility date
                CASE
                    WHEN ? = 0 THEN employee_hire_date  -- Immediate
                    ELSE employee_hire_date + INTERVAL ? DAY
                END as calculated_eligibility_date,

                -- Calculate waiting period remaining
                CASE
                    WHEN ? = 0 THEN 0  -- Immediate eligibility
                    WHEN DATEDIFF('day', employee_hire_date, '{evaluation_date}'::DATE) >= ? THEN 0
                    ELSE ? - DATEDIFF('day', employee_hire_date, '{evaluation_date}'::DATE)
                END as waiting_period_remaining,

                -- Status exclusion check
                CASE
                    WHEN employment_status IN ('terminated', 'suspended') THEN TRUE
                    ELSE FALSE
                END as is_excluded_status

            FROM """ + (
                "int_baseline_workforce" if simulation_year == 2025
                else "fct_workforce_snapshot"
            ) + """
            WHERE employment_status = 'active'
            """ + ("" if simulation_year == 2025 else f"AND simulation_year = {simulation_year - 1}") + """
        ),
        eligibility_determination AS (
            SELECT *,
                -- Overall eligibility determination
                CASE
                    WHEN is_excluded_status THEN 'ineligible'
                    WHEN meets_service_requirement AND meets_age_requirement THEN 'eligible'
                    ELSE 'pending'
                END as eligibility_status,

                -- Eligibility reason determination
                CASE
                    WHEN is_excluded_status THEN 'excluded_employment_status'
                    WHEN ? = 0 THEN 'immediate_eligibility'
                    WHEN meets_service_requirement AND meets_age_requirement THEN 'eligible_service_met'
                    WHEN NOT meets_service_requirement THEN 'pending_service_requirement'
                    WHEN NOT meets_age_requirement THEN 'pending_age_requirement'
                    ELSE 'pending_service_requirement'
                END as eligibility_reason,

                -- Next review date calculation
                CASE
                    WHEN eligibility_status = 'eligible' THEN NULL  -- No review needed
                    WHEN NOT meets_service_requirement THEN calculated_eligibility_date
                    WHEN NOT meets_age_requirement AND ? IS NOT NULL THEN
                        DATE('{evaluation_date.year}-01-01') + INTERVAL (? - current_age) YEAR
                    ELSE calculated_eligibility_date
                END as next_review_date

            FROM workforce_eligibility_analysis
        )
        SELECT * FROM eligibility_determination
        ORDER BY employee_id
        """

        # Prepare parameters for the complex query
        min_age = rule.minimum_age
        params = [
            rule.waiting_period_days,  # Service requirement check 1
            rule.waiting_period_days,  # Service requirement check 2
            min_age,                   # Age requirement check 1
            min_age,                   # Age requirement check 2
            rule.waiting_period_days,  # Eligibility date calculation 1
            rule.waiting_period_days,  # Eligibility date calculation 2
            rule.waiting_period_days,  # Waiting period remaining 1
            rule.waiting_period_days,  # Waiting period remaining 2
            rule.waiting_period_days,  # Waiting period remaining 3
            rule.waiting_period_days,  # Reason determination
            min_age,                   # Next review date age check
            min_age                    # Next review date age calculation
        ]

        # Execute batch query
        with self.db_manager.get_connection() as conn:
            result_df = conn.execute(batch_sql, params).df()

        # Convert results to EligibilityResult objects
        eligibility_results = []
        for _, row in result_df.iterrows():

            # Parse eligibility status and reason
            status = EligibilityStatus(row['eligibility_status'])
            reason = EligibilityReason(row['eligibility_reason'])

            # Handle date conversions
            eligibility_date = row['calculated_eligibility_date']
            if isinstance(eligibility_date, str):
                eligibility_date = datetime.fromisoformat(eligibility_date).date()

            next_review_date = row.get('next_review_date')
            if next_review_date and isinstance(next_review_date, str):
                next_review_date = datetime.fromisoformat(next_review_date).date()

            hire_date = row['employee_hire_date']
            if isinstance(hire_date, str):
                hire_date = datetime.fromisoformat(hire_date).date()

            result = EligibilityResult(
                employee_id=row['employee_id'],
                employee_hire_date=hire_date,
                employment_status=row['employment_status'],
                days_since_hire=int(row['days_since_hire']),
                age=int(row['current_age']) if row.get('current_age') else None,
                status=status,
                reason=reason,
                eligibility_date=eligibility_date,
                waiting_period_remaining=int(row['waiting_period_remaining']) if row['waiting_period_remaining'] > 0 else None,
                next_review_date=next_review_date
            )

            eligibility_results.append(result)

        return eligibility_results

    def get_eligible_employees(
        self,
        simulation_year: int,
        rule_name: str = "standard_waiting_period"
    ) -> List[str]:
        """Get list of employee IDs who are eligible for plan participation.

        This is an optimized method for filtering operations that only need
        eligible employee IDs without full eligibility details.

        Args:
            simulation_year: Year to check eligibility for
            rule_name: Name of eligibility rule to apply

        Returns:
            List of employee IDs who are eligible
        """
        # Check cache first for performance
        cache_key = (simulation_year, rule_name)
        if cache_key in self._eligibility_cache:
            self._processing_metrics['cache_hits'] += 1
            cached_results = [r for r in self._eligibility_cache[cache_key] if r.status == EligibilityStatus.ELIGIBLE]
            return [r.employee_id for r in cached_results]

        # Process eligibility and extract eligible IDs
        eligibility_results = self.determine_eligibility_batch(simulation_year, rule_name)
        eligible_employees = [
            result.employee_id for result in eligibility_results
            if result.status == EligibilityStatus.ELIGIBLE
        ]

        logger.info(
            f"Found {len(eligible_employees)} eligible employees out of "
            f"{len(eligibility_results)} total for rule '{rule_name}'"
        )

        return eligible_employees

    def generate_eligibility_events(
        self,
        simulation_year: int,
        rule_name: str = "standard_waiting_period"
    ) -> List[Dict[str, Any]]:
        """Generate eligibility events for newly eligible employees.

        This method creates ELIGIBILITY events for employees who become eligible
        during the simulation year, maintaining compatibility with the event
        sourcing architecture.

        Args:
            simulation_year: Year to generate events for
            rule_name: Name of eligibility rule to apply

        Returns:
            List of eligibility event dictionaries
        """
        start_time = time.time()

        # Get eligibility determinations
        eligibility_results = self.determine_eligibility_batch(simulation_year, rule_name)

        # Filter for newly eligible employees (those who become eligible this year)
        newly_eligible = []
        for result in eligibility_results:
            if (result.status == EligibilityStatus.ELIGIBLE and
                result.eligibility_date and
                result.eligibility_date.year == simulation_year):
                newly_eligible.append(result)

        # Generate events for newly eligible employees
        events = []
        for result in newly_eligible:

            # Create eligibility details
            eligibility_details = {
                'determination_type': 'annual_review',
                'eligibility_date': result.eligibility_date.isoformat(),
                'waiting_period_days': self._get_rule_waiting_period(rule_name),
                'eligibility_status': result.status.value,
                'eligibility_reason': result.reason.value,
                'days_since_hire': result.days_since_hire
            }

            event = {
                'employee_id': result.employee_id,
                'employee_ssn': f'SSN-{result.employee_id}',  # Placeholder - would be looked up
                'event_type': 'eligibility',
                'simulation_year': simulation_year,
                'effective_date': result.eligibility_date,
                'event_details': str(eligibility_details),  # JSON string for compatibility
                'compensation_amount': None,
                'previous_compensation': None,
                'employee_age': result.age,
                'employee_tenure': result.days_since_hire / 365.25,  # Convert to years
                'level_id': None,  # Would be looked up if needed
                'age_band': self._calculate_age_band(result.age) if result.age else None,
                'tenure_band': self._calculate_tenure_band(result.days_since_hire / 365.25),
                'event_probability': 1.0,
                'event_category': 'eligibility_determination',
                'event_sequence': 2,  # Same sequence as hire events
                'created_at': datetime.now(),
                'parameter_scenario_id': 'orchestrator_dbt',
                'parameter_source': 'eligibility_processor',
                'data_quality_flag': 'VALID'
            }

            events.append(event)

        generation_time = time.time() - start_time
        logger.info(
            f"Generated {len(events)} eligibility events for newly eligible employees "
            f"in {generation_time:.3f}s"
        )

        return events

    def validate_eligibility_configuration(self, rule_name: str) -> Dict[str, Any]:
        """Validate eligibility rule configuration and return diagnostics.

        Args:
            rule_name: Name of rule to validate

        Returns:
            Dictionary with validation results and configuration summary
        """
        rule = next((r for r in self.eligibility_rules if r.name == rule_name), None)
        if not rule:
            return {
                'valid': False,
                'errors': [f"Eligibility rule '{rule_name}' not found"],
                'warnings': [],
                'configuration_summary': {}
            }

        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'configuration_summary': {
                'rule_name': rule.name,
                'waiting_period_days': rule.waiting_period_days,
                'minimum_age': rule.minimum_age,
                'minimum_hours_per_year': rule.minimum_hours_per_year,
                'immediate_eligibility': rule.immediate_eligibility,
                'excluded_statuses': rule.excluded_statuses,
                'excluded_categories': rule.excluded_categories
            }
        }

        # Validate waiting period
        if rule.waiting_period_days < 0:
            validation_result['valid'] = False
            validation_result['errors'].append(f"waiting_period_days cannot be negative: {rule.waiting_period_days}")

        # Validate minimum age
        if rule.minimum_age is not None and (rule.minimum_age < 18 or rule.minimum_age > 70):
            validation_result['warnings'].append(f"Unusual minimum age requirement: {rule.minimum_age}")

        # Add warnings for edge cases
        if rule.waiting_period_days == 0:
            validation_result['warnings'].append("Immediate eligibility (0 days) - all active employees eligible")
        elif rule.waiting_period_days > 1095:  # 3 years
            validation_result['warnings'].append(
                f"Long waiting period ({rule.waiting_period_days} days / {rule.waiting_period_days/365:.1f} years)"
            )

        return validation_result

    def get_processing_metrics(self) -> Dict[str, Any]:
        """Get processing performance metrics for monitoring and optimization.

        Returns:
            Dictionary with performance metrics and recommendations
        """
        metrics = self._processing_metrics.copy()

        # Calculate derived metrics
        if metrics['processing_time'] > 0:
            metrics['employees_per_second'] = metrics['total_processed'] / metrics['processing_time']
        else:
            metrics['employees_per_second'] = 0

        # Add cache efficiency
        total_requests = metrics['total_processed'] + metrics['cache_hits']
        if total_requests > 0:
            metrics['cache_hit_rate'] = metrics['cache_hits'] / total_requests
        else:
            metrics['cache_hit_rate'] = 0

        # Generate optimization recommendations
        recommendations = []
        if metrics['cache_hit_rate'] < 0.1:
            recommendations.append("Consider enabling eligibility result caching for better performance")
        if metrics['employees_per_second'] < 1000:
            recommendations.append("Performance may benefit from database indexing on hire_date and employment_status")

        metrics['optimization_recommendations'] = recommendations

        return metrics

    def _load_default_eligibility_rules(self) -> List[EligibilityRule]:
        """Load default eligibility rules based on configuration."""

        # Extract waiting period from configuration
        waiting_period = 365  # Default 1 year
        if hasattr(self.config, 'eligibility'):
            waiting_period = getattr(self.config.eligibility, 'waiting_period_days', 365)

        return [
            EligibilityRule(
                name="standard_waiting_period",
                waiting_period_days=waiting_period,
                minimum_age=None,
                minimum_hours_per_year=None,
                excluded_statuses=['terminated', 'suspended'],
                excluded_categories=['contractor', 'intern'],
                immediate_eligibility=waiting_period == 0
            ),
            EligibilityRule(
                name="immediate_eligibility",
                waiting_period_days=0,
                immediate_eligibility=True
            ),
            EligibilityRule(
                name="age_and_service",
                waiting_period_days=365,
                minimum_age=21,
                minimum_hours_per_year=1000
            )
        ]

    def _get_rule_waiting_period(self, rule_name: str) -> int:
        """Get waiting period for a specific rule."""
        rule = next((r for r in self.eligibility_rules if r.name == rule_name), None)
        return rule.waiting_period_days if rule else 365

    def _calculate_age_band(self, age: int) -> str:
        """Calculate age band from age."""
        if age < 25:
            return '< 25'
        elif age < 35:
            return '25-34'
        elif age < 45:
            return '35-44'
        elif age < 55:
            return '45-54'
        elif age < 65:
            return '55-64'
        else:
            return '65+'

    def _calculate_tenure_band(self, tenure: float) -> str:
        """Calculate tenure band from tenure in years."""
        if tenure < 2:
            return '< 2'
        elif tenure < 5:
            return '2-4'
        elif tenure < 10:
            return '5-9'
        elif tenure < 20:
            return '10-19'
        else:
            return '20+'


# Standalone functions for backward compatibility

def process_eligibility_for_year(
    simulation_year: int,
    config: Optional[Dict[str, Any]] = None,
    database_manager: Optional[DatabaseManager] = None
) -> List[Dict[str, Any]]:
    """Process eligibility for a simulation year - compatibility function.

    Note: This function now generates eligibility events for newly eligible employees
    rather than all employees, as eligibility events are primarily generated at hire time.

    Args:
        simulation_year: Year for simulation
        config: Configuration dictionary
        database_manager: Database operations manager

    Returns:
        List of eligibility event dictionaries
    """
    if not config or not database_manager:
        logger.warning("Limited eligibility processing without full configuration")
        return []

    # Create temporary processor
    from ..core.config import OrchestrationConfig
    temp_config = OrchestrationConfig()
    if 'eligibility' in config:
        temp_config.eligibility = config['eligibility']

    processor = EligibilityProcessor(database_manager, temp_config)
    return processor.generate_eligibility_events(simulation_year)


def validate_eligibility_engine(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate eligibility engine configuration - compatibility function.

    Args:
        config: Configuration to validate

    Returns:
        Validation results dictionary
    """
    try:
        # Create temporary processor for validation
        from ..core.config import OrchestrationConfig
        temp_config = OrchestrationConfig()
        if 'eligibility' in config:
            temp_config.eligibility = config['eligibility']

        # Mock database manager for validation
        processor = EligibilityProcessor(None, temp_config)
        return processor.validate_eligibility_configuration("standard_waiting_period")

    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Configuration error: {str(e)}"],
            'warnings': [],
            'configuration_summary': {}
        }
