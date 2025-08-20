#!/usr/bin/env python3
"""
Simple Multi-Year Simulation Runner

⚠️  DEPRECATION WARNING: Consider using orchestrator_dbt/run_multi_year.py for production workloads
    This simple runner is intended for basic testing and development only.

Reads config/simulation_config.yaml and runs multi-year simulations.
Uses the working foundation approach with simple subprocess calls.
"""

import json
import subprocess
import sys
from pathlib import Path

import duckdb
import yaml

from shared_utils import ExecutionMutex, print_execution_warning


def load_config():
    """Load simulation configuration from YAML file."""
    config_path = Path("config/simulation_config.yaml")

    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Extract simulation parameters
        simulation = config.get("simulation", {})
        start_year = simulation.get("start_year", 2025)
        end_year = simulation.get("end_year", 2029)
        random_seed = simulation.get("random_seed", 42)

        # Extract compensation parameters
        compensation = config.get("compensation", {})
        cola_rate = compensation.get("cola_rate", 0.005)
        merit_budget = compensation.get("merit_budget", 0.025)

        print(f"📋 Configuration loaded:")
        print(f"   Years: {start_year} - {end_year}")
        print(f"   Random seed: {random_seed}")
        print(f"   COLA rate: {cola_rate}")
        print(f"   Merit budget: {merit_budget}")

        return {
            "start_year": start_year,
            "end_year": end_year,
            "random_seed": random_seed,
            "cola_rate": cola_rate,
            "merit_budget": merit_budget,
            "config": config,
        }

    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        sys.exit(1)


