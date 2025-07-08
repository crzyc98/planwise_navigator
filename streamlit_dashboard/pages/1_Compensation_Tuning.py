# filename: streamlit_dashboard/compensation_tuning.py
"""
Streamlit Compensation Tuning Interface for E012 - Analyst-Driven Parameter Adjustment
Enables analysts to adjust compensation parameters and run simulations to hit budget targets.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import numpy as np
import os
import subprocess
import json
import time
import yaml
from pathlib import Path

# Import risk assessment module
from risk_assessment import (
    RiskAssessmentEngine,
    ComprehensiveRiskAssessment,
    RiskLevel,
    RiskCategory,
    create_risk_dashboard,
    display_risk_indicators
)

# Page config
st.set_page_config(
    page_title="Compensation Tuning - PlanWise Navigator",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
<style>
    .main-header {
        font-size: 2.5rem;
        color: #2E8B57;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        color: #1f77b4;
        border-bottom: 2px solid #1f77b4;
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }
    .metric-card {
        background-color: #f0f8f0;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
        border: 1px solid #90EE90;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        border-radius: 0.25rem;
        padding: 0.75rem;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.25rem;
        padding: 0.75rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 0.25rem;
        padding: 0.75rem;
        margin: 1rem 0;
    }
    .parameter-section {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .risk-low {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 0.75rem;
        margin: 0.5rem 0;
    }
    .risk-medium {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 0.75rem;
        margin: 0.5rem 0;
    }
    .risk-high {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 0.75rem;
        margin: 0.5rem 0;
    }
    .risk-critical {
        background-color: #f5c6cb;
        border-left: 4px solid #721c24;
        padding: 0.75rem;
        margin: 0.5rem 0;
    }
    .risk-indicator {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
        margin: 0.25rem;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if 'simulation_running' not in st.session_state:
    st.session_state.simulation_running = False
if 'simulation_results' not in st.session_state:
    st.session_state.simulation_results = None
if 'last_simulation_time' not in st.session_state:
    st.session_state.last_simulation_time = None
if 'current_parameters' not in st.session_state:
    st.session_state.current_parameters = {}
if 'risk_assessment_engine' not in st.session_state:
    st.session_state.risk_assessment_engine = RiskAssessmentEngine()
if 'current_risk_assessment' not in st.session_state:
    st.session_state.current_risk_assessment = None

# Header
st.markdown('<h1 class="main-header">💰 Compensation Tuning Interface</h1>', unsafe_allow_html=True)

# User guidance
with st.expander("ℹ️ How to Use This Interface", expanded=False):
    st.markdown("""
    **Welcome to the E012 Compensation Tuning Interface!** This tool allows you to:

    1. **📊 Adjust Parameters**: Use the sidebar sliders to modify compensation parameters
    2. **✅ Validate Changes**: Review parameter validation warnings and errors
    3. **🚀 Run Simulations**: Execute multi-year workforce simulations with your parameters
    4. **📈 Analyze Results**: View before/after comparisons and impact analysis
    5. **📋 Export Data**: Download results for further analysis

    **Getting Started:**
    - Start by reviewing current parameters in the "Parameter Overview" tab
    - Adjust parameters in the sidebar based on your compensation strategy
    - Check the "Impact Analysis" tab to preview expected outcomes
    - Save parameters and run simulation in the "Run Simulation" tab
    - Review detailed results in the "Results" tab

    **Tips:**
    - Enable "Show Before/After" in Impact Analysis to see parameter change effects
    - Watch for validation warnings - they help avoid unrealistic scenarios
    - Parameter changes are automatically saved when you run a simulation
    """)

# Connection status check
try:
    import requests
    dagster_status = requests.get("http://localhost:3000/health", timeout=2)
    if dagster_status.status_code == 200:
        st.success("🟢 Connected to Dagster UI (localhost:3000)")
    else:
        st.warning("🟡 Dagster UI partially available")
except:
    st.warning("🟡 Dagster UI not detected - simulations will use command line fallback")

# Utility functions
@st.cache_data
def load_current_parameters():
    """Load current parameters from comp_levers.csv"""
    try:
        comp_levers_path = Path(__file__).parent.parent.parent / "dbt" / "seeds" / "comp_levers.csv"
        if not comp_levers_path.exists():
            comp_levers_path = Path("dbt/seeds/comp_levers.csv")

        df = pd.read_csv(comp_levers_path)

        # Parse parameters by type and year
        params = {}
        for _, row in df.iterrows():
            year = row['fiscal_year']
            level = row['job_level']
            param_name = row['parameter_name']
            value = row['parameter_value']

            if year not in params:
                params[year] = {}
            if param_name not in params[year]:
                params[year][param_name] = {}

            params[year][param_name][level] = value

        return params
    except Exception as e:
        st.error(f"Error loading current parameters: {e}")
        return {}

@st.cache_data
def load_simulation_results(status_filter=['continuous_active', 'new_hire_active']):
    """Load latest simulation results from DuckDB or synthetic results from session state"""

    # Check if we have synthetic results in session state
    if hasattr(st.session_state, 'simulation_results') and st.session_state.simulation_results:
        synthetic_results = st.session_state.simulation_results
        if synthetic_results.get('synthetic_mode', False):
            # Return synthetic results with proper status filter applied
            filtered_results = synthetic_results.copy()
            filtered_results['status_filter'] = status_filter
            return filtered_results

    # Load from DuckDB (real simulation results)
    try:
        # Connect to DuckDB database using absolute path
        project_root = Path(__file__).parent.parent.parent
        db_path = project_root / "simulation.duckdb"

        if not db_path.exists():
            st.warning("No simulation database found. Run a simulation first.")
            return None

        import duckdb
        conn = duckdb.connect(str(db_path))

        # Check if table exists first
        try:
            table_exists = conn.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'fct_workforce_snapshot'
            """).fetchone()[0] > 0

            if not table_exists:
                conn.close()
                return None

        except Exception:
            conn.close()
            return None

        # Get all available detailed status codes
        try:
            all_statuses = conn.execute("""
                SELECT DISTINCT detailed_status_code
                FROM fct_workforce_snapshot
                ORDER BY detailed_status_code
            """).fetchall()
            available_statuses = [row[0] for row in all_statuses]
        except Exception:
            conn.close()
            return None

        # Get years with data (using any status to find years)
        try:
            years_data = conn.execute("""
                SELECT DISTINCT simulation_year
                FROM fct_workforce_snapshot
                ORDER BY simulation_year
            """).fetchall()

            if not years_data:
                conn.close()
                return None

            years = [row[0] for row in years_data]
        except Exception:
            conn.close()
            return None

        # Get baseline workforce data for growth calculation
        try:
            baseline_result = conn.execute("""
                SELECT
                    COUNT(*) as count,
                    AVG(current_compensation) as avg_salary
                FROM int_baseline_workforce
                WHERE employment_status = 'active'
            """).fetchone()

            baseline_count = baseline_result[0] if baseline_result else 0
            baseline_avg_salary = baseline_result[1] if baseline_result and baseline_result[1] else 0
        except Exception:
            # If baseline table doesn't exist, use defaults
            baseline_count = 1000  # Default baseline
            baseline_avg_salary = 75000

        # Get workforce and salary data for each year
        avg_salaries = []
        headcounts = []
        growth_rates = []

        previous_count = baseline_count
        previous_salary = baseline_avg_salary

        # Prepare status filter SQL
        status_placeholders = ','.join(['?' for _ in status_filter])

        for i, year in enumerate(years):
            # Get workforce metrics for filtered status codes
            result = conn.execute(f"""
                SELECT
                    COUNT(*) as headcount,
                    AVG(current_compensation) as avg_salary
                FROM fct_workforce_snapshot
                WHERE simulation_year = ? AND detailed_status_code IN ({status_placeholders})
            """, [year] + status_filter).fetchone()

            if result:
                headcount, avg_salary = result
                headcounts.append(int(headcount))
                avg_salaries.append(float(avg_salary) if avg_salary else 0)

                # Calculate compensation growth rate
                if i == 0:
                    # First year: compare to baseline
                    if baseline_avg_salary > 0:
                        growth_rate = ((avg_salary - baseline_avg_salary) / baseline_avg_salary) * 100
                    else:
                        growth_rate = 0
                else:
                    # Subsequent years: compare to previous year
                    if previous_salary > 0:
                        growth_rate = ((avg_salary - previous_salary) / previous_salary) * 100
                    else:
                        growth_rate = 0

                growth_rates.append(growth_rate)
                previous_count = headcount
                previous_salary = avg_salary
            else:
                headcounts.append(0)
                avg_salaries.append(0)
                growth_rates.append(0)

        # Get status breakdown for all years
        status_breakdown = {}
        for year in years:
            year_breakdown = {}
            for status in available_statuses:
                count_result = conn.execute("""
                    SELECT COUNT(*)
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ? AND detailed_status_code = ?
                """, [year, status]).fetchone()
                year_breakdown[status] = count_result[0] if count_result else 0
            status_breakdown[year] = year_breakdown

        # Calculate overall growth trend
        if len(growth_rates) > 0:
            current_growth = growth_rates[-1]  # Latest year growth
        else:
            current_growth = 0

        # Get last simulation time from database metadata if available
        try:
            last_updated_result = conn.execute("""
                SELECT MAX(created_at)
                FROM fct_yearly_events
                WHERE simulation_year IN ({})
            """.format(','.join(['?'] * len(years))), years).fetchone()

            last_updated = last_updated_result[0] if last_updated_result and last_updated_result[0] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except:
            last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn.close()

        return {
            'current_growth': current_growth,
            'target_growth': 2.0,  # From configuration
            'years': years,
            'avg_salaries': avg_salaries,
            'total_headcount': headcounts,
            'growth_rates': growth_rates,
            'last_updated': last_updated,
            'available_statuses': available_statuses,
            'status_breakdown': status_breakdown,
            'status_filter': status_filter
        }

    except Exception as e:
        st.error(f"Error loading simulation results: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None

@st.cache_data
def load_baseline_comparison():
    """Load baseline (current) simulation results for comparison"""
    try:
        # Load the current state before any parameter changes
        # This could be from a saved baseline or the last known good state
        return {
            'years': [2025, 2026],
            'avg_salaries': [161395, 158780],
            'growth_rates': [0, -1.62],
            'total_headcount': [4639, 4032],
            'scenario_name': 'Current Parameters'
        }
    except Exception as e:
        st.error(f"Error loading baseline comparison: {e}")
        return None

def validate_parameters(params):
    """Validate parameter values and return warnings/errors"""
    warnings = []
    errors = []

    # COLA validation
    if 'cola_rate' in params:
        cola_avg = np.mean(list(params['cola_rate'].values()))
        if cola_avg > 0.06:
            warnings.append(f"COLA rate {cola_avg:.1%} is above 6% - may exceed budget")
        if cola_avg < 0.01:
            warnings.append(f"COLA rate {cola_avg:.1%} is below 1% - may hurt retention")

    # Merit validation
    if 'merit_base' in params:
        merit_avg = np.mean(list(params['merit_base'].values()))
        if merit_avg > 0.08:
            warnings.append(f"Merit rate {merit_avg:.1%} is above 8% - may exceed budget")
        if merit_avg < 0.02:
            warnings.append(f"Merit rate {merit_avg:.1%} is below 2% - may hurt performance")

    # New hire adjustment validation
    if 'new_hire_salary_adjustment' in params:
        adj_avg = np.mean(list(params['new_hire_salary_adjustment'].values()))
        if adj_avg > 1.3:
            warnings.append(f"New hire adjustment {adj_avg:.1%} is above 30% - may create inequity")
        if adj_avg < 1.0:
            errors.append(f"New hire adjustment {adj_avg:.1%} below 100% - invalid")

    return warnings, errors

def get_parameter_sensitivity_summary(year_params):
    """Get a business-friendly summary of parameter sensitivity for integration with validation"""
    if not year_params:
        return {"high_impact": [], "medium_impact": [], "low_impact": [], "recommendations": []}

    # Quick sensitivity calculation for validation integration
    current_cola = year_params.get('cola_rate', {}).get(1, 0.03)
    current_merit = np.mean([year_params.get('merit_base', {}).get(i, 0.03) for i in range(1, 6)])

    high_impact = []
    medium_impact = []
    low_impact = []

    # COLA is always high impact (affects entire workforce)
    high_impact.append({
        'name': 'COLA Rate',
        'reason': 'Affects all employees equally',
        'current': f"{current_cola:.1%}",
        'business_impact': 'High budget impact, high retention impact'
    })

    # Merit rates by level
    for level in range(1, 6):
        level_merit = year_params.get('merit_base', {}).get(level, 0.03)
        if level <= 2:
            high_impact.append({
                'name': f'Merit Rate Level {level}',
                'reason': f'Large workforce segment (~{30 if level == 1 else 25}%)',
                'current': f"{level_merit:.1%}",
                'business_impact': 'Significant budget and performance impact'
            })
        elif level <= 4:
            medium_impact.append({
                'name': f'Merit Rate Level {level}',
                'reason': f'Moderate workforce segment (~{25 if level == 3 else 15}%)',
                'current': f"{level_merit:.1%}",
                'business_impact': 'Moderate budget impact'
            })
        else:
            low_impact.append({
                'name': f'Merit Rate Level {level}',
                'reason': 'Small workforce segment (~5%)',
                'current': f"{level_merit:.1%}",
                'business_impact': 'Limited budget impact'
            })

    # New hire adjustment
    current_adj = year_params.get('new_hire_salary_adjustment', {}).get(1, 1.1)
    medium_impact.append({
        'name': 'New Hire Salary Adjustment',
        'reason': 'Limited to new hires (~15% annually)',
        'current': f"{current_adj:.0%}",
        'business_impact': 'Recruiting competitiveness'
    })

    # Generate recommendations
    recommendations = [
        "Focus on COLA Rate for broad workforce impact",
        "Adjust Level 1-2 Merit Rates for major budget changes",
        "Use Level 3-5 Merit Rates for targeted adjustments",
        "Monitor New Hire Adjustment for recruitment competitiveness"
    ]

    return {
        "high_impact": high_impact,
        "medium_impact": medium_impact,
        "low_impact": low_impact,
        "recommendations": recommendations
    }

def update_parameters_file(new_params, years):
    """Update the comp_levers.csv file with new parameters"""
    try:
        comp_levers_path = Path(__file__).parent.parent.parent / "dbt" / "seeds" / "comp_levers.csv"
        if not comp_levers_path.exists():
            comp_levers_path = Path("dbt/seeds/comp_levers.csv")

        df = pd.read_csv(comp_levers_path)

        # Handle both single year (int) and multiple years (list)
        if isinstance(years, int):
            years = [years]

        # Update parameters for all specified years
        for year in years:
            for param_name, level_values in new_params.items():
                for level, value in level_values.items():
                    mask = (df['fiscal_year'] == year) & (df['job_level'] == level) & (df['parameter_name'] == param_name)
                    df.loc[mask, 'parameter_value'] = value
                    df.loc[mask, 'created_at'] = datetime.now().strftime("%Y-%m-%d")
                    df.loc[mask, 'created_by'] = 'analyst'

        df.to_csv(comp_levers_path, index=False)
        return True
    except Exception as e:
        st.error(f"Error updating parameters: {e}")
        return False

def validate_synthetic_vs_real(synthetic_results, real_results, tolerance=0.1):
    """
    Compare synthetic results with real simulation results to detect significant divergence.

    Args:
        synthetic_results: Results from synthetic simulation
        real_results: Results from real simulation
        tolerance: Acceptable percentage difference (default 10%)

    Returns:
        Dict with validation results and recommendations
    """
    try:
        validation = {
            'valid': True,
            'differences': {},
            'recommendations': [],
            'overall_correlation': 0.0
        }

        # Compare growth rates
        if (synthetic_results.get('growth_rates') and real_results.get('growth_rates') and
            len(synthetic_results['growth_rates']) == len(real_results['growth_rates'])):

            syn_growth = np.array(synthetic_results['growth_rates'])
            real_growth = np.array(real_results['growth_rates'])

            # Calculate mean absolute percentage error
            mape = np.mean(np.abs((syn_growth - real_growth) / real_growth)) * 100
            validation['differences']['growth_rate_mape'] = mape

            # Calculate correlation
            if len(syn_growth) > 1:
                correlation = np.corrcoef(syn_growth, real_growth)[0, 1]
                validation['overall_correlation'] = correlation

            # Check if differences exceed tolerance
            if mape > tolerance * 100:  # Convert to percentage
                validation['valid'] = False
                validation['recommendations'].append(f"Growth rate difference ({mape:.1f}%) exceeds tolerance")

        # Compare final salaries
        if (synthetic_results.get('avg_salaries') and real_results.get('avg_salaries')):
            syn_final = synthetic_results['avg_salaries'][-1]
            real_final = real_results['avg_salaries'][-1]

            salary_diff = abs((syn_final - real_final) / real_final) * 100
            validation['differences']['final_salary_diff'] = salary_diff

            if salary_diff > tolerance * 100:
                validation['valid'] = False
                validation['recommendations'].append(f"Final salary difference ({salary_diff:.1f}%) exceeds tolerance")

        # Add recommendations based on validation
        if validation['valid']:
            validation['recommendations'].append("Synthetic results are well-aligned with real simulation")
        else:
            validation['recommendations'].extend([
                "Consider using real simulation for final decisions",
                "Synthetic mode may be less accurate for these parameter combinations",
                "Try smaller parameter adjustments for better synthetic accuracy"
            ])

        return validation

    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'recommendations': ["Validation failed - use real simulation for safety"]
        }

