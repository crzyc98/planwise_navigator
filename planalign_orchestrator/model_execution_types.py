#!/usr/bin/env python3
"""
Model Execution Type Classification System

Defines execution safety classifications for dbt models to enable selective parallelization
while preserving data integrity for state-dependent operations.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Any
from pathlib import Path


class ModelExecutionType(Enum):
    """Classification of model execution safety for parallelization.

    SEQUENTIAL: Must run sequentially due to state dependencies or ordering requirements
    PARALLEL_SAFE: Can execute concurrently with other parallel-safe models
    CONDITIONAL: Execution safety depends on runtime conditions or dependencies
    """
    SEQUENTIAL = "sequential"
    PARALLEL_SAFE = "parallel_safe"
    CONDITIONAL = "conditional"


@dataclass
class ModelClassification:
    """Complete classification information for a dbt model."""
    model_name: str
    execution_type: ModelExecutionType
    dependencies: Set[str]
    tags: Set[str]
    reason: str
    parallel_group: Optional[str] = None  # For grouping parallel-safe models
    memory_intensive: bool = False
    threads_safe: bool = True


@dataclass
class ParallelExecutionGroup:
    """Group of models that can execute in parallel together."""
    group_id: str
    models: List[str]
    max_parallelism: int
    dependencies: Set[str]  # Groups this group depends on
    resource_requirements: Dict[str, Any]


class ModelClassifier:
    """Classifies dbt models based on their execution safety and dependency patterns."""

    def __init__(self):
        self.classifications: Dict[str, ModelClassification] = {}
        self._initialize_classifications()

    def _initialize_classifications(self) -> None:
        """Initialize model classifications based on known patterns."""

        # SEQUENTIAL: State accumulator models that must run in order
        sequential_models = {
            "int_enrollment_state_accumulator": "Temporal state tracking across years",
            "int_deferral_rate_state_accumulator": "Deferral rate state accumulation",
            "int_deferral_rate_state_accumulator_v2": "Enhanced deferral rate state accumulation",
            "int_deferral_escalation_state_accumulator": "Escalation state tracking",
            "int_workforce_previous_year": "Previous year workforce state",
            "int_workforce_previous_year_v2": "Enhanced previous year workforce state",
            "int_active_employees_prev_year_snapshot": "Previous year employee snapshot",
            "fct_yearly_events": "Event sequencing and ordering critical",
            "fct_workforce_snapshot": "Depends on all events and state accumulators",
            "int_workforce_snapshot_optimized": "Complex workforce state computation",
        }

        # PARALLEL_SAFE: Independent calculations that don't depend on mutable state
        parallel_safe_models = {
            # Hazard calculations - independent mathematical computations
            "int_hazard_termination": "Independent hazard calculation using static config",
            "int_hazard_promotion": "Independent hazard calculation using static config",
            "int_hazard_merit": "Independent hazard calculation using static config",

            # Staging models - pure data transformations
            "stg_census_data": "Data cleaning and validation",
            "stg_comp_levers": "Parameter staging",
            "stg_comp_targets": "Target staging",
            "stg_scenario_meta": "Metadata staging",

            # Configuration models - static reference data
            "stg_config_cola_by_year": "Static configuration data",
            "stg_config_termination_hazard_tenure_multipliers": "Static configuration data",
            "stg_config_promotion_hazard_tenure_multipliers": "Static configuration data",
            "stg_config_promotion_hazard_age_multipliers": "Static configuration data",
            "stg_config_termination_hazard_age_multipliers": "Static configuration data",
            "stg_config_raises_hazard": "Static configuration data",
            "stg_config_job_levels": "Static configuration data",
            "stg_config_promotion_hazard_base": "Static configuration data",
            "stg_config_termination_hazard_base": "Static configuration data",

            # Independent business logic models
            "int_effective_parameters": "Parameter calculation independent of workforce state",
            "int_baseline_workforce": "Initial workforce setup (year 1 only)",
            "int_workforce_needs": "Hiring demand calculation",
            "int_workforce_needs_by_level": "Level-specific hiring demand",
            "int_new_hire_compensation_staging": "New hire compensation calculation",
            "int_employer_eligibility": "Eligibility determination based on static rules",
            "int_plan_eligibility_determination": "Plan eligibility calculation",

            # Data quality and validation models
            "dq_employee_contributions_validation": "Independent data validation",
            "dq_performance_monitoring": "Performance metrics calculation",
            "dq_compliance_monitoring": "Compliance checking",

            # Reporting models
            "dim_hazard_table": "Reference dimension table",
            "dim_payroll_calendar": "Calendar dimension table",
        }

        # CONDITIONAL: Models with complex dependencies that may or may not be parallel-safe
        conditional_models = {
            # Event generation models - may have interdependencies
            "int_termination_events": "Depends on hazard calculations and workforce state",
            "int_hiring_events": "Depends on workforce needs and termination events",
            "int_promotion_events": "Depends on workforce state and hazard calculations",
            "int_merit_events": "Depends on workforce state and promotion timing",
            "int_new_hire_termination_events": "Depends on hiring events",

            # Enrollment and contribution models - complex state dependencies
            "int_enrollment_events": "Depends on eligibility and enrollment decisions",
            "int_voluntary_enrollment_decision": "Depends on multiple state factors",
            "int_proactive_voluntary_enrollment": "Depends on enrollment decisions",
            "int_synthetic_baseline_enrollment_events": "Baseline enrollment setup",
            "int_employee_contributions": "Depends on deferral rates and compensation",
            "int_employee_match_calculations": "Depends on contributions",
            "int_employer_core_contributions": "Depends on eligibility and contributions",
            "int_deferral_rate_escalation_events": "Depends on enrollment state",

            # Complex snapshot and aggregation models
            "int_employee_compensation_by_year": "Complex compensation aggregation",
            "fct_employer_match_events": "Depends on multiple contribution calculations",
            "fct_compensation_growth": "Growth calculation across multiple models",
        }

        # Create classifications
        for model, reason in sequential_models.items():
            self.classifications[model] = ModelClassification(
                model_name=model,
                execution_type=ModelExecutionType.SEQUENTIAL,
                dependencies=set(),  # Will be populated by dependency analyzer
                tags={"sequential_required", "state_accumulator"},
                reason=reason,
                threads_safe=False
            )

        for model, reason in parallel_safe_models.items():
            # Group similar models together
            if model.startswith("stg_"):
                group = "staging"
            elif model.startswith("int_hazard_"):
                group = "hazard_calculations"
            elif model.startswith("dq_"):
                group = "data_quality"
            elif model.startswith("dim_"):
                group = "dimensions"
            else:
                group = "independent_logic"

            self.classifications[model] = ModelClassification(
                model_name=model,
                execution_type=ModelExecutionType.PARALLEL_SAFE,
                dependencies=set(),  # Will be populated by dependency analyzer
                tags={"parallel_safe", group},
                reason=reason,
                parallel_group=group,
                threads_safe=True
            )

        for model, reason in conditional_models.items():
            self.classifications[model] = ModelClassification(
                model_name=model,
                execution_type=ModelExecutionType.CONDITIONAL,
                dependencies=set(),  # Will be populated by dependency analyzer
                tags={"conditional", "event_generation"},
                reason=reason,
                threads_safe=True  # May be safe in some contexts
            )

    def classify_model(self, model_name: str) -> ModelClassification:
        """Get classification for a specific model."""
        if model_name in self.classifications:
            return self.classifications[model_name]

        # Default classification for unknown models
        return ModelClassification(
            model_name=model_name,
            execution_type=ModelExecutionType.CONDITIONAL,
            dependencies=set(),
            tags={"unknown", "conditional"},
            reason=f"Unknown model {model_name} - conservative classification",
            threads_safe=True
        )

    def get_parallel_safe_models(self, models: List[str]) -> List[str]:
        """Filter list to only parallel-safe models."""
        return [
            model for model in models
            if self.classify_model(model).execution_type == ModelExecutionType.PARALLEL_SAFE
        ]

    def get_sequential_models(self, models: List[str]) -> List[str]:
        """Filter list to only sequential models."""
        return [
            model for model in models
            if self.classify_model(model).execution_type == ModelExecutionType.SEQUENTIAL
        ]

    def get_parallel_groups(self, models: List[str]) -> Dict[str, List[str]]:
        """Group parallel-safe models by their parallel group."""
        groups: Dict[str, List[str]] = {}

        for model in models:
            classification = self.classify_model(model)
            if (classification.execution_type == ModelExecutionType.PARALLEL_SAFE and
                classification.parallel_group):

                if classification.parallel_group not in groups:
                    groups[classification.parallel_group] = []
                groups[classification.parallel_group].append(model)

        return groups

    def can_run_in_parallel(self, model_a: str, model_b: str) -> bool:
        """Check if two models can run in parallel together."""
        class_a = self.classify_model(model_a)
        class_b = self.classify_model(model_b)

        # Both must be parallel-safe or conditional
        if (class_a.execution_type == ModelExecutionType.SEQUENTIAL or
            class_b.execution_type == ModelExecutionType.SEQUENTIAL):
            return False

        # Check for mutual dependencies
        if model_a in class_b.dependencies or model_b in class_a.dependencies:
            return False

        # Both parallel-safe models can run together
        if (class_a.execution_type == ModelExecutionType.PARALLEL_SAFE and
            class_b.execution_type == ModelExecutionType.PARALLEL_SAFE):
            return True

        # For conditional models, be conservative and don't parallelize
        return False

    def get_model_tags(self, model_name: str) -> Set[str]:
        """Get dbt tags that should be applied to a model."""
        classification = self.classify_model(model_name)

        tags = set(classification.tags)

        # Add execution type tag
        if classification.execution_type == ModelExecutionType.SEQUENTIAL:
            tags.add("sequential_required")
        elif classification.execution_type == ModelExecutionType.PARALLEL_SAFE:
            tags.add("parallel_safe")

        # Add thread safety tag
        if classification.threads_safe:
            tags.add("threads_safe")
        else:
            tags.add("single_threaded")

        return tags

    def export_classification_report(self) -> Dict[str, Any]:
        """Export a comprehensive classification report."""
        by_type = {}
        for exec_type in ModelExecutionType:
            by_type[exec_type.value] = []

        for classification in self.classifications.values():
            by_type[classification.execution_type.value].append({
                "model": classification.model_name,
                "reason": classification.reason,
                "tags": list(classification.tags),
                "parallel_group": classification.parallel_group,
                "threads_safe": classification.threads_safe
            })

        return {
            "total_models": len(self.classifications),
            "by_execution_type": by_type,
            "parallel_groups": self.get_parallel_groups(list(self.classifications.keys()))
        }
