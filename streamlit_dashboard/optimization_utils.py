"""
Optimization Utilities for PlanWise Navigator

This module provides utility functions for parameter conversion, result formatting,
and integration between different optimization interfaces.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime, date
import pandas as pd
import numpy as np
import json
import streamlit as st
from pathlib import Path

# Import optimization storage and schemas
from .optimization_storage import (
    OptimizationRun, OptimizationMetadata, OptimizationConfiguration,
    OptimizationResults, OptimizationObjective, OptimizationType,
    OptimizationEngine, OptimizationStatus, ExportFormat,
    get_optimization_storage
)
from .optimization_schemas import get_parameter_schema, RiskLevel


class ParameterConverter:
    """Converts parameters between different interface formats."""

    @staticmethod
    def advanced_optimization_to_unified(
        params: Dict[str, float],
        objectives: Dict[str, float],
        algorithm: str,
        scenario_id: str,
        **kwargs
    ) -> OptimizationRun:
        """Convert advanced_optimization.py format to unified format."""

        # Create metadata
        metadata = OptimizationMetadata(
            scenario_id=scenario_id,
            optimization_type=OptimizationType.ADVANCED_SCIPY,
            optimization_engine=OptimizationEngine.SCIPY_SLSQP if algorithm == "SLSQP" else OptimizationEngine.SCIPY_DE,
            status=OptimizationStatus.DRAFT,
            random_seed=kwargs.get('random_seed'),
            max_evaluations=kwargs.get('max_evaluations'),
            timeout_minutes=kwargs.get('timeout_minutes'),
            use_synthetic_mode=kwargs.get('use_synthetic', False),
            description=f"Advanced optimization run - {algorithm}"
        )

        # Create objectives
        objective_list = []
        for name, weight in objectives.items():
            objective_list.append(OptimizationObjective(
                name=name,
                weight=weight,
                direction="minimize",
                description=f"{name.title()} optimization objective"
            ))

        # Create configuration
        schema = get_parameter_schema()
        parameter_bounds = {}
        for param_name in params.keys():
            param_def = schema.get_parameter(param_name)
            if param_def:
                parameter_bounds[param_name] = (
                    param_def.bounds.min_value,
                    param_def.bounds.max_value
                )

        configuration = OptimizationConfiguration(
            objectives=objective_list,
            initial_parameters=params,
            parameter_bounds=parameter_bounds,
            algorithm_config={
                'method': algorithm,
                'max_evaluations': kwargs.get('max_evaluations', 100),
                'tolerance': kwargs.get('tolerance', 1e-6)
            }
        )

        # Create empty results (to be filled later)
        results = OptimizationResults()

        return OptimizationRun(
            metadata=metadata,
            configuration=configuration,
            results=results
        )

    @staticmethod
    def compensation_tuning_to_unified(
        params: Dict[str, Dict[int, float]],
        scenario_id: str,
        apply_mode: str = "Single Year",
        target_year: int = 2025,
        **kwargs
    ) -> OptimizationRun:
        """Convert compensation_tuning.py format to unified format."""

        # Convert nested parameter format to flat format
        flat_params = {}
        schema = get_parameter_schema()

        # Convert merit rates
        if 'merit_base' in params:
            for level, value in params['merit_base'].items():
                flat_params[f"merit_rate_level_{level}"] = value

        # Convert COLA rate (uniform across levels)
        if 'cola_rate' in params and params['cola_rate']:
            flat_params['cola_rate'] = list(params['cola_rate'].values())[0]

        # Convert new hire adjustment
        if 'new_hire_salary_adjustment' in params and params['new_hire_salary_adjustment']:
            flat_params['new_hire_salary_adjustment'] = list(params['new_hire_salary_adjustment'].values())[0]

        # Convert promotion parameters
        for param_type in ['promotion_probability', 'promotion_raise']:
            if param_type in params:
                for level, value in params[param_type].items():
                    flat_params[f"{param_type}_level_{level}"] = value

        # Create metadata
        metadata = OptimizationMetadata(
            scenario_id=scenario_id,
            optimization_type=OptimizationType.COMPENSATION_TUNING,
            optimization_engine=OptimizationEngine.MANUAL,
            status=OptimizationStatus.DRAFT,
            random_seed=kwargs.get('random_seed', 42),
            description=f"Compensation tuning - {apply_mode} - Year {target_year}",
            tags=['compensation_tuning', apply_mode.lower().replace(' ', '_'), f"year_{target_year}"]
        )

        # Create single objective (budget optimization)
        objectives = [OptimizationObjective(
            name="budget_optimization",
            weight=1.0,
            direction="minimize",
            description="Optimize compensation parameters within budget constraints"
        )]

        # Create configuration
        parameter_bounds = {}
        for param_name in flat_params.keys():
            param_def = schema.get_parameter(param_name)
            if param_def:
                parameter_bounds[param_name] = (
                    param_def.bounds.min_value,
                    param_def.bounds.max_value
                )

        configuration = OptimizationConfiguration(
            objectives=objectives,
            initial_parameters=flat_params,
            parameter_bounds=parameter_bounds,
            algorithm_config={
                'apply_mode': apply_mode,
                'target_year': target_year,
                'years': kwargs.get('target_years', [target_year])
            }
        )

        # Create empty results
        results = OptimizationResults()

        return OptimizationRun(
            metadata=metadata,
            configuration=configuration,
            results=results
        )

    @staticmethod
    def unified_to_advanced_optimization(run: OptimizationRun) -> Dict[str, Any]:
        """Convert unified format back to advanced_optimization.py format."""
        return {
            'scenario_id': run.metadata.scenario_id,
            'algorithm': run.metadata.optimization_engine.value.replace('scipy_', '').upper(),
            'parameters': run.results.optimal_parameters or run.configuration.initial_parameters,
            'objectives': {
                obj.name: obj.weight for obj in run.configuration.objectives
            },
            'objective_value': run.results.objective_value,
            'converged': run.metadata.converged,
            'function_evaluations': run.metadata.function_evaluations,
            'runtime_seconds': run.metadata.runtime_seconds,
            'risk_level': run.results.risk_level
        }

    @staticmethod
    def unified_to_compensation_tuning(run: OptimizationRun) -> Dict[str, Any]:
        """Convert unified format back to compensation_tuning.py format."""
        params = run.results.optimal_parameters or run.configuration.initial_parameters

        # Convert flat format to nested format
        result = {
            'merit_base': {},
            'cola_rate': {},
            'new_hire_salary_adjustment': {},
            'promotion_probability': {},
            'promotion_raise': {}
        }

        # Extract merit rates by level
        for level in range(1, 6):
            merit_key = f"merit_rate_level_{level}"
            if merit_key in params:
                result['merit_base'][level] = params[merit_key]

        # Extract COLA rate (uniform)
        if 'cola_rate' in params:
            for level in range(1, 6):
                result['cola_rate'][level] = params['cola_rate']

        # Extract new hire adjustment
        if 'new_hire_salary_adjustment' in params:
            for level in range(1, 6):
                result['new_hire_salary_adjustment'][level] = params['new_hire_salary_adjustment']

        # Extract promotion parameters
        for level in range(1, 6):
            prob_key = f"promotion_probability_level_{level}"
            raise_key = f"promotion_raise_level_{level}"

            if prob_key in params:
                result['promotion_probability'][level] = params[prob_key]

            if raise_key in params:
                result['promotion_raise'][level] = params[raise_key]

        return result


class ResultFormatter:
    """Formats optimization results for display in different interfaces."""

    @staticmethod
    def format_for_streamlit_metrics(run: OptimizationRun) -> Dict[str, Any]:
        """Format results for Streamlit metric displays."""
        metadata = run.metadata
        results = run.results

        return {
            'summary_metrics': {
                'Run ID': metadata.run_id[:8] + "...",
                'Status': metadata.status.value.title(),
                'Algorithm': metadata.optimization_engine.value.replace('_', ' ').title(),
                'Runtime': f"{metadata.runtime_seconds:.1f}s" if metadata.runtime_seconds else "N/A",
                'Converged': "✅ Yes" if metadata.converged else "❌ No",
                'Evaluations': str(metadata.function_evaluations) if metadata.function_evaluations else "N/A"
            },
            'objective_metrics': {
                'Objective Value': f"{results.objective_value:.6f}" if results.objective_value else "N/A",
                'Risk Level': results.risk_level,
                'Warnings': len(results.parameter_warnings),
                'Violations': len(results.constraint_violations)
            },
            'business_metrics': {
                'Cost Impact': results.estimated_cost_impact.get('value', 'N/A') if results.estimated_cost_impact else 'N/A',
                'Employees Affected': results.estimated_employee_impact.get('count', 'N/A') if results.estimated_employee_impact else 'N/A',
                'Confidence': results.estimated_cost_impact.get('confidence', 'N/A') if results.estimated_cost_impact else 'N/A'
            }
        }

    @staticmethod
    def format_parameters_table(run: OptimizationRun) -> pd.DataFrame:
        """Format parameters as a comparison table."""
        initial_params = run.configuration.initial_parameters
        optimal_params = run.results.optimal_parameters or initial_params

        schema = get_parameter_schema()

        data = []
        for param_name in optimal_params.keys():
            param_def = schema.get_parameter(param_name)
            initial_value = initial_params.get(param_name, 0)
            optimal_value = optimal_params[param_name]
            change = optimal_value - initial_value
            change_pct = (change / initial_value * 100) if initial_value != 0 else 0

            data.append({
                'Parameter': param_def.display_name if param_def else param_name,
                'Initial Value': f"{initial_value:.4f}",
                'Optimal Value': f"{optimal_value:.4f}",
                'Change': f"{change:+.4f}",
                'Change %': f"{change_pct:+.2f}%",
                'Unit': param_def.unit.value if param_def else "unknown",
                'Category': param_def.category.value if param_def else "unknown"
            })

        return pd.DataFrame(data)

    @staticmethod
    def format_objective_breakdown(run: OptimizationRun) -> pd.DataFrame:
        """Format objective breakdown as a table."""
        objectives_config = {obj.name: obj.weight for obj in run.configuration.objectives}
        objectives_values = run.results.objective_breakdown

        data = []
        for name, weight in objectives_config.items():
            value = objectives_values.get(name, 0)
            weighted_value = value * weight

            data.append({
                'Objective': name.title(),
                'Weight': f"{weight:.3f}",
                'Raw Value': f"{value:.6f}",
                'Weighted Value': f"{weighted_value:.6f}",
                'Contribution %': f"{(weighted_value / run.results.objective_value * 100):.1f}%" if run.results.objective_value else "N/A"
            })

        return pd.DataFrame(data)

    @staticmethod
    def format_risk_assessment(run: OptimizationRun) -> Dict[str, Any]:
        """Format risk assessment for display."""
        results = run.results

        # Risk level colors
        risk_colors = {
            'LOW': '🟢',
            'MEDIUM': '🟡',
            'HIGH': '🟠',
            'CRITICAL': '🔴'
        }

        # Risk messages
        risk_messages = {
            'LOW': 'Parameters are within safe ranges and recommended for implementation.',
            'MEDIUM': 'Parameters require review but are generally acceptable with monitoring.',
            'HIGH': 'Parameters are aggressive and require careful evaluation before implementation.',
            'CRITICAL': 'Parameters pose significant risks and should not be implemented without thorough review.'
        }

        return {
            'level': results.risk_level,
            'icon': risk_colors.get(results.risk_level, '⚪'),
            'message': risk_messages.get(results.risk_level, 'Unknown risk level'),
            'warnings': results.parameter_warnings,
            'violations': results.constraint_violations,
            'assessment_details': results.risk_assessment
        }

    @staticmethod
    def create_parameter_comparison_chart_data(run: OptimizationRun) -> Dict[str, Any]:
        """Create data for parameter comparison charts."""
        initial_params = run.configuration.initial_parameters
        optimal_params = run.results.optimal_parameters or initial_params

        # Group parameters by category
        schema = get_parameter_schema()
        categories = {}

        for param_name in optimal_params.keys():
            param_def = schema.get_parameter(param_name)
            if param_def:
                category = param_def.category.value
                if category not in categories:
                    categories[category] = {
                        'parameters': [],
                        'initial_values': [],
                        'optimal_values': [],
                        'changes': []
                    }

                initial_value = initial_params.get(param_name, 0)
                optimal_value = optimal_params[param_name]
                change = optimal_value - initial_value

                categories[category]['parameters'].append(param_def.display_name)
                categories[category]['initial_values'].append(initial_value)
                categories[category]['optimal_values'].append(optimal_value)
                categories[category]['changes'].append(change)

        return categories


class SessionStateIntegration:
    """Manages integration with Streamlit session state."""

    @staticmethod
    def save_current_optimization(run: OptimizationRun, interface_type: str = "advanced"):
        """Save current optimization to session state."""
        if 'optimization_results' not in st.session_state:
            st.session_state.optimization_results = {}

        st.session_state.optimization_results[interface_type] = run
        st.session_state.last_optimization_run_id = run.metadata.run_id
        st.session_state.last_optimization_interface = interface_type

    @staticmethod
    def load_current_optimization(interface_type: str = "advanced") -> Optional[OptimizationRun]:
        """Load current optimization from session state."""
        if 'optimization_results' not in st.session_state:
            return None

        return st.session_state.optimization_results.get(interface_type)

    @staticmethod
    def get_recent_optimizations(limit: int = 5) -> List[OptimizationRun]:
        """Get recent optimizations from session state and storage."""
        storage = get_optimization_storage()
        recent_metadata = storage.get_recent_runs(limit)

        recent_runs = []
        for metadata in recent_metadata:
            run = storage.load_run_with_session_cache(metadata.run_id)
            if run:
                recent_runs.append(run)

        return recent_runs

    @staticmethod
    def clear_optimization_cache():
        """Clear optimization cache from session state."""
        if 'optimization_results' in st.session_state:
            del st.session_state.optimization_results

        if 'last_optimization_run_id' in st.session_state:
            del st.session_state.last_optimization_run_id

        if 'last_optimization_interface' in st.session_state:
            del st.session_state.last_optimization_interface

        # Clear storage cache too
        storage = get_optimization_storage()
        storage.clear_session_cache()


class ValidationUtils:
    """Utilities for parameter validation and risk assessment."""

    @staticmethod
    def validate_optimization_run(run: OptimizationRun) -> Dict[str, Any]:
        """Comprehensive validation of an optimization run."""
        schema = get_parameter_schema()
        params = run.results.optimal_parameters or run.configuration.initial_parameters

        validation_results = schema.validate_parameter_set(params)

        # Add business rules validation
        business_warnings = []
        business_errors = []

        # Check for extreme parameter combinations
        if 'merit_rate_level_1' in params and 'cola_rate' in params:
            total_compensation_increase = params['merit_rate_level_1'] + params['cola_rate']
            if total_compensation_increase > 0.15:  # 15%
                business_warnings.append("Combined merit and COLA rates exceed 15% - may impact budget significantly")

        # Check promotion probability consistency
        promo_probs = [params.get(f"promotion_probability_level_{i}", 0) for i in range(1, 6)]
        if any(promo_probs[i] > promo_probs[i-1] for i in range(1, len(promo_probs))):
            business_warnings.append("Higher-level positions have higher promotion probabilities than lower levels - check for logical consistency")

        # Check new hire premium reasonableness
        if 'new_hire_salary_adjustment' in params:
            if params['new_hire_salary_adjustment'] > 1.25:  # 25% premium
                business_warnings.append("New hire salary adjustment above 25% may indicate market competitiveness issues")

        validation_results['business_warnings'] = business_warnings
        validation_results['business_errors'] = business_errors

        return validation_results

    @staticmethod
    def calculate_parameter_sensitivity(run: OptimizationRun) -> Dict[str, float]:
        """Calculate parameter sensitivity scores."""
        if not run.results.parameter_history or len(run.results.parameter_history) < 2:
            return {}

        # Calculate variance of each parameter during optimization
        history_df = pd.DataFrame(run.results.parameter_history)
        sensitivity_scores = {}

        for param in history_df.columns:
            variance = history_df[param].var()
            mean_value = history_df[param].mean()

            # Normalize by mean to get coefficient of variation
            if mean_value != 0:
                sensitivity_scores[param] = variance / (mean_value ** 2)
            else:
                sensitivity_scores[param] = 0

        return sensitivity_scores

    @staticmethod
    def assess_business_impact(run: OptimizationRun) -> Dict[str, Any]:
        """Assess potential business impact of optimization results."""
        params = run.results.optimal_parameters or run.configuration.initial_parameters

        # Mock business impact calculation (would integrate with simulation results in practice)
        total_merit_impact = sum(params.get(f"merit_rate_level_{i}", 0) for i in range(1, 6))
        cola_impact = params.get('cola_rate', 0) * 5  # Applied to all levels

        estimated_cost_impact = {
            'value': (total_merit_impact + cola_impact) * 1000000,  # Mock $1M per percentage point
            'confidence': 'Medium',
            'range': [0.8, 1.2]  # 80%-120% confidence interval
        }

        estimated_employee_impact = {
            'count': 1200,  # Mock employee count
            'percentage': 85.0,
            'risk_level': run.results.risk_level
        }

        return {
            'estimated_cost_impact': estimated_cost_impact,
            'estimated_employee_impact': estimated_employee_impact
        }


# Utility functions for backward compatibility
def convert_legacy_results(legacy_results: Dict[str, Any], interface_type: str) -> OptimizationRun:
    """Convert legacy optimization results to unified format."""
    if interface_type == "advanced_optimization":
        return ParameterConverter.advanced_optimization_to_unified(
            params=legacy_results.get('parameters', {}),
            objectives=legacy_results.get('objectives', {}),
            algorithm=legacy_results.get('algorithm', 'SLSQP'),
            scenario_id=legacy_results.get('scenario_id', 'legacy_import')
        )
    elif interface_type == "compensation_tuning":
        return ParameterConverter.compensation_tuning_to_unified(
            params=legacy_results.get('parameters', {}),
            scenario_id=legacy_results.get('scenario_id', 'legacy_import')
        )
    else:
        raise ValueError(f"Unknown interface type: {interface_type}")


def export_optimization_summary(run: OptimizationRun, format: str = "markdown") -> str:
    """Export optimization summary in specified format."""
    if format == "markdown":
        return _create_markdown_summary(run)
    elif format == "html":
        return _create_html_summary(run)
    else:
        raise ValueError(f"Unsupported format: {format}")


def _create_markdown_summary(run: OptimizationRun) -> str:
    """Create markdown summary of optimization run."""
    metadata = run.metadata
    results = run.results

    summary = f"""# Optimization Run Summary

