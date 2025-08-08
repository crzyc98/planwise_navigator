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

        # Extract compensation parameters
        compensation = config.get('compensation', {})
        cola_rate = compensation.get('cola_rate', 0.005)
        merit_budget = compensation.get('merit_budget', 0.025)

        print(f"📋 Configuration loaded:")
        print(f"   Years: {start_year} - {end_year}")
        print(f"   Random seed: {random_seed}")
        print(f"   COLA rate: {cola_rate}")
        print(f"   Merit budget: {merit_budget}")

        return {
            'start_year': start_year,
            'end_year': end_year,
            'random_seed': random_seed,
            'cola_rate': cola_rate,
            'merit_budget': merit_budget,
            'config': config
        }

    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        sys.exit(1)


def run_dbt_command(command_args, description="Running dbt command", simulation_year=None, compensation_params=None):
    """Run a dbt command with error handling (like working staging approach)."""

    # Build command
    cmd = ["dbt"] + command_args

    # Build vars dictionary
    vars_dict = {}
    if simulation_year:
        vars_dict["simulation_year"] = simulation_year

    # Add compensation parameters if provided
    if compensation_params:
        vars_dict.update(compensation_params)

    # Add vars to command if any are specified
    if vars_dict:
        vars_string = ", ".join(f"{key}: {value}" for key, value in vars_dict.items())
        cmd.extend(["--vars", f"{{{vars_string}}}"])

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

        # Epic E034: Employee contribution summary
        try:
            contributions_query = """
            SELECT
                COUNT(*) as enrolled_employees,
                ROUND(SUM(annual_contribution_amount), 0) as total_contributions,
                ROUND(AVG(annual_contribution_amount), 0) as avg_contribution,
                ROUND(AVG(effective_annual_deferral_rate) * 100, 1) as avg_deferral_rate
            FROM int_employee_contributions
            WHERE simulation_year = ?
            """
            contributions_result = conn.execute(contributions_query, [year]).fetchone()

            if contributions_result and contributions_result[0] > 0:
                enrolled, total_contrib, avg_contrib, avg_rate = contributions_result
                print(f"\n💰 Employee Contributions Summary:")
                print(f"   Enrolled employees           : {enrolled:4,}")
                print(f"   Total annual contributions   : ${total_contrib:10,.0f}")
                print(f"   Average contribution         : ${avg_contrib:6,.0f}")
                print(f"   Average deferral rate        : {avg_rate:4.1f}%")

            # Check for contribution data quality issues
            dq_query = """
            SELECT COUNT(*) as validation_failures
            FROM dq_employee_contributions_validation
            WHERE simulation_year = ?
            """
            dq_result = conn.execute(dq_query, [year]).fetchone()
            if dq_result and dq_result[0] > 0:
                failures = dq_result[0]
                print(f"   ⚠️  Data quality issues      : {failures:4,} validation failures")
            else:
                print(f"   ✅ Data quality              : All validations passed")

        except Exception as contrib_error:
            print(f"   ⚠️  Contribution summary unavailable: {contrib_error}")

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

        # Check for employer match events (E025)
        match_count = sum(count for event_type, count in events_results if event_type == 'EMPLOYER_MATCH')
        if match_count > 0:
            # Get match cost information
            match_query = """
            SELECT
                COUNT(*) as match_count,
                SUM(compensation_amount) as total_match_cost,
                AVG(compensation_amount) as avg_match_amount
            FROM fct_yearly_events
            WHERE simulation_year = ? AND event_type = 'EMPLOYER_MATCH'
            """
            match_result = conn.execute(match_query, [year]).fetchone()
            if match_result:
                match_cnt, total_cost, avg_match = match_result
                print(f"\n💰 Employer Match Summary:")
                print(f"   Employees receiving match    : {match_cnt:,}")
                print(f"   Total match cost             : ${total_cost:,.2f}")
                print(f"   Average match per employee   : ${avg_match:,.2f}")

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


