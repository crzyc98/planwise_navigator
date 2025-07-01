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
        comp_levers_path = Path("../dbt/seeds/comp_levers.csv")
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
    """Load latest simulation results from DuckDB"""
    try:
        # Connect to DuckDB database
        db_path = Path("../simulation.duckdb")
        if not db_path.exists():
            db_path = Path("simulation.duckdb")

        if not db_path.exists():
            st.warning("No simulation database found. Run a simulation first.")
            return None

        import duckdb
        conn = duckdb.connect(str(db_path))

        # Get all available detailed status codes
        all_statuses = conn.execute("""
            SELECT DISTINCT detailed_status_code
            FROM fct_workforce_snapshot
            ORDER BY detailed_status_code
        """).fetchall()
        available_statuses = [row[0] for row in all_statuses]

        # Get years with data (using any status to find years)
        years_data = conn.execute("""
            SELECT DISTINCT simulation_year
            FROM fct_workforce_snapshot
            ORDER BY simulation_year
        """).fetchall()

        if not years_data:
            conn.close()
            return None

        years = [row[0] for row in years_data]

        # Get baseline workforce data for growth calculation
        baseline_result = conn.execute("""
            SELECT
                COUNT(*) as count,
                AVG(current_compensation) as avg_salary
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
        """).fetchone()

        baseline_count = baseline_result[0]
        baseline_avg_salary = baseline_result[1] if baseline_result[1] else 0

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

def update_parameters_file(new_params, years):
    """Update the comp_levers.csv file with new parameters"""
    try:
        comp_levers_path = Path("../dbt/seeds/comp_levers.csv")
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
            with st.spinner(f"Running simulation iteration {iteration + 1}..."):
                simulation_success = run_simulation()

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

            # Calculate average growth across simulation years
            if len(results['growth_rates']) > 0:
                current_growth = np.mean(results['growth_rates'])
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

        # Reduce adjustment factor as iterations progress (convergence acceleration)
        adjustment_factor *= (0.8 ** (iteration - 1))

        # Calculate parameter adjustments
        # Gap > 0 means we need to increase growth (increase compensation parameters)
        # Gap < 0 means we need to decrease growth (decrease compensation parameters)

        gap_adjustment = gap * adjustment_factor / 100  # Convert percentage to decimal

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

def run_simulation():
    try:
        # First, run dbt to update parameter tables
        st.info("Updating parameter tables...")
        dbt_result = subprocess.run([
            "dbt", "seed", "--select", "comp_levers"
        ], capture_output=True, text=True, cwd="../dbt")

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
            "dbt", "run", "--select", "stg_comp_levers int_effective_parameters"
        ], capture_output=True, text=True, cwd="../dbt")

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
                env = os.environ.copy()
                env["DAGSTER_HOME"] = "/Users/nicholasamaral/planwise_navigator/.dagster"

                # Try multiple dagster binary paths
                dagster_paths = [
                    "venv/bin/dagster",      # Relative to project root
                    "dagster",               # System path
                    "/usr/local/bin/dagster" # Common system location
                ]

                dagster_cmd = None
                for path in dagster_paths:
                    try:
                        # Test if dagster binary exists
                        test_result = subprocess.run([path, "--help"],
                                                   capture_output=True, text=True,
                                                   cwd="../", env=env, timeout=5)
                        if test_result.returncode == 0:
                            dagster_cmd = path
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
                cmd = [dagster_cmd, "job", "execute", "--job", "multi_year_simulation", "-f", "definitions.py", "--config", config_file]
                st.info(f"🚀 Executing command: {' '.join(cmd)}")
                st.info(f"📁 Working directory: {os.path.abspath('../')}")
                st.info(f"🏠 DAGSTER_HOME: {env.get('DAGSTER_HOME')}")
                st.info(f"🎲 Random seed: {random_seed}")
                st.info(f"⚙️ Job config: {job_config}")

                result = subprocess.run(cmd, capture_output=True, text=True, cwd="../", env=env, timeout=600)

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
                    db_path = Path("../simulation.duckdb")
                    if not db_path.exists():
                        db_path = Path("simulation.duckdb")

                    conn = duckdb.connect(str(db_path))
                    snapshot_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year").fetchall()
                    event_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_yearly_events ORDER BY simulation_year").fetchall()
                    conn.close()

                    st.info(f"📊 Post-simulation verification:")
                    st.info(f"   • Workforce snapshot years: {[y[0] for y in snapshot_years]}")
                    st.info(f"   • Event years: {[y[0] for y in event_years]}")

                    if len(snapshot_years) == 1 and len(event_years) == 1:
                        st.warning("⚠️ Only single-year data found - simulation may not have processed all years correctly")
                    elif len(snapshot_years) >= 5:
                        st.success("✅ Multi-year data found - full simulation successful!")
                    else:
                        st.warning(f"⚠️ Partial data found - {len(snapshot_years)} years in database")

                except Exception as e:
                    st.error(f"Database verification failed: {e}")

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
                    db_path = Path("../simulation.duckdb")
                    if not db_path.exists():
                        db_path = Path("simulation.duckdb")

                    conn = duckdb.connect(str(db_path))
                    snapshot_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year").fetchall()
                    event_years = conn.execute("SELECT DISTINCT simulation_year FROM fct_yearly_events ORDER BY simulation_year").fetchall()
                    conn.close()

                    st.info(f"📊 Post-simulation verification:")
                    st.info(f"   • Workforce snapshot years: {[y[0] for y in snapshot_years]}")
                    st.info(f"   • Event years: {[y[0] for y in event_years]}")

                    if len(snapshot_years) >= 5:
                        st.success("✅ Multi-year data found - full simulation successful!")
                    else:
                        st.warning(f"⚠️ Only {len(snapshot_years)} year(s) found - trying fallback method")

                except Exception as e:
                    st.error(f"Database verification failed: {e}")

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
                            "dbt", "run", "--select", model, "--vars",
                            f"{{'simulation_year': {year}}}"
                        ], capture_output=True, text=True, cwd="../dbt")

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

