"""
Year transition coordination for multi-year simulation orchestration.

Handles the transition between simulation years including state transfer,
data continuity validation, and coordination between year processing cycles.
Implements various strategies for state transfer optimization.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Protocol, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .simulation_state import WorkforceState, StateManager, WorkforceRecord
from .year_processor import YearContext, YearResult, ProcessingMode
from ..core.database_manager import DatabaseManager
from ..core.config import OrchestrationConfig


logger = logging.getLogger(__name__)


class TransitionStrategy(Enum):
    """Strategy for year-to-year state transition."""
    INCREMENTAL = "incremental"      # Transfer only changes
    FULL_STATE = "full_state"        # Transfer complete state
    OPTIMIZED = "optimized"          # Intelligent optimization
    VALIDATION_HEAVY = "validation"  # Extra validation steps


@dataclass
class TransitionContext:
    """Context for year-to-year transition."""
    from_year: int
    to_year: int
    from_state: WorkforceState
    strategy: TransitionStrategy = TransitionStrategy.OPTIMIZED
    validation_enabled: bool = True
    data_integrity_checks: bool = True
    performance_monitoring: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TransitionValidation:
    """Validation results for year transition."""
    passed: bool
    total_checks: int
    failed_checks: int
    warnings: int
    validation_details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings_list: List[str] = field(default_factory=list)
    execution_time: float = 0.0


@dataclass
class StateTransferResult:
    """Result of state transfer operation."""
    success: bool
    records_transferred: int
    records_modified: int
    records_added: int
    records_removed: int
    execution_time: float
    transfer_strategy: TransitionStrategy
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


@dataclass
class TransitionResult:
    """Complete result of year transition."""
    from_year: int
    to_year: int
    success: bool
    total_execution_time: float
    state_transfer_result: Optional[StateTransferResult] = None
    validation_result: Optional[TransitionValidation] = None
    next_year_context: Optional[YearContext] = None
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class StateTransferStrategy(ABC):
    """Abstract strategy for state transfer between years."""

    @abstractmethod
    async def transfer_state(
        self,
        context: TransitionContext,
        state_manager: StateManager
    ) -> StateTransferResult:
        """Transfer state from one year to the next."""
        pass


class IncrementalTransferStrategy(StateTransferStrategy):
    """Transfer only changed records between years."""

    async def transfer_state(
        self,
        context: TransitionContext,
        state_manager: StateManager
    ) -> StateTransferResult:
        """Transfer incremental changes between years."""
        logger.info(f"Starting incremental transfer from {context.from_year} to {context.to_year}")
        start_time = time.time()

        try:
            # Get the current state for the from_year
            from_state = context.from_state

            # Calculate incremental changes
            changes = await self._calculate_incremental_changes(from_state, context)

            # Apply changes to create new year state
            new_state = await self._apply_incremental_changes(from_state, changes, context)

            # Store the new state
            state_manager.store_year_state(context.to_year, new_state)

            execution_time = time.time() - start_time

            logger.info(f"Incremental transfer completed: {changes['modified']} modified, "
                       f"{changes['added']} added, {changes['removed']} removed")

            return StateTransferResult(
                success=True,
                records_transferred=len(from_state.workforce_records),
                records_modified=changes['modified'],
                records_added=changes['added'],
                records_removed=changes['removed'],
                execution_time=execution_time,
                transfer_strategy=TransitionStrategy.INCREMENTAL,
                metadata={
                    "transfer_efficiency": changes['modified'] / len(from_state.workforce_records) if from_state.workforce_records else 0,
                    "change_summary": changes
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Incremental transfer failed: {e}")

            return StateTransferResult(
                success=False,
                records_transferred=0,
                records_modified=0,
                records_added=0,
                records_removed=0,
                execution_time=execution_time,
                transfer_strategy=TransitionStrategy.INCREMENTAL,
                errors=[f"Incremental transfer failed: {str(e)}"]
            )

    async def _calculate_incremental_changes(
        self,
        from_state: WorkforceState,
        context: TransitionContext
    ) -> Dict[str, int]:
        """Calculate what changes need to be applied."""
        # Simulate change calculation
        total_records = len(from_state.workforce_records)

        # Estimate changes based on year progression
        modified = max(1, int(total_records * 0.15))  # 15% of records change
        added = max(1, int(total_records * 0.05))     # 5% new hires
        removed = max(1, int(total_records * 0.03))   # 3% terminations

        return {
            "modified": modified,
            "added": added,
            "removed": removed
        }

    async def _apply_incremental_changes(
        self,
        from_state: WorkforceState,
        changes: Dict[str, int],
        context: TransitionContext
    ) -> WorkforceState:
        """Apply incremental changes to create new state."""
        # Create a copy of the workforce records
        new_records = []

        # Apply changes to existing records
        for i, record in enumerate(from_state.workforce_records):
            new_record = WorkforceRecord(
                employee_id=record.employee_id,
                hire_date=record.hire_date,
                termination_date=record.termination_date,
                job_level=record.job_level,
                salary=record.salary * 1.03 if i < changes['modified'] else record.salary,  # 3% raise for modified
                department=record.department,
                location=record.location,
                age=record.age + 1,  # Age everyone by 1 year
                tenure_years=record.tenure_years + 1.0,  # Increase tenure
                is_active=False if i < changes['removed'] else record.is_active,  # Terminate some
                plan_eligible=record.plan_eligible,
                plan_enrolled=record.plan_enrolled,
                enrollment_date=record.enrollment_date,
                contribution_rate=record.contribution_rate
            )
            new_records.append(new_record)

        # Add new hires
        for i in range(changes['added']):
            hire_record = WorkforceRecord(
                employee_id=f"NEW_{context.to_year}_{i:06d}",
                hire_date=date(context.to_year, 1, 1),
                job_level="L1",
                salary=55000.0,
                department="Engineering",
                location="Boston",
                age=25,
                tenure_years=0.0,
                is_active=True,
                plan_eligible=True,
                plan_enrolled=False  # New hires start not enrolled
            )
            new_records.append(hire_record)

        # Create new workforce state
        new_state = WorkforceState(
            year=context.to_year,
            workforce_records=new_records,
            metadata={
                "transition_strategy": TransitionStrategy.INCREMENTAL.value,
                "changes_applied": changes,
                "source_year": context.from_year
            }
        )

        return new_state


class FullStateTransferStrategy(StateTransferStrategy):
    """Transfer complete state between years."""

    async def transfer_state(
        self,
        context: TransitionContext,
        state_manager: StateManager
    ) -> StateTransferResult:
        """Transfer complete state between years."""
        logger.info(f"Starting full state transfer from {context.from_year} to {context.to_year}")
        start_time = time.time()

        try:
            # Clone the complete state
            from_state = context.from_state
            new_state = await self._clone_and_update_state(from_state, context)

            # Store the new state
            state_manager.store_year_state(context.to_year, new_state)

            execution_time = time.time() - start_time
            records_count = len(from_state.workforce_records)

            logger.info(f"Full state transfer completed: {records_count} records transferred")

            return StateTransferResult(
                success=True,
                records_transferred=records_count,
                records_modified=records_count,  # All records updated
                records_added=0,
                records_removed=0,
                execution_time=execution_time,
                transfer_strategy=TransitionStrategy.FULL_STATE,
                metadata={
                    "transfer_efficiency": 1.0,  # Full transfer
                    "state_size_mb": len(str(new_state)) / (1024 * 1024)
                }
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Full state transfer failed: {e}")

            return StateTransferResult(
                success=False,
                records_transferred=0,
                records_modified=0,
                records_added=0,
                records_removed=0,
                execution_time=execution_time,
                transfer_strategy=TransitionStrategy.FULL_STATE,
                errors=[f"Full state transfer failed: {str(e)}"]
            )

    async def _clone_and_update_state(
        self,
        from_state: WorkforceState,
        context: TransitionContext
    ) -> WorkforceState:
        """Clone state and update for new year."""
        # Create updated records for new year
        updated_records = []

        for record in from_state.workforce_records:
            # Update record for new year
            updated_record = WorkforceRecord(
                employee_id=record.employee_id,
                hire_date=record.hire_date,
                termination_date=record.termination_date,
                job_level=record.job_level,
                salary=record.salary * 1.025,  # 2.5% annual increase
                department=record.department,
                location=record.location,
                age=record.age + 1,
                tenure_years=record.tenure_years + 1.0,
                is_active=record.is_active,
                plan_eligible=record.plan_eligible,
                plan_enrolled=record.plan_enrolled,
                enrollment_date=record.enrollment_date,
                contribution_rate=record.contribution_rate
            )
            updated_records.append(updated_record)

        # Create new state
        new_state = WorkforceState(
            year=context.to_year,
            workforce_records=updated_records,
            metadata={
                "transition_strategy": TransitionStrategy.FULL_STATE.value,
                "source_year": context.from_year,
                "full_state_transfer": True
            }
        )

        return new_state


class OptimizedTransferStrategy(StateTransferStrategy):
    """Optimized transfer strategy with intelligent decision making."""

    def __init__(self):
        """Initialize optimized transfer strategy."""
        self.incremental_strategy = IncrementalTransferStrategy()
        self.full_state_strategy = FullStateTransferStrategy()

    async def transfer_state(
        self,
        context: TransitionContext,
        state_manager: StateManager
    ) -> StateTransferResult:
        """Use optimized transfer strategy based on state analysis."""
        logger.info(f"Starting optimized transfer from {context.from_year} to {context.to_year}")

        # Analyze state to determine best strategy
        strategy = await self._analyze_optimal_strategy(context)

        if strategy == TransitionStrategy.INCREMENTAL:
            logger.debug("Using incremental transfer strategy")
            return await self.incremental_strategy.transfer_state(context, state_manager)
        else:
            logger.debug("Using full state transfer strategy")
            return await self.full_state_strategy.transfer_state(context, state_manager)

    async def _analyze_optimal_strategy(self, context: TransitionContext) -> TransitionStrategy:
        """Analyze state to determine optimal transfer strategy."""
        from_state = context.from_state

        # Decision criteria
        record_count = len(from_state.workforce_records)

        # Use incremental for larger datasets
        if record_count > 10000:
            return TransitionStrategy.INCREMENTAL

        # Use full state for smaller datasets or when data integrity is critical
        return TransitionStrategy.FULL_STATE


class TransitionValidator:
    """Validates year-to-year transitions for data integrity."""

    def __init__(self, config: OrchestrationConfig):
        """
        Initialize transition validator.

        Args:
            config: Orchestration configuration
        """
        self.config = config

    async def validate_transition(
        self,
        context: TransitionContext,
        new_state: WorkforceState
    ) -> TransitionValidation:
        """
        Validate year-to-year transition.

        Args:
            context: Transition context
            new_state: New year workforce state

        Returns:
            Validation results
        """
        logger.debug(f"Validating transition from {context.from_year} to {context.to_year}")
        start_time = time.time()

        validation_checks = []
        errors = []
        warnings = []

        try:
            # Data continuity checks
            continuity_result = await self._validate_data_continuity(context, new_state)
            validation_checks.append(("data_continuity", continuity_result))
            if not continuity_result["passed"]:
                errors.extend(continuity_result["errors"])

            # Business logic checks
            business_result = await self._validate_business_logic(context, new_state)
            validation_checks.append(("business_logic", business_result))
            if not business_result["passed"]:
                errors.extend(business_result["errors"])

            # Performance checks
            performance_result = await self._validate_performance_metrics(context, new_state)
            validation_checks.append(("performance", performance_result))
            if not performance_result["passed"]:
                warnings.extend(performance_result["warnings"])

            execution_time = time.time() - start_time

            # Overall validation result
            total_checks = len(validation_checks)
            failed_checks = sum(1 for _, result in validation_checks if not result["passed"])
            passed = failed_checks == 0

            validation_details = {
                check_name: result for check_name, result in validation_checks
            }

            logger.debug(f"Transition validation completed: {total_checks - failed_checks}/{total_checks} checks passed")

            return TransitionValidation(
                passed=passed,
                total_checks=total_checks,
                failed_checks=failed_checks,
                warnings=len(warnings),
                validation_details=validation_details,
                errors=errors,
                warnings_list=warnings,
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Transition validation failed: {e}")

            return TransitionValidation(
                passed=False,
                total_checks=1,
                failed_checks=1,
                warnings=0,
                errors=[f"Validation failed: {str(e)}"],
                execution_time=execution_time
            )

    async def _validate_data_continuity(
        self,
        context: TransitionContext,
        new_state: WorkforceState
    ) -> Dict[str, Any]:
        """Validate data continuity using MVP database validation."""
        errors = []

        try:
            # Import MVP database validation components
            from orchestrator_mvp.core.database_manager import get_connection
            from orchestrator_mvp.core.multi_year_simulation import validate_year_transition

            # Use MVP validation for year transition
            loop = asyncio.get_event_loop()
            mvp_validation_passed = await loop.run_in_executor(
                None,
                validate_year_transition,
                context.from_year,
                context.to_year
            )

            if not mvp_validation_passed:
                errors.append(f"MVP year transition validation failed for {context.from_year} -> {context.to_year}")

            # Database-level validation using actual data
            conn = get_connection()
            try:
                # Check workforce snapshot exists for both years
                snapshot_query = """
                    SELECT simulation_year,
                           COUNT(*) as total_employees,
                           COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees
                    FROM fct_workforce_snapshot
                    WHERE simulation_year IN (?, ?)
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                """

                results = conn.execute(snapshot_query, [context.from_year, context.to_year]).fetchall()

                if len(results) < 2:
                    errors.append(f"Missing workforce snapshot data for year transition {context.from_year} -> {context.to_year}")
                else:
                    from_year_data, to_year_data = results
                    from_total, from_active = from_year_data[1], from_year_data[2]
                    to_total, to_active = to_year_data[1], to_year_data[2]

                    # Validate workforce continuity
                    if to_active == 0:
                        errors.append(f"No active employees in year {context.to_year}")

                    # Check reasonable workforce growth (within expected bounds)
                    if from_active > 0:
                        growth_rate = (to_active - from_active) / from_active
                        if growth_rate < -0.5 or growth_rate > 1.0:  # Between -50% and +100%
                            errors.append(f"Unrealistic workforce growth rate: {growth_rate:.1%}")

                    # Validate event data exists
                    events_query = """
                        SELECT simulation_year, event_type, COUNT(*) as event_count
                        FROM fct_yearly_events
                        WHERE simulation_year = ?
                        GROUP BY simulation_year, event_type
                    """

                    event_results = conn.execute(events_query, [context.to_year]).fetchall()
                    if not event_results:
                        errors.append(f"No events found for year {context.to_year}")

            finally:
                conn.close()

            # State-level validation
            from_count = len(context.from_state.workforce_records)
            to_count = len(new_state.workforce_records)

            if to_count == 0:
                errors.append("New state has zero workforce records")

            # Calculate continuity metrics
            continuity_rate = 0.0
            if from_count > 0 and to_count > 0:
                from_ids = {r.employee_id for r in context.from_state.workforce_records}
                to_ids = {r.employee_id for r in new_state.workforce_records}
                continuing_employees = len(from_ids.intersection(to_ids))
                continuity_rate = continuing_employees / len(from_ids)

            return {
                "passed": len(errors) == 0,
                "errors": errors,
                "metrics": {
                    "workforce_change": (to_count - from_count) / from_count if from_count > 0 else 0,
                    "continuity_rate": continuity_rate,
                    "mvp_validation_passed": mvp_validation_passed
                }
            }

        except Exception as e:
            logger.error(f"Data continuity validation failed: {e}")
            errors.append(f"Validation error: {str(e)}")

            return {
                "passed": False,
                "errors": errors,
                "metrics": {"error": str(e)}
            }

    async def _validate_business_logic(
        self,
        context: TransitionContext,
        new_state: WorkforceState
    ) -> Dict[str, Any]:
        """Validate business logic constraints."""
        errors = []

        # Check age progression
        age_errors = await self._check_age_progression(context, new_state)
        errors.extend(age_errors)

        # Check salary progression
        salary_errors = await self._check_salary_progression(context, new_state)
        errors.extend(salary_errors)

        # Check plan enrollment logic
        enrollment_errors = await self._check_enrollment_logic(new_state)
        errors.extend(enrollment_errors)

        return {
            "passed": len(errors) == 0,
            "errors": errors
        }

    async def _check_age_progression(
        self,
        context: TransitionContext,
        new_state: WorkforceState
    ) -> List[str]:
        """Check that ages progressed correctly."""
        errors = []

        # Create lookup for previous ages
        prev_ages = {r.employee_id: r.age for r in context.from_state.workforce_records}

        for record in new_state.workforce_records:
            if record.employee_id in prev_ages:
                prev_age = prev_ages[record.employee_id]
                expected_age = prev_age + 1

                if record.age != expected_age:
                    errors.append(f"Employee {record.employee_id} age incorrect: "
                                f"expected {expected_age}, got {record.age}")

        return errors

    async def _check_salary_progression(
        self,
        context: TransitionContext,
        new_state: WorkforceState
    ) -> List[str]:
        """Check that salaries progressed reasonably."""
        errors = []

        # Create lookup for previous salaries
        prev_salaries = {r.employee_id: r.salary for r in context.from_state.workforce_records}

        for record in new_state.workforce_records:
            if record.employee_id in prev_salaries:
                prev_salary = prev_salaries[record.employee_id]

                # Check for reasonable salary change (between -5% and +50%)
                if prev_salary > 0:
                    change_ratio = (record.salary - prev_salary) / prev_salary
                    if change_ratio < -0.05 or change_ratio > 0.5:
                        errors.append(f"Employee {record.employee_id} salary change unreasonable: "
                                    f"{change_ratio:.1%}")

        return errors

    async def _check_enrollment_logic(self, new_state: WorkforceState) -> List[str]:
        """Check plan enrollment logic."""
        errors = []

        for record in new_state.workforce_records:
            # Can't be enrolled without being eligible
            if record.plan_enrolled and not record.plan_eligible:
                errors.append(f"Employee {record.employee_id} enrolled but not eligible")

            # Enrollment date should exist if enrolled
            if record.plan_enrolled and not record.enrollment_date:
                errors.append(f"Employee {record.employee_id} enrolled but no enrollment date")

        return errors

    async def _validate_performance_metrics(
        self,
        context: TransitionContext,
        new_state: WorkforceState
    ) -> Dict[str, Any]:
        """Validate performance metrics."""
        warnings = []

        # Check state size for performance implications
        state_size = len(new_state.workforce_records)
        if state_size > 50000:
            warnings.append(f"Large state size ({state_size} records) may impact performance")

        # Check total payroll for reasonableness
        total_payroll = new_state.total_payroll
        if total_payroll == 0:
            warnings.append("Total payroll is zero")

        return {
            "passed": True,  # Performance issues are warnings, not failures
            "warnings": warnings,
            "performance_metrics": {
                "state_size": state_size,
                "total_payroll": total_payroll
            }
        }


class YearTransition:
    """
    Main coordinator for year-to-year transitions in multi-year simulations.

    Handles state transfer, validation, and preparation of next year context
    using appropriate strategies and comprehensive error handling.
    """

    def __init__(
        self,
        config: OrchestrationConfig,
        database_manager: DatabaseManager,
        state_manager: StateManager
    ):
        """
        Initialize year transition coordinator.

        Args:
            config: Orchestration configuration
            database_manager: Database manager for data operations
            state_manager: State manager for workforce state
        """
        self.config = config
        self.database_manager = database_manager
        self.state_manager = state_manager

        # Initialize transfer strategies
        self.transfer_strategies = {
            TransitionStrategy.INCREMENTAL: IncrementalTransferStrategy(),
            TransitionStrategy.FULL_STATE: FullStateTransferStrategy(),
            TransitionStrategy.OPTIMIZED: OptimizedTransferStrategy()
        }

        # Initialize validator
        self.validator = TransitionValidator(config)

        # Transition history
        self._transition_history: List[TransitionResult] = []

        logger.info("YearTransition initialized with multiple transfer strategies")

    async def execute_transition(self, context: TransitionContext) -> TransitionResult:
        """
        Execute complete year-to-year transition.

        Args:
            context: Transition context

        Returns:
            Transition result with all operation details
        """
        logger.info(f"Starting year transition from {context.from_year} to {context.to_year} "
                   f"using {context.strategy.value} strategy")

        start_time = time.time()

        try:
            # Step 1: Transfer state using selected strategy
            transfer_strategy = self.transfer_strategies.get(
                context.strategy,
                self.transfer_strategies[TransitionStrategy.OPTIMIZED]
            )

            state_transfer_result = await transfer_strategy.transfer_state(context, self.state_manager)

            if not state_transfer_result.success:
                logger.error(f"State transfer failed for {context.from_year} -> {context.to_year}")
                return self._create_failure_result(context, start_time, state_transfer_result)

            # Step 2: Validate transition if enabled
            validation_result = None
            if context.validation_enabled:
                new_state = self.state_manager.get_year_state(context.to_year)
                if new_state:
                    validation_result = await self.validator.validate_transition(context, new_state)

                    if not validation_result.passed:
                        logger.warning(f"Transition validation failed for {context.from_year} -> {context.to_year}")
                        # Continue with warnings, don't fail the transition

            # Step 3: Prepare next year context
            next_year_context = await self._prepare_next_year_context(context)

            # Calculate performance metrics
            total_execution_time = time.time() - start_time
            performance_metrics = {
                "total_execution_time": total_execution_time,
                "state_transfer_time": state_transfer_result.execution_time,
                "validation_time": validation_result.execution_time if validation_result else 0,
                "records_per_second": state_transfer_result.records_transferred / total_execution_time if total_execution_time > 0 else 0,
                "transition_strategy": context.strategy.value
            }

            # Create successful result
            result = TransitionResult(
                from_year=context.from_year,
                to_year=context.to_year,
                success=True,
                total_execution_time=total_execution_time,
                state_transfer_result=state_transfer_result,
                validation_result=validation_result,
                next_year_context=next_year_context,
                performance_metrics=performance_metrics
            )

            # Track transition history
            self._transition_history.append(result)

            logger.info(f"Year transition completed successfully: {context.from_year} -> {context.to_year} "
                       f"in {total_execution_time:.2f}s")

            return result

        except Exception as e:
            total_execution_time = time.time() - start_time
            logger.error(f"Year transition failed: {context.from_year} -> {context.to_year}: {e}")

            result = TransitionResult(
                from_year=context.from_year,
                to_year=context.to_year,
                success=False,
                total_execution_time=total_execution_time,
                performance_metrics={
                    "error": str(e),
                    "execution_time": total_execution_time
                }
            )

            self._transition_history.append(result)
            return result

    async def _prepare_next_year_context(self, transition_context: TransitionContext) -> YearContext:
        """Prepare context for next year processing."""
        # Get the newly created state
        new_state = self.state_manager.get_year_state(transition_context.to_year)

        # Create year context for next year processing
        year_context = YearContext(
            year=transition_context.to_year,
            previous_workforce=new_state,
            configuration=transition_context.metadata.get("configuration", {}),
            processing_mode=ProcessingMode.OPTIMIZED,
            enable_validation=transition_context.validation_enabled,
            metadata={
                "transition_completed": True,
                "previous_year": transition_context.from_year,
                "transition_strategy": transition_context.strategy.value
            }
        )

        return year_context

    def _create_failure_result(
        self,
        context: TransitionContext,
        start_time: float,
        state_transfer_result: StateTransferResult
    ) -> TransitionResult:
        """Create failure result for transition."""
        total_execution_time = time.time() - start_time

        result = TransitionResult(
            from_year=context.from_year,
            to_year=context.to_year,
            success=False,
            total_execution_time=total_execution_time,
            state_transfer_result=state_transfer_result,
            performance_metrics={
                "failure_reason": "state_transfer_failed",
                "execution_time": total_execution_time
            }
        )

        self._transition_history.append(result)
        return result

    def get_transition_history(self) -> List[TransitionResult]:
        """Get history of all transitions."""
        return self._transition_history.copy()

    def get_transition_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary of all transitions."""
        if not self._transition_history:
            return {"message": "No transition history available"}

        successful_transitions = [t for t in self._transition_history if t.success]
        failed_transitions = [t for t in self._transition_history if not t.success]

        total_time = sum(t.total_execution_time for t in self._transition_history)
        avg_time = total_time / len(self._transition_history)

        strategy_counts = {}
        for transition in successful_transitions:
            if transition.state_transfer_result:
                strategy = transition.state_transfer_result.transfer_strategy.value
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        return {
            "total_transitions": len(self._transition_history),
            "successful_transitions": len(successful_transitions),
            "failed_transitions": len(failed_transitions),
            "success_rate": len(successful_transitions) / len(self._transition_history),
            "total_execution_time": total_time,
            "average_execution_time": avg_time,
            "strategy_usage": strategy_counts,
            "total_records_transferred": sum(
                t.state_transfer_result.records_transferred
                for t in successful_transitions
                if t.state_transfer_result
            )
        }


# Custom exceptions
class TransitionError(Exception):
    """Base exception for transition errors."""
    pass


class StateTransferError(TransitionError):
    """Exception for state transfer errors."""
    pass


class TransitionValidationError(TransitionError):
    """Exception for transition validation errors."""
    pass