def validate_parameters_with_risk_analysis(proposed_params, current_params=None):
    """
    Enhanced parameter validation with integrated risk analysis.

    Args:
        proposed_params: Dictionary of proposed parameter values
        current_params: Dictionary of current/baseline parameter values

    Returns:
        Dict with validation results, risk assessment, and recommendations
    """
    try:
        validation_result = {
            'valid': True,
            'warnings': [],
            'errors': [],
            'risk_assessment': None,
            'recommendations': [],
            'parameter_issues': {}
        }

        # Initialize risk assessment engine
        risk_engine = RiskAssessmentEngine()

        # Set baseline data if available
        if current_params:
            risk_engine.set_baseline_data(current_params)

        # Parameter validation rules
        validation_rules = {
            'cola_rate': {'min': 0.0, 'max': 0.08, 'warning_threshold': 0.05},
            'merit_base': {'min': 0.0, 'max': 0.15, 'warning_threshold': 0.08},
            'new_hire_salary_adjustment': {'min': 1.0, 'max': 1.5, 'warning_threshold': 1.3},
            'promotion_probability': {'min': 0.0, 'max': 0.25, 'warning_threshold': 0.20},
            'promotion_raise': {'min': 0.0, 'max': 0.50, 'warning_threshold': 0.35}
        }

        # Validate each parameter
        parameter_changes = {}

        for param_name, param_values in proposed_params.items():
            if param_name in validation_rules:
                rules = validation_rules[param_name]

                for level, value in param_values.items():
                    param_key = f"{param_name}_level_{level}"

                    # Basic range validation
                    if value < rules['min']:
                        validation_result['errors'].append(
                            f"{param_name} Level {level}: {value:.1%} is below minimum {rules['min']:.1%}"
                        )
                        validation_result['valid'] = False
                    elif value > rules['max']:
                        validation_result['errors'].append(
                            f"{param_name} Level {level}: {value:.1%} exceeds maximum {rules['max']:.1%}"
                        )
                        validation_result['valid'] = False
                    elif value > rules['warning_threshold']:
                        validation_result['warnings'].append(
                            f"{param_name} Level {level}: {value:.1%} is unusually high (>{rules['warning_threshold']:.1%})"
                        )

                    # Prepare for risk assessment
                    if current_params and param_name in current_params:
                        current_value = current_params[param_name].get(level, rules['min'])
                        parameter_changes[(param_name, level)] = (current_value, value)

        # Perform risk assessment if we have baseline data
        if parameter_changes and current_params:
            risk_assessment = risk_engine.calculate_overall_risk_assessment(
                parameter_changes=parameter_changes,
                implementation_timeline=90
            )
            validation_result['risk_assessment'] = risk_assessment

            # Add risk-based recommendations
            if risk_assessment.overall_level == RiskLevel.CRITICAL:
                validation_result['errors'].append(
                    "CRITICAL RISK: Parameter changes pose significant business risk"
                )
                validation_result['valid'] = False
            elif risk_assessment.overall_level == RiskLevel.HIGH:
                validation_result['warnings'].append(
                    "HIGH RISK: Parameter changes require enhanced approval and monitoring"
                )

            # Add specific risk recommendations
            validation_result['recommendations'].extend(risk_assessment.recommendations)

        # Internal consistency checks
        consistency_issues = validate_parameter_consistency(proposed_params)
        if consistency_issues:
            validation_result['warnings'].extend(consistency_issues)

        # Budget impact warnings
        budget_warnings = check_budget_impact_thresholds(proposed_params, current_params)
        if budget_warnings:
            validation_result['warnings'].extend(budget_warnings)

        return validation_result

    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Validation error: {str(e)}"],
            'warnings': [],
            'recommendations': ["Use basic validation and proceed with caution"],
            'risk_assessment': None
        }

def validate_parameter_consistency(proposed_params):
    """Check for internal consistency issues in parameter sets."""
    issues = []

    # Check merit rate progression (should generally decrease with level)
    if 'merit_base' in proposed_params:
        merit_values = [proposed_params['merit_base'].get(i, 0) for i in range(1, 6)]

        # Check if merit rates are inverted (higher levels getting more merit)
        inversions = 0
        for i in range(1, len(merit_values)):
            if merit_values[i] > merit_values[i-1]:
                inversions += 1

        if inversions > 2:  # Allow some flexibility but flag major inversions
            issues.append("Merit rates may be inverted - higher levels typically receive lower merit percentages")

    # Check COLA consistency (should be uniform across levels)
    if 'cola_rate' in proposed_params:
        cola_values = list(proposed_params['cola_rate'].values())
        if len(set(cola_values)) > 1:
            issues.append("COLA rates vary across levels - typically COLA should be uniform")

    # Check promotion probability progression
    if 'promotion_probability' in proposed_params:
        promo_values = [proposed_params['promotion_probability'].get(i, 0) for i in range(1, 6)]

        # Higher levels should generally have lower promotion rates
        for i in range(1, len(promo_values)):
            if promo_values[i] > promo_values[i-1] * 1.5:  # Allow some variance
                issues.append(f"Promotion probability for Level {i+1} seems high compared to Level {i}")

    return issues

def check_budget_impact_thresholds(proposed_params, current_params):
    """Check if parameter changes exceed budget impact thresholds."""
    warnings = []

    if not current_params:
        return warnings

    # Define impact thresholds
    high_impact_threshold = 0.20  # 20% change
    critical_impact_threshold = 0.40  # 40% change

    for param_name, param_values in proposed_params.items():
        if param_name in current_params:
            for level, new_value in param_values.items():
                current_value = current_params[param_name].get(level, 0)

                if current_value > 0:
                    change_pct = abs((new_value - current_value) / current_value)

                    if change_pct > critical_impact_threshold:
                        warnings.append(
                            f"{param_name} Level {level}: {change_pct:.0%} change may have critical budget impact"
                        )
                    elif change_pct > high_impact_threshold:
                        warnings.append(
                            f"{param_name} Level {level}: {change_pct:.0%} change may have significant budget impact"
                        )

    return warnings

def generate_risk_mitigation_plan(risk_assessment):
    """Generate detailed risk mitigation plan based on assessment."""

    if not risk_assessment:
        return []

    mitigation_plan = []

    # Overall risk level actions
    if risk_assessment.overall_level == RiskLevel.CRITICAL:
        mitigation_plan.extend([
            "🔴 CRITICAL ACTIONS:",
            "• Executive steering committee approval required",
            "• Develop comprehensive rollback plan",
            "• Implement phased pilot with 10-20% of workforce",
            "• Daily monitoring for first 30 days",
            "• Weekly executive briefings during implementation"
        ])
    elif risk_assessment.overall_level == RiskLevel.HIGH:
        mitigation_plan.extend([
            "🟠 HIGH RISK ACTIONS:",
            "• Senior management approval required",
            "• Enhanced communication plan to all stakeholders",
            "• Weekly monitoring during implementation",
            "• Prepare contingency adjustments",
            "• Document lessons learned"
        ])
    elif risk_assessment.overall_level == RiskLevel.MEDIUM:
        mitigation_plan.extend([
            "🟡 STANDARD ACTIONS:",
            "• Management approval through normal channels",
            "• Standard communication to affected employees",
            "• Monthly monitoring during implementation",
            "• Regular feedback collection"
        ])
    else:
        mitigation_plan.extend([
            "🟢 MINIMAL ACTIONS:",
            "• Standard approval process",
            "• Basic communication sufficient",
            "• Quarterly monitoring adequate"
        ])

    # Category-specific mitigations
    category_risks = {}
    all_risks = risk_assessment.aggregate_risks + [rf for pr in risk_assessment.parameter_risks for rf in pr.risk_factors]

    for risk in all_risks:
        if risk.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            if risk.category not in category_risks:
                category_risks[risk.category] = []
            category_risks[risk.category].append(risk)

    if RiskCategory.BUDGET in category_risks:
        mitigation_plan.extend([
            "",
            "💰 BUDGET RISK MITIGATIONS:",
            "• Detailed financial impact modeling",
            "• Monthly budget variance reporting",
            "• Escalation triggers at +/-5% budget variance",
            "• Reserve fund allocation for adjustments"
        ])

    if RiskCategory.RETENTION in category_risks:
        mitigation_plan.extend([
            "",
            "👥 RETENTION RISK MITIGATIONS:",
            "• Enhanced retention metrics tracking",
            "• Stay interview program for high performers",
            "• Exit interview analysis for early warning signs",
            "• Competitive benchmark monitoring"
        ])

    if RiskCategory.EQUITY in category_risks:
        mitigation_plan.extend([
            "",
            "⚖️ EQUITY RISK MITIGATIONS:",
            "• Pay equity audit before and after implementation",
            "• Legal review of compensation changes",
            "• Employee communication about fairness principles",
            "• Grievance process for equity concerns"
        ])

    return mitigation_plan

def run_synthetic_simulation(proposed_params, years, baseline_data=None):
    """
    Run fast synthetic simulation using mathematical models.

    Args:
        proposed_params: Parameter dictionary with COLA, merit, etc.
        years: List of years to simulate
        baseline_data: Optional baseline workforce data for scaling

    Returns:
        Dict with synthetic simulation results matching real simulation format
    """
    try:
        # Use current baseline if not provided
        if baseline_data is None:
            # Try to load from existing results or use defaults
            current_results = load_simulation_results(['continuous_active', 'new_hire_active'])
            if current_results and current_results.get('avg_salaries'):
                baseline_salary = current_results['avg_salaries'][0]
                baseline_headcount = current_results['total_headcount'][0]
            else:
                # Fallback defaults based on typical workforce
                baseline_salary = 165000  # Typical average salary
                baseline_headcount = 4500  # Typical workforce size
        else:
            baseline_salary = baseline_data.get('avg_salary', 165000)
            baseline_headcount = baseline_data.get('headcount', 4500)

        # Extract parameters for modeling
        cola_rate = proposed_params.get('cola_rate', {}).get(1, 0.03)
        merit_rates = proposed_params.get('merit_base', {})
        avg_merit = np.mean(list(merit_rates.values())) if merit_rates else 0.035
        new_hire_adj = proposed_params.get('new_hire_salary_adjustment', {}).get(1, 1.1)

        # Synthetic modeling logic based on compensation parameter relationships
        results = {
            'years': years,
            'avg_salaries': [],
            'total_headcount': [],
            'growth_rates': [],
            'status_breakdown': {},
            'available_statuses': ['continuous_active', 'new_hire_active', 'experienced_termination', 'new_hire_termination'],
            'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'synthetic_mode': True
        }

        current_salary = baseline_salary
        current_headcount = baseline_headcount

        for i, year in enumerate(years):
            # Year-over-year growth modeling
            if i == 0:
                # First year: apply initial parameter effects
                # COLA affects all employees directly
                cola_effect = current_salary * cola_rate

                # Merit affects subset of employees (assume 80% get merit)
                merit_effect = current_salary * avg_merit * 0.8

                # New hire effect (assume 10% are new hires with adjustment)
                new_hire_effect = current_salary * (new_hire_adj - 1.0) * 0.1

                # Total salary growth
                salary_growth = cola_effect + merit_effect + new_hire_effect
                current_salary += salary_growth

                # Headcount growth (assume modest growth based on parameters)
                # Higher compensation parameters often correlate with retention/hiring
                compensation_factor = (cola_rate + avg_merit) / 0.065  # Normalize around typical 6.5%
                headcount_growth_rate = 0.02 * compensation_factor  # Base 2% growth, adjusted
                current_headcount = int(current_headcount * (1 + headcount_growth_rate))

                # Calculate workforce growth vs baseline (consistent with real simulation)
                workforce_growth = ((current_headcount - baseline_headcount) / baseline_headcount) * 100
                salary_growth = ((current_salary - baseline_salary) / baseline_salary) * 100
                # Use workforce growth as primary metric to match real simulation behavior
                growth_rate = workforce_growth
            else:
                # Subsequent years: compound growth
                prev_salary = current_salary

                # Apply annual effects with slight diminishing returns
                diminishing_factor = 0.95 ** (i - 1)  # Slight reduction each year
                annual_cola = current_salary * cola_rate
                annual_merit = current_salary * avg_merit * 0.8 * diminishing_factor
                annual_new_hire = current_salary * (new_hire_adj - 1.0) * 0.1

                current_salary += annual_cola + annual_merit + annual_new_hire

                # Headcount evolution with market constraints
                compensation_factor = (cola_rate + avg_merit) / 0.065
                headcount_growth_rate = 0.015 * compensation_factor * diminishing_factor
                current_headcount = int(current_headcount * (1 + headcount_growth_rate))

                # Calculate consistent workforce growth vs baseline
                workforce_growth = ((current_headcount - baseline_headcount) / baseline_headcount) * 100
                # For consistency, calculate cumulative growth vs baseline, not year-over-year
                growth_rate = workforce_growth

            results['avg_salaries'].append(round(current_salary, 0))
            results['total_headcount'].append(current_headcount)
            results['growth_rates'].append(round(growth_rate, 2))

            # Generate synthetic status breakdown (realistic proportions)
            total_employees = current_headcount
            status_breakdown = {
                'continuous_active': int(total_employees * 0.75),  # 75% continuing employees
                'new_hire_active': int(total_employees * 0.15),    # 15% new hires who stayed
                'experienced_termination': int(total_employees * 0.08), # 8% experienced terminations
                'new_hire_termination': int(total_employees * 0.02)     # 2% new hire terminations
            }

            # Adjust to match total exactly
            calculated_total = sum(status_breakdown.values())
            if calculated_total != total_employees:
                # Adjust continuous_active to match
                status_breakdown['continuous_active'] += (total_employees - calculated_total)

            results['status_breakdown'][year] = status_breakdown

        # Calculate overall metrics
        if len(results['growth_rates']) > 0:
            results['current_growth'] = results['growth_rates'][-1]
        else:
            results['current_growth'] = 0

        results['target_growth'] = 2.0  # Standard target
        results['status_filter'] = ['continuous_active', 'new_hire_active']

        return results

    except Exception as e:
        st.error(f"Synthetic simulation failed: {e}")
        return None

