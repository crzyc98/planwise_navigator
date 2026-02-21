#!/usr/bin/env python3
"""
Workflow Definition Module

Defines the workflow stages, stage definitions, and checkpoint structures for
the PlanWise Navigator pipeline orchestration. This module provides the foundation
for building year-specific workflows with proper dependency tracking and validation.

This is a pure workflow definition module with no dependencies on other pipeline
components - it serves as the foundational layer for pipeline orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class WorkflowStage(Enum):
    """Enumeration of pipeline workflow stages.

    Stages are executed in dependency order, with each stage completing before
    dependent stages begin. This ensures proper data flow and consistency.
    """
    INITIALIZATION = "initialization"
    FOUNDATION = "foundation"
    EVENT_GENERATION = "event_generation"
    STATE_ACCUMULATION = "state_accumulation"
    VALIDATION = "validation"
    REPORTING = "reporting"
    CLEANUP = "cleanup"


@dataclass
class StageDefinition:
    """Definition of a workflow stage with dependencies and validation.

    Attributes:
        name: The workflow stage identifier
        dependencies: List of stages that must complete before this stage
        models: List of dbt model selectors to execute in this stage
        validation_rules: List of validation rules to apply after stage completion
        parallel_safe: Whether models in this stage can be executed in parallel
        checkpoint_enabled: Whether to create a checkpoint after stage completion
    """
    name: WorkflowStage
    dependencies: List[WorkflowStage]
    models: List[str]
    validation_rules: List[str]
    parallel_safe: bool = False
    checkpoint_enabled: bool = True


@dataclass
class WorkflowCheckpoint:
    """Checkpoint data for workflow recovery.

    Attributes:
        year: Simulation year for this checkpoint
        stage: Workflow stage that was completed
        timestamp: ISO timestamp of checkpoint creation
        state_hash: Hash of the workflow state for validation
    """
    year: int
    stage: WorkflowStage
    timestamp: str
    state_hash: str


class WorkflowBuilder:
    """Builder for creating year-specific workflow definitions.

    This class encapsulates the logic for building workflow stage definitions
    based on simulation year. Year 1 includes baseline workforce initialization,
    while subsequent years use incremental data preservation.
    """

    @staticmethod
    def build_year_workflow(year: int, start_year: int) -> List[StageDefinition]:
        """Build workflow stage definitions for a specific simulation year.

        Args:
            year: The simulation year to build workflow for
            start_year: The first year of the simulation (for conditional logic)

        Returns:
            List of stage definitions in execution order

        Notes:
            - Year 1 includes full baseline workforce initialization
            - Year 2+ uses incremental preservation and helper models
            - Workflow ensures proper dependency ordering and validation
        """
        # Align initialization with working runner: broader staging on first year
        if year == start_year:
            initialization_models = [
                "staging.*",
                "int_baseline_workforce",
            ]
        else:
            initialization_models = [
                "int_active_employees_prev_year_snapshot",
            ]

        # Epic E042 Fix: Conditional foundation models to preserve historical data
        if year == start_year:
            # Year 1: Include baseline workforce (created from census)
            # Ensure new-hire staging is built so NH_YYYY_* appear in compensation
            foundation_models = [
                "int_baseline_workforce",
                "int_new_hire_compensation_staging",
                "int_employee_compensation_by_year",
                "int_effective_parameters",
                "int_workforce_needs",
                "int_workforce_needs_by_level",
            ]
        else:
            # Year 2+: Skip baseline workforce (use incremental data preservation)
            # int_baseline_workforce is incremental and preserves Year 1 data
            # Include helper models for Year N-1 workforce data (circular dependency fix)
            foundation_models = [
                "int_prev_year_workforce_summary",
                "int_prev_year_workforce_by_level",
                "int_employee_compensation_by_year",
                "int_effective_parameters",
                "int_workforce_needs",
                "int_workforce_needs_by_level",
            ]

        return [
            StageDefinition(
                name=WorkflowStage.INITIALIZATION,
                dependencies=[],
                models=initialization_models,
                validation_rules=["data_freshness_check"],
            ),
            StageDefinition(
                name=WorkflowStage.FOUNDATION,
                dependencies=[WorkflowStage.INITIALIZATION],
                models=foundation_models,
                validation_rules=["row_count_drift", "compensation_reasonableness"],
            ),
            StageDefinition(
                name=WorkflowStage.EVENT_GENERATION,
                dependencies=[WorkflowStage.FOUNDATION],
                # Match working runner ordering exactly for determinism
                models=[
                    # E049: Ensure synthetic baseline enrollment events are built in the first year
                    # so census deferral rates feed the state accumulator and snapshot participation.
                    *(
                        ["int_synthetic_baseline_enrollment_events"]
                        if year == start_year
                        else []
                    ),
                    "int_termination_events",
                    "int_hiring_events",
                    "int_new_hire_termination_events",
                    # Build employer eligibility after new-hire terminations to ensure flags are available
                    "int_employer_eligibility",
                    "int_hazard_promotion",
                    "int_hazard_merit",
                    "int_promotion_events",
                    "int_merit_events",
                    "int_eligibility_determination",
                    "int_voluntary_enrollment_decision",
                    "int_proactive_voluntary_enrollment",
                    "int_enrollment_events",
                    "int_deferral_match_response_events",
                    "int_deferral_rate_escalation_events",
                ],
                validation_rules=["hire_termination_ratio", "event_sequence"],
                parallel_safe=False,
            ),
            StageDefinition(
                name=WorkflowStage.STATE_ACCUMULATION,
                dependencies=[WorkflowStage.EVENT_GENERATION],
                models=[
                    "fct_yearly_events",
                    # Epic E068B: Build employee state accumulator early for O(1) state access
                    "int_employee_state_by_year",
                    # Build proration snapshot before contributions so all bases are prorated
                    "int_workforce_snapshot_optimized",
                    "int_enrollment_state_accumulator",
                    "int_deferral_rate_state_accumulator_v2",
                    "int_deferral_escalation_state_accumulator",
                    # Build employer contributions after contributions are computed to ensure proration
                    "int_employee_contributions",
                    "int_employer_core_contributions",
                    "int_employee_match_calculations",
                    "fct_employer_match_events",
                    "fct_workforce_snapshot",
                ],
                validation_rules=["state_consistency", "accumulator_integrity"],
                parallel_safe=False,  # Ensure proper sequencing of state models
            ),
            StageDefinition(
                name=WorkflowStage.VALIDATION,
                dependencies=[WorkflowStage.STATE_ACCUMULATION],
                models=[
                    "dq_employee_contributions_validation",
                ],
                validation_rules=["dq_suite"],
            ),
            StageDefinition(
                name=WorkflowStage.REPORTING,
                dependencies=[WorkflowStage.VALIDATION],
                models=[
                    # Future: Add reporting models here
                ],
                validation_rules=[],
            ),
        ]
