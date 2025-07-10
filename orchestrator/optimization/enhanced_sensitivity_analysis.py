"""
S050: Enhanced Parameter Sensitivity Analysis

Advanced sensitivity analysis with gradient-based methods, parameter interactions,
and real-time sensitivity tracking for optimization guidance.
"""

from __future__ import annotations
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from scipy.optimize import approx_fprime
from scipy.stats import pearsonr
import logging

from orchestrator.resources.duckdb_resource import DuckDBResource

logger = logging.getLogger(__name__)


@dataclass
class SensitivityResult:
    """Individual parameter sensitivity result."""
    parameter_name: str
    gradient: float
    relative_impact: float
    direction: str  # 'increase' or 'decrease'
    confidence: float
    numerical_stability: float


@dataclass
class InteractionEffect:
    """Parameter interaction effect."""
    parameter_1: str
    parameter_2: str
    interaction_strength: float
    interaction_type: str  # 'synergistic', 'antagonistic', 'neutral'
    confidence: float


@dataclass
class SensitivityAnalysisReport:
    """Comprehensive sensitivity analysis report."""
    timestamp: str
    base_parameters: Dict[str, float]
    base_objective_value: float
    parameter_sensitivities: List[SensitivityResult]
    interaction_effects: List[InteractionEffect]
    parameter_rankings: List[Tuple[str, float]]
    optimization_recommendations: List[str]
    analysis_metadata: Dict[str, Any]