def create_enrollment_registry(year):
    """Create or update enrollment registry table to prevent duplicate enrollments."""
    print(f"📋 Creating enrollment registry for year {year}...")

    conn = get_database_connection()
    if not conn:
        print("❌ Cannot create enrollment registry - database connection failed")
        return False

    try:
        # For first year, create registry from baseline workforce
        if year == 2025:  # Start year
            create_registry_sql = """
            CREATE OR REPLACE TABLE enrollment_registry AS
            SELECT DISTINCT
                employee_id,
                employee_enrollment_date AS first_enrollment_date,
                2025 AS first_enrollment_year,
                'baseline' AS enrollment_source,
                true AS is_enrolled,
                CURRENT_TIMESTAMP AS last_updated
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
              AND employee_enrollment_date IS NOT NULL
              AND employee_id IS NOT NULL
            """
        else:
            # For subsequent years, add newly enrolled employees from previous year's events
            prev_year = year - 1
            update_registry_sql = f"""
            INSERT INTO enrollment_registry
            SELECT DISTINCT
                employee_id,
                MIN(effective_date) AS first_enrollment_date,
                {prev_year} AS first_enrollment_year,
                'simulation_event' AS enrollment_source,
                true AS is_enrolled,
                CURRENT_TIMESTAMP AS last_updated
            FROM fct_yearly_events
            WHERE simulation_year = {prev_year}
              AND event_type = 'enrollment'
              AND employee_id IS NOT NULL
              -- Only add if not already in registry
              AND employee_id NOT IN (
                  SELECT employee_id FROM enrollment_registry WHERE is_enrolled = true
              )
            GROUP BY employee_id
            """

        if year == 2025:
            conn.execute(create_registry_sql)
            count_result = conn.execute("SELECT COUNT(*) FROM enrollment_registry").fetchone()
            count = count_result[0] if count_result else 0
            print(f"✅ Created enrollment registry with {count:,} enrolled employees from baseline")
        else:
            conn.execute(update_registry_sql)
            # Get count of newly added employees
            count_result = conn.execute(f"""
                SELECT COUNT(*) FROM enrollment_registry
                WHERE first_enrollment_year = {prev_year}
            """).fetchone()
            new_count = count_result[0] if count_result else 0
            print(f"✅ Added {new_count:,} newly enrolled employees from year {prev_year}")

        return True

    except Exception as e:
        print(f"❌ Error creating enrollment registry: {e}")
        return False
    finally:
        conn.close()


def update_enrollment_registry_post_year(year):
    """Update enrollment registry with new enrollments from the completed year."""
    print(f"📋 Updating enrollment registry after year {year}...")

    conn = get_database_connection()
    if not conn:
        print("❌ Cannot update enrollment registry - database connection failed")
        return False

    try:
        # Add newly enrolled employees from this year's events
        update_registry_sql = f"""
        INSERT INTO enrollment_registry
        SELECT DISTINCT
            employee_id,
            MIN(effective_date) AS first_enrollment_date,
            {year} AS first_enrollment_year,
            'simulation_event' AS enrollment_source,
            true AS is_enrolled,
            CURRENT_TIMESTAMP AS last_updated
        FROM fct_yearly_events
        WHERE simulation_year = {year}
          AND event_type = 'enrollment'
          AND employee_id IS NOT NULL
          -- Only add if not already in registry
          AND employee_id NOT IN (
              SELECT employee_id FROM enrollment_registry WHERE is_enrolled = true
          )
        GROUP BY employee_id
        """

        conn.execute(update_registry_sql)

        # Get count of newly added employees
        count_result = conn.execute(f"""
            SELECT COUNT(*) FROM enrollment_registry
            WHERE first_enrollment_year = {year}
        """).fetchone()
        new_count = count_result[0] if count_result else 0
        print(f"✅ Added {new_count:,} newly enrolled employees from year {year} to registry")

        return True

    except Exception as e:
        print(f"❌ Error updating enrollment registry: {e}")
        return False
    finally:
        conn.close()