## Metadata
- **Run ID**: {metadata.run_id}
- **Scenario**: {metadata.scenario_id}
- **Type**: {metadata.optimization_type.value}
- **Engine**: {metadata.optimization_engine.value}
- **Status**: {metadata.status.value}
- **Created**: {metadata.created_at.strftime('%Y-%m-%d %H:%M:%S')}
- **Runtime**: {metadata.runtime_seconds:.1f}s (if metadata.runtime_seconds else "N/A")

## Results
- **Objective Value**: {results.objective_value:.6f if results.objective_value else "N/A"}
- **Risk Level**: {results.risk_level}
- **Converged**: {"Yes" if metadata.converged else "No"}
- **Function Evaluations**: {metadata.function_evaluations or "N/A"}

## Optimal Parameters
"""

    # Add parameter table
    params_table = ResultFormatter.format_parameters_table(run)
    summary += params_table.to_markdown(index=False)

    # Add warnings if any
    if results.parameter_warnings:
        summary += "\n\n## Warnings\n"
        for warning in results.parameter_warnings:
            summary += f"- {warning}\n"

    return summary


def _create_html_summary(run: OptimizationRun) -> str:
    """Create HTML summary of optimization run."""
    # This would create an HTML version of the summary
    # For brevity, just convert markdown to basic HTML
    markdown_summary = _create_markdown_summary(run)

    # Basic markdown to HTML conversion
    html = markdown_summary.replace('\n## ', '\n<h2>').replace('\n# ', '\n<h1>')
    html = html.replace('##', '</h2>').replace('#', '</h1>')
    html = f"<html><body>{html}</body></html>"

    return html


if __name__ == "__main__":
    # Test the utility functions
    print("Testing optimization utilities...")

    # Test parameter conversion
    test_params = {
        'merit_rate_level_1': 0.045,
        'merit_rate_level_2': 0.040,
        'cola_rate': 0.025
    }

    test_objectives = {
        'cost': 0.4,
        'equity': 0.3,
        'targets': 0.3
    }

    # Convert to unified format
    run = ParameterConverter.advanced_optimization_to_unified(
        params=test_params,
        objectives=test_objectives,
        algorithm="SLSQP",
        scenario_id="test_scenario"
    )

    print(f"Created optimization run: {run.metadata.run_id}")
    print(f"Parameters: {len(run.configuration.initial_parameters)}")
    print(f"Objectives: {len(run.configuration.objectives)}")

    # Test result formatting
    metrics = ResultFormatter.format_for_streamlit_metrics(run)
    print(f"Formatted metrics: {list(metrics.keys())}")

    print("All tests passed!")
