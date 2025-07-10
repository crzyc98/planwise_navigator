"""
S050: Business Constraints Framework

Enterprise-grade constraint framework for enforcing business rules
and compliance requirements in compensation optimization.
"""

from __future__ import annotations
import json
import math
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import numpy as np
import logging

from orchestrator.resources.duckdb_resource import DuckDBResource

logger = logging.getLogger(__name__)


@dataclass
class ConstraintViolation:
    """Details of a constraint violation."""
    constraint_name: str
    violation_score: float
    violation_type: str
    severity: str  # 'critical', 'warning', 'info'
    description: str
    suggested_fix: Optional[str] = None
    parameters_affected: List[str] = None


@dataclass
class ConstraintEvaluationResult:
    """Result of constraint evaluation."""
    constraint_name: str
    passed: bool
    violation_score: float
    penalty: float
    execution_time_ms: float
    metadata: Dict[str, Any]


class BusinessConstraint(ABC):
    """Abstract base class for business constraints."""

    def __init__(
        self,
        name: str,
        description: str,
        severity: str = 'warning',
        enabled: bool = True,
        weight: float = 1.0
    ):
        self.name = name
        self.description = description
        self.severity = severity  # 'critical', 'warning', 'info'
        self.enabled = enabled
        self.weight = weight

    @abstractmethod
    def evaluate(
        self,
        parameters: Dict[str, float],
        context: Dict[str, Any]
    ) -> ConstraintEvaluationResult:
        """Evaluate constraint against parameters and context."""
        pass

    @abstractmethod
    def calculate_penalty(self, violation_score: float) -> float:
        """Calculate penalty for constraint violation."""
        pass

    def get_penalty_multiplier(self) -> float:
        """Get penalty multiplier based on severity."""
        multipliers = {
            'critical': 1000.0,
            'warning': 100.0,
            'info': 10.0
        }
        return multipliers.get(self.severity, 100.0)