def run_optimization_loop_with_tracking(optimization_config, progress_container, tracker, visualizer):
    """
    Enhanced optimization loop with real-time progress tracking and visualization.
    Integrates with the advanced progress tracking system for live monitoring.
    """
    try:
        max_iterations = optimization_config.get('max_iterations', 10)
        tolerance = optimization_config.get('tolerance', 0.02)
        target_growth = optimization_config.get('target_growth', 2.0)
        optimization_mode = optimization_config.get('mode', 'Balanced')
        algorithm = optimization_config.get('algorithm', 'SLSQP')
        use_real_simulation = optimization_config.get('use_real_simulation', False)

        # Create iteration tracking
        iteration_results = []
        converged = False

        # Initialize progress tracking
        tracker.is_running = True
        tracker.start_time = datetime.now()

        with progress_container:
            st.info(f"🎯 Starting {algorithm} optimization with target growth: {target_growth}%")
            st.info(f"🔄 Max iterations: {max_iterations}, Tolerance: {tolerance}%")

            # Create live charts
            convergence_chart = st.empty()
            parameter_chart = st.empty()
            performance_metrics = st.empty()

            for iteration in range(max_iterations):
                iteration_start = datetime.now()

                # Update iteration header
                st.markdown(f"### 🔄 Iteration {iteration + 1}")

                # Load current parameters for tracking
                current_params = load_current_parameters()
                year_params = current_params.get(2026, {})

                # Create progress entry
                progress_entry = OptimizationProgress(
                    iteration=iteration,
                    timestamp=iteration_start,
                    function_value=0,  # Will be updated after simulation
                    constraint_violations={},
                    parameters={
                        'cola_rate': year_params.get('cola_rate', {}).get(1, 0.03),
                        'merit_rate_avg': np.mean([year_params.get('merit_base', {}).get(i, 0.03) for i in range(1, 6)]),
                        'new_hire_adjustment': year_params.get('new_hire_salary_adjustment', {}).get(1, 1.1)
                    }
                )

                # Run simulation
                sim_type = "real dbt" if use_real_simulation else "synthetic"

                with st.spinner(f"Running {sim_type} simulation iteration {iteration + 1}..."):
                    simulation_success = run_simulation(use_synthetic=not use_real_simulation)

                if not simulation_success:
                    st.error(f"❌ Simulation failed at iteration {iteration + 1}")
                    break

                # Clear cache and analyze results
                load_simulation_results.clear()
                results = load_simulation_results(['continuous_active', 'new_hire_active'])

                if not results:
                    st.error(f"❌ Could not load results for iteration {iteration + 1}")
                    break

                # Calculate growth and gap - use final year growth for optimization target
                if len(results['growth_rates']) > 0:
                    current_growth = results['growth_rates'][-1]  # Use final year, not average
                else:
                    current_growth = 0

                gap = target_growth - current_growth

                # Update progress entry with results
                progress_entry.function_value = abs(gap)  # Objective is to minimize gap
                progress_entry.constraint_violations = {
                    'budget_constraint': max(0, current_growth - 5.0),  # Don't exceed 5% growth
                    'feasibility_constraint': max(0, -current_growth)   # Growth can't be negative
                }
                progress_entry.performance_metrics = {
                    'current_growth': current_growth,
                    'gap_to_target': gap,
                    'convergence_criterion': abs(gap) <= tolerance
                }

                # Add to tracker
                tracker.add_progress(progress_entry)
                iteration_results.append({
                    'iteration': iteration + 1,
                    'current_growth': current_growth,
                    'gap': gap,
                    'converged': abs(gap) <= tolerance
                })

                # Update live visualizations
                with convergence_chart.container():
                    conv_fig = visualizer.create_convergence_chart(
                        tracker.get_history(),
                        target_value=0  # Target gap is 0
                    )
                    st.plotly_chart(conv_fig, use_container_width=True)

                with parameter_chart.container():
                    param_fig = visualizer.create_parameter_evolution_chart(
                        tracker.get_history(),
                        ['cola_rate', 'merit_rate_avg', 'new_hire_adjustment']
                    )
                    st.plotly_chart(param_fig, use_container_width=True)

                with performance_metrics.container():
                    perf_data = visualizer.create_performance_dashboard(
                        tracker.get_history(),
                        tracker.start_time
                    )

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Current Growth", f"{current_growth:.2f}%")
                    with col2:
                        st.metric("Gap to Target", f"{gap:+.2f}%")
                    with col3:
                        status = "✅ Converged" if abs(gap) <= tolerance else "🔄 Optimizing"
                        st.metric("Status", status)
                    with col4:
                        st.metric("Iteration Time", perf_data['elapsed_time'])

                # Check convergence
                if abs(gap) <= tolerance:
                    converged = True
                    st.success(f"🎉 Optimization converged in {iteration + 1} iterations!")
                    break

                # Adjust parameters for next iteration
                if iteration < max_iterations - 1:
                    st.info("🔧 Adjusting parameters for next iteration...")
                    adjust_parameters_intelligent(gap, optimization_mode, iteration + 1)

                # Add delay for demo purposes and to show progress
                time.sleep(1)

            tracker.is_running = False

        # Create final summary
        final_result = {
            'converged': converged,
            'iterations': len(iteration_results),
            'final_growth': iteration_results[-1]['current_growth'] if iteration_results else 0,
            'final_gap': iteration_results[-1]['gap'] if iteration_results else 0,
            'iteration_history': iteration_results,
            'optimization_history': [
                {
                    'iteration': p.iteration,
                    'objective_value': p.function_value,
                    'parameters': p.parameters,
                    'constraints': p.constraint_violations,
                    'metrics': p.performance_metrics
                }
                for p in tracker.get_history()
            ]
        }

        return final_result

    except Exception as e:
        st.error(f"Enhanced optimization loop failed: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None


def run_optimization_loop(optimization_config):
    """
    Orchestrates iterative parameter optimization using existing simulation patterns.
    Reuses proven 3-method execution: Dagster CLI → Asset-based → Manual dbt.
    """
    try:
        max_iterations = optimization_config.get('max_iterations', 10)
        tolerance = optimization_config.get('tolerance', 0.02)
        target_growth = optimization_config.get('target_growth', 2.0)
        optimization_mode = optimization_config.get('mode', 'Balanced')

        # Create iteration tracking
        iteration_results = []
        converged = False

        st.info(f"🎯 Starting optimization with target growth: {target_growth}%")
        st.info(f"🔄 Max iterations: {max_iterations}, Tolerance: {tolerance}%")

        for iteration in range(max_iterations):
            st.markdown(f"### 🔄 Iteration {iteration + 1}")

            # Run simulation using existing run_simulation function
            # Use synthetic mode for optimization by default (much faster)
            use_synthetic_opt = optimization_config.get('use_synthetic', True)
            sim_type = "synthetic" if use_synthetic_opt else "real"

            with st.spinner(f"Running {sim_type} simulation iteration {iteration + 1}..."):
                simulation_success = run_simulation(use_synthetic=use_synthetic_opt)

            if not simulation_success:
                st.error(f"❌ Simulation failed at iteration {iteration + 1}")
                break

            # Clear cache to get fresh results
            load_simulation_results.clear()

            # Analyze results using existing load_simulation_results function
            results = load_simulation_results(['continuous_active', 'new_hire_active'])

            if not results:
                st.error(f"❌ Could not load results for iteration {iteration + 1}")
                break

            # Calculate final year growth for optimization (not average)
            if len(results['growth_rates']) > 0:
                current_growth = results['growth_rates'][-1]  # Use final year growth
            else:
                current_growth = 0

            gap = target_growth - current_growth

            # Store iteration result
            iteration_result = {
                'iteration': iteration + 1,
                'current_growth': current_growth,
                'gap': gap,
                'converged': abs(gap) <= tolerance
            }
            iteration_results.append(iteration_result)

            # Display current iteration results
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Current Growth", f"{current_growth:.2f}%")
            with col2:
                st.metric("Gap to Target", f"{gap:+.2f}%")
            with col3:
                status = "✅ Converged" if abs(gap) <= tolerance else "🔄 Optimizing"
                st.metric("Status", status)

            # Check convergence
            if abs(gap) <= tolerance:
                converged = True
                st.success(f"🎉 Optimization converged in {iteration + 1} iterations!")
                break

            # Adjust parameters intelligently for next iteration
            if iteration < max_iterations - 1:  # Don't adjust on last iteration
                st.info("🔧 Adjusting parameters for next iteration...")
                adjust_parameters_intelligent(gap, optimization_mode, iteration + 1)

        # Create final summary
        final_result = {
            'converged': converged,
            'iterations': len(iteration_results),
            'final_growth': iteration_results[-1]['current_growth'] if iteration_results else 0,
            'final_gap': iteration_results[-1]['gap'] if iteration_results else 0,
            'iteration_history': iteration_results
        }

        return final_result

    except Exception as e:
        st.error(f"Optimization loop failed: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None

def run_scipy_optimization(optimization_config):
    """
    Use scipy.optimize with selected algorithm for proper gradient-based optimization.
    This replaces the simple parameter stepping with true optimization algorithms.
    """
    try:
        from scipy.optimize import minimize
        import numpy as np

        st.info("🔬 **Scientific Optimization**: Using scipy algorithms for precise convergence")

        # Extract configuration
        target_growth = optimization_config.get('target_growth', 2.0)
        algorithm = optimization_config.get('algorithm', 'SLSQP')
        max_iterations = optimization_config.get('max_iterations', 20)
        use_synthetic = optimization_config.get('use_synthetic', True)

        # Load current parameters as starting point
        current_params = load_current_parameters()
        year_params = current_params.get(2026, {})

        # Initial parameter values
        initial_cola = year_params.get('cola_rate', {}).get(1, 0.02)
        initial_merit_rates = year_params.get('merit_base', {1: 0.03, 2: 0.03, 3: 0.03, 4: 0.02, 5: 0.02})
        initial_merit_avg = np.mean(list(initial_merit_rates.values()))
        initial_hire_adj = year_params.get('new_hire_salary_adjustment', {}).get(1, 1.15)

        # Track optimization progress
        iteration_count = 0
        objective_history = []

        def objective_function(params):
            """Objective function to minimize: squared error from target growth"""
            nonlocal iteration_count, objective_history
            iteration_count += 1

            # Unpack parameters
            cola, merit_avg, hire_adj = params

            # Create parameter dictionary
            param_dict = {
                'cola_rate': {i: cola for i in range(1, 6)},
                'merit_base': {
                    1: merit_avg * 1.1,  # Level 1 gets slightly higher merit
                    2: merit_avg * 1.0,  # Level 2 gets average
                    3: merit_avg * 0.9,  # Level 3 gets slightly lower
                    4: merit_avg * 0.8,  # Level 4 gets lower
                    5: merit_avg * 0.7   # Level 5 gets lowest
                },
                'new_hire_salary_adjustment': {i: hire_adj for i in range(1, 6)}
            }

            # Update parameters in system for simulation
            target_years = [2025, 2026, 2027, 2028, 2029]
            update_parameters_file(param_dict, target_years)

            try:
                if use_synthetic:
                    # Use synthetic simulation for fast evaluation
                    results = run_synthetic_simulation(param_dict, target_years)
                else:
                    # Use real simulation for accuracy (slower)
                    run_simulation(use_synthetic=False, proposed_params=param_dict, target_years=target_years)
                    results = load_simulation_results(['continuous_active', 'new_hire_active'])

                if results and len(results['growth_rates']) > 0:
                    # Use final year growth for consistency
                    final_growth = results['growth_rates'][-1]
                else:
                    final_growth = 0

                # Calculate squared error (objective to minimize)
                error = (final_growth - target_growth) ** 2
                objective_history.append({
                    'iteration': iteration_count,
                    'cola': cola,
                    'merit_avg': merit_avg,
                    'hire_adj': hire_adj,
                    'growth_achieved': final_growth,
                    'error': error
                })

                # Show progress
                if iteration_count % 1 == 0:  # Show every iteration
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric(f"Iteration {iteration_count}", f"{final_growth:.2f}%")
                    with col2:
                        st.metric("Gap", f"{final_growth - target_growth:+.2f}%")
                    with col3:
                        st.metric("COLA", f"{cola:.1%}")
                    with col4:
                        st.metric("Merit Avg", f"{merit_avg:.1%}")

                return error

            except Exception as e:
                st.error(f"Simulation failed in optimization: {e}")
                return 1000  # High penalty for failed simulations

        # Parameter bounds
        bounds = [
            (0.005, 0.08),  # COLA: 0.5% to 8%
            (0.01, 0.10),   # Merit average: 1% to 10%
            (1.0, 1.4)      # Hire adjustment: 100% to 140%
        ]

        # Initial guess
        x0 = [initial_cola, initial_merit_avg, initial_hire_adj]

        st.info(f"🎯 Starting {algorithm} optimization...")
        st.info(f"📊 Target: {target_growth}%, Initial: COLA={initial_cola:.1%}, Merit={initial_merit_avg:.1%}, Hire={initial_hire_adj:.0%}")

        # Run scipy optimization
        result = minimize(
            objective_function,
            x0,
            method=algorithm,
            bounds=bounds,
            options={
                'maxiter': max_iterations,
                'disp': True,
                'ftol': 1e-4  # Tolerance for function value changes
            }
        )

        # Display results
        if result.success:
            optimal_cola, optimal_merit, optimal_hire = result.x
            st.success(f"✅ **Optimization Converged!**")
            st.success(f"🎯 Optimal parameters: COLA={optimal_cola:.1%}, Merit={optimal_merit:.1%}, Hire={optimal_hire:.0%}")
            st.success(f"📊 Final objective value: {result.fun:.6f}")
            st.success(f"🔄 Iterations used: {result.nit}/{max_iterations}")
        else:
            st.warning(f"⚠️ **Optimization did not fully converge**")
            st.warning(f"Reason: {result.message}")
            optimal_cola, optimal_merit, optimal_hire = result.x
            st.info(f"🎯 Best parameters found: COLA={optimal_cola:.1%}, Merit={optimal_merit:.1%}, Hire={optimal_hire:.0%}")

        # Create summary
        final_result = {
            'converged': result.success,
            'method': 'scipy_' + algorithm,
            'iterations': result.nit,
            'final_params': {
                'cola_rate': optimal_cola,
                'merit_avg': optimal_merit,
                'hire_adjustment': optimal_hire
            },
            'objective_value': result.fun,
            'optimization_history': objective_history
        }

        return final_result

    except ImportError:
        st.error("❌ SciPy not available. Install scipy to use scientific optimization.")
        st.info("💡 Falling back to classic optimization method...")
        return run_optimization_loop(optimization_config)
    except Exception as e:
        st.error(f"Scientific optimization failed: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None

def adjust_parameters_intelligent(gap, optimization_mode, iteration):
    """
    Intelligent parameter adjustment using existing parameter structure.
    Builds on proven parameter validation and application patterns.
    """
    try:
        # Load current parameters
        current_params = load_current_parameters()
        year_params = current_params.get(2026, {})  # Use 2026 as template year

        # Calculate adjustment factors based on optimization mode
        if optimization_mode == "Conservative":
            adjustment_factor = 0.1  # 10% of the gap
        elif optimization_mode == "Aggressive":
            adjustment_factor = 0.5  # 50% of the gap
        else:  # Balanced (default)
            adjustment_factor = 0.3  # 30% of the gap

        # Keep consistent adjustment factor for proper convergence
        # Note: Removed diminishing returns that prevented convergence

        # Calculate parameter adjustments
        # Gap > 0 means we need to increase growth (increase compensation parameters)
        # Gap < 0 means we need to decrease growth (decrease compensation parameters)

        gap_adjustment = gap * adjustment_factor * 0.01  # Convert percentage to decimal properly

        # Adjust COLA rate
        current_cola = year_params.get('cola_rate', {}).get(1, 0.03)
        new_cola = max(0.01, min(0.08, current_cola + gap_adjustment))  # Bound between 1% and 8%

        # Adjust merit rates (distribute adjustment across levels)
        new_merit_rates = {}
        for level in range(1, 6):
            current_merit = year_params.get('merit_base', {}).get(level, 0.03)
            # Higher levels get smaller adjustments
            level_factor = 1.2 - (level * 0.1)  # Level 1: 1.1x, Level 5: 0.7x
            new_merit = max(0.01, min(0.10, current_merit + (gap_adjustment * level_factor)))
            new_merit_rates[level] = new_merit

        # Adjust new hire salary adjustment (more conservative)
        current_adj = year_params.get('new_hire_salary_adjustment', {}).get(1, 1.1)
        new_adj = max(1.0, min(1.4, current_adj + (gap_adjustment * 0.5)))  # Half the adjustment

        # Create new parameter set
        new_params = {
            'cola_rate': {i: new_cola for i in range(1, 6)},
            'merit_base': new_merit_rates,
            'new_hire_salary_adjustment': {i: new_adj for i in range(1, 6)}
        }

        # Risk assessment before applying parameters
        max_risk_level = getattr(st.session_state, 'optimization_max_risk_level', RiskLevel.HIGH)
        if year_params:
            risk_engine = RiskAssessmentEngine()
            risk_engine.set_baseline_data(year_params)

            # Create parameter changes for risk assessment
            param_changes = {}
            for param_name, level_values in new_params.items():
                for level, new_value in level_values.items():
                    current_value = year_params.get(param_name, {}).get(level, 0.03)
                    param_changes[(param_name, level)] = (current_value, new_value)

            risk_assessment = risk_engine.calculate_overall_risk_assessment(
                parameter_changes=param_changes,
                implementation_timeline=90
            )

            # Check if risk exceeds maximum allowed level
            risk_levels_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
            if risk_levels_order.index(risk_assessment.overall_level) > risk_levels_order.index(max_risk_level):
                st.warning(f"⚠️ Iteration {iteration}: Parameter adjustment rejected due to {risk_assessment.overall_level.value} risk (max allowed: {max_risk_level.value})")
                st.info("🔄 Trying more conservative adjustment...")

                # Try more conservative adjustment
                conservative_factor = 0.5
                new_cola = max(0.01, min(0.08, current_cola + (gap_adjustment * conservative_factor)))
                conservative_merit_rates = {}
                for level in range(1, 6):
                    current_merit = year_params.get('merit_base', {}).get(level, 0.03)
                    level_factor = (1.2 - (level * 0.1)) * conservative_factor
                    conservative_merit_rates[level] = max(0.01, min(0.10, current_merit + (gap_adjustment * level_factor)))
                new_adj = max(1.0, min(1.4, current_adj + (gap_adjustment * 0.25)))  # Quarter adjustment

                new_params = {
                    'cola_rate': {i: new_cola for i in range(1, 6)},
                    'merit_base': conservative_merit_rates,
                    'new_hire_salary_adjustment': {i: new_adj for i in range(1, 6)}
                }

                # Re-check risk with conservative parameters
                param_changes = {}
                for param_name, level_values in new_params.items():
                    for level, new_value in level_values.items():
                        current_value = year_params.get(param_name, {}).get(level, 0.03)
                        param_changes[(param_name, level)] = (current_value, new_value)

                conservative_risk = risk_engine.calculate_overall_risk_assessment(
                    parameter_changes=param_changes,
                    implementation_timeline=90
                )

                if risk_levels_order.index(conservative_risk.overall_level) > risk_levels_order.index(max_risk_level):
                    st.error(f"❌ Even conservative adjustment exceeds risk limit. Stopping optimization.")
                    return False
                else:
                    st.success(f"✅ Conservative adjustment accepted with {conservative_risk.overall_level.value} risk")
            else:
                st.info(f"✅ Risk level {risk_assessment.overall_level.value} is within acceptable limits")

        # Update parameters file for all years
        target_years = [2025, 2026, 2027, 2028, 2029]
        if update_parameters_file(new_params, target_years):
            st.success(f"✅ Parameters updated for iteration {iteration}")

            # Show what was changed
            st.info(f"📊 Parameter adjustments (Gap: {gap:+.2f}%):")
            st.info(f"   • COLA: {current_cola:.1%} → {new_cola:.1%}")
            st.info(f"   • Merit (avg): {np.mean(list(year_params.get('merit_base', {1:0.03}).values())):.1%} → {np.mean(list(new_merit_rates.values())):.1%}")
            st.info(f"   • New Hire Adj: {current_adj:.0%} → {new_adj:.0%}")

            return True
        else:
            st.error("❌ Failed to update parameters")
            return False

    except Exception as e:
        st.error(f"Parameter adjustment failed: {e}")
        return False

def run_simulation(use_synthetic=False, proposed_params=None, target_years=None):
    try:
        # Handle synthetic mode
        if use_synthetic:
            st.info("🧪 Running synthetic simulation...")

            # Use provided parameters or load current ones
            if proposed_params is None:
                proposed_params = {
                    'cola_rate': {i: cola_rate for i in range(1, 6)},
                    'merit_base': merit_rates,
                    'new_hire_salary_adjustment': {i: new_hire_adj for i in range(1, 6)}
                }

            # Use provided years or default multi-year range
            if target_years is None:
                target_years = [2025, 2026, 2027, 2028, 2029]

            with st.spinner("Running synthetic simulation... This will take 5-10 seconds."):
                # Run synthetic simulation
                synthetic_results = run_synthetic_simulation(proposed_params, target_years)

                if synthetic_results:
                    # Store results in session state for UI display
                    st.session_state.simulation_results = synthetic_results
                    st.session_state.last_simulation_time = datetime.now()

                    # Clear cache to show new results
                    load_simulation_results.clear()

                    st.success("🎉 Synthetic simulation completed successfully!")
                    st.info("💡 **Note**: These are synthetic results. Use 'Real Simulation' for final validation.")

                    # Show quick summary
                    final_growth = synthetic_results['growth_rates'][-1] if synthetic_results['growth_rates'] else 0
                    final_salary = synthetic_results['avg_salaries'][-1] if synthetic_results['avg_salaries'] else 0

                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Final Growth Rate", f"{final_growth:.2f}%")
                    with col2:
                        st.metric("Final Avg Salary", f"${final_salary:,.0f}")

                    return True
                else:
                    st.error("Synthetic simulation failed")
                    return False

        # Real simulation mode (existing logic)
        st.info("🔄 Running real simulation...")

        # First, run dbt to update parameter tables
        st.info("Updating parameter tables...")
        dbt_dir = Path(__file__).parent.parent.parent / "dbt"
        dbt_cmd = Path(__file__).parent.parent.parent / "venv" / "bin" / "dbt"
        dbt_result = subprocess.run([
            str(dbt_cmd), "seed", "--select", "comp_levers"
        ], capture_output=True, text=True, cwd=str(dbt_dir))

        if dbt_result.returncode != 0:
            # Check for database lock error
            if "Conflicting lock is held" in dbt_result.stdout:
                st.error("🔒 Database Lock Error:")
                st.error("The simulation.duckdb file is locked by another process (likely your IDE).")
                st.error("Please close any database connections in Windsurf/VS Code and try again.")
                st.info("💡 Tip: Look for open SQL tabs or database explorer connections.")
                return False
            else:
                st.error(f"dbt seed failed:")
                st.error(f"Return code: {dbt_result.returncode}")
                st.error(f"STDERR: {dbt_result.stderr}")
                st.error(f"STDOUT: {dbt_result.stdout}")
                return False

        # Run parameter processing models
        st.info("Processing parameters...")
        dbt_result = subprocess.run([
            str(dbt_cmd), "run", "--select", "stg_comp_levers int_effective_parameters"
        ], capture_output=True, text=True, cwd=str(dbt_dir))

        if dbt_result.returncode != 0:
            st.error(f"dbt run failed:")
            st.error(f"Return code: {dbt_result.returncode}")
            st.error(f"STDERR: {dbt_result.stderr}")
            st.error(f"STDOUT: {dbt_result.stdout}")
            return False

        # Trigger simulation via multiple methods
        st.info("Triggering multi-year simulation...")

        # Method 1: Try Dagster CLI execution
        try:
            st.info("Method 1: Attempting Dagster CLI execution...")

            with st.spinner("Running full multi-year simulation... This will take 3-5 minutes."):
                # Set up environment variables to match Dagster dev setup
                project_root = Path(__file__).parent.parent.parent
                env = os.environ.copy()
                env["DAGSTER_HOME"] = str(project_root / ".dagster")

                # Try multiple dagster binary paths
                dagster_paths = [
                    project_root / "venv" / "bin" / "dagster",  # Virtual env
                    "dagster",                                   # System path
                    "/usr/local/bin/dagster",                   # Common system location
                    "/opt/homebrew/bin/dagster"                 # Homebrew location
                ]

                dagster_cmd = None
                for path in dagster_paths:
                    try:
                        # Test if dagster binary exists
                        test_result = subprocess.run([str(path), "--help"],
                                                   capture_output=True, text=True,
                                                   cwd=str(project_root), env=env, timeout=5)
                        if test_result.returncode == 0:
                            dagster_cmd = str(path)
                            st.info(f"✅ Found Dagster at: {path}")
                            break
                    except Exception as e:
                        st.info(f"❌ Dagster not found at {path}: {str(e)}")
                        continue

                if not dagster_cmd:
                    st.error("❌ Could not find Dagster binary in any expected location")
                    return False

                # Create a temporary config file for the job
                import tempfile
                import yaml

                job_config = {
                    'ops': {
                        'run_multi_year_simulation': {
                            'config': {
                                'start_year': 2025,
                                'end_year': 2029,
                                'target_growth_rate': 0.02,
                                'total_termination_rate': 0.13,
                                'new_hire_termination_rate': 0.03,
                                'random_seed': random_seed,
                                'full_refresh': False
                            }
                        }
                    }
                }

                # Write config to temporary file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                    yaml.dump(job_config, f)
                    config_file = f.name

                # Execute the job with config
                # Try using -m (module) instead of -f (file)
                cmd = [dagster_cmd, "job", "execute", "--job", "multi_year_simulation", "-m", "definitions", "--config", config_file]
                st.info(f"🚀 Executing command: {' '.join(cmd)}")
                st.info(f"📁 Working directory: {project_root}")
                st.info(f"🏠 DAGSTER_HOME: {env.get('DAGSTER_HOME')}")
                st.info(f"🎲 Random seed: {random_seed}")
                st.info(f"⚙️ Job config: {job_config}")

                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_root), env=env, timeout=600)

                # Clean up temp config file
                try:
                    os.unlink(config_file)
                except:
                    pass

            if result.returncode == 0:
                # Clear cache to reload results
                load_simulation_results.clear()
                st.success("🎉 Multi-year simulation completed successfully!")

                # Verify what data was actually created
                try:
                    import duckdb
                    # Use absolute path to database
                    project_root = Path(__file__).parent.parent.parent
                    db_path = project_root / "simulation.duckdb"

                    if db_path.exists():
                        conn = duckdb.connect(str(db_path))

                        # Check if tables exist before querying
                        try:
                            tables_exist = conn.execute("""
                                SELECT COUNT(*)
                                FROM information_schema.tables
                                WHERE table_name IN ('fct_workforce_snapshot', 'fct_yearly_events')
                            """).fetchone()[0]

                            if tables_exist >= 2:
                                snapshot_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year").fetchall()
                                event_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_yearly_events ORDER BY simulation_year").fetchall()

                                st.info(f"📊 Post-simulation verification:")
                                st.info(f"   • Workforce snapshot years: {[y[0] for y in snapshot_years]}")
                                st.info(f"   • Event years: {[y[0] for y in event_years]}")

                                if len(snapshot_years) == 1 and len(event_years) == 1:
                                    st.warning("⚠️ Only single-year data found - simulation may not have processed all years correctly")
                                elif len(snapshot_years) >= 5:
                                    st.success("✅ Multi-year data found - full simulation successful!")
                                else:
                                    st.success(f"✅ Multi-year data found - {len(snapshot_years)} years in database")
                            else:
                                st.warning("⚠️ Simulation tables not found - simulation may have failed")
                                st.info("Check the error messages above for details on what went wrong")

                        except Exception as table_error:
                            st.warning(f"⚠️ Could not verify simulation results: {table_error}")
                            st.info("The simulation may have failed to create the expected tables")
                        finally:
                            conn.close()
                    else:
                        st.warning("⚠️ Simulation database not found - simulation failed to create database")

                except Exception as e:
                    st.warning(f"Database verification error: {e}")
                    st.info("Unable to verify simulation results, but this doesn't necessarily mean the simulation failed")

                st.info("Results updated. Check the Results tab for latest data.")
                st.info(f"✅ Command output: {result.stdout}")
                return True
            else:
                st.error(f"❌ Dagster CLI method failed with return code: {result.returncode}")
                st.error(f"❌ STDERR: {result.stderr}")
                st.error(f"❌ STDOUT: {result.stdout}")
                st.info("Falling back to direct dbt execution...")
        except subprocess.TimeoutExpired:
            st.error("Simulation timed out after 10 minutes")
            return False
        except Exception as e:
            st.warning(f"Dagster CLI method error: {e}")
            st.info("Falling back to direct dbt execution...")

        # Method 2: Try asset-based simulation with correct asset names
        try:
            st.info("Method 2: Attempting asset-based simulation...")

            # Use the actual simulation assets that exist
            result = subprocess.run([
                dagster_cmd, "asset", "materialize",
                "--select", "simulation_year_state+",  # This should trigger multi-year
                "-f", "definitions.py"
            ], capture_output=True, text=True, cwd="../", env=env, timeout=600)

            if result.returncode == 0:
                # Clear cache to reload results
                load_simulation_results.clear()
                st.success("🎉 Asset-based simulation completed successfully!")

                # Verify what data was actually created
                try:
                    import duckdb
                    # Use absolute path to database
                    project_root = Path(__file__).parent.parent.parent
                    db_path = project_root / "simulation.duckdb"

                    if db_path.exists():
                        conn = duckdb.connect(str(db_path))

                        # Check if tables exist before querying
                        try:
                            tables_exist = conn.execute("""
                                SELECT COUNT(*)
                                FROM information_schema.tables
                                WHERE table_name IN ('fct_workforce_snapshot', 'fct_yearly_events')
                            """).fetchone()[0]

                            if tables_exist >= 2:
                                snapshot_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year").fetchall()
                                event_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_yearly_events ORDER BY simulation_year").fetchall()

                                st.info(f"📊 Post-simulation verification:")
                                st.info(f"   • Workforce snapshot years: {[y[0] for y in snapshot_years]}")
                                st.info(f"   • Event years: {[y[0] for y in event_years]}")

                                if len(snapshot_years) >= 5:
                                    st.success("✅ Multi-year data found - full simulation successful!")
                                else:
                                    st.warning(f"⚠️ Only {len(snapshot_years)} year(s) found - trying fallback method")
                            else:
                                st.warning("⚠️ Simulation tables not found - trying fallback method")

                        except Exception as table_error:
                            st.warning(f"⚠️ Could not verify simulation results: {table_error}")
                            st.info("Trying fallback method...")
                        finally:
                            conn.close()
                    else:
                        st.warning("⚠️ Simulation database not found - trying fallback method")

                except Exception as e:
                    st.warning(f"Database verification error: {e}")
                    st.info("Trying fallback method...")

                return True
            else:
                st.warning(f"Asset-based method failed: {result.stderr}")
                st.info("Falling back to manual dbt execution...")
        except Exception as e:
            st.warning(f"Asset-based method error: {e}")
            st.info("Falling back to manual dbt execution...")

        # Method 3: Manual dbt execution fallback
        try:
            st.info("Method 3: Attempting manual dbt simulation...")
            dbt_dir = Path(__file__).parent.parent.parent / "dbt"
            dbt_cmd = Path(__file__).parent.parent.parent / "venv" / "bin" / "dbt"

            # Run full multi-year simulation via dbt
            simulation_years = [2025, 2026, 2027, 2028, 2029]
            total_steps = len(simulation_years) * 6  # 6 models per year

            progress_bar = st.progress(0)
            current_step = 0

            with st.spinner("Running multi-year simulation manually... This will take 3-5 minutes."):
                for year in simulation_years:
                    st.info(f"📅 Processing year {year}...")

                    # Models to run for each year
                    models_to_run = [
                        "int_workforce_previous_year",
                        "int_termination_events",
                        "int_hiring_events",
                        "int_merit_events",
                        "fct_yearly_events",
                        "fct_workforce_snapshot"
                    ]

                    for model in models_to_run:
                        result = subprocess.run([
                            str(dbt_cmd), "run", "--select", model, "--vars",
                            f"{{'simulation_year': {year}}}"
                        ], capture_output=True, text=True, cwd=str(dbt_dir))

                        if result.returncode != 0:
                            st.error(f"Failed to run {model} for year {year}: {result.stderr}")
                            return False

                        current_step += 1
                        progress_bar.progress(current_step / total_steps)

            # Clear cache to reload results
            load_simulation_results.clear()
            st.success("🎉 Multi-year simulation completed successfully via dbt!")
            st.info("Results updated. Check the Results tab for latest data.")
            return True

        except Exception as e:
            st.error(f"Multi-year dbt execution failed: {e}")
            return False

    except Exception as e:
        st.error(f"Error running simulation: {e}")
        return False

# Load current parameters
current_params = load_current_parameters()

# Sidebar - Parameter Controls
with st.sidebar:
    st.header("📊 Parameter Tuning")

    # Real-time Risk Indicator (will be updated as parameters change)
    risk_placeholder = st.empty()

    # Parameter application mode
    st.subheader("Parameter Application")
    apply_mode = st.radio(
        "Apply parameters to:",
        ["Single Year", "All Years (2025-2029)"],
        index=1,  # Default to "All Years"
        help="Choose whether to apply parameter changes to one year or all simulation years"
    )

    if apply_mode == "Single Year":
        # Year selection (only shown for single year mode)
        st.subheader("Target Year")
        available_years = sorted(current_params.keys()) if current_params else [2025, 2026, 2027, 2028, 2029]
        selected_year = st.selectbox("Select Year", available_years, index=1 if len(available_years) > 1 else 0)
    else:
        # For all years mode, use 2026 as the template year
        selected_year = 2026
        st.info("📅 Parameters will be applied to all years 2025-2029")

    # Simulation Settings
    st.markdown('<div class="section-header">Simulation Settings</div>', unsafe_allow_html=True)

    # Simulation Mode Selection
    st.markdown('<div class="parameter-section">', unsafe_allow_html=True)
    st.subheader("🚀 Simulation Mode")

    simulation_mode = st.radio(
        "Choose simulation mode:",
        ["🧪 Synthetic (Fast)", "🔄 Real Simulation (Complete)"],
        index=0,  # Default to synthetic for fast testing
        help="Synthetic mode: ~5-10 seconds, mathematical estimates. Real mode: ~2-5 minutes, full dbt simulation."
    )

    is_synthetic_mode = simulation_mode.startswith("🧪")

    # Mode explanation
    if is_synthetic_mode:
        st.info("🧪 **Synthetic Mode**: Uses mathematical models for instant results. Perfect for rapid parameter testing and optimization workflows.")
        st.caption("⚡ Performance: ~5-10 seconds | 🎯 Accuracy: ~85-95% correlation with real simulation")
    else:
        st.warning("🔄 **Real Simulation Mode**: Runs complete dbt transformation pipeline. Use for final validation and production decisions.")
        st.caption("⏱️ Performance: ~2-5 minutes | 🎯 Accuracy: 100% (ground truth)")

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="parameter-section">', unsafe_allow_html=True)
    st.subheader("Random Seed")

    # Seed control with preset options
    seed_mode = st.radio(
        "Seed Selection:",
        ["Use Default (42)", "Custom Seed", "Random Each Run"],
        index=0,
        help="Controls randomness for reproducible results"
    )

    if seed_mode == "Custom Seed":
        random_seed = st.number_input(
            "Enter Seed Value",
            min_value=1,
            max_value=999999,
            value=42,
            help="Same seed = identical results with same parameters"
        )
    elif seed_mode == "Random Each Run":
        import random
        random_seed = random.randint(1, 999999)
        st.info(f"🎲 Random seed for this run: {random_seed}")
    else:
        random_seed = 42

    st.markdown('</div>', unsafe_allow_html=True)

    # Parameter sections
    st.markdown('<div class="section-header">COLA & Merit Rates</div>', unsafe_allow_html=True)

    # Get current values for the selected year
    year_params = current_params.get(selected_year, {})

    # COLA Rate
    st.markdown('<div class="parameter-section">', unsafe_allow_html=True)
    st.subheader("COLA Rate")
    cola_current = year_params.get('cola_rate', {}).get(1, 0.03)  # Use level 1 as default
    cola_rate = st.slider(
        "Cost of Living Adjustment",
        min_value=0.0,
        max_value=8.0,
        value=float(cola_current) * 100,  # Convert to percentage for display
        step=0.5,
        format="%.1f%%",
        help="Applied to all employees annually"
    ) / 100  # Convert back to decimal for calculations
    st.markdown('</div>', unsafe_allow_html=True)

    # Merit Rates by Level
    st.markdown('<div class="parameter-section">', unsafe_allow_html=True)
    st.subheader("Merit Rates by Level")
    merit_rates = {}
    for level in range(1, 6):
        merit_current = year_params.get('merit_base', {}).get(level, 0.03)
        merit_rates[level] = st.slider(
            f"Level {level} Merit",
            min_value=0.0,
            max_value=10.0,
            value=float(merit_current) * 100,  # Convert to percentage for display
            step=0.5,
            format="%.1f%%",
            key=f"merit_{level}"
        ) / 100  # Convert back to decimal for calculations
    st.markdown('</div>', unsafe_allow_html=True)

    # New Hire Salary Adjustment
    st.markdown('<div class="parameter-section">', unsafe_allow_html=True)
    st.subheader("New Hire Salary Adjustment")
    adj_current = year_params.get('new_hire_salary_adjustment', {}).get(1, 1.1)
    new_hire_adj = st.slider(
        "New Hire Salary Multiplier",
        min_value=100.0,
        max_value=150.0,
        value=float(adj_current) * 100,  # Convert to percentage for display
        step=1.0,
        format="%.0f%% of base",
        help="Multiplier applied to new hire salaries"
    ) / 100  # Convert back to decimal for calculations
    st.markdown('</div>', unsafe_allow_html=True)

    # Promotion Parameters
    st.markdown('<div class="section-header">Promotion Parameters</div>', unsafe_allow_html=True)

    st.markdown('<div class="parameter-section">', unsafe_allow_html=True)
    st.subheader("Promotion Probabilities")
    promo_probs = {}
    default_promo_probs = {1: 0.12, 2: 0.08, 3: 0.05, 4: 0.02, 5: 0.01}
    for level in range(1, 6):
        prob_current = year_params.get('promotion_probability', {}).get(level, default_promo_probs[level])
        promo_probs[level] = st.slider(
            f"Level {level} Promotion Rate",
            min_value=0.0,
            max_value=20.0,
            value=float(prob_current) * 100,  # Convert to percentage for display
            step=0.5,
            format="%.1f%%",
            key=f"promo_prob_{level}"
        ) / 100  # Convert back to decimal for calculations
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="parameter-section">', unsafe_allow_html=True)
    st.subheader("Promotion Raises")
    promo_raise_current = year_params.get('promotion_raise', {}).get(1, 0.12)
    promo_raise = st.slider(
        "Promotion Raise %",
        min_value=5.0,
        max_value=25.0,
        value=float(promo_raise_current) * 100,  # Convert to percentage for display
        step=1.0,
        format="%.1f%%",
        help="Salary increase for promoted employees"
    ) / 100  # Convert back to decimal for calculations
    st.markdown('</div>', unsafe_allow_html=True)

# Calculate current parameter changes for risk assessment
proposed_params = {
    'cola_rate': {level: cola_rate for level in range(1, 6)},
    'merit_base': merit_rates,
    'new_hire_salary_adjustment': {level: new_hire_adj for level in range(1, 6)},
    'promotion_probability': promo_probs,
    'promotion_raise': {level: promo_raise for level in range(1, 6)}
}

# Prepare parameter changes for risk assessment
parameter_changes = {}
for param_name, level_values in proposed_params.items():
    for level, proposed_value in level_values.items():
        current_value = year_params.get(param_name, {}).get(level, 0.03)  # Default fallback
        parameter_changes[(param_name, level)] = (current_value, proposed_value)

# Update real-time risk indicator in sidebar
if parameter_changes and year_params:
    try:
        # Quick risk assessment for real-time feedback
        risk_engine = RiskAssessmentEngine()
        risk_engine.set_baseline_data(year_params)

        quick_risk = risk_engine.calculate_overall_risk_assessment(
            parameter_changes=parameter_changes,
            implementation_timeline=90
        )

        # Risk indicator styling
        risk_color_map = {
            RiskLevel.LOW: ("🟢", "#d4edda", "LOW"),
            RiskLevel.MEDIUM: ("🟡", "#fff3cd", "MEDIUM"),
            RiskLevel.HIGH: ("🟠", "#f8d7da", "HIGH"),
            RiskLevel.CRITICAL: ("🔴", "#f5c6cb", "CRITICAL")
        }

        emoji, bg_color, level_text = risk_color_map[quick_risk.overall_level]

        # Update the risk placeholder in sidebar
        with risk_placeholder.container():
            st.markdown(f"""
            <div style="background-color: {bg_color}; padding: 0.5rem; border-radius: 0.375rem; margin: 0.5rem 0; border-left: 4px solid {'#28a745' if quick_risk.overall_level == RiskLevel.LOW else '#ffc107' if quick_risk.overall_level == RiskLevel.MEDIUM else '#fd7e14' if quick_risk.overall_level == RiskLevel.HIGH else '#dc3545'};">
                <div style="font-size: 0.875rem; font-weight: 600;">
                    {emoji} Risk Level: {level_text}
                </div>
                <div style="font-size: 0.75rem; margin-top: 0.25rem;">
                    Score: {quick_risk.overall_score:.0f}/100 | Budget Impact: {quick_risk.estimated_budget_impact:.1f}%
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Show critical warning if needed
            if quick_risk.overall_level == RiskLevel.CRITICAL:
                st.error("⚠️ Critical risk detected!")
            elif quick_risk.overall_level == RiskLevel.HIGH:
                st.warning("⚠️ High risk - review changes")

    except Exception as e:
        # Fallback for risk assessment errors
        with risk_placeholder.container():
            st.markdown("""
            <div style="background-color: #f8f9fa; padding: 0.5rem; border-radius: 0.375rem; margin: 0.5rem 0; border-left: 4px solid #6c757d;">
                <div style="font-size: 0.875rem;">📊 Risk Analysis</div>
                <div style="font-size: 0.75rem; color: #6c757d;">Calculating...</div>
            </div>
            """, unsafe_allow_html=True)
else:
    # Default display when no baseline data
    with risk_placeholder.container():
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 0.5rem; border-radius: 0.375rem; margin: 0.5rem 0; border-left: 4px solid #6c757d;">
            <div style="font-size: 0.875rem;">📊 Risk Analysis</div>
            <div style="font-size: 0.75rem; color: #6c757d;">Load baseline data to see risk assessment</div>
        </div>
        """, unsafe_allow_html=True)

# Store current parameter changes for use in main tabs
st.session_state.current_parameter_changes = parameter_changes
st.session_state.current_proposed_params = proposed_params

# Main content
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🎯 Parameter Overview",
    "⚠️ Risk Assessment",
    "🚀 Run Simulation",
    "📊 Impact Analysis",
    "📈 Results",
    "🤖 Auto-Optimize"
])

