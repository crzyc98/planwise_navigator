"""
Sensitivity analysis for optimization parameters.

Calculates parameter sensitivities and provides insights into
which parameters have the most impact on objectives.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, Any, List, Tuple
from orchestrator.resources.duckdb_resource import DuckDBResource
from .objective_functions import ObjectiveFunctions

class SensitivityAnalyzer:
    """Parameter sensitivity analysis for compensation optimization."""

    def __init__(self, duckdb_resource: DuckDBResource, scenario_id: str):
        self.duckdb_resource = duckdb_resource
        self.scenario_id = scenario_id
        self.obj_funcs = ObjectiveFunctions(duckdb_resource, scenario_id)

    def calculate_sensitivities(
        self,
        parameters: Dict[str, float],
        objectives: Dict[str, float],
        perturbation_pct: float = 0.01
    ) -> Dict[str, float]:
        """
        Calculate parameter sensitivities using finite differences.

        Args:
            parameters: Base parameter values
            objectives: Objective weights
            perturbation_pct: Percentage perturbation for sensitivity calculation

        Returns:
            Dictionary of parameter sensitivities
        """

        # Calculate baseline objective value
        baseline_value = self.obj_funcs.combined_objective(parameters, objectives)

        sensitivities = {}

        for param_name, base_value in parameters.items():
            # Calculate perturbation amount
            perturbation = base_value * perturbation_pct
            if perturbation == 0:
                perturbation = 0.001  # Minimum perturbation for zero values

            # Create perturbed parameters
            perturbed_params = parameters.copy()
            perturbed_params[param_name] = base_value + perturbation

            try:
                # Calculate perturbed objective value
                perturbed_value = self.obj_funcs.combined_objective(perturbed_params, objectives)

                # Calculate sensitivity (derivative approximation)
                sensitivity = (perturbed_value - baseline_value) / perturbation
                sensitivities[param_name] = sensitivity

            except Exception as e:
                # Handle evaluation failures
                sensitivities[param_name] = 0.0

        return sensitivities

    def rank_parameter_importance(
        self,
        sensitivities: Dict[str, float]
    ) -> List[Tuple[str, float]]:
        """
        Rank parameters by importance (absolute sensitivity).

        Args:
            sensitivities: Parameter sensitivity values

        Returns:
            List of (parameter_name, importance_score) sorted by importance
        """

        # Calculate importance as absolute sensitivity
        importance_scores = [
            (param_name, abs(sensitivity))
            for param_name, sensitivity in sensitivities.items()
        ]

        # Sort by importance (descending)
        importance_scores.sort(key=lambda x: x[1], reverse=True)

        return importance_scores

    def generate_sensitivity_report(
        self,
        parameters: Dict[str, float],
        objectives: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive sensitivity analysis report.

        Args:
            parameters: Base parameter values
            objectives: Objective weights

        Returns:
            Comprehensive sensitivity report
        """

        # Calculate sensitivities
        sensitivities = self.calculate_sensitivities(parameters, objectives)

        # Rank parameters
        importance_ranking = self.rank_parameter_importance(sensitivities)

        # Calculate statistics
        sensitivity_values = list(sensitivities.values())

        report = {
            "parameter_sensitivities": sensitivities,
            "importance_ranking": importance_ranking,
            "sensitivity_statistics": {
                "mean_sensitivity": np.mean(np.abs(sensitivity_values)),
                "max_sensitivity": max(np.abs(sensitivity_values)) if sensitivity_values else 0.0,
                "min_sensitivity": min(np.abs(sensitivity_values)) if sensitivity_values else 0.0,
                "std_sensitivity": np.std(sensitivity_values) if sensitivity_values else 0.0
            },
            "most_sensitive_parameters": importance_ranking[:5],  # Top 5
            "least_sensitive_parameters": importance_ranking[-5:] if len(importance_ranking) >= 5 else [],
            "recommendations": self._generate_sensitivity_recommendations(importance_ranking)
        }

        return report

    def _generate_sensitivity_recommendations(
        self,
        importance_ranking: List[Tuple[str, float]]
    ) -> List[str]:
        """Generate recommendations based on sensitivity analysis."""

        recommendations = []

        if not importance_ranking:
            return ["No parameters analyzed"]

        # Most important parameter
        most_important = importance_ranking[0]
        recommendations.append(
            f"Focus optimization on '{most_important[0]}' - highest impact parameter"
        )

        # Check for parameters with very low sensitivity
        low_sensitivity_threshold = 0.001
        low_sensitivity_params = [
            name for name, importance in importance_ranking
            if importance < low_sensitivity_threshold
        ]

        if low_sensitivity_params:
            recommendations.append(
                f"Consider fixing these low-impact parameters: {', '.join(low_sensitivity_params[:3])}"
            )

        # Check for high-variance parameters
        sensitivities = [importance for _, importance in importance_ranking]
        if len(sensitivities) > 1:
            sensitivity_range = max(sensitivities) - min(sensitivities)
            if sensitivity_range > 0.1:
                recommendations.append(
                    "High sensitivity variance detected - prioritize most important parameters"
                )

        return recommendations