def run_dbt_command(
    command_args, description="Running dbt command", simulation_year=None, dbt_vars=None
):
    """Run a dbt command with error handling (like working staging approach)."""

    # Build command
    cmd = ["dbt"] + command_args

    # Build vars dictionary
    vars_dict = {}
    if simulation_year:
        vars_dict["simulation_year"] = simulation_year

    # Add provided dbt vars if any
    if dbt_vars:
        vars_dict.update(dbt_vars)

    # Add vars to command if any are specified
    if vars_dict:
        # Use JSON for --vars to ensure proper quoting/types (valid YAML subset)
        cmd.extend(["--vars", json.dumps(vars_dict)])

    print(f"🔧 {description}...")

    try:
        result = subprocess.run(
            cmd, cwd="dbt", check=True, capture_output=True, text=True
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


def extract_dbt_vars_from_config(full_config: dict) -> dict:
    """Map simulation YAML config to dbt vars used across models.

    Keeps names aligned with model expectations and defaults.
    """
    cfg = full_config.get("config", full_config)

    comp = cfg.get("compensation", {})
    elig = cfg.get("eligibility", {})
    plan_elig = cfg.get("plan_eligibility", {})
    enroll = cfg.get("enrollment", {})
    auto = enroll.get("auto_enrollment", {})
    proactive = enroll.get("proactive_enrollment", {})
    timing = enroll.get("timing", {})
    # Note: workforce growth/termination vars are handled in navigator orchestrator

    dbt_vars = {}

    # Compensation vars already passed before; include for completeness
    if "cola_rate" in comp:
        dbt_vars["cola_rate"] = comp["cola_rate"]
    if "merit_budget" in comp:
        dbt_vars["merit_budget"] = comp["merit_budget"]

    # Eligibility and plan eligibility mapping used by timing/eligibility models
    if "waiting_period_days" in elig:
        dbt_vars["eligibility_waiting_days"] = elig["waiting_period_days"]
        dbt_vars["minimum_service_days"] = elig["waiting_period_days"]
    if "minimum_age" in plan_elig:
        dbt_vars["minimum_age"] = plan_elig["minimum_age"]

    # Auto-enrollment core vars
    if "enabled" in auto:
        dbt_vars["auto_enrollment_enabled"] = bool(auto["enabled"])
    if "scope" in auto:
        dbt_vars["auto_enrollment_scope"] = str(auto["scope"])
    if "hire_date_cutoff" in auto and auto["hire_date_cutoff"]:
        # Pass as string to avoid Jinja date formatting surprises
        dbt_vars["auto_enrollment_hire_date_cutoff"] = str(auto["hire_date_cutoff"])
    if "window_days" in auto:
        dbt_vars["auto_enrollment_window_days"] = int(auto["window_days"])
    if "default_deferral_rate" in auto:
        dbt_vars["auto_enrollment_default_deferral_rate"] = float(
            auto["default_deferral_rate"]
        )
    if "opt_out_grace_period" in auto:
        dbt_vars["auto_enrollment_opt_out_grace_period"] = int(
            auto["opt_out_grace_period"]
        )

    # Proactive enrollment vars
    if "enabled" in proactive:
        dbt_vars["proactive_enrollment_enabled"] = bool(proactive["enabled"])
    tw = proactive.get("timing_window", {})
    if "min_days" in tw:
        dbt_vars["proactive_enrollment_min_days"] = int(tw["min_days"])
    if "max_days" in tw:
        dbt_vars["proactive_enrollment_max_days"] = int(tw["max_days"])
    probs = proactive.get("probability_by_demographics", {})
    if probs:
        if "young" in probs:
            dbt_vars["proactive_enrollment_rate_young"] = float(probs["young"])
        if "mid_career" in probs:
            dbt_vars["proactive_enrollment_rate_mid_career"] = float(
                probs["mid_career"]
            )
        if "mature" in probs:
            dbt_vars["proactive_enrollment_rate_mature"] = float(probs["mature"])
        if "senior" in probs:
            dbt_vars["proactive_enrollment_rate_senior"] = float(probs["senior"])

    # Timing/business day adjustment used by window model
    if "business_day_adjustment" in timing:
        dbt_vars["enrollment_business_day_adjustment"] = bool(
            timing["business_day_adjustment"]
        )

    # Random seed for deterministic behavior where supported
    if "random_seed" in cfg.get("simulation", {}):
        dbt_vars["random_seed"] = cfg["simulation"]["random_seed"]

    # Growth/termination vars intentionally omitted here to avoid drift with new orchestrator

    # Employer match configuration (E039): map YAML to dbt vars used by match engine
    employer = cfg.get("employer_match", {})
    active = employer.get("active_formula")
    formulas = employer.get("formulas")
    if active is not None:
        dbt_vars["active_match_formula"] = str(active)
    if formulas is not None:
        dbt_vars["match_formulas"] = formulas

    # Employer core contribution configuration (E039): pass nested structure directly
    core = cfg.get("employer_core_contribution", {})
    if core:
        dbt_vars["employer_core_contribution"] = core

    return dbt_vars


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
                print(
                    f"   Net growth                 : {growth:+4,} ({growth_pct:+5.1f}%)"
                )

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
                print(
                    f"   Net growth                   : {growth:+4,} ({growth_pct:+5.1f}%)"
                )

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
                print(
                    f"   ⚠️  Data quality issues      : {failures:4,} validation failures"
                )
            else:
                print(f"   ✅ Data quality              : All validations passed")

        except Exception as contrib_error:
            print(f"   ⚠️  Contribution summary unavailable: {contrib_error}")

        # Additional validation checks
        print(f"\n🔍 Data Quality Checks:")

        # Check for reasonable hire/termination ratios
        hire_count = sum(
            count for event_type, count in events_results if event_type == "hire"
        )
        term_count = sum(
            count
            for event_type, count in events_results
            if event_type in ["termination", "TERMINATION"]
        )

        if hire_count > 0 and term_count > 0:
            turnover_ratio = term_count / hire_count
            print(
                f"   Hire/Termination ratio       : {hire_count:,} hires, {term_count:,} terms (ratio: {turnover_ratio:.2f})"
            )

            # Flag unusual ratios
            if hire_count > 2000:
                print(
                    f"   ⚠️  HIGH HIRE COUNT: {hire_count:,} hires may be excessive for one year"
                )
            if term_count > 1000:
                print(
                    f"   ⚠️  HIGH TERMINATION COUNT: {term_count:,} terminations may be excessive"
                )

        # Check employer match via dedicated match events table (E039)
        try:
            match_query = """
                SELECT COUNT(*) as match_count,
                       SUM(amount) as total_match_cost,
                       AVG(amount) as avg_match_amount
                FROM fct_employer_match_events
                WHERE simulation_year = ?
            """
            match_result = conn.execute(match_query, [year]).fetchone()
            if match_result and match_result[0] > 0:
                match_cnt, total_cost, avg_match = match_result
                print(f"\n💰 Employer Match Summary:")
                print(f"   Employees receiving match    : {match_cnt:,}")
                print(f"   Total match cost             : ${total_cost:,.2f}")
                print(f"   Average match per employee   : ${avg_match:,.2f}")
        except Exception:
            pass

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
        """.format(
            ",".join("?" * len(completed_years))
        )

        progression_results = conn.execute(
            progression_query, completed_years
        ).fetchall()

        if progression_results:
            print("📈 Workforce Progression:")
            print("   Year  | Total Emp | Active | New Hires | Exp Terms | NH Terms")
            print("   ------|-----------|--------|-----------|-----------|----------")

            baseline_active = None
            for row in progression_results:
                year, total, active, nh_active, exp_terms, nh_terms = row
                print(
                    f"   {year} | {total:9,} | {active:6,} | {nh_active:9,} | {exp_terms:9,} | {nh_terms:8,}"
                )

                if baseline_active is None:
                    baseline_active = active

            # New summary: Active employees with deferrals using new participation status
            print("\n💰 Active Employee Deferral Participation:")
            print("   Year  | Active EEs | Participating | Participation %")
            print("   ------|------------|---------------|----------------")

            participation_query = """
            SELECT
                simulation_year,
                COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
                COUNT(CASE WHEN employment_status = 'active' AND participation_status = 'participating' THEN 1 END) as participating_employees
            FROM fct_workforce_snapshot
            WHERE simulation_year IN ({})
            GROUP BY simulation_year
            ORDER BY simulation_year
            """.format(
                ",".join("?" * len(completed_years))
            )

            participation_results = conn.execute(
                participation_query, completed_years
            ).fetchall()

            if participation_results:
                for year, active_count, participating in participation_results:
                    participation_pct = (
                        (participating / active_count * 100) if active_count > 0 else 0
                    )
                    print(
                        f"   {year} | {active_count:10,} | {participating:13,} | {participation_pct:14.1f}%"
                    )

            # Additional detail: Participation breakdown by method
            print("\n📋 Participation Breakdown by Method:")
            print(
                "   Year  | Auto Enroll | Voluntary  | Opted Out  | Not Auto   | Unenrolled"
            )
            print(
                "   ------|-------------|------------|------------|------------|------------"
            )

            detail_query = """
            SELECT
                simulation_year,
                COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'participating - auto enrollment' THEN 1 END) as auto_enrolled,
                COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'participating - voluntary enrollment' THEN 1 END) as voluntary,
                COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'not_participating - opted out of AE' THEN 1 END) as opted_out,
                COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'not_participating - not auto enrolled' THEN 1 END) as not_auto,
                COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'not_participating - proactively unenrolled' THEN 1 END) as unenrolled
            FROM fct_workforce_snapshot
            WHERE simulation_year IN ({})
            GROUP BY simulation_year
            ORDER BY simulation_year
            """.format(
                ",".join("?" * len(completed_years))
            )

            detail_results = conn.execute(detail_query, completed_years).fetchall()

            if detail_results:
                for (
                    year,
                    auto,
                    voluntary,
                    opted_out,
                    not_auto,
                    unenrolled,
                ) in detail_results:
                    print(
                        f"   {year} | {auto:11,} | {voluntary:10,} | {opted_out:10,} | {not_auto:10,} | {unenrolled:10,}"
                    )

            # Calculate overall growth
            if len(progression_results) >= 2 and baseline_active:
                final_active = progression_results[-1][
                    2
                ]  # active employees in last year
                total_growth = final_active - baseline_active
                growth_pct = (total_growth / baseline_active) * 100
                years_elapsed = len(completed_years)
                cagr = (
                    (final_active / baseline_active) ** (1 / (years_elapsed - 1)) - 1
                ) * 100

                print(f"\n📊 Overall Growth Analysis:")
                print(f"   Starting active workforce    : {baseline_active:6,}")
                print(f"   Ending active workforce      : {final_active:6,}")
                print(
                    f"   Total net growth             : {total_growth:+6,} ({growth_pct:+5.1f}%)"
                )
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
        """.format(
            ",".join("?" * len(completed_years))
        )

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
                years_list = ", ".join(
                    f"{year}: {count:,}" for year, count in year_counts
                )
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
            count_result = conn.execute(
                "SELECT COUNT(*) FROM enrollment_registry"
            ).fetchone()
            count = count_result[0] if count_result else 0
            print(
                f"✅ Created enrollment registry with {count:,} enrolled employees from baseline"
            )
        else:
            conn.execute(update_registry_sql)
            # Get count of newly added employees
            count_result = conn.execute(
                f"""
                SELECT COUNT(*) FROM enrollment_registry
                WHERE first_enrollment_year = {prev_year}
            """
            ).fetchone()
            new_count = count_result[0] if count_result else 0
            print(
                f"✅ Added {new_count:,} newly enrolled employees from year {prev_year}"
            )

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
        count_result = conn.execute(
            f"""
            SELECT COUNT(*) FROM enrollment_registry
            WHERE first_enrollment_year = {year}
        """
        ).fetchone()
        new_count = count_result[0] if count_result else 0
        print(
            f"✅ Added {new_count:,} newly enrolled employees from year {year} to registry"
        )

        return True

    except Exception as e:
        print(f"❌ Error updating enrollment registry: {e}")
        return False
    finally:
        conn.close()


