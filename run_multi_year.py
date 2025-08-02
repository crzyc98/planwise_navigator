#!/usr/bin/env python3
"""
Simple Multi-Year Simulation Runner

⚠️  DEPRECATION WARNING: Consider using orchestrator_dbt/run_multi_year.py for production workloads
    This simple runner is intended for basic testing and development only.

Reads config/simulation_config.yaml and runs multi-year simulations.
Uses the working foundation approach with simple subprocess calls.
"""

import yaml
import subprocess
import sys
from pathlib import Path
import duckdb
from shared_utils import ExecutionMutex, print_execution_warning


def load_config():
    """Load simulation configuration from YAML file."""
    config_path = Path("config/simulation_config.yaml")

    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Extract simulation parameters
        simulation = config.get('simulation', {})
        start_year = simulation.get('start_year', 2025)
        end_year = simulation.get('end_year', 2029)
        random_seed = simulation.get('random_seed', 42)

        print(f"📋 Configuration loaded:")
        print(f"   Years: {start_year} - {end_year}")
        print(f"   Random seed: {random_seed}")

        return {
            'start_year': start_year,
            'end_year': end_year,
            'random_seed': random_seed,
            'config': config
        }

    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        sys.exit(1)


def run_dbt_command(command_args, description="Running dbt command", simulation_year=None):
    """Run a dbt command with error handling (like working staging approach)."""

    # Build command
    cmd = ["dbt"] + command_args

    # Add simulation_year variable if provided
    if simulation_year:
        cmd.extend(["--vars", f"simulation_year: {simulation_year}"])

    print(f"🔧 {description}...")

    try:
        result = subprocess.run(
            cmd,
            cwd="dbt",
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✅ {description} completed")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"   Command: {' '.join(cmd)}")
        if e.stdout:
            print(f"   stdout: {e.stdout[-500:]}")  # Last 500 chars
        if e.stderr:
            print(f"   stderr: {e.stderr[-500:]}")
        return False


def get_database_connection():
    """Get DuckDB connection to the simulation database."""
    db_path = Path("simulation.duckdb")
    if not db_path.exists():
        print(f"⚠️ Database file not found: {db_path}")
        return None

    try:
        conn = duckdb.connect(str(db_path))
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return None


def audit_year_results(year):
    """Audit and display year-end results similar to MVP orchestrator."""
    print(f"\n📊 YEAR {year} AUDIT RESULTS")
    print("=" * 50)

    conn = get_database_connection()
    if not conn:
        print("❌ Cannot audit - database connection failed")
        return

    try:
        # Get year-end workforce breakdown by detailed status
        workforce_query = """
        SELECT
            detailed_status_code,
            COUNT(*) as employee_count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as percentage
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
        GROUP BY detailed_status_code
        ORDER BY employee_count DESC
        """

        workforce_results = conn.execute(workforce_query, [year]).fetchall()

        if workforce_results:
            print("📋 Year-end Employment Makeup by Status:")
            total_employees = sum(row[1] for row in workforce_results)
            for status, count, pct in workforce_results:
                print(f"   {status:25}: {count:4,} ({pct:4.1f}%)")
            print(f"   {'TOTAL':25}: {total_employees:4,} (100.0%)")

        # Get event counts for the year
        events_query = """
        SELECT
            event_type,
            COUNT(*) as event_count
        FROM fct_yearly_events
        WHERE simulation_year = ?
        GROUP BY event_type
        ORDER BY event_count DESC
        """

        events_results = conn.execute(events_query, [year]).fetchall()

        if events_results:
            print(f"\n📈 Year {year} Event Summary:")
            total_events = sum(row[1] for row in events_results)
            for event_type, count in events_results:
                print(f"   {event_type:15}: {count:4,}")
            print(f"   {'TOTAL':15}: {total_events:4,}")

        # Get baseline comparison (for first year) or year-over-year growth
        if year == 2025:
            # Compare with baseline workforce
            baseline_query = """
            SELECT COUNT(*) as baseline_count
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
            """
            baseline_result = conn.execute(baseline_query).fetchone()
            baseline_count = baseline_result[0] if baseline_result else 0

            # Get year-end active employees
            active_query = """
            SELECT COUNT(*) as active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            active_result = conn.execute(active_query, [year]).fetchone()
            active_count = active_result[0] if active_result else 0

            print(f"\n📊 Growth from Baseline:")
            print(f"   Baseline active employees  : {baseline_count:4,}")
            print(f"   Year-end active employees  : {active_count:4,}")

            if baseline_count > 0:
                growth = active_count - baseline_count
                growth_pct = (growth / baseline_count) * 100
                print(f"   Net growth                 : {growth:+4,} ({growth_pct:+5.1f}%)")

        else:
            # Year-over-year comparison
            prev_year_query = """
            SELECT COUNT(*) as prev_active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            prev_result = conn.execute(prev_year_query, [year - 1]).fetchone()
            prev_count = prev_result[0] if prev_result else 0

            current_query = """
            SELECT COUNT(*) as current_active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            current_result = conn.execute(current_query, [year]).fetchone()
            current_count = current_result[0] if current_result else 0

            print(f"\n📊 Year-over-Year Growth:")
            print(f"   Year {year-1} active employees: {prev_count:4,}")
            print(f"   Year {year} active employees  : {current_count:4,}")

            if prev_count > 0:
                growth = current_count - prev_count
                growth_pct = (growth / prev_count) * 100
                print(f"   Net growth                   : {growth:+4,} ({growth_pct:+5.1f}%)")

        # Additional validation checks
        print(f"\n🔍 Data Quality Checks:")

        # Check for reasonable hire/termination ratios
        hire_count = sum(count for event_type, count in events_results if event_type == 'hire')
        term_count = sum(count for event_type, count in events_results if event_type in ['termination', 'TERMINATION'])

        if hire_count > 0 and term_count > 0:
            turnover_ratio = term_count / hire_count
            print(f"   Hire/Termination ratio       : {hire_count:,} hires, {term_count:,} terms (ratio: {turnover_ratio:.2f})")

            # Flag unusual ratios
            if hire_count > 2000:
                print(f"   ⚠️  HIGH HIRE COUNT: {hire_count:,} hires may be excessive for one year")
            if term_count > 1000:
                print(f"   ⚠️  HIGH TERMINATION COUNT: {term_count:,} terminations may be excessive")

        print()  # Extra line for spacing

    except Exception as e:
        print(f"❌ Error during year audit: {e}")
    finally:
        conn.close()


def display_multi_year_summary(start_year, end_year, completed_years):
    """Display comprehensive multi-year simulation summary."""
    if len(completed_years) < 2:
        return  # Skip summary if less than 2 years completed

    print("\n" + "=" * 60)
    print("📊 MULTI-YEAR SIMULATION SUMMARY")
    print("=" * 60)

    conn = get_database_connection()
    if not conn:
        print("❌ Cannot generate summary - database connection failed")
        return

    try:
        # Get workforce progression across all completed years
        progression_query = """
        SELECT
            simulation_year,
            COUNT(*) as total_employees,
            COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
            COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as new_hires_active,
            COUNT(CASE WHEN detailed_status_code = 'experienced_termination' THEN 1 END) as experienced_terms,
            COUNT(CASE WHEN detailed_status_code = 'new_hire_termination' THEN 1 END) as new_hire_terms
        FROM fct_workforce_snapshot
        WHERE simulation_year IN ({})
        GROUP BY simulation_year
        ORDER BY simulation_year
        """.format(','.join('?' * len(completed_years)))

        progression_results = conn.execute(progression_query, completed_years).fetchall()

        if progression_results:
            print("📈 Workforce Progression:")
            print("   Year  | Total Emp | Active | New Hires | Exp Terms | NH Terms")
            print("   ------|-----------|--------|-----------|-----------|----------")

            baseline_active = None
            for row in progression_results:
                year, total, active, nh_active, exp_terms, nh_terms = row
                print(f"   {year} | {total:9,} | {active:6,} | {nh_active:9,} | {exp_terms:9,} | {nh_terms:8,}")

                if baseline_active is None:
                    baseline_active = active

            # Calculate overall growth
            if len(progression_results) >= 2 and baseline_active:
                final_active = progression_results[-1][2]  # active employees in last year
                total_growth = final_active - baseline_active
                growth_pct = (total_growth / baseline_active) * 100
                years_elapsed = len(completed_years)
                cagr = ((final_active / baseline_active) ** (1 / (years_elapsed - 1)) - 1) * 100

                print(f"\n📊 Overall Growth Analysis:")
                print(f"   Starting active workforce    : {baseline_active:6,}")
                print(f"   Ending active workforce      : {final_active:6,}")
                print(f"   Total net growth             : {total_growth:+6,} ({growth_pct:+5.1f}%)")
                print(f"   Compound Annual Growth Rate  : {cagr:5.1f}%")

        # Get total events summary
        events_summary_query = """
        SELECT
            event_type,
            simulation_year,
            COUNT(*) as event_count
        FROM fct_yearly_events
        WHERE simulation_year IN ({})
        GROUP BY event_type, simulation_year
        ORDER BY event_type, simulation_year
        """.format(','.join('?' * len(completed_years)))

        events_results = conn.execute(events_summary_query, completed_years).fetchall()

        if events_results:
            print(f"\n📋 Multi-Year Event Summary:")
            # Group by event type
            events_by_type = {}
            for event_type, year, count in events_results:
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append((year, count))

            for event_type, year_counts in events_by_type.items():
                total_events = sum(count for _, count in year_counts)
                years_list = ', '.join(f"{year}: {count:,}" for year, count in year_counts)
                print(f"   {event_type:15}: {total_events:5,} total ({years_list})")

    except Exception as e:
        print(f"❌ Error generating multi-year summary: {e}")
    finally:
        conn.close()


def run_year_simulation(year, is_first_year=False):
    """Run simulation for a single year."""
    print(f"\n🎯 Running simulation for year {year}")
    print("-" * 40)

    # Step 1: Foundation setup (seeds and staging)
    if is_first_year:
        print("📋 Setting up foundation (first year)...")
        if not run_dbt_command(["seed"], "Loading seed data"):
            return False
        if not run_dbt_command(["run", "--models", "stg_census_data"], "Running census staging"):
            return False
        if not run_dbt_command(["run", "--models", "int_baseline_workforce"], "Creating baseline workforce"):
            return False

    # Step 2: Parameters and workforce setup
    if not run_dbt_command(["run", "--models", "int_effective_parameters"], "Resolving parameters", year):
        return False

    # Step 3: Event generation (with simulation_year)
    event_models = [
        "int_termination_events",
        "int_new_hire_termination_events",
        "int_promotion_events",
        "int_hiring_events",
        "int_merit_events"
    ]

    for model in event_models:
        if not run_dbt_command(["run", "--models", model], f"Running {model}", year):
            return False

    # Step 4: Consolidation
    if not run_dbt_command(["run", "--models", "fct_yearly_events"], "Consolidating events", year):
        return False
    if not run_dbt_command(["run", "--models", "fct_workforce_snapshot"], "Creating workforce snapshot", year):
        return False

    print(f"✅ Year {year} simulation completed successfully!")

    # Audit year results
    audit_year_results(year)

    return True


def clear_simulation_database():
    """Clear previous simulation results to ensure clean run."""
    print("🧹 Clearing previous simulation results...")

    conn = get_database_connection()
    if not conn:
        print("⚠️  Cannot clear database - connection failed, proceeding anyway")
        return True

    try:
        # Tables to clear (in dependency order)
        tables_to_clear = [
            'fct_workforce_snapshot',
            'fct_yearly_events',
            'fct_compensation_growth',
            'fct_participant_balance_snapshots'
        ]

        cleared_tables = []

        for table in tables_to_clear:
            try:
                # Check if table exists
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1")

                # Clear the table
                result = conn.execute(f"DELETE FROM {table}")
                rows_deleted = result.fetchone()

                cleared_tables.append(table)
                print(f"   ✅ Cleared {table}")

            except Exception as table_error:
                # Table might not exist, which is fine
                print(f"   ⏭️  Skipped {table} (table may not exist)")
                continue

        if cleared_tables:
            print(f"✅ Database cleared successfully - {len(cleared_tables)} tables cleared")
        else:
            print("ℹ️  No tables needed clearing")

        return True

    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        print("⚠️  Proceeding with simulation anyway...")
        return True  # Don't fail the entire simulation for clearing issues

    finally:
        conn.close()


def main():
    """Main function - run multi-year simulation."""
    print("🎯 Simple Multi-Year Simulation Runner")
    print("⚠️  DEPRECATION WARNING: Consider using orchestrator_dbt/run_multi_year.py for production")
    print("=" * 50)

    # Check for conflicting systems
    print_execution_warning()

    # Acquire execution mutex to prevent concurrent runs
    with ExecutionMutex("simulation_execution"):
        print("🔒 Acquired execution lock - preventing concurrent simulations")

        # Load configuration
        config = load_config()
        start_year = config['start_year']
        end_year = config['end_year']

        print(f"\n🚀 Starting multi-year simulation...")
        print(f"   Years: {start_year} - {end_year}")
        print(f"   Total years: {end_year - start_year + 1}")

        # **CRITICAL FIX**: Clear database before starting simulation
        if not clear_simulation_database():
            print("❌ Database clearing failed, aborting simulation")
            return 1

        # Track results
        completed_years = []
        failed_years = []

        # Run simulation for each year
        for year in range(start_year, end_year + 1):
            is_first_year = (year == start_year)

            try:
                success = run_year_simulation(year, is_first_year)
                if success:
                    completed_years.append(year)
                else:
                    failed_years.append(year)
                    print(f"❌ Simulation failed for year {year}")
                    break  # Stop on first failure

            except KeyboardInterrupt:
                print(f"\n⚡ Simulation interrupted by user")
                break
            except Exception as e:
                print(f"\n💥 Unexpected error in year {year}: {e}")
                failed_years.append(year)
                break

        # Final results
        print("\n" + "=" * 50)
        print("🎯 MULTI-YEAR SIMULATION RESULTS")
        print("=" * 50)

        if completed_years:
            print(f"✅ Completed years: {completed_years}")
            print(f"   Success count: {len(completed_years)}/{end_year - start_year + 1}")

        if failed_years:
            print(f"❌ Failed years: {failed_years}")

        # Display multi-year summary if multiple years completed
        if len(completed_years) > 1:
            display_multi_year_summary(start_year, end_year, completed_years)

        if len(completed_years) == (end_year - start_year + 1):
            print(f"\n🎉 Multi-year simulation completed successfully!")
            print(f"   All {len(completed_years)} years simulated")
            return 0
        else:
            print(f"\n💥 Multi-year simulation failed")
            print(f"   {len(completed_years)} of {end_year - start_year + 1} years completed")
            return 1


if __name__ == "__main__":
    main()