# Main content
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 Parameter Overview",
    "📊 Impact Analysis",
    "🚀 Run Simulation",
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

    # Parameter validation
    st.markdown('<div class="section-header">Parameter Validation</div>', unsafe_allow_html=True)

    # Prepare parameters for validation
    proposed_params = {
        'cola_rate': {i: cola_rate for i in range(1, 6)},
        'merit_base': merit_rates,
        'new_hire_salary_adjustment': {i: new_hire_adj for i in range(1, 6)}
    }

    warnings, errors = validate_parameters(proposed_params)

    if errors:
        for error in errors:
            st.markdown(f'<div class="error-box">❌ <strong>Error:</strong> {error}</div>', unsafe_allow_html=True)

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
    st.markdown('<div class="section-header">Impact Analysis</div>', unsafe_allow_html=True)
    st.info("🔍 Preview the expected impact of your parameter changes before running the simulation")

    # Parameter Change Summary
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

        # Recommendations
        st.subheader("💡 Recommendations")

        if estimated_final_growth < 1.5:
            st.warning("📉 Projected growth is below 1.5%. Consider increasing COLA or merit rates.")
        elif estimated_final_growth > 3.0:
            st.warning("📈 Projected growth is above 3.0%. This may exceed budget constraints.")
        else:
            st.success("✅ Projected growth appears reasonable for typical compensation strategies.")

        # Run simulation prompt
        st.markdown("---")
        st.info("💡 **Next Step:** Go to the 'Run Simulation' tab to test these parameter changes and see actual results!")

    else:
        st.warning("No baseline parameter data available. Unable to calculate impact analysis.")

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
            if st.button("🚀 Run Simulation", type="primary", disabled=not can_run):
                st.info("🔍 Button clicked! Starting simulation process...")

                if changes_made:
                    # Save parameters first
                    st.info("💾 Saving parameters...")
                    target_years = [selected_year] if apply_mode == "Single Year" else [2025, 2026, 2027, 2028, 2029]
                    if update_parameters_file(proposed_params, target_years):
                        years_msg = f"year {selected_year}" if apply_mode == "Single Year" else "all years (2025-2029)"
                        st.success(f"✅ Parameters saved successfully for {years_msg}!")
                        st.session_state.simulation_running = True

                        # Call the REAL simulation function
                        st.info("🚀 Calling simulation function...")
                        if run_simulation():
                            st.session_state.simulation_running = False
                            st.session_state.last_simulation_time = datetime.now()
                            st.balloons()
                        else:
                            st.session_state.simulation_running = False
                            st.error("Simulation failed - check error messages above")
                    else:
                        st.error("Failed to save parameters")
                else:
                    st.warning("No changes to apply - make parameter adjustments first")

    # Simulation history and tips
    if st.session_state.last_simulation_time:
        st.subheader("Last Simulation")
        st.write(f"Completed: {st.session_state.last_simulation_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Performance tips
    with st.expander("⚡ Performance Tips"):
        st.markdown("""
        **Simulation Performance:**
        - Multi-year simulations typically take 2-5 minutes
        - Parameter validation is instant
        - Large parameter changes may require longer processing time
        - Check Dagster UI (localhost:3000) for detailed progress

        **Best Practices:**
        - Start with small parameter adjustments (±0.5%)
        - Test single-year impacts before multi-year runs
        - Save baseline scenarios before major changes
        - Use validation warnings to guide parameter selection
        """)

with tab4:
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
                db_path = Path("../simulation.duckdb")
                if not db_path.exists():
                    db_path = Path("simulation.duckdb")

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
        db_path = Path("../simulation.duckdb")
        if not db_path.exists():
            db_path = Path("simulation.duckdb")

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
        st.success(f"Results last updated: {sim_results['last_updated']}")

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
        st.info("No simulation results available. Run a simulation to see results.")

with tab5:
    st.markdown('<div class="section-header">🤖 Auto-Optimize Parameters</div>', unsafe_allow_html=True)
    st.info("🎯 Let the system automatically find optimal parameters to meet your target growth rate")

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

        optimization_config = {
            'target_growth': target_growth,
            'max_iterations': max_iterations,
            'tolerance': tolerance,
            'mode': optimization_mode
        }

        # Run optimization loop
        with st.spinner("Running automated optimization... This may take 20-50 minutes."):
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