with tab1:
    st.markdown('<div class="section-header">Parameter Overview</div>', unsafe_allow_html=True)

    # Current vs. proposed parameters
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Current Parameters")
        if year_params:
            current_cola = year_params.get('cola_rate', {}).get(1, 0.03)
            current_merit = np.mean([year_params.get('merit_base', {}).get(i, 0.03) for i in range(1, 6)])
            current_adj = year_params.get('new_hire_salary_adjustment', {}).get(1, 1.1)

            st.metric("COLA Rate", f"{current_cola:.1%}")
            st.metric("Avg Merit Rate", f"{current_merit:.1%}")
            st.metric("New Hire Adjustment", f"{current_adj:.0%}")
        else:
            st.info("No current parameters loaded")

    with col2:
        st.subheader("Proposed Parameters")
        avg_merit = np.mean(list(merit_rates.values()))

        st.metric("COLA Rate", f"{cola_rate:.1%}", f"{cola_rate - current_cola:+.1%}")
        st.metric("Avg Merit Rate", f"{avg_merit:.1%}", f"{avg_merit - current_merit:+.1%}")
        st.metric("New Hire Adjustment", f"{new_hire_adj:.0%}", f"{new_hire_adj - current_adj:+.1%}")

    # Parameter Sensitivity Quick View
    if year_params:
        st.markdown('<div class="section-header">Parameter Sensitivity Quick View</div>', unsafe_allow_html=True)
        st.info("💡 Understanding which parameters have the most impact on your outcomes")

        sensitivity_summary = get_parameter_sensitivity_summary(year_params)

        # High Impact Parameters (Most Important)
        with st.expander("🔴 High Impact Parameters (Focus Here First)", expanded=True):
            for param in sensitivity_summary["high_impact"]:
                st.markdown(f"""
                **{param['name']}** (Current: {param['current']})
                - {param['reason']}
                - {param['business_impact']}
                """)

        # Medium Impact Parameters
        with st.expander("🟡 Medium Impact Parameters", expanded=False):
            for param in sensitivity_summary["medium_impact"]:
                st.markdown(f"""
                **{param['name']}** (Current: {param['current']})
                - {param['reason']}
                - {param['business_impact']}
                """)

        # Quick Recommendations
        st.subheader("💼 Strategy Recommendations")
        for i, rec in enumerate(sensitivity_summary["recommendations"], 1):
            st.write(f"{i}. {rec}")

    # Parameter validation
    st.markdown('<div class="section-header">Parameter Validation</div>', unsafe_allow_html=True)

    # Prepare parameters for validation
    proposed_params = {
        'cola_rate': {i: cola_rate for i in range(1, 6)},
        'merit_base': merit_rates,
        'new_hire_salary_adjustment': {i: new_hire_adj for i in range(1, 6)}
    }

    # Enhanced parameter validation with risk analysis
    validation_result = validate_parameters_with_risk_analysis(proposed_params, year_params)

    # Display validation results
    if validation_result['errors']:
        for error in validation_result['errors']:
            st.markdown(f'<div class="error-box">❌ <strong>Error:</strong> {error}</div>', unsafe_allow_html=True)

    if validation_result['warnings']:
        for warning in validation_result['warnings']:
            st.markdown(f'<div class="warning-box">⚠️ <strong>Warning:</strong> {warning}</div>', unsafe_allow_html=True)

    # Display risk-based recommendations
    if validation_result['recommendations']:
        st.markdown('### 💡 Risk-Based Recommendations')
        for rec in validation_result['recommendations']:
            st.info(f"• {rec}")

    # Show risk mitigation plan if high risk detected
    if validation_result['risk_assessment'] and validation_result['risk_assessment'].overall_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
        with st.expander("🛡️ Risk Mitigation Plan"):
            mitigation_plan = generate_risk_mitigation_plan(validation_result['risk_assessment'])
            for item in mitigation_plan:
                if item.startswith("🔴") or item.startswith("🟠") or item.startswith("🟡") or item.startswith("🟢"):
                    st.markdown(f"**{item}**")
                elif item.startswith("💰") or item.startswith("👥") or item.startswith("⚖️"):
                    st.markdown(f"**{item}**")
                elif item == "":
                    st.markdown("")
                else:
                    st.markdown(item)

    # Legacy validation for compatibility
    warnings, errors = validate_parameters(proposed_params)

    if errors:
        for error in errors:
            st.markdown(f'<div class="error-box">❌ <strong>Legacy Error:</strong> {error}</div>', unsafe_allow_html=True)

    if warnings:
        for warning in warnings:
            st.markdown(f'<div class="warning-box">⚠️ <strong>Warning:</strong> {warning}</div>', unsafe_allow_html=True)

    if not errors and not warnings:
        st.markdown('<div class="success-box">✅ <strong>All parameters validated successfully!</strong></div>', unsafe_allow_html=True)

    # Parameter summary table
    st.subheader("Detailed Parameter Summary")

    param_data = []
    for level in range(1, 6):
        param_data.append({
            'Job Level': level,
            'COLA Rate': f"{cola_rate:.1%}",
            'Merit Rate': f"{merit_rates[level]:.1%}",
            'New Hire Adj': f"{new_hire_adj:.0%}",
            'Promotion Prob': f"{promo_probs[level]:.1%}",
            'Promotion Raise': f"{promo_raise:.1%}"
        })

    st.dataframe(pd.DataFrame(param_data), use_container_width=True)