def run_year_simulation(year, is_first_year=False, compensation_params=None):
    """Run simulation for a single year."""
    print(f"\n🎯 Running simulation for year {year}")
    print("-" * 40)

    # Step 0: Create/update enrollment registry (prevents duplicate enrollments)
    # For first year, create registry from baseline. For subsequent years, it was updated at end of previous year.
    if is_first_year:
        if not create_enrollment_registry(year):
            print(f"❌ Failed to create enrollment registry for year {year}")
            return False

    # Step 1: Foundation setup (seeds and staging)
    if is_first_year:
        print("📋 Setting up foundation (first year)...")
        if not run_dbt_command(["seed"], "Loading seed data"):
            return False
        # Run all staging models
        if not run_dbt_command(["run", "--models", "staging.*"], "Running all staging models"):
            return False
        if not run_dbt_command(["run", "--models", "int_baseline_workforce"], "Creating baseline workforce"):
            return False

    # Step 2: Workforce transition setup (for subsequent years)
    if not is_first_year:
        # Run the snapshot model without dependency checking to avoid cycle detection
        if not run_dbt_command(["run", "--models", "int_active_employees_prev_year_snapshot", "--no-defer", "--full-refresh"], "Setting up previous year snapshot", year, compensation_params):
            return False

    # Step 3: Parameters (must come before workforce needs) - Pass compensation params here!
    if not run_dbt_command(["run", "--models", "int_effective_parameters"], "Resolving parameters", year, compensation_params):
        return False

    # Step 4: Employee compensation and workforce needs calculation
    if not run_dbt_command(["run", "--models", "int_employee_compensation_by_year"], "Calculating employee compensation", year, compensation_params):
        return False
    if not run_dbt_command(["run", "--models", "int_workforce_needs"], "Calculating workforce needs", year, compensation_params):
        return False
    if not run_dbt_command(["run", "--models", "int_workforce_needs_by_level"], "Calculating workforce needs by level", year, compensation_params):
        return False

    # Step 5: Event generation (with simulation_year and compensation parameters)
    event_models = [
        "int_termination_events",
        "int_hiring_events",
        "int_new_hire_termination_events",
        "int_hazard_promotion",
        "int_hazard_merit",
        "int_promotion_events",
        "int_merit_events",
        "int_eligibility_determination",
        "int_enrollment_events",
        "int_employee_contributions",  # E034 Contribution calculations
        "int_employee_match_calculations",  # E025 Match calculations
        "fct_employer_match_events"  # E025 Match event generation
    ]

    for model in event_models:
        if not run_dbt_command(["run", "--models", model], f"Running {model}", year, compensation_params):
            return False

    # Step 6: Consolidation
    if not run_dbt_command(["run", "--models", "fct_yearly_events"], "Consolidating events", year, compensation_params):
        return False

    # Step 7: Enrollment state accumulator (fixed circular dependency)
    if not run_dbt_command(["run", "--models", "int_enrollment_state_accumulator"], "Building enrollment state accumulator", year, compensation_params):
        return False

    # Step 8: Employee contribution calculations (Epic E034)
    if not run_dbt_command(["run", "--models", "int_employee_contributions"], "Calculating employee contributions", year, compensation_params):
        return False

    # Step 9: Final workforce snapshot (includes contribution data)
    if not run_dbt_command(["run", "--models", "fct_workforce_snapshot"], "Creating workforce snapshot", year, compensation_params):
        return False

    # Step 10: Data quality validation for contributions
    if not run_dbt_command(["run", "--models", "dq_employee_contributions_validation"], "Validating contribution data quality", year, compensation_params):
        return False

    print(f"✅ Year {year} simulation completed successfully!")

    # Update enrollment registry with this year's enrollments (for next year's use)
    if not update_enrollment_registry_post_year(year):
        print(f"⚠️ Failed to update enrollment registry after year {year} - duplicate enrollments may occur next year")
        # Don't fail the simulation for this

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
            'fct_participant_balance_snapshots',
            'int_employee_contributions',  # Epic E034: Employee contribution calculations
            'dq_employee_contributions_validation',  # Epic E034: Data quality validation
            'enrollment_registry'  # Clear enrollment registry for fresh simulation
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

        # Extract compensation parameters for dbt
        compensation_params = {
            'cola_rate': config['cola_rate'],
            'merit_budget': config['merit_budget']
        }

        print(f"\n🚀 Starting multi-year simulation...")
        print(f"   Years: {start_year} - {end_year}")
        print(f"   Total years: {end_year - start_year + 1}")
        print(f"   Compensation parameters: COLA={compensation_params['cola_rate']}, Merit={compensation_params['merit_budget']}")

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
                success = run_year_simulation(year, is_first_year, compensation_params)
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