class EnhancedSensitivityAnalyzer:
    """
    Advanced sensitivity analysis engine with gradient-based methods.

    Features:
    - Finite difference gradient approximation
    - Parameter interaction analysis (Hessian matrix)
    - Adaptive step sizing
    - Parallel computation
    - Real-time sensitivity tracking
    - Statistical confidence estimation
    """

    def __init__(
        self,
        duckdb_resource: DuckDBResource,
        objective_function: Callable[[Dict[str, float]], float],
        parameter_bounds: Dict[str, Tuple[float, float]],
        step_size: float = 1e-4,
        max_workers: int = 4
    ):
        self.duckdb_resource = duckdb_resource
        self.objective_function = objective_function
        self.parameter_bounds = parameter_bounds
        self.step_size = step_size
        self.max_workers = max_workers
        self._sensitivity_cache = {}
        self._initialize_tracking_tables()

    def _initialize_tracking_tables(self):
        """Initialize DuckDB tables for sensitivity tracking."""
        with self.duckdb_resource.get_connection() as conn:
            # Sensitivity analysis history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sensitivity_analysis_history (
                    analysis_id VARCHAR PRIMARY KEY,
                    timestamp TIMESTAMP,
                    base_params_json VARCHAR,
                    base_objective_value DOUBLE,
                    total_parameters INTEGER,
                    analysis_runtime_seconds DOUBLE,
                    step_size DOUBLE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Individual parameter sensitivities
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parameter_sensitivities (
                    analysis_id VARCHAR,
                    parameter_name VARCHAR,
                    gradient DOUBLE,
                    relative_impact DOUBLE,
                    direction VARCHAR,
                    confidence DOUBLE,
                    numerical_stability DOUBLE,
                    PRIMARY KEY (analysis_id, parameter_name),
                    FOREIGN KEY (analysis_id) REFERENCES sensitivity_analysis_history(analysis_id)
                )
            """)

            # Parameter interactions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parameter_interactions (
                    analysis_id VARCHAR,
                    parameter_1 VARCHAR,
                    parameter_2 VARCHAR,
                    interaction_strength DOUBLE,
                    interaction_type VARCHAR,
                    confidence DOUBLE,
                    PRIMARY KEY (analysis_id, parameter_1, parameter_2),
                    FOREIGN KEY (analysis_id) REFERENCES sensitivity_analysis_history(analysis_id)
                )
            """)

            # Create indexes
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sensitivity_timestamp ON sensitivity_analysis_history(timestamp DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_param_sensitivity ON parameter_sensitivities(relative_impact DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_interactions ON parameter_interactions(interaction_strength DESC)")
            except:
                pass

    def analyze_sensitivity(
        self,
        base_parameters: Dict[str, float],
        objectives: Dict[str, float],
        include_interactions: bool = True,
        adaptive_step_size: bool = True
    ) -> SensitivityAnalysisReport:
        """
        Perform comprehensive sensitivity analysis.

        Args:
            base_parameters: Base parameter set to analyze
            objectives: Objective weights for multi-objective analysis
            include_interactions: Whether to compute parameter interactions
            adaptive_step_size: Whether to use adaptive step sizing

        Returns:
            Comprehensive sensitivity analysis report
        """
        start_time = time.time()
        analysis_id = f"sensitivity_{int(start_time)}"

        logger.info(f"Starting sensitivity analysis {analysis_id}")

        # Calculate base objective value
        base_objective_value = self._evaluate_objective_safe(base_parameters, objectives)

        # Calculate first-order sensitivities (gradients)
        parameter_sensitivities = self._calculate_parameter_gradients(
            base_parameters, objectives, adaptive_step_size
        )

        # Calculate second-order effects (interactions)
        interaction_effects = []
        if include_interactions:
            interaction_effects = self._calculate_parameter_interactions(
                base_parameters, objectives
            )

        # Rank parameters by importance
        parameter_rankings = self._rank_parameters(parameter_sensitivities)

        # Generate optimization recommendations
        recommendations = self._generate_recommendations(
            parameter_sensitivities, interaction_effects, base_parameters
        )

        # Create analysis metadata
        analysis_metadata = {
            "analysis_id": analysis_id,
            "runtime_seconds": time.time() - start_time,
            "step_size": self.step_size,
            "adaptive_step_used": adaptive_step_size,
            "interactions_computed": include_interactions,
            "numerical_stability_score": self._calculate_overall_stability(parameter_sensitivities),
            "total_function_evaluations": self._get_function_evaluation_count()
        }

        # Create report
        report = SensitivityAnalysisReport(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            base_parameters=base_parameters,
            base_objective_value=base_objective_value,
            parameter_sensitivities=parameter_sensitivities,
            interaction_effects=interaction_effects,
            parameter_rankings=parameter_rankings,
            optimization_recommendations=recommendations,
            analysis_metadata=analysis_metadata
        )

        # Store results
        self._store_analysis_results(report)

        logger.info(f"Sensitivity analysis {analysis_id} completed in {analysis_metadata['runtime_seconds']:.2f}s")

        return report

    def _calculate_parameter_gradients(
        self,
        base_parameters: Dict[str, float],
        objectives: Dict[str, float],
        adaptive_step_size: bool = True
    ) -> List[SensitivityResult]:
        """Calculate gradients for all parameters using finite differences."""
        parameter_names = list(base_parameters.keys())
        sensitivities = []

        # Prepare for parallel computation
        tasks = []
        for param_name in parameter_names:
            tasks.append((param_name, base_parameters, objectives, adaptive_step_size))

        # Calculate gradients in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_param = {
                executor.submit(self._calculate_single_gradient, *task): task[0]
                for task in tasks
            }

            for future in as_completed(future_to_param):
                param_name = future_to_param[future]
                try:
                    sensitivity = future.result()
                    sensitivities.append(sensitivity)
                except Exception as e:
                    logger.warning(f"Failed to calculate sensitivity for {param_name}: {e}")
                    # Create a fallback sensitivity result
                    sensitivities.append(SensitivityResult(
                        parameter_name=param_name,
                        gradient=0.0,
                        relative_impact=0.0,
                        direction='neutral',
                        confidence=0.0,
                        numerical_stability=0.0
                    ))

        return sensitivities

    def _calculate_single_gradient(
        self,
        param_name: str,
        base_parameters: Dict[str, float],
        objectives: Dict[str, float],
        adaptive_step_size: bool
    ) -> SensitivityResult:
        """Calculate gradient for a single parameter."""
        base_value = base_parameters[param_name]
        base_objective = self._evaluate_objective_safe(base_parameters, objectives)

        # Determine step size
        step_size = self.step_size
        if adaptive_step_size:
            step_size = self._adaptive_step_size(param_name, base_value)

        # Forward difference
        forward_params = base_parameters.copy()
        forward_params[param_name] = self._clamp_parameter(
            param_name, base_value + step_size
        )
        forward_objective = self._evaluate_objective_safe(forward_params, objectives)

        # Backward difference
        backward_params = base_parameters.copy()
        backward_params[param_name] = self._clamp_parameter(
            param_name, base_value - step_size
        )
        backward_objective = self._evaluate_objective_safe(backward_params, objectives)

        # Central difference gradient
        gradient = (forward_objective - backward_objective) / (2 * step_size)

        # Calculate relative impact
        relative_impact = abs(gradient * base_value / base_objective) if base_objective != 0 else 0

        # Determine direction
        direction = 'decrease' if gradient < 0 else 'increase' if gradient > 0 else 'neutral'

        # Calculate confidence based on numerical stability
        confidence = self._calculate_gradient_confidence(
            base_objective, forward_objective, backward_objective, step_size
        )

        # Calculate numerical stability
        stability = self._calculate_numerical_stability(
            base_objective, forward_objective, backward_objective
        )

        return SensitivityResult(
            parameter_name=param_name,
            gradient=gradient,
            relative_impact=relative_impact,
            direction=direction,
            confidence=confidence,
            numerical_stability=stability
        )

    def _calculate_parameter_interactions(
        self,
        base_parameters: Dict[str, float],
        objectives: Dict[str, float]
    ) -> List[InteractionEffect]:
        """Calculate second-order parameter interactions (Hessian approximation)."""
        parameter_names = list(base_parameters.keys())
        interactions = []

        # Calculate interaction effects for all parameter pairs
        for i, param1 in enumerate(parameter_names):
            for j, param2 in enumerate(parameter_names[i+1:], i+1):
                interaction = self._calculate_interaction_effect(
                    param1, param2, base_parameters, objectives
                )
                if interaction:
                    interactions.append(interaction)

        return interactions

    def _calculate_interaction_effect(
        self,
        param1: str,
        param2: str,
        base_parameters: Dict[str, float],
        objectives: Dict[str, float]
    ) -> Optional[InteractionEffect]:
        """Calculate interaction effect between two parameters."""
        try:
            step_size = self.step_size

            # Base evaluation
            f_00 = self._evaluate_objective_safe(base_parameters, objectives)

            # Single parameter perturbations
            params_10 = base_parameters.copy()
            params_10[param1] = self._clamp_parameter(
                param1, base_parameters[param1] + step_size
            )
            f_10 = self._evaluate_objective_safe(params_10, objectives)

            params_01 = base_parameters.copy()
            params_01[param2] = self._clamp_parameter(
                param2, base_parameters[param2] + step_size
            )
            f_01 = self._evaluate_objective_safe(params_01, objectives)

            # Double perturbation
            params_11 = base_parameters.copy()
            params_11[param1] = self._clamp_parameter(
                param1, base_parameters[param1] + step_size
            )
            params_11[param2] = self._clamp_parameter(
                param2, base_parameters[param2] + step_size
            )
            f_11 = self._evaluate_objective_safe(params_11, objectives)

            # Second-order cross derivative (interaction effect)
            interaction_strength = (f_11 - f_10 - f_01 + f_00) / (step_size ** 2)

            # Classify interaction type
            if abs(interaction_strength) < 1e-6:
                interaction_type = 'neutral'
            elif interaction_strength > 0:
                interaction_type = 'synergistic'
            else:
                interaction_type = 'antagonistic'

            # Calculate confidence
            confidence = self._calculate_interaction_confidence(
                f_00, f_10, f_01, f_11, step_size
            )

            return InteractionEffect(
                parameter_1=param1,
                parameter_2=param2,
                interaction_strength=abs(interaction_strength),
                interaction_type=interaction_type,
                confidence=confidence
            )

        except Exception as e:
            logger.warning(f"Failed to calculate interaction between {param1} and {param2}: {e}")
            return None

    def _adaptive_step_size(self, param_name: str, base_value: float) -> float:
        """Calculate adaptive step size based on parameter characteristics."""
        # Get parameter bounds
        if param_name in self.parameter_bounds:
            min_val, max_val = self.parameter_bounds[param_name]
            param_range = max_val - min_val
            # Use 0.1% of parameter range as step size
            adaptive_step = param_range * 0.001
        else:
            # Fallback: use percentage of base value
            adaptive_step = abs(base_value) * 0.001 if base_value != 0 else self.step_size

        # Ensure minimum step size
        return max(adaptive_step, 1e-6)

    def _clamp_parameter(self, param_name: str, value: float) -> float:
        """Clamp parameter value to its defined bounds."""
        if param_name in self.parameter_bounds:
            min_val, max_val = self.parameter_bounds[param_name]
            return max(min_val, min(max_val, value))
        return value

    def _evaluate_objective_safe(
        self,
        parameters: Dict[str, float],
        objectives: Dict[str, float]
    ) -> float:
        """Safely evaluate objective function with error handling."""
        try:
            # Create cache key
            cache_key = self._create_cache_key(parameters, objectives)

            # Check cache first
            if cache_key in self._sensitivity_cache:
                return self._sensitivity_cache[cache_key]

            # Evaluate objective function
            result = self.objective_function(parameters)

            # Handle different return types
            if isinstance(result, dict):
                # Multi-objective case: combine using weights
                combined_result = 0.0
                total_weight = sum(objectives.values())
                if total_weight > 0:
                    for obj_name, weight in objectives.items():
                        if obj_name in result:
                            combined_result += (weight / total_weight) * result[obj_name]
                result = combined_result
            elif not isinstance(result, (int, float)):
                result = float(result)

            # Validate result
            if math.isnan(result) or math.isinf(result):
                result = 1e6  # Large penalty for invalid results

            # Cache result
            self._sensitivity_cache[cache_key] = result
            return result

        except Exception as e:
            logger.warning(f"Objective evaluation failed: {e}")
            return 1e6  # Large penalty for failed evaluations

    def _create_cache_key(
        self,
        parameters: Dict[str, float],
        objectives: Dict[str, float]
    ) -> str:
        """Create cache key for parameter/objective combination."""
        # Round values to avoid floating point precision issues
        rounded_params = {k: round(v, 8) for k, v in parameters.items()}
        rounded_objectives = {k: round(v, 8) for k, v in objectives.items()}

        import hashlib
        content = str(sorted(rounded_params.items())) + str(sorted(rounded_objectives.items()))
        return hashlib.md5(content.encode()).hexdigest()

    def _calculate_gradient_confidence(
        self,
        base_val: float,
        forward_val: float,
        backward_val: float,
        step_size: float
    ) -> float:
        """Calculate confidence in gradient calculation."""
        # Check for numerical stability
        if abs(base_val) < 1e-10:
            return 0.5  # Low confidence for near-zero base values

        # Check for reasonable derivative magnitude
        forward_diff = abs(forward_val - base_val)
        backward_diff = abs(backward_val - base_val)

        # If changes are too small relative to step size, low confidence
        relative_change = max(forward_diff, backward_diff) / abs(base_val)
        if relative_change < step_size * 0.1:
            return 0.3

        # If forward and backward give very different results, low confidence
        asymmetry = abs(forward_diff - backward_diff) / max(forward_diff, backward_diff, 1e-10)
        if asymmetry > 0.5:
            return 0.4

        return 0.9  # High confidence

    def _calculate_numerical_stability(
        self,
        base_val: float,
        forward_val: float,
        backward_val: float
    ) -> float:
        """Calculate numerical stability score for gradient calculation."""
        # Check for smooth behavior
        if abs(base_val) < 1e-10:
            return 0.5

        forward_ratio = forward_val / base_val if base_val != 0 else 1.0
        backward_ratio = backward_val / base_val if base_val != 0 else 1.0

        # Stability is higher when ratios are close to 1 and similar
        forward_stability = 1.0 / (1.0 + abs(forward_ratio - 1.0))
        backward_stability = 1.0 / (1.0 + abs(backward_ratio - 1.0))
        ratio_consistency = 1.0 / (1.0 + abs(forward_ratio - backward_ratio))

        return (forward_stability + backward_stability + ratio_consistency) / 3.0

    def _calculate_interaction_confidence(
        self,
        f_00: float,
        f_10: float,
        f_01: float,
        f_11: float,
        step_size: float
    ) -> float:
        """Calculate confidence in interaction effect calculation."""
        # Check if all evaluations are reasonable
        values = [f_00, f_10, f_01, f_11]
        if any(math.isnan(v) or math.isinf(v) for v in values):
            return 0.0

        # Check for numerical consistency
        max_val = max(values)
        min_val = min(values)
        if max_val == 0 or abs(max_val - min_val) / max_val < step_size:
            return 0.3

        return 0.8

    def _rank_parameters(
        self,
        sensitivities: List[SensitivityResult]
    ) -> List[Tuple[str, float]]:
        """Rank parameters by their relative impact."""
        rankings = []
        for sensitivity in sensitivities:
            # Combine relative impact with confidence
            importance_score = sensitivity.relative_impact * sensitivity.confidence
            rankings.append((sensitivity.parameter_name, importance_score))

        # Sort by importance score (descending)
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def _generate_recommendations(
        self,
        sensitivities: List[SensitivityResult],
        interactions: List[InteractionEffect],
        base_parameters: Dict[str, float]
    ) -> List[str]:
        """Generate optimization recommendations based on sensitivity analysis."""
        recommendations = []

        # Top sensitive parameters
        high_impact_params = [
            s for s in sensitivities
            if s.relative_impact > 0.1 and s.confidence > 0.5
        ]

        if high_impact_params:
            recommendations.append(
                f"Focus optimization on {len(high_impact_params)} high-impact parameters: " +
                ", ".join([p.parameter_name for p in high_impact_params[:3]])
            )

        # Direction recommendations
        for sensitivity in sensitivities[:3]:  # Top 3 parameters
            if sensitivity.confidence > 0.6:
                if sensitivity.direction == 'decrease':
                    recommendations.append(
                        f"Consider decreasing {sensitivity.parameter_name} to improve objective"
                    )
                elif sensitivity.direction == 'increase':
                    recommendations.append(
                        f"Consider increasing {sensitivity.parameter_name} to improve objective"
                    )

        # Interaction recommendations
        strong_interactions = [
            i for i in interactions
            if i.interaction_strength > 0.01 and i.confidence > 0.5
        ]

        if strong_interactions:
            recommendations.append(
                f"Found {len(strong_interactions)} significant parameter interactions - " +
                "consider adjusting parameters together rather than independently"
            )

        # Stability warnings
        unstable_params = [
            s.parameter_name for s in sensitivities
            if s.numerical_stability < 0.5
        ]

        if unstable_params:
            recommendations.append(
                f"Exercise caution with {', '.join(unstable_params[:3])} - " +
                "these parameters show numerical instability"
            )

        return recommendations

    def _calculate_overall_stability(
        self,
        sensitivities: List[SensitivityResult]
    ) -> float:
        """Calculate overall numerical stability score."""
        if not sensitivities:
            return 0.0

        stability_scores = [s.numerical_stability for s in sensitivities]
        return np.mean(stability_scores)

    def _get_function_evaluation_count(self) -> int:
        """Get total function evaluations performed."""
        # This would track actual function evaluations
        # For now, estimate based on cache size
        return len(self._sensitivity_cache)

    def _store_analysis_results(self, report: SensitivityAnalysisReport):
        """Store sensitivity analysis results in database."""
        analysis_id = report.analysis_metadata["analysis_id"]

        with self.duckdb_resource.get_connection() as conn:
            # Store main analysis record
            conn.execute("""
                INSERT INTO sensitivity_analysis_history (
                    analysis_id, timestamp, base_params_json, base_objective_value,
                    total_parameters, analysis_runtime_seconds, step_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                analysis_id,
                report.timestamp,
                str(report.base_parameters),
                report.base_objective_value,
                len(report.parameter_sensitivities),
                report.analysis_metadata["runtime_seconds"],
                report.analysis_metadata["step_size"]
            ])

            # Store parameter sensitivities
            for sensitivity in report.parameter_sensitivities:
                conn.execute("""
                    INSERT INTO parameter_sensitivities (
                        analysis_id, parameter_name, gradient, relative_impact,
                        direction, confidence, numerical_stability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [
                    analysis_id,
                    sensitivity.parameter_name,
                    sensitivity.gradient,
                    sensitivity.relative_impact,
                    sensitivity.direction,
                    sensitivity.confidence,
                    sensitivity.numerical_stability
                ])

            # Store interactions
            for interaction in report.interaction_effects:
                conn.execute("""
                    INSERT INTO parameter_interactions (
                        analysis_id, parameter_1, parameter_2, interaction_strength,
                        interaction_type, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, [
                    analysis_id,
                    interaction.parameter_1,
                    interaction.parameter_2,
                    interaction.interaction_strength,
                    interaction.interaction_type,
                    interaction.confidence
                ])

    def get_historical_sensitivity_trends(
        self,
        parameter_name: str,
        days_back: int = 30
    ) -> pd.DataFrame:
        """Get historical sensitivity trends for a parameter."""
        with self.duckdb_resource.get_connection() as conn:
            return conn.execute("""
                SELECT
                    h.timestamp,
                    s.gradient,
                    s.relative_impact,
                    s.confidence,
                    s.numerical_stability
                FROM sensitivity_analysis_history h
                JOIN parameter_sensitivities s ON h.analysis_id = s.analysis_id
                WHERE s.parameter_name = ?
                AND h.timestamp >= CURRENT_TIMESTAMP - INTERVAL ? DAY
                ORDER BY h.timestamp DESC
            """, [parameter_name, days_back]).df()

    def clear_cache(self):
        """Clear sensitivity analysis cache."""
        self._sensitivity_cache.clear()