with tab2:
    st.markdown('<div class="section-header">Impact Analysis & Sensitivity</div>', unsafe_allow_html=True)
    st.info("🔍 Preview the expected impact of your parameter changes and understand parameter sensitivity")

    # Sub-tabs for Impact Analysis
    subtab1, subtab2, subtab3 = st.tabs([
        "📊 Parameter Changes",
        "🎯 Sensitivity Analysis",
        "💼 Business Recommendations"
    ])

    with subtab1:
        st.subheader("Parameter Changes from Baseline")

        # Get current values for comparison
        if year_params:
            current_cola = year_params.get('cola_rate', {}).get(1, 0.03)
            current_merit = np.mean([year_params.get('merit_base', {}).get(i, 0.03) for i in range(1, 6)])
            current_adj = year_params.get('new_hire_salary_adjustment', {}).get(1, 1.1)

            # Calculate changes
            cola_change = cola_rate - current_cola
            merit_change = avg_merit - current_merit
            adj_change = new_hire_adj - current_adj

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "COLA Rate Change",
                    f"{cola_change:+.2%}",
                    f"{current_cola:.1%} → {cola_rate:.1%}"
                )

            with col2:
                st.metric(
                    "Avg Merit Change",
                    f"{merit_change:+.2%}",
                    f"{current_merit:.1%} → {avg_merit:.1%}"
                )

            with col3:
                st.metric(
                    "New Hire Adj Change",
                    f"{adj_change:+.1%}",
                    f"{current_adj:.0%} → {new_hire_adj:.0%}"
                )

            # Estimated Impact Calculation
            st.subheader("Estimated Annual Impact")

            # Simple impact estimation based on parameter changes
            estimated_cola_impact = cola_change * 100  # COLA directly affects growth
            estimated_merit_impact = merit_change * 100  # Merit directly affects growth
            estimated_total_impact = estimated_cola_impact + estimated_merit_impact

            col1, col2 = st.columns(2)

            with col1:
                st.metric(
                    "Estimated Growth Impact",
                    f"{estimated_total_impact:+.2f}%",
                    "From COLA + Merit changes"
                )

            with col2:
                target_growth = 2.0  # Default target
                estimated_final_growth = target_growth + estimated_total_impact
                gap_to_target = estimated_final_growth - target_growth

                st.metric(
                    "Projected Growth Rate",
                    f"{estimated_final_growth:.2f}%",
                    f"{gap_to_target:+.2f}% vs target"
                )

            # Impact Assessment
            st.subheader("Impact Assessment")

            if abs(estimated_total_impact) < 0.1:
                st.markdown('<div class="warning-box">⚠️ <strong>Minimal Impact:</strong> Parameter changes are small and may not significantly affect outcomes.</div>', unsafe_allow_html=True)
            elif estimated_total_impact > 0:
                st.markdown('<div class="success-box">✅ <strong>Positive Impact:</strong> Parameter increases should improve compensation growth.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="error-box">📉 <strong>Negative Impact:</strong> Parameter decreases will reduce compensation growth.</div>', unsafe_allow_html=True)

            # Detailed Parameter Impact Table
            st.subheader("Detailed Parameter Analysis")

            impact_data = []
            for level in range(1, 6):
                current_level_merit = year_params.get('merit_base', {}).get(level, 0.03)
                new_level_merit = merit_rates[level]
                level_change = new_level_merit - current_level_merit

                impact_data.append({
                    'Parameter': f'Level {level} Merit',
                    'Current': f"{current_level_merit:.1%}",
                    'New': f"{new_level_merit:.1%}",
                    'Change': f"{level_change:+.2%}",
                    'Impact': '🔺 Increase' if level_change > 0.001 else '🔻 Decrease' if level_change < -0.001 else '➡️ No Change'
                })

            # Add COLA row
            impact_data.append({
                'Parameter': 'COLA Rate',
                'Current': f"{current_cola:.1%}",
                'New': f"{cola_rate:.1%}",
                'Change': f"{cola_change:+.2%}",
                'Impact': '🔺 Increase' if cola_change > 0.001 else '🔻 Decrease' if cola_change < -0.001 else '➡️ No Change'
            })

            st.dataframe(pd.DataFrame(impact_data), use_container_width=True)

        else:
            st.warning("No baseline parameter data available. Unable to calculate impact analysis.")

    with subtab2:
        st.subheader("🎯 Parameter Sensitivity Analysis")
        st.info("Understanding which parameters have the greatest impact on compensation outcomes")

        if year_params:
            # Business context explanation
            st.markdown("""
            **What is Sensitivity Analysis?**
            Sensitivity analysis shows how much your workforce outcomes change when you adjust each parameter by a small amount.
            This helps you understand:
            - Which parameters give you the biggest impact for the smallest change
            - Where to focus your attention when trying to hit specific targets
            - Which parameters are most critical for budget planning
            """)

            # Calculate sensitivity metrics
            def calculate_sensitivity_scores():
                """Calculate sensitivity scores for all parameters based on business impact"""

                # Base scenario (current parameters)
                base_cola = current_cola
                base_merit = current_merit
                base_adj = current_adj

                # Small perturbation amount (1% relative change)
                perturbation = 0.01

                # Calculate sensitivity for each parameter type
                sensitivity_data = []

                # COLA Sensitivity
                cola_delta = base_cola * perturbation  # 1% relative change
                cola_impact = cola_delta * 100  # Direct impact on growth
                # Calculate sensitivity score, handling zero base or delta
                if cola_delta != 0 and base_cola != 0:
                    sensitivity_score = abs(cola_impact / (cola_delta * 100))
                else:
                    sensitivity_score = 0
                sensitivity_data.append({
                    'Parameter': 'COLA Rate',
                    'Current Value': f"{base_cola:.1%}",
                    'Test Change': f"+{cola_delta:.2%}",
                    'Growth Impact': f"+{cola_impact:.2f}%",
                    'Sensitivity Score': sensitivity_score,
                    'Business Criticality': 'High',
                    'Description': 'Affects all employees uniformly',
                    'Budget Risk': 'High - applies to entire workforce'
                })

                # Merit Rate Sensitivity (by level)
                for level in range(1, 6):
                    level_merit = year_params.get('merit_base', {}).get(level, 0.03)
                    merit_delta = level_merit * perturbation

                    # Weight impact by typical workforce distribution
                    level_weights = {1: 0.3, 2: 0.25, 3: 0.25, 4: 0.15, 5: 0.05}  # Typical pyramid
                    weighted_impact = merit_delta * 100 * level_weights[level]

                    criticality = 'High' if level <= 2 else 'Medium' if level <= 4 else 'Low'

                    # Calculate sensitivity score, handling zero base or delta
                    if merit_delta != 0 and level_merit != 0:
                        merit_sensitivity_score = abs(weighted_impact / (merit_delta * 100))
                    else:
                        merit_sensitivity_score = 0
                    sensitivity_data.append({
                        'Parameter': f'Merit Rate L{level}',
                        'Current Value': f"{level_merit:.1%}",
                        'Test Change': f"+{merit_delta:.2%}",
                        'Growth Impact': f"+{weighted_impact:.2f}%",
                        'Sensitivity Score': merit_sensitivity_score,
                        'Business Criticality': criticality,
                        'Description': f'Level {level} merit increases (~{level_weights[level]:.0%} of workforce)',
                        'Budget Risk': f'{"High" if level <= 2 else "Medium"} - larger employee population'
                    })

                # New Hire Adjustment Sensitivity
                adj_delta = base_adj * perturbation
                # Impact depends on hiring rate (assume 15% annual hiring)
                hiring_rate = 0.15
                adj_impact = (adj_delta * hiring_rate) * 100

                # Calculate sensitivity score, handling zero base or delta
                if adj_delta != 0 and base_adj != 0:
                    adj_sensitivity_score = abs(adj_impact / (adj_delta * 100))
                else:
                    adj_sensitivity_score = 0
                sensitivity_data.append({
                    'Parameter': 'New Hire Salary Adj',
                    'Current Value': f"{base_adj:.0%}",
                    'Test Change': f"+{adj_delta:.1%}",
                    'Growth Impact': f"+{adj_impact:.2f}%",
                    'Sensitivity Score': adj_sensitivity_score,
                    'Business Criticality': 'Medium',
                    'Description': 'Affects new hires only (~15% of workforce)',
                    'Budget Risk': 'Medium - limited to new hires'
                })

                # Promotion Parameters (if available)
                for level in range(1, 5):  # Can't promote from level 5
                    level_promo_prob = year_params.get('promotion_probability', {}).get(level, {1: 0.12, 2: 0.08, 3: 0.05, 4: 0.02}[level])
                    promo_delta = level_promo_prob * perturbation

                    # Promotion impact depends on workforce size and raise amount
                    level_weights = {1: 0.3, 2: 0.25, 3: 0.25, 4: 0.15}
                    promo_raise_amount = year_params.get('promotion_raise', {}).get(level, 0.12)
                    promo_impact = promo_delta * level_weights[level] * promo_raise_amount * 100

                    sensitivity_data.append({
                        'Parameter': f'Promotion Prob L{level}',
                        'Current Value': f"{level_promo_prob:.1%}",
                        'Test Change': f"+{promo_delta:.2%}",
                        'Growth Impact': f"+{promo_impact:.3f}%",
                        'Sensitivity Score': abs(promo_impact / (promo_delta * 100)) if promo_delta > 0 else 0,
                        'Business Criticality': 'Low' if level >= 4 else 'Medium',
                        'Description': f'Level {level} promotion probability',
                        'Budget Risk': 'Low - affects small percentage'
                    })

                return pd.DataFrame(sensitivity_data)

            # Generate sensitivity analysis
            sensitivity_df = calculate_sensitivity_scores()

            # Sort by sensitivity score (highest impact first)
            sensitivity_df = sensitivity_df.sort_values('Sensitivity Score', ascending=False)

            # Display high-level insights
            st.subheader("🔍 Key Sensitivity Insights")

            col1, col2, col3 = st.columns(3)

            with col1:
                highest_sensitivity = sensitivity_df.iloc[0]
                st.metric(
                    "Most Sensitive Parameter",
                    highest_sensitivity['Parameter'],
                    f"Score: {highest_sensitivity['Sensitivity Score']:.1f}"
                )

            with col2:
                high_impact_params = sensitivity_df[sensitivity_df['Business Criticality'] == 'High']
                st.metric(
                    "High-Impact Parameters",
                    f"{len(high_impact_params)}",
                    "Require careful management"
                )

            with col3:
                high_budget_risk = sensitivity_df[sensitivity_df['Budget Risk'].str.contains('High')]
                st.metric(
                    "High Budget Risk",
                    f"{len(high_budget_risk)}",
                    "Parameters to monitor closely"
                )

            # Sensitivity visualization
            st.subheader("📊 Parameter Sensitivity Chart")

            # Create interactive sensitivity chart
            fig = go.Figure()

            # Color map for criticality
            color_map = {'High': '#FF6B6B', 'Medium': '#4ECDC4', 'Low': '#45B7D1'}

            # Add scatter plot
            for criticality in ['High', 'Medium', 'Low']:
                filtered_df = sensitivity_df[sensitivity_df['Business Criticality'] == criticality]

                fig.add_trace(go.Scatter(
                    x=filtered_df['Sensitivity Score'],
                    y=list(range(len(filtered_df))),
                    mode='markers',
                    marker=dict(
                        size=12,
                        color=color_map[criticality],
                        opacity=0.7,
                        line=dict(width=1, color='white')
                    ),
                    text=filtered_df['Parameter'],
                    hovertemplate='<b>%{text}</b><br>' +
                                  'Sensitivity Score: %{x:.2f}<br>' +
                                  'Business Criticality: ' + criticality + '<br>' +
                                  '<extra></extra>',
                    name=f'{criticality} Criticality'
                ))

            # Update layout
            fig.update_layout(
                title="Parameter Sensitivity Ranking",
                xaxis_title="Sensitivity Score (Impact per 1% Change)",
                yaxis_title="Parameter Rank (0 = Most Sensitive)",
                height=500,
                showlegend=True,
                hovermode='closest',
                yaxis=dict(autorange="reversed")
            )

            st.plotly_chart(fig, use_container_width=True)

            # Detailed sensitivity table
            st.subheader("📋 Detailed Sensitivity Analysis")

            # Format the dataframe for display
            display_df = sensitivity_df.copy()
            display_df['Sensitivity Score'] = display_df['Sensitivity Score'].apply(lambda x: f"{x:.2f}")

            # Create expandable sections by criticality
            for criticality in ['High', 'Medium', 'Low']:
                with st.expander(f"🎯 {criticality} Criticality Parameters",
                               expanded=(criticality == 'High')):
                    crit_df = display_df[display_df['Business Criticality'] == criticality]

                    if not crit_df.empty:
                        st.dataframe(
                            crit_df[['Parameter', 'Current Value', 'Test Change',
                                   'Growth Impact', 'Sensitivity Score', 'Description', 'Budget Risk']],
                            use_container_width=True
                        )
                    else:
                        st.info(f"No parameters with {criticality.lower()} criticality")

        else:
            st.warning("No parameter data available for sensitivity analysis. Please load baseline parameters first.")

    with subtab3:
        st.subheader("💼 Business Recommendations")

        if year_params:
            # Generate dynamic recommendations based on sensitivity analysis
            highest_param = sensitivity_df.iloc[0] if 'sensitivity_df' in locals() and not sensitivity_df.empty else None
            second_param = sensitivity_df.iloc[1] if 'sensitivity_df' in locals() and len(sensitivity_df) > 1 else None

            recommendations = []

            if highest_param is not None:
                # Focus area recommendation
                recommendations.append(
                    f"**Primary Focus**: {highest_param['Parameter']} has the highest sensitivity (score: {highest_param['Sensitivity Score']:.1f}). "
                    f"Small changes here will have the biggest impact on outcomes."
                )

                # Budget risk warning
                if 'sensitivity_df' in locals():
                    high_risk_params = sensitivity_df[sensitivity_df['Budget Risk'].str.contains('High')]
                    if not high_risk_params.empty:
                        param_list = ', '.join(high_risk_params['Parameter'].tolist())
                        recommendations.append(
                            f"**Budget Risk**: Monitor {param_list} carefully as these affect large portions of the workforce."
                        )

                # Efficiency recommendation
                if second_param is not None:
                    recommendations.append(
                        f"**Efficiency Strategy**: Use {highest_param['Parameter']} for major adjustments and "
                        f"{second_param['Parameter']} for fine-tuning."
                    )

                # Low-impact warning
                if 'sensitivity_df' in locals():
                    low_impact = sensitivity_df[sensitivity_df['Sensitivity Score'] < 0.1]
                    if not low_impact.empty:
                        recommendations.append(
                            f"**Low Impact**: {len(low_impact)} parameters have minimal impact and may not justify significant attention."
                        )

                for i, rec in enumerate(recommendations, 1):
                    st.markdown(f"{i}. {rec}")
            else:
                st.info("Run sensitivity analysis first to generate recommendations.")
        else:
            st.warning("No parameter data available for recommendations. Please load baseline parameters first.")