def create_deferral_escalation_registry():
    """Create deferral escalation registry table if it does not exist."""
    conn = get_database_connection()
    if not conn:
        print(
            "❌ Cannot create deferral escalation registry - database connection failed"
        )
        return False

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deferral_escalation_registry (
                employee_id VARCHAR,
                first_escalation_enrollment_date DATE,
                first_escalation_year INTEGER,
                in_auto_escalation_program BOOLEAN,
                total_escalations INTEGER,
                last_escalation_date DATE,
                last_updated TIMESTAMP
            )
            """
        )
        print("✅ Ensured deferral_escalation_registry exists")
        return True
    except Exception as e:
        print(f"❌ Error creating deferral escalation registry: {e}")
        return False
    finally:
        conn.close()


def update_deferral_escalation_registry_post_year(year: int) -> bool:
    """Update deferral escalation registry with this year's escalation events."""
    print(f"📋 Updating deferral escalation registry after year {year}...")

    conn = get_database_connection()
    if not conn:
        print(
            "❌ Cannot update deferral escalation registry - database connection failed"
        )
        return False

    try:
        # Ensure table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deferral_escalation_registry (
                employee_id VARCHAR,
                first_escalation_enrollment_date DATE,
                first_escalation_year INTEGER,
                in_auto_escalation_program BOOLEAN,
                total_escalations INTEGER,
                last_escalation_date DATE,
                last_updated TIMESTAMP
            )
            """
        )

        # Insert newly escalated employees not yet in registry
        conn.execute(
            f"""
            INSERT INTO deferral_escalation_registry
            SELECT
                employee_id,
                MIN(effective_date) AS first_escalation_enrollment_date,
                {year} AS first_escalation_year,
                true AS in_auto_escalation_program,
                COUNT(*) AS total_escalations,
                MAX(effective_date) AS last_escalation_date,
                CURRENT_TIMESTAMP AS last_updated
            FROM fct_yearly_events
            WHERE simulation_year = {year}
              AND event_type = 'deferral_escalation'
              AND employee_id IS NOT NULL
              AND employee_id NOT IN (
                  SELECT employee_id FROM deferral_escalation_registry
              )
            GROUP BY employee_id
            """
        )

        # Update existing participants with counts and last escalation date for this year
        conn.execute(
            f"""
            UPDATE deferral_escalation_registry AS r
            SET
                total_escalations = r.total_escalations + s.cnt,
                last_escalation_date = CASE
                    WHEN r.last_escalation_date IS NULL THEN s.max_date
                    WHEN s.max_date IS NULL THEN r.last_escalation_date
                    WHEN r.last_escalation_date >= s.max_date THEN r.last_escalation_date
                    ELSE s.max_date
                END,
                last_updated = CURRENT_TIMESTAMP
            FROM (
                SELECT employee_id, COUNT(*) AS cnt, MAX(effective_date) AS max_date
                FROM fct_yearly_events
                WHERE simulation_year = {year}
                  AND event_type = 'deferral_escalation'
                GROUP BY employee_id
            ) AS s
            WHERE r.employee_id = s.employee_id
            """
        )

        # Report summary
        new_cnt = conn.execute(
            f"SELECT COUNT(*) FROM deferral_escalation_registry WHERE first_escalation_year = {year}"
        ).fetchone()[0]
        print(
            f"✅ Deferral escalation registry updated; new enrollments added: {new_cnt}"
        )

        return True
    except Exception as e:
        print(f"❌ Error updating deferral escalation registry: {e}")
        return False
    finally:
        conn.close()


def run_year_simulation(year, is_first_year=False, dbt_vars=None):
    """Run simulation for a single year."""
    print(f"\n🎯 Running simulation for year {year}")
    print("-" * 40)

    # Step 1: INITIALIZATION (align with navigator_orchestrator)
    if is_first_year:
        print("📋 Setting up initialization (first year)...")
        if not run_dbt_command(["seed"], "Loading seed data"):
            return False
        # Build staging and baseline for first year
        if not run_dbt_command(
            ["run", "--models", "staging.*"], "Running all staging models"
        ):
            return False
        if not run_dbt_command(
            ["run", "--models", "int_baseline_workforce"],
            "Creating baseline workforce",
            year,
            dbt_vars,
        ):
            return False
        # Ensure new hire comp staging exists for deterministic compensation (year 1)
        if not run_dbt_command(
            ["run", "--models", "int_new_hire_compensation_staging"],
            "Preparing new hire compensation staging",
            year,
            dbt_vars,
        ):
            return False

    # Step 2: Create/update registries (prevent duplicate enrollments/escalations across years)
    # For first year, create registry from baseline. For subsequent years, it was updated at end of previous year.
    if is_first_year:
        if not create_enrollment_registry(year):
            print(f"❌ Failed to create enrollment registry for year {year}")
            return False
        if not create_deferral_escalation_registry():
            print(
                f"❌ Failed to ensure deferral escalation registry exists for year {year}"
            )
            return False

    # Step 2b: Workforce transition setup (for subsequent years)
    if not is_first_year:
        # Run the snapshot model without dependency checking to avoid cycle detection
        if not run_dbt_command(
            [
                "run",
                "--models",
                "int_active_employees_prev_year_snapshot",
                "--no-defer",
                "--full-refresh",
            ],
            "Setting up previous year snapshot",
            year,
            dbt_vars,
        ):
            return False

    # Step 3: FOUNDATION (align order with orchestrator)
    # Year 1 already built baseline and new_hire_compensation_staging above.
    # Now build comp, parameters, needs, needs_by_level, eligibility
    if not run_dbt_command(
        ["run", "--models", "int_employee_compensation_by_year"],
        "Calculating employee compensation",
        year,
        dbt_vars,
    ):
        return False
    if not run_dbt_command(
        ["run", "--models", "int_effective_parameters"],
        "Resolving parameters",
        year,
        dbt_vars,
    ):
        return False
    if not run_dbt_command(
        ["run", "--models", "int_workforce_needs"],
        "Calculating workforce needs",
        year,
        dbt_vars,
    ):
        return False
    if not run_dbt_command(
        ["run", "--models", "int_workforce_needs_by_level"],
        "Calculating workforce needs by level",
        year,
        dbt_vars,
    ):
        return False
    if not run_dbt_command(
        ["run", "--models", "int_employer_eligibility"],
        "Determining employer contribution eligibility",
        year,
        dbt_vars,
    ):
        return False

    # Step 6: Event generation (with simulation_year and compensation parameters)
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
        "int_deferral_rate_escalation_events",  # E036 Deferral rate escalation events
    ]

    for model in event_models:
        if not run_dbt_command(
            ["run", "--models", model], f"Running {model}", year, dbt_vars
        ):
            return False

    # Step 4: STATE ACCUMULATION (align order with orchestrator)
    # Consolidate events
    if not run_dbt_command(
        ["run", "--models", "fct_yearly_events"], "Consolidating events", year, dbt_vars
    ):
        return False
    # Build proration snapshot before accumulators and contributions
    if not run_dbt_command(
        ["run", "--models", "int_workforce_snapshot_optimized"],
        "Building proration snapshot",
        year,
        dbt_vars,
    ):
        return False
    # Accumulators: enrollment then deferral (v2), then escalation
    if not run_dbt_command(
        ["run", "--models", "int_enrollment_state_accumulator"],
        "Building enrollment state accumulator",
        year,
        dbt_vars,
    ):
        return False
    if not run_dbt_command(
        ["run", "--models", "int_deferral_rate_state_accumulator_v2"],
        "Building deferral rate state accumulator (v2)",
        year,
        dbt_vars,
    ):
        return False
    if not run_dbt_command(
        ["run", "--models", "int_deferral_escalation_state_accumulator"],
        "Building deferral escalation state accumulator",
        year,
        dbt_vars,
    ):
        return False
    # Contributions (after accumulators)
    if not run_dbt_command(
        ["run", "--models", "int_employee_contributions"],
        "Calculating employee contributions",
        year,
        dbt_vars,
    ):
        return False
    # Employer core contributions after employee contributions
    if not run_dbt_command(
        ["run", "--models", "int_employer_core_contributions"],
        "Calculating employer core contributions",
        year,
        dbt_vars,
    ):
        return False
    # Employer match
    if not run_dbt_command(
        ["run", "--models", "int_employee_match_calculations"],
        "Calculating employer match",
        year,
        dbt_vars,
    ):
        return False
    if not run_dbt_command(
        ["run", "--models", "fct_employer_match_events"],
        "Generating employer match events",
        year,
        dbt_vars,
    ):
        return False
    # Final workforce snapshot
    if not run_dbt_command(
        ["run", "--models", "fct_workforce_snapshot"],
        "Creating workforce snapshot",
        year,
        dbt_vars,
    ):
        return False

    # Step 12: Data quality validation for contributions
    if not run_dbt_command(
        ["run", "--models", "dq_employee_contributions_validation"],
        "Validating contribution data quality",
        year,
        dbt_vars,
    ):
        return False

    print(f"✅ Year {year} simulation completed successfully!")

    # Update enrollment registry with this year's enrollments (for next year's use)
    if not update_enrollment_registry_post_year(year):
        print(
            f"⚠️ Failed to update enrollment registry after year {year} - duplicate enrollments may occur next year"
        )
        # Don't fail the simulation for this

    # Update deferral escalation registry with this year's escalations
    if not update_deferral_escalation_registry_post_year(year):
        print(f"⚠️ Failed to update deferral escalation registry after year {year}")

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
            "fct_workforce_snapshot",
            "fct_yearly_events",
            "fct_compensation_growth",
            "fct_participant_balance_snapshots",
            "int_employee_contributions",  # Epic E034: Employee contribution calculations
            "dq_employee_contributions_validation",  # Epic E034: Data quality validation
            "enrollment_registry",  # Clear enrollment registry for fresh simulation
            "deferral_escalation_registry",  # Clear deferral escalation registry for fresh simulation
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
            print(
                f"✅ Database cleared successfully - {len(cleared_tables)} tables cleared"
            )
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
    print(
        "⚠️  DEPRECATION WARNING: Consider using orchestrator_dbt/run_multi_year.py for production"
    )
    print("=" * 50)

    # Check for conflicting systems
    print_execution_warning()

    # Acquire execution mutex to prevent concurrent runs
    with ExecutionMutex("simulation_execution"):
        print("🔒 Acquired execution lock - preventing concurrent simulations")

        # Load configuration
        config = load_config()
        start_year = config["start_year"]
        end_year = config["end_year"]

        # Extract dbt vars from config (compensation, eligibility, enrollment)
        dbt_vars = extract_dbt_vars_from_config(config)

        print(f"\n🚀 Starting multi-year simulation...")
        print(f"   Years: {start_year} - {end_year}")
        print(f"   Total years: {end_year - start_year + 1}")
        print(
            f"   Compensation parameters: COLA={dbt_vars.get('cola_rate')}, Merit={dbt_vars.get('merit_budget')}"
        )

        # **CRITICAL FIX**: Clear database before starting simulation
        if not clear_simulation_database():
            print("❌ Database clearing failed, aborting simulation")
            return 1

        # Track results
        completed_years = []
        failed_years = []

        # Run simulation for each year
        for year in range(start_year, end_year + 1):
            is_first_year = year == start_year

            try:
                success = run_year_simulation(year, is_first_year, dbt_vars)
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
            print(
                f"   Success count: {len(completed_years)}/{end_year - start_year + 1}"
            )

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
            print(
                f"   {len(completed_years)} of {end_year - start_year + 1} years completed"
            )
            return 1


if __name__ == "__main__":
    main()