class BudgetConstraint(BusinessConstraint):
    """Budget constraint ensuring total compensation stays within limits."""

    def __init__(
        self,
        max_total_budget: float,
        budget_buffer_pct: float = 0.05,
        **kwargs
    ):
        super().__init__(
            name="budget_constraint",
            description=f"Total compensation budget must not exceed ${max_total_budget:,.0f}",
            severity="critical",
            **kwargs
        )
        self.max_total_budget = max_total_budget
        self.budget_buffer_pct = budget_buffer_pct

    def evaluate(
        self,
        parameters: Dict[str, float],
        context: Dict[str, Any]
    ) -> ConstraintEvaluationResult:
        start_time = time.time()

        # Calculate total expected compensation cost
        total_cost = self._calculate_total_cost(parameters, context)

        # Calculate violation
        budget_with_buffer = self.max_total_budget * (1 - self.budget_buffer_pct)
        violation_score = max(0, total_cost - budget_with_buffer)

        passed = violation_score == 0
        penalty = self.calculate_penalty(violation_score)

        execution_time = (time.time() - start_time) * 1000

        return ConstraintEvaluationResult(
            constraint_name=self.name,
            passed=passed,
            violation_score=violation_score,
            penalty=penalty,
            execution_time_ms=execution_time,
            metadata={
                "total_cost": total_cost,
                "budget_limit": budget_with_buffer,
                "budget_utilization_pct": (total_cost / self.max_total_budget) * 100,
                "overage_amount": violation_score
            }
        )

    def calculate_penalty(self, violation_score: float) -> float:
        if violation_score == 0:
            return 0.0

        # Exponential penalty for budget overruns
        base_penalty = self.get_penalty_multiplier()
        relative_overage = violation_score / self.max_total_budget

        return base_penalty * (1 + relative_overage) ** 2

    def _calculate_total_cost(
        self,
        parameters: Dict[str, float],
        context: Dict[str, Any]
    ) -> float:
        """Calculate total compensation cost based on parameters."""
        # This would integrate with workforce simulation
        # For now, use a simplified calculation

        workforce_size = context.get('workforce_size', 1000)
        avg_salary = context.get('avg_salary', 75000)

        # Calculate merit cost
        merit_cost = 0
        for level in range(1, 6):
            merit_rate = parameters.get(f'merit_rate_level_{level}', 0)
            level_employees = context.get(f'level_{level}_count', workforce_size // 5)
            level_avg_salary = context.get(f'level_{level}_avg_salary', avg_salary)

            merit_cost += merit_rate * level_employees * level_avg_salary

        # Calculate COLA cost
        cola_rate = parameters.get('cola_rate', 0)
        cola_cost = cola_rate * workforce_size * avg_salary

        # Calculate promotion cost
        promotion_cost = 0
        for level in range(1, 5):  # Can't promote from level 5
            promo_prob = parameters.get(f'promotion_probability_level_{level}', 0)
            promo_raise = parameters.get(f'promotion_raise_level_{level}', 0)
            level_employees = context.get(f'level_{level}_count', workforce_size // 5)
            level_avg_salary = context.get(f'level_{level}_avg_salary', avg_salary)

            expected_promotions = promo_prob * level_employees
            promotion_cost += expected_promotions * promo_raise * level_avg_salary

        return merit_cost + cola_cost + promotion_cost


class EquityConstraint(BusinessConstraint):
    """Equity constraint ensuring fair compensation distribution."""

    def __init__(
        self,
        max_variance_ratio: float = 0.15,
        min_level_progression: float = 1.05,
        **kwargs
    ):
        super().__init__(
            name="equity_constraint",
            description="Compensation must maintain equity across levels and demographics",
            severity="warning",
            **kwargs
        )
        self.max_variance_ratio = max_variance_ratio
        self.min_level_progression = min_level_progression

    def evaluate(
        self,
        parameters: Dict[str, float],
        context: Dict[str, Any]
    ) -> ConstraintEvaluationResult:
        start_time = time.time()

        violations = []
        total_violation = 0

        # Check merit rate variance across levels
        merit_rates = [parameters.get(f'merit_rate_level_{i}', 0) for i in range(1, 6)]
        if merit_rates:
            variance_ratio = np.std(merit_rates) / np.mean(merit_rates) if np.mean(merit_rates) > 0 else 0
            if variance_ratio > self.max_variance_ratio:
                violation = variance_ratio - self.max_variance_ratio
                violations.append(f"Merit rate variance too high: {variance_ratio:.3f}")
                total_violation += violation

        # Check level progression
        for level in range(1, 5):
            current_merit = parameters.get(f'merit_rate_level_{level}', 0)
            next_merit = parameters.get(f'merit_rate_level_{level+1}', 0)

            if current_merit > 0 and next_merit > 0:
                progression_ratio = current_merit / next_merit
                if progression_ratio < self.min_level_progression:
                    violation = self.min_level_progression - progression_ratio
                    violations.append(f"Level {level} to {level+1} progression insufficient")
                    total_violation += violation

        passed = total_violation == 0
        penalty = self.calculate_penalty(total_violation)

        execution_time = (time.time() - start_time) * 1000

        return ConstraintEvaluationResult(
            constraint_name=self.name,
            passed=passed,
            violation_score=total_violation,
            penalty=penalty,
            execution_time_ms=execution_time,
            metadata={
                "violations": violations,
                "merit_rate_variance": variance_ratio if merit_rates else 0,
                "level_progressions": self._calculate_level_progressions(parameters)
            }
        )

    def calculate_penalty(self, violation_score: float) -> float:
        if violation_score == 0:
            return 0.0

        return self.get_penalty_multiplier() * violation_score * 10

    def _calculate_level_progressions(self, parameters: Dict[str, float]) -> List[float]:
        """Calculate progression ratios between levels."""
        progressions = []
        for level in range(1, 5):
            current = parameters.get(f'merit_rate_level_{level}', 0)
            next_level = parameters.get(f'merit_rate_level_{level+1}', 0)
            if current > 0 and next_level > 0:
                progressions.append(current / next_level)
            else:
                progressions.append(1.0)
        return progressions


class IndividualRaiseConstraint(BusinessConstraint):
    """Constraint on individual raise amounts."""

    def __init__(
        self,
        min_raise_pct: float = 0.01,
        max_raise_pct: float = 0.25,
        **kwargs
    ):
        super().__init__(
            name="individual_raise_constraint",
            description=f"Individual raises must be between {min_raise_pct:.1%} and {max_raise_pct:.1%}",
            severity="warning",
            **kwargs
        )
        self.min_raise_pct = min_raise_pct
        self.max_raise_pct = max_raise_pct

    def evaluate(
        self,
        parameters: Dict[str, float],
        context: Dict[str, Any]
    ) -> ConstraintEvaluationResult:
        start_time = time.time()

        violations = []
        total_violation = 0

        # Check merit rates
        for level in range(1, 6):
            merit_rate = parameters.get(f'merit_rate_level_{level}', 0)

            if merit_rate < self.min_raise_pct:
                violation = self.min_raise_pct - merit_rate
                violations.append(f"Level {level} merit rate below minimum")
                total_violation += violation

            if merit_rate > self.max_raise_pct:
                violation = merit_rate - self.max_raise_pct
                violations.append(f"Level {level} merit rate above maximum")
                total_violation += violation

        # Check promotion raises
        for level in range(1, 5):
            promo_raise = parameters.get(f'promotion_raise_level_{level}', 0)

            if promo_raise < self.min_raise_pct:
                violation = self.min_raise_pct - promo_raise
                violations.append(f"Level {level} promotion raise below minimum")
                total_violation += violation

            if promo_raise > self.max_raise_pct:
                violation = promo_raise - self.max_raise_pct
                violations.append(f"Level {level} promotion raise above maximum")
                total_violation += violation

        passed = total_violation == 0
        penalty = self.calculate_penalty(total_violation)

        execution_time = (time.time() - start_time) * 1000

        return ConstraintEvaluationResult(
            constraint_name=self.name,
            passed=passed,
            violation_score=total_violation,
            penalty=penalty,
            execution_time_ms=execution_time,
            metadata={
                "violations": violations,
                "merit_rate_ranges": self._get_merit_rate_ranges(parameters),
                "promotion_raise_ranges": self._get_promotion_raise_ranges(parameters)
            }
        )

    def calculate_penalty(self, violation_score: float) -> float:
        if violation_score == 0:
            return 0.0

        return self.get_penalty_multiplier() * violation_score * 50

    def _get_merit_rate_ranges(self, parameters: Dict[str, float]) -> Dict[str, Tuple[float, float]]:
        """Get merit rate ranges by level."""
        return {
            f"level_{level}": (
                parameters.get(f'merit_rate_level_{level}', 0),
                parameters.get(f'merit_rate_level_{level}', 0)
            )
            for level in range(1, 6)
        }

    def _get_promotion_raise_ranges(self, parameters: Dict[str, float]) -> Dict[str, Tuple[float, float]]:
        """Get promotion raise ranges by level."""
        return {
            f"level_{level}": (
                parameters.get(f'promotion_raise_level_{level}', 0),
                parameters.get(f'promotion_raise_level_{level}', 0)
            )
            for level in range(1, 5)
        }


class MeritocracyConstraint(BusinessConstraint):
    """Constraint ensuring meritocratic compensation increases."""

    def __init__(
        self,
        min_performance_correlation: float = 0.3,
        **kwargs
    ):
        super().__init__(
            name="meritocracy_constraint",
            description="Higher performance must correlate with higher compensation increases",
            severity="info",
            **kwargs
        )
        self.min_performance_correlation = min_performance_correlation

    def evaluate(
        self,
        parameters: Dict[str, float],
        context: Dict[str, Any]
    ) -> ConstraintEvaluationResult:
        start_time = time.time()

        # This would typically require performance data from context
        # For now, implement a simplified check based on level progression

        merit_rates = [parameters.get(f'merit_rate_level_{i}', 0) for i in range(1, 6)]

        # Check if higher levels (assumed higher performance) get higher rates
        violations = []
        total_violation = 0

        for i in range(len(merit_rates) - 1):
            if merit_rates[i] < merit_rates[i + 1]:
                # Higher level has lower merit rate - potential meritocracy violation
                violation = merit_rates[i + 1] - merit_rates[i]
                violations.append(f"Level {i+1} has lower merit than Level {i+2}")
                total_violation += violation

        passed = total_violation == 0
        penalty = self.calculate_penalty(total_violation)

        execution_time = (time.time() - start_time) * 1000

        return ConstraintEvaluationResult(
            constraint_name=self.name,
            passed=passed,
            violation_score=total_violation,
            penalty=penalty,
            execution_time_ms=execution_time,
            metadata={
                "violations": violations,
                "merit_rate_by_level": {f"level_{i+1}": rate for i, rate in enumerate(merit_rates)},
                "performance_correlation_score": self._calculate_correlation_score(merit_rates)
            }
        )

    def calculate_penalty(self, violation_score: float) -> float:
        if violation_score == 0:
            return 0.0

        return self.get_penalty_multiplier() * violation_score * 20

    def _calculate_correlation_score(self, merit_rates: List[float]) -> float:
        """Calculate correlation score for merit rates by level."""
        if len(merit_rates) < 2:
            return 1.0

        # Simple correlation with level (higher level = higher expected merit)
        levels = list(range(1, len(merit_rates) + 1))

        try:
            correlation = np.corrcoef(levels, merit_rates)[0, 1]
            return correlation if not np.isnan(correlation) else 0.0
        except:
            return 0.0


class BusinessConstraintFramework:
    """
    Enterprise-grade constraint framework for business rules enforcement.

    Features:
    - Configurable constraint registration
    - Parallel constraint evaluation
    - Weighted penalty calculation
    - Violation reporting and analysis
    - Historical constraint tracking
    """

    def __init__(self, duckdb_resource: DuckDBResource, config_path: Optional[Path] = None):
        self.duckdb_resource = duckdb_resource
        self.constraints: Dict[str, BusinessConstraint] = {}
        self.config_path = config_path
        self._initialize_tracking_tables()
        self._load_default_constraints()

        if config_path and config_path.exists():
            self._load_constraints_from_config()

    def _initialize_tracking_tables(self):
        """Initialize DuckDB tables for constraint tracking."""
        with self.duckdb_resource.get_connection() as conn:
            # Constraint evaluation history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS constraint_evaluations (
                    evaluation_id VARCHAR PRIMARY KEY,
                    timestamp TIMESTAMP,
                    parameters_json VARCHAR,
                    context_json VARCHAR,
                    total_constraints INTEGER,
                    passed_constraints INTEGER,
                    total_penalty DOUBLE,
                    evaluation_time_ms DOUBLE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Individual constraint results
            conn.execute("""
                CREATE TABLE IF NOT EXISTS constraint_results (
                    evaluation_id VARCHAR,
                    constraint_name VARCHAR,
                    passed BOOLEAN,
                    violation_score DOUBLE,
                    penalty DOUBLE,
                    execution_time_ms DOUBLE,
                    metadata_json VARCHAR,
                    PRIMARY KEY (evaluation_id, constraint_name),
                    FOREIGN KEY (evaluation_id) REFERENCES constraint_evaluations(evaluation_id)
                )
            """)

            # Create indexes
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_constraint_eval_timestamp ON constraint_evaluations(timestamp DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_constraint_results_name ON constraint_results(constraint_name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_constraint_results_penalty ON constraint_results(penalty DESC)")
            except:
                pass

    def _load_default_constraints(self):
        """Load default business constraints."""
        # Budget constraint
        self.register_constraint(BudgetConstraint(
            max_total_budget=50_000_000,  # $50M total budget
            budget_buffer_pct=0.05
        ))

        # Equity constraint
        self.register_constraint(EquityConstraint(
            max_variance_ratio=0.15,
            min_level_progression=1.05
        ))

        # Individual raise constraint
        self.register_constraint(IndividualRaiseConstraint(
            min_raise_pct=0.01,
            max_raise_pct=0.25
        ))

        # Meritocracy constraint
        self.register_constraint(MeritocracyConstraint(
            min_performance_correlation=0.3
        ))

    def _load_constraints_from_config(self):
        """Load constraints from YAML configuration file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Update existing constraints with config values
            if 'budget' in config:
                budget_config = config['budget']
                if 'budget_constraint' in self.constraints:
                    constraint = self.constraints['budget_constraint']
                    constraint.max_total_budget = budget_config.get('max_total_spend', constraint.max_total_budget)

            if 'equity' in config:
                equity_config = config['equity']
                if 'equity_constraint' in self.constraints:
                    constraint = self.constraints['equity_constraint']
                    constraint.max_variance_ratio = equity_config.get('max_variance_ratio', constraint.max_variance_ratio)

            # Add more config loading as needed

        except Exception as e:
            logger.warning(f"Failed to load constraints config: {e}")

    def register_constraint(self, constraint: BusinessConstraint):
        """Register a business constraint."""
        self.constraints[constraint.name] = constraint
        logger.info(f"Registered constraint: {constraint.name}")

    def unregister_constraint(self, constraint_name: str):
        """Unregister a business constraint."""
        if constraint_name in self.constraints:
            del self.constraints[constraint_name]
            logger.info(f"Unregistered constraint: {constraint_name}")

    def evaluate_all_constraints(
        self,
        parameters: Dict[str, float],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Evaluate all registered constraints.

        Returns:
            Comprehensive constraint evaluation results
        """
        if context is None:
            context = {}

        start_time = time.time()
        evaluation_id = f"eval_{int(start_time * 1000)}"

        results = []
        total_penalty = 0.0
        passed_count = 0

        # Evaluate each enabled constraint
        for constraint_name, constraint in self.constraints.items():
            if not constraint.enabled:
                continue

            try:
                result = constraint.evaluate(parameters, context)
                results.append(result)

                total_penalty += result.penalty * constraint.weight
                if result.passed:
                    passed_count += 1

            except Exception as e:
                logger.error(f"Failed to evaluate constraint {constraint_name}: {e}")
                # Create error result
                error_result = ConstraintEvaluationResult(
                    constraint_name=constraint_name,
                    passed=False,
                    violation_score=float('inf'),
                    penalty=1000.0,
                    execution_time_ms=0.0,
                    metadata={"error": str(e)}
                )
                results.append(error_result)
                total_penalty += 1000.0

        # Calculate summary metrics
        total_constraints = len([c for c in self.constraints.values() if c.enabled])
        evaluation_time = (time.time() - start_time) * 1000

        # Identify critical violations
        critical_violations = [
            r for r in results
            if not r.passed and self.constraints[r.constraint_name].severity == 'critical'
        ]

        # Create comprehensive result
        evaluation_result = {
            "evaluation_id": evaluation_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total_constraints": total_constraints,
                "passed_constraints": passed_count,
                "failed_constraints": total_constraints - passed_count,
                "total_penalty": total_penalty,
                "feasible": len(critical_violations) == 0,
                "evaluation_time_ms": evaluation_time
            },
            "constraint_results": [asdict(r) for r in results],
            "violations": self._categorize_violations(results),
            "recommendations": self._generate_constraint_recommendations(results, parameters)
        }

        # Store results
        self._store_evaluation_results(evaluation_result, parameters, context)

        return evaluation_result

    def _categorize_violations(
        self,
        results: List[ConstraintEvaluationResult]
    ) -> Dict[str, List[str]]:
        """Categorize violations by severity."""
        violations = {
            "critical": [],
            "warning": [],
            "info": []
        }

        for result in results:
            if not result.passed:
                constraint = self.constraints[result.constraint_name]
                violations[constraint.severity].append({
                    "constraint": result.constraint_name,
                    "description": constraint.description,
                    "violation_score": result.violation_score,
                    "penalty": result.penalty
                })

        return violations

    def _generate_constraint_recommendations(
        self,
        results: List[ConstraintEvaluationResult],
        parameters: Dict[str, float]
    ) -> List[str]:
        """Generate recommendations based on constraint violations."""
        recommendations = []

        # Critical violations
        critical_failures = [
            r for r in results
            if not r.passed and self.constraints[r.constraint_name].severity == 'critical'
        ]

        if critical_failures:
            recommendations.append(
                f"CRITICAL: {len(critical_failures)} critical constraints failed - "
                "optimization results may not be feasible for deployment"
            )

        # High penalty constraints
        high_penalty = [r for r in results if r.penalty > 100]
        if high_penalty:
            worst_constraint = max(high_penalty, key=lambda x: x.penalty)
            recommendations.append(
                f"Focus on resolving {worst_constraint.constraint_name} - "
                f"highest penalty ({worst_constraint.penalty:.2f})"
            )

        # Constraint-specific recommendations
        for result in results:
            if not result.passed:
                constraint_name = result.constraint_name

                if constraint_name == 'budget_constraint':
                    recommendations.append(
                        "Consider reducing merit rates or promotion probabilities to meet budget"
                    )
                elif constraint_name == 'equity_constraint':
                    recommendations.append(
                        "Adjust merit rates to reduce variance and improve level progression"
                    )
                elif constraint_name == 'individual_raise_constraint':
                    recommendations.append(
                        "Ensure all merit and promotion rates fall within acceptable ranges"
                    )

        return recommendations

    def _store_evaluation_results(
        self,
        evaluation_result: Dict[str, Any],
        parameters: Dict[str, float],
        context: Dict[str, Any]
    ):
        """Store constraint evaluation results in database."""
        evaluation_id = evaluation_result["evaluation_id"]
        summary = evaluation_result["summary"]

        with self.duckdb_resource.get_connection() as conn:
            # Store main evaluation record
            conn.execute("""
                INSERT INTO constraint_evaluations (
                    evaluation_id, timestamp, parameters_json, context_json,
                    total_constraints, passed_constraints, total_penalty, evaluation_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                evaluation_id,
                evaluation_result["timestamp"],
                json.dumps(parameters),
                json.dumps(context),
                summary["total_constraints"],
                summary["passed_constraints"],
                summary["total_penalty"],
                summary["evaluation_time_ms"]
            ])

            # Store individual constraint results
            for result in evaluation_result["constraint_results"]:
                conn.execute("""
                    INSERT INTO constraint_results (
                        evaluation_id, constraint_name, passed, violation_score,
                        penalty, execution_time_ms, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [
                    evaluation_id,
                    result["constraint_name"],
                    result["passed"],
                    result["violation_score"],
                    result["penalty"],
                    result["execution_time_ms"],
                    json.dumps(result["metadata"])
                ])

    def get_constraint_history(
        self,
        constraint_name: str,
        days_back: int = 30
    ) -> pd.DataFrame:
        """Get historical constraint performance."""
        with self.duckdb_resource.get_connection() as conn:
            return conn.execute("""
                SELECT
                    e.timestamp,
                    r.passed,
                    r.violation_score,
                    r.penalty,
                    r.execution_time_ms
                FROM constraint_evaluations e
                JOIN constraint_results r ON e.evaluation_id = r.evaluation_id
                WHERE r.constraint_name = ?
                AND e.timestamp >= CURRENT_TIMESTAMP - INTERVAL ? DAY
                ORDER BY e.timestamp DESC
            """, [constraint_name, days_back]).df()

    def get_constraint_statistics(self) -> Dict[str, Any]:
        """Get constraint framework statistics."""
        with self.duckdb_resource.get_connection() as conn:
            stats = conn.execute("""
                SELECT
                    COUNT(DISTINCT evaluation_id) as total_evaluations,
                    AVG(total_penalty) as avg_total_penalty,
                    AVG(passed_constraints::FLOAT / total_constraints) as avg_pass_rate,
                    AVG(evaluation_time_ms) as avg_evaluation_time
                FROM constraint_evaluations
                WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL 30 DAY
            """).fetchone()

            constraint_stats = conn.execute("""
                SELECT
                    constraint_name,
                    COUNT(*) as evaluation_count,
                    AVG(CASE WHEN passed THEN 1.0 ELSE 0.0 END) as pass_rate,
                    AVG(penalty) as avg_penalty
                FROM constraint_results r
                JOIN constraint_evaluations e ON r.evaluation_id = e.evaluation_id
                WHERE e.timestamp >= CURRENT_TIMESTAMP - INTERVAL 30 DAY
                GROUP BY constraint_name
                ORDER BY avg_penalty DESC
            """).df()

            return {
                "overall_stats": {
                    "total_evaluations": stats[0] if stats[0] else 0,
                    "avg_total_penalty": stats[1] if stats[1] else 0,
                    "avg_pass_rate": stats[2] if stats[2] else 0,
                    "avg_evaluation_time_ms": stats[3] if stats[3] else 0
                },
                "constraint_stats": constraint_stats.to_dict('records') if not constraint_stats.empty else [],
                "registered_constraints": {
                    name: {
                        "description": constraint.description,
                        "severity": constraint.severity,
                        "enabled": constraint.enabled,
                        "weight": constraint.weight
                    }
                    for name, constraint in self.constraints.items()
                }
            }


# Add missing import
import time