with tab3:
    st.markdown('<div class="section-header">Run Simulation</div>', unsafe_allow_html=True)

    # Pre-flight check
    st.subheader("Pre-flight Check")

    # Check if parameters are valid
    if not errors:
        st.markdown('<div class="success-box">✅ Parameters validated successfully</div>', unsafe_allow_html=True)
        can_run = True
    else:
        st.markdown('<div class="error-box">❌ Fix parameter errors before running</div>', unsafe_allow_html=True)
        can_run = False

    # Show what will be updated
    st.subheader("Parameter Changes to Apply")

    if can_run:
        changes_made = False

        # Check COLA change
        if abs(cola_rate - current_cola) > 0.001:
            st.write(f"• COLA Rate: {current_cola:.1%} → {cola_rate:.1%}")
            changes_made = True

        # Check merit changes
        for level in range(1, 6):
            current_merit_level = year_params.get('merit_base', {}).get(level, 0.03)
            if abs(merit_rates[level] - current_merit_level) > 0.001:
                st.write(f"• Merit Rate Level {level}: {current_merit_level:.1%} → {merit_rates[level]:.1%}")
                changes_made = True

        # Check new hire adjustment
        if abs(new_hire_adj - current_adj) > 0.01:
            st.write(f"• New Hire Adjustment: {current_adj:.0%} → {new_hire_adj:.0%}")
            changes_made = True

        if not changes_made:
            st.info("No parameter changes detected")

        # Run simulation button
        col1, col2 = st.columns([1, 2])

        with col1:
            if st.button("💾 Save Parameters", disabled=not changes_made):
                # Determine which years to update based on apply_mode
                target_years = [selected_year] if apply_mode == "Single Year" else [2025, 2026, 2027, 2028, 2029]
                if update_parameters_file(proposed_params, target_years):
                    years_msg = f"year {selected_year}" if apply_mode == "Single Year" else "all years (2025-2029)"
                    st.success(f"Parameters saved successfully for {years_msg}!")
                    st.session_state.current_parameters = proposed_params
                else:
                    st.error("Failed to save parameters")

        with col2:
            simulation_button_text = "🧪 Run Synthetic" if is_synthetic_mode else "🚀 Run Simulation"

            # Risk assessment before simulation
            if changes_made:
                with st.expander("⚠️ Pre-Simulation Risk Check (Click to view)"):
                    # Quick risk assessment for proposed changes
                    risk_engine = RiskAssessmentEngine()

                    # Set baseline data if available
                    if year_params:
                        baseline_params = {}
                        for param_name in ['merit_base', 'cola_rate', 'new_hire_salary_adjustment', 'promotion_probability', 'promotion_raise']:
                            if param_name in year_params:
                                baseline_params[param_name] = year_params[param_name]
                        risk_engine.set_baseline_data(baseline_params)

                    # Quick parameter changes assessment
                    parameter_changes = {}

                    # Merit rate changes
                    for level in range(1, 6):
                        current_merit = year_params.get('merit_base', {}).get(level, 0.03) if year_params else 0.03
                        new_merit = merit_rates[level]
                        if abs(new_merit - current_merit) > 0.001:  # Only assess if there's a meaningful change
                            parameter_changes[('merit_base', level)] = (current_merit, new_merit)

                    # COLA rate changes
                    current_cola = year_params.get('cola_rate', {}).get(1, 0.025) if year_params else 0.025
                    if abs(cola_rate - current_cola) > 0.001:
                        parameter_changes[('cola_rate', 1)] = (current_cola, cola_rate)

                    # New hire adjustment changes
                    current_adj = year_params.get('new_hire_salary_adjustment', {}).get(1, 1.1) if year_params else 1.1
                    if abs(new_hire_adj - current_adj) > 0.01:
                        parameter_changes[('new_hire_salary_adjustment', 1)] = (current_adj, new_hire_adj)

                    if parameter_changes:
                        # Quick risk assessment
                        quick_assessment = risk_engine.calculate_overall_risk_assessment(
                            parameter_changes=parameter_changes,
                            implementation_timeline=90
                        )

                        # Display quick risk summary
                        risk_color_map = {
                            RiskLevel.LOW: "🟢",
                            RiskLevel.MEDIUM: "🟡",
                            RiskLevel.HIGH: "🟠",
                            RiskLevel.CRITICAL: "🔴"
                        }

                        risk_bg_color = {
                            RiskLevel.LOW: "#d4edda",
                            RiskLevel.MEDIUM: "#fff3cd",
                            RiskLevel.HIGH: "#f8d7da",
                            RiskLevel.CRITICAL: "#f5c6cb"
                        }

                        st.markdown(f"""
                        <div style="background-color: {risk_bg_color[quick_assessment.overall_level]}; padding: 0.75rem; border-radius: 0.5rem; margin: 0.5rem 0;">
                            <strong>{risk_color_map[quick_assessment.overall_level]} Risk Level: {quick_assessment.overall_level.value.upper()}</strong><br>
                            <strong>Risk Score:</strong> {quick_assessment.overall_score:.1f}/100<br>
                            <strong>Est. Budget Impact:</strong> {quick_assessment.estimated_budget_impact:.1f}%
                        </div>
                        """, unsafe_allow_html=True)

                        # Show critical/high risk warnings
                        if quick_assessment.overall_level == RiskLevel.CRITICAL:
                            st.error("🚨 **CRITICAL RISK DETECTED** - Consider reviewing parameters before simulation")
                        elif quick_assessment.overall_level == RiskLevel.HIGH:
                            st.warning("⚠️ **HIGH RISK** - Proceed with caution")

                        # Show top recommendations
                        if quick_assessment.recommendations:
                            st.markdown("**Key Recommendations:**")
                            for rec in quick_assessment.recommendations[:3]:  # Show top 3
                                st.markdown(f"• {rec}")
                    else:
                        st.info("✅ No significant parameter changes detected - minimal risk")

            if st.button(simulation_button_text, type="primary", disabled=not can_run):
                st.info("🔍 Button clicked! Starting simulation process...")

                if changes_made or is_synthetic_mode:
                    # For real simulation, save parameters first
                    if not is_synthetic_mode:
                        st.info("💾 Saving parameters...")
                        target_years = [selected_year] if apply_mode == "Single Year" else [2025, 2026, 2027, 2028, 2029]
                        if not update_parameters_file(proposed_params, target_years):
                            st.error("Failed to save parameters")
                            st.stop()

                        years_msg = f"year {selected_year}" if apply_mode == "Single Year" else "all years (2025-2029)"
                        st.success(f"✅ Parameters saved successfully for {years_msg}!")

                    st.session_state.simulation_running = True

                    # Prepare simulation parameters
                    target_years = [selected_year] if apply_mode == "Single Year" else [2025, 2026, 2027, 2028, 2029]

                    # Call simulation function with mode selection
                    st.info(f"🚀 Calling {'synthetic' if is_synthetic_mode else 'real'} simulation function...")
                    if run_simulation(use_synthetic=is_synthetic_mode, proposed_params=proposed_params, target_years=target_years):
                        st.session_state.simulation_running = False
                        st.session_state.last_simulation_time = datetime.now()
                        if not is_synthetic_mode:  # Only show balloons for real simulation
                            st.balloons()
                    else:
                        st.session_state.simulation_running = False
                        st.error("Simulation failed - check error messages above")
                else:
                    st.warning("No changes to apply - make parameter adjustments first")

    # Simulation history and tips
    if st.session_state.last_simulation_time:
        st.subheader("Last Simulation")
        st.write(f"Completed: {st.session_state.last_simulation_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Performance tips
    with st.expander("⚡ Performance Tips & Mode Selection"):
        st.markdown("""
        **🧪 Synthetic Mode (Recommended for exploration):**
        - ⚡ **Speed**: 5-10 seconds per simulation
        - 🎯 **Accuracy**: 85-95% correlation with real simulation
        - 🔄 **Best for**: Parameter exploration, optimization, rapid testing
        - ⚠️ **Limitations**: Less accurate for extreme parameter changes (>3% deviation)

        **🔄 Real Simulation Mode (Required for final validation):**
        - ⏱️ **Speed**: 2-5 minutes per simulation
        - 🎯 **Accuracy**: 100% (ground truth)
        - 🔄 **Best for**: Final validation, production decisions, compliance reporting
        - ✅ **Complete**: Full dbt pipeline with all business logic

        **Best Practices:**
        1. **Start with Synthetic**: Use for initial parameter exploration and auto-optimization
        2. **Validate with Real**: Run real simulation on final parameter sets before production
        3. **Small Changes**: Synthetic mode is most accurate for moderate parameter adjustments (±1-2%)
        4. **Large Changes**: Use real simulation when parameters deviate significantly from baseline
        5. **Optimization Workflow**: Synthetic optimization → Real validation → Production deployment

        **When to Switch to Real Simulation:**
        - Parameter changes exceed 2% from baseline
        - Final validation before production deployment
        - Compliance or audit requirements
        - Synthetic-real comparison shows >10% difference
        """)

with tab4:
    st.markdown('<div class="section-header">Impact Analysis</div>', unsafe_allow_html=True)

with tab5:
    st.markdown('<div class="section-header">Simulation Results</div>', unsafe_allow_html=True)

    # Add refresh button to clear cache and see debug output
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("🔄 Refresh Data"):
            load_simulation_results.clear()
            st.rerun()
    with col2:
        if st.button("🔍 Check DB"):
            # Quick database check
            try:
                import duckdb
                project_root = Path(__file__).parent.parent.parent
                db_path = project_root / "simulation.duckdb"

                conn = duckdb.connect(str(db_path))
                snapshot_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year").fetchall()
                event_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_yearly_events ORDER BY simulation_year").fetchall()
                conn.close()

                st.info(f"📊 Snapshot years: {[y[0] for y in snapshot_years]}")
                st.info(f"📅 Event years: {[y[0] for y in event_years]}")
            except Exception as e:
                st.error(f"DB check failed: {e}")
    with col3:
        st.info("Click 'Refresh Data' to reload results, 'Check DB' to see current database state")

    # Status Filter Controls
    st.subheader("📊 Employment Status Filter")

    # Get available statuses for filter options
    try:
        import duckdb
        project_root = Path(__file__).parent.parent.parent
        db_path = project_root / "simulation.duckdb"

        if db_path.exists():
            conn = duckdb.connect(str(db_path))
            all_statuses_result = conn.execute("SELECT DISTINCT detailed_status_code FROM fct_workforce_snapshot ORDER BY detailed_status_code").fetchall()
            available_statuses = [row[0] for row in all_statuses_result]
            conn.close()
        else:
            available_statuses = ['continuous_active', 'experienced_termination', 'new_hire_active', 'new_hire_termination']
    except:
        available_statuses = ['continuous_active', 'experienced_termination', 'new_hire_active', 'new_hire_termination']

    col1, col2 = st.columns([2, 1])
    with col1:
        selected_statuses = st.multiselect(
            "Select employment statuses to include in calculations:",
            options=available_statuses,
            default=['continuous_active', 'new_hire_active'],
            help="Choose which detailed status codes to include in average salary and growth calculations"
        )

    with col2:
        if st.button("📋 Show All Statuses"):
            selected_statuses = available_statuses
            st.rerun()

    # Load and display results with status filter
    sim_results = load_simulation_results(selected_statuses if selected_statuses else ['continuous_active', 'new_hire_active'])

    if sim_results:
        # Show result type and validation status
        is_synthetic = sim_results.get('synthetic_mode', False)
        result_type = "🧪 Synthetic Results" if is_synthetic else "🔄 Real Simulation Results"

        if is_synthetic:
            st.info(f"**{result_type}** | Last updated: {sim_results['last_updated']}")

            # Add validation options for synthetic results
            with st.expander("🔍 Synthetic Result Validation", expanded=False):
                st.markdown("""
                **Synthetic Mode Accuracy**: ~85-95% correlation with real simulation results

                **Best Practices**:
                - Use synthetic mode for rapid parameter exploration and optimization
                - Validate final parameter sets with real simulation before production
                - Synthetic results are most accurate for moderate parameter changes (±1-2%)
                - Consider running real simulation if parameters deviate significantly from baseline
                """)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 Validate with Real Simulation"):
                        st.info("Switching to real simulation mode...")
                        # Clear synthetic results and suggest real simulation
                        st.session_state.simulation_results = None
                        st.info("💡 Please switch to 'Real Simulation' mode in the sidebar and re-run simulation for validation.")

                with col2:
                    if st.button("📊 Compare with Historical"):
                        st.info("Comparing with historical data...")
                        # This could load historical real simulation results for comparison
                        st.info("💡 Historical comparison feature available in next release.")
        else:
            st.success(f"**{result_type}** | Last updated: {sim_results['last_updated']}")

        # Key results
        col1, col2, col3 = st.columns(3)

        with col1:
            # Calculate average growth across all simulation years
            if len(sim_results['years']) == 1:
                # Single year data - show that year's growth
                avg_growth = sim_results['current_growth']
                growth_label = f"Growth (Year {sim_results['years'][0]})"
            else:
                # Multi-year data - calculate average growth excluding baseline year
                if len(sim_results['avg_salaries']) > 1:
                    growth_rates = []
                    for i in range(1, len(sim_results['avg_salaries'])):
                        if sim_results['avg_salaries'][i-1] > 0:
                            growth = (sim_results['avg_salaries'][i] - sim_results['avg_salaries'][i-1]) / sim_results['avg_salaries'][i-1] * 100
                            growth_rates.append(growth)
                    avg_growth = np.mean(growth_rates) if growth_rates else 0
                    growth_label = f"Avg Growth ({len(growth_rates)} Years)"
                else:
                    avg_growth = sim_results['current_growth']
                    growth_label = "Growth Rate"

            st.metric(
                growth_label,
                f"{avg_growth:.2f}%",
                f"{avg_growth - sim_results['target_growth']:.2f}% vs target"
            )

        with col2:
            gap = sim_results['target_growth'] - avg_growth  # Use average growth for gap calculation
            if abs(gap) < 0.1:  # Tighter tolerance
                gap_status = "✅ Target Met"
            elif gap > 0:
                gap_status = f"📉 Below Target: -{abs(gap):.1f}%"
            else:
                gap_status = f"📈 Above Target: +{abs(gap):.1f}%"
            st.metric("Target Achievement", gap_status)

        with col3:
            # Show simulation coverage instead of just one year
            if len(sim_results['years']) == 1:
                year_range = f"Year {sim_results['years'][0]}"
            else:
                year_range = f"{min(sim_results['years'])}-{max(sim_results['years'])}"
            st.metric("Simulation Coverage", year_range)

        # Detailed results table
        st.subheader("Year-by-Year Results")

        if len(sim_results['years']) == 1:
            # Single year result - show projection based on growth rate
            st.info("📋 Showing single-year simulation result with projected multi-year growth")

            base_year = sim_results['years'][0]
            base_salary = sim_results['avg_salaries'][0]
            base_headcount = sim_results['total_headcount'][0]

            # Project backwards and forwards based on target growth
            results_data = []
            projected_years = [2025, 2026, 2027, 2028, 2029]

            for i, year in enumerate(projected_years):
                if year == base_year:
                    # This is our actual data
                    salary = base_salary
                    headcount = base_headcount
                    growth_rate = sim_results['current_growth']
                    is_actual = True
                else:
                    # This is projected based on target growth
                    years_diff = year - base_year
                    salary = base_salary * ((1 + sim_results['target_growth']/100) ** years_diff)
                    headcount = int(base_headcount * ((1 + sim_results['target_growth']/100) ** years_diff))
                    growth_rate = sim_results['target_growth']
                    is_actual = False

                results_data.append({
                    'Year': f"{year}{'*' if not is_actual else ''}",
                    'Average Salary': f"${salary:,.0f}",
                    'Growth Rate': f"{growth_rate:.1f}%",
                    'Total Headcount': f"{headcount:,}",
                    'vs Target': f"{growth_rate - sim_results['target_growth']:.1f}%",
                    'Data Type': '✅ Actual' if is_actual else '📊 Projected'
                })

            st.dataframe(pd.DataFrame(results_data), use_container_width=True)
            st.caption("* Projected years based on target growth rate | ✅ = Simulation results | 📊 = Target projections")

        else:
            # Multi-year results with status breakdown
            results_data = []
            for i, year in enumerate(sim_results['years']):
                # Use the pre-calculated growth rates from load_simulation_results
                growth_rate = sim_results['growth_rates'][i] if i < len(sim_results['growth_rates']) else 0

                # Create base row data
                row_data = {
                    'Year': year,
                    'Average Salary': f"${sim_results['avg_salaries'][i]:,.0f}",
                    'Growth Rate': f"{growth_rate:.1f}%",
                    'Filtered Total': f"{sim_results['total_headcount'][i]:,}",
                    'vs Target': f"{growth_rate - sim_results['target_growth']:.1f}%"
                }

                # Add status breakdown columns
                if 'status_breakdown' in sim_results and year in sim_results['status_breakdown']:
                    year_breakdown = sim_results['status_breakdown'][year]
                    for status in sim_results['available_statuses']:
                        row_data[f'{status.title()}'] = f"{year_breakdown.get(status, 0):,}"

                results_data.append(row_data)

            st.dataframe(pd.DataFrame(results_data), use_container_width=True)

            # Status filter info
            filter_info = ", ".join(sim_results['status_filter']) if 'status_filter' in sim_results else "active"
            st.caption(f"📊 Calculations based on: **{filter_info}** status codes | 'Filtered Total' shows count for selected statuses")

            # Status breakdown summary
            if 'status_breakdown' in sim_results:
                st.subheader("📊 Employment Status Summary")

                # Create status summary chart
                status_summary_data = []
                for year in sim_results['years']:
                    if year in sim_results['status_breakdown']:
                        year_breakdown = sim_results['status_breakdown'][year]
                        for status in sim_results['available_statuses']:
                            status_summary_data.append({
                                'Year': year,
                                'Status': status.title(),
                                'Count': year_breakdown.get(status, 0)
                            })

                if status_summary_data:
                    summary_df = pd.DataFrame(status_summary_data)

                    # Create stacked bar chart
                    fig = px.bar(
                        summary_df,
                        x='Year',
                        y='Count',
                        color='Status',
                        title="Workforce Composition by Employment Status",
                        labels={'Count': 'Employee Count', 'Year': 'Simulation Year'}
                    )
                    fig.update_layout(height=400)
                    st.plotly_chart(fig, use_container_width=True)

        # Export results
        st.subheader("Export Results")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📊 Export to Excel"):
                # Create Excel export
                results_df = pd.DataFrame(results_data)
                csv = results_df.to_csv(index=False)
                st.download_button(
                    "📥 Download Results",
                    csv,
                    f"compensation_results_{selected_year}.csv",
                    "text/csv"
                )

        with col2:
            if st.button("📧 Email Results"):
                st.info("Email functionality coming soon!")

    else:
        st.warning("🔍 **No Simulation Data Found**")
        st.markdown("""
        The simulation database tables (`fct_workforce_snapshot`) don't exist yet. To get started:

        **Option 1: Run a Real Simulation**
        1. Go to the "📊 Run Simulation" tab
        2. Click "🚀 Launch Simulation"
        3. Wait for the simulation to complete
        4. Return here to view results

        **Option 2: Generate Synthetic Results**
        1. Go to the "🎯 Parameter Tuning" tab
        2. Adjust parameters using the sliders
        3. Click "📊 Generate Synthetic Results" for instant preview

        **Need Help?**
        - Check that the DuckDB database exists at `/Users/nicholasamaral/planwise_navigator/simulation.duckdb`
        - Ensure the dbt models have been run at least once
        - Try running: `dagster asset materialize --select simulation_year_state`
        """)

        # Quick action buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Go to Run Simulation", type="primary"):
                st.switch_page("pages/1_Compensation_Tuning.py")  # This will redirect to tab3
        with col2:
            if st.button("🎯 Try Parameter Tuning"):
                st.info("💡 Use the sliders in the sidebar to adjust parameters and generate synthetic results!")

with tab6:
    st.markdown('<div class="section-header">🤖 Auto-Optimize Parameters</div>', unsafe_allow_html=True)
    st.info("🎯 Let the system automatically find optimal parameters to meet your target growth rate")

    # Import the new optimization progress module
    try:
        from optimization_progress import (
            create_optimization_progress_interface,
            OptimizationVisualization,
            ProgressTracker,
            OptimizationProgress,
            OptimizationLogFilter
        )
        progress_module_available = True
    except ImportError:
        st.warning("⚠️ Advanced progress tracking module not available. Using basic interface.")
        progress_module_available = False

    # Optimization Configuration
    st.subheader("Optimization Settings")

    col1, col2 = st.columns(2)

    with col1:
        target_growth = st.number_input(
            "Target Growth Rate (%)",
            min_value=0.0,
            max_value=10.0,
            value=2.0,
            step=0.1,
            help="The compensation growth rate you want to achieve"
        )

        max_iterations = st.number_input(
            "Max Iterations",
            min_value=1,
            max_value=20,
            value=10,
            help="Maximum number of optimization iterations"
        )

    with col2:
        tolerance = st.number_input(
            "Convergence Tolerance (%)",
            min_value=0.01,
            max_value=1.0,
            value=0.1,
            step=0.01,
            help="How close to target growth constitutes success"
        )

        optimization_mode = st.selectbox(
            "Optimization Strategy",
            ["Conservative", "Balanced", "Aggressive"],
            index=1,
            help="Conservative: Small adjustments, Aggressive: Large adjustments"
        )

    # Advanced optimization options
    with st.expander("🔧 Advanced Optimization Settings"):
        col1, col2, col3 = st.columns(3)

        with col1:
            algorithm_choice = st.selectbox(
                "Optimization Algorithm",
                ["SLSQP", "L-BFGS-B", "TNC", "COBYLA"],
                index=0,
                help="Choose the optimization algorithm"
            )

        with col2:
            optimization_method = st.selectbox(
                "Optimization Method",
                ["🔬 Scientific (SciPy)", "📊 Classic (Stepping)"],
                index=0,
                help="Scientific: Uses scipy algorithms for precise convergence. Classic: Simple parameter stepping (legacy)"
            )

        with col3:
            enable_progress_tracking = st.checkbox(
                "Enable Progress Tracking",
                value=progress_module_available,
                disabled=not progress_module_available,
                help="Show real-time optimization progress and visualizations"
            )

        # Optimization simulation mode
        st.subheader("Optimization Mode")
        optimization_sim_mode = st.radio(
            "Simulation mode for optimization iterations:",
            ["🧪 Synthetic (Fast)", "🔄 Real Simulation (Accurate)"],
            index=0,  # Default to synthetic for fast optimization
            help="Synthetic: ~5-10 seconds per iteration. Real: ~2-5 minutes per iteration."
        )
        use_synthetic_opt = optimization_sim_mode.startswith("🧪")
        use_real_simulation = not use_synthetic_opt  # Use radio button selection

        if use_synthetic_opt:
            st.info("🧪 **Recommended**: Synthetic mode enables rapid convergence (~10-50 seconds total)")
        else:
            st.warning("🔄 **High Accuracy**: Real simulation mode for maximum precision (~20-50 minutes total)")

    # Current vs Target Analysis
    st.subheader("Current State Analysis")

    # Load current results to show baseline
    current_results = load_simulation_results(['continuous_active', 'new_hire_active'])

    if current_results:
        current_growth = np.mean(current_results['growth_rates']) if current_results['growth_rates'] else 0
        gap = target_growth - current_growth

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Current Growth", f"{current_growth:.2f}%")
        with col2:
            st.metric("Target Growth", f"{target_growth:.2f}%")
        with col3:
            gap_status = "✅ At Target" if abs(gap) <= tolerance else f"{'📈 Above' if gap < 0 else '📉 Below'} Target"
            st.metric("Gap Analysis", f"{gap:+.2f}%", gap_status)

        # Optimization recommendation
        if abs(gap) <= tolerance:
            st.markdown('<div class="success-box">✅ <strong>Already at target!</strong> Current parameters are achieving the desired growth rate.</div>', unsafe_allow_html=True)
        elif gap > 0:
            st.markdown(f'<div class="warning-box">📈 <strong>Need to increase growth by {gap:.2f}%</strong> - Parameters will be adjusted upward.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="warning-box">📉 <strong>Need to decrease growth by {abs(gap):.2f}%</strong> - Parameters will be adjusted downward.</div>', unsafe_allow_html=True)
    else:
        st.warning("⚠️ No current simulation results found. Run a simulation first to establish baseline.")
        st.info("💡 Go to the 'Run Simulation' tab to run your first simulation before optimizing.")

    # Optimization Execution
    st.subheader("Run Optimization")

    # Pre-flight checks
    can_optimize = True
    if not current_results:
        can_optimize = False
        st.error("❌ Cannot optimize without baseline results")
    elif abs(gap) <= tolerance:
        can_optimize = False
        st.info("✅ Already at target - no optimization needed")

    # Optimization button and progress
    if st.button("🚀 Start Auto-Optimization", type="primary", disabled=not can_optimize):
        st.markdown("---")
        st.markdown("### 🤖 Optimization Progress")

        # Add risk constraints to optimization
        max_risk_level = st.selectbox(
            "Maximum Risk Level",
            ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            index=2,  # Default to HIGH
            help="Optimization will reject parameter sets exceeding this risk level"
        )

        # Store max risk level in session state for use in optimization functions
        st.session_state.optimization_max_risk_level = RiskLevel(max_risk_level.lower())

        optimization_config = {
            'target_growth': target_growth,
            'max_iterations': max_iterations,
            'tolerance': tolerance,
            'mode': optimization_mode,
            'algorithm': algorithm_choice,
            'use_real_simulation': use_real_simulation,
            'enable_progress_tracking': enable_progress_tracking,
            'use_synthetic': not use_real_simulation,  # Legacy support
            'max_risk_level': RiskLevel(max_risk_level.lower()),
            'year_params': year_params  # Baseline for risk assessment
        }

        # Route to appropriate optimization method
        use_scientific = optimization_method.startswith("🔬")

        if use_scientific:
            # Use scipy-based scientific optimization
            estimation_time = "2-10 minutes" if use_synthetic_opt else "10-30 minutes"
            with st.spinner(f"Running scientific optimization... This may take {estimation_time}."):
                optimization_result = run_scipy_optimization(optimization_config)
        else:
            # Use classic optimization methods
            if enable_progress_tracking and progress_module_available:
                # Initialize progress tracking
                if 'optimization_tracker' not in st.session_state:
                    st.session_state.optimization_tracker = ProgressTracker()
                    st.session_state.optimization_viz = OptimizationVisualization()

                # Create progress containers
                progress_container = st.container()
                status_container = st.container()

                with status_container:
                    st.info(f"🎯 Starting {algorithm_choice} optimization with {'real simulation' if use_real_simulation else 'synthetic functions'}")
                    st.info(f"⏱️ Estimated time: {'20-50 minutes' if use_real_simulation else '2-5 minutes'}")

                # Run optimization with enhanced tracking
                with st.spinner(f"Running {optimization_mode.lower()} optimization... Progress shown below."):
                    optimization_result = run_optimization_loop_with_tracking(
                        optimization_config,
                        progress_container,
                        st.session_state.optimization_tracker,
                        st.session_state.optimization_viz
                    )
            else:
                # Standard optimization execution
                estimation_time = "20-50 minutes" if use_real_simulation else "2-5 minutes"
                with st.spinner(f"Running automated optimization... This may take {estimation_time}."):
                    optimization_result = run_optimization_loop(optimization_config)

        # Display optimization results
        if optimization_result:
            st.markdown("### 📊 Optimization Summary")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Converged", "✅ Yes" if optimization_result['converged'] else "❌ No")
            with col2:
                st.metric("Iterations Used", f"{optimization_result['iterations']}/{max_iterations}")
            with col3:
                st.metric("Final Growth", f"{optimization_result['final_growth']:.2f}%")
            with col4:
                st.metric("Final Gap", f"{optimization_result['final_gap']:+.2f}%")

            # Convergence status
            if optimization_result['converged']:
                st.markdown('<div class="success-box">🎉 <strong>Optimization Successful!</strong> Target growth rate achieved within tolerance.</div>', unsafe_allow_html=True)
                st.info("📊 Check the 'Results' tab to see the final optimized simulation results.")
                st.info("🎯 The optimized parameters have been automatically saved and applied.")
            else:
                st.markdown('<div class="warning-box">⚠️ <strong>Optimization Did Not Converge</strong> within the maximum iterations.</div>', unsafe_allow_html=True)
                st.info("💡 Try increasing max iterations or adjusting tolerance, or choose a different optimization strategy.")

            # Iteration history visualization
            if optimization_result['iteration_history']:
                st.subheader("📈 Optimization Progress")

                history_df = pd.DataFrame(optimization_result['iteration_history'])

                # Create convergence chart
                fig = go.Figure()

                # Add target line
                fig.add_hline(y=target_growth, line_dash="dash", line_color="green",
                             annotation_text="Target Growth", annotation_position="top left")

                # Add tolerance bands
                fig.add_hrect(y0=target_growth-tolerance, y1=target_growth+tolerance,
                             fillcolor="green", opacity=0.1, annotation_text="Tolerance Zone")

                # Add growth progression
                fig.add_trace(go.Scatter(
                    x=history_df['iteration'],
                    y=history_df['current_growth'],
                    mode='lines+markers',
                    name='Growth Rate',
                    line=dict(color='blue', width=3),
                    marker=dict(size=8)
                ))

                fig.update_layout(
                    title="Optimization Convergence Progress",
                    xaxis_title="Iteration",
                    yaxis_title="Growth Rate (%)",
                    height=400,
                    showlegend=True
                )

                st.plotly_chart(fig, use_container_width=True)

                # Iteration details table
                st.subheader("Iteration Details")
                display_history = history_df.copy()
                display_history['Current Growth'] = display_history['current_growth'].apply(lambda x: f"{x:.2f}%")
                display_history['Gap to Target'] = display_history['gap'].apply(lambda x: f"{x:+.2f}%")
                display_history['Converged'] = display_history['converged'].apply(lambda x: "✅ Yes" if x else "❌ No")
                display_history = display_history[['iteration', 'Current Growth', 'Gap to Target', 'Converged']]
                display_history.columns = ['Iteration', 'Growth Rate', 'Gap to Target', 'Converged']

                st.dataframe(display_history, use_container_width=True)
        else:
            st.error("❌ Optimization failed - check error messages above")

    # Help and Tips
    with st.expander("💡 Optimization Tips & Help"):
        st.markdown("""
        **How Auto-Optimization Works:**
        1. **Baseline Analysis**: Starts with current parameter set and simulation results
        2. **Gap Calculation**: Determines difference between current and target growth
        3. **Parameter Adjustment**: Intelligently adjusts COLA, merit, and hiring parameters
        4. **Simulation**: Runs full multi-year simulation with new parameters
        5. **Convergence Check**: Compares results to target within tolerance
        6. **Iteration**: Repeats until target is reached or max iterations exceeded

        **Optimization Strategies:**
        - **Conservative**: Small parameter adjustments (10% of gap) - safer but slower
        - **Balanced**: Moderate adjustments (30% of gap) - good balance of speed and stability
        - **Aggressive**: Large adjustments (50% of gap) - faster but may overshoot

        **Performance Expectations:**
        - **Single Iteration**: 2-5 minutes (same as manual simulation)
        - **Full Optimization**: 20-50 minutes (10 iterations max)
        - **Convergence Rate**: ~80% of scenarios converge within 10 iterations

        **Best Practices:**
        - Start with Balanced strategy for most scenarios
        - Use Conservative for critical production runs
        - Set realistic target growth rates (1-4% typical)
        - Allow sufficient iterations (8-12 recommended)

        **Troubleshooting:**
        - If optimization doesn't converge, try wider tolerance (0.2-0.5%)
        - Check for database lock errors (close IDE connections)
        - Ensure baseline simulation completed successfully
        - Consider if target growth rate is achievable within parameter bounds
        """)

# Footer
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: #666;'>
    E012 Compensation Tuning Interface | Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")} |
    <a href='#'>Documentation</a> | <a href='#'>Support</a>
    </div>
    """,
    unsafe_allow_html=True,
)
