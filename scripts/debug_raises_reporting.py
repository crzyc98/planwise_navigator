#!/usr/bin/env python3
"""
Debug script for investigating "Raises: 0" bug in Year Transition Validation reporting.
Traces the raise event counting logic through the validation system to identify why
raise counts are showing as zero when merit events should be generated.
"""

import duckdb
import pandas as pd
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

def connect_to_database():
    """Connect to the simulation database"""
    db_path = project_root / "simulation.duckdb"
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        sys.exit(1)
    return duckdb.connect(str(db_path))

def replicate_validation_query(conn, simulation_year=2025):
    """Replicate the exact validation query from multi_year_simulation.py"""
    print(f"\n📊 REPLICATING VALIDATION QUERY FOR YEAR {simulation_year}")
    print("=" * 70)

    # This replicates the query from validate_year_transition() function
    validation_query = """
    SELECT
        COUNT(CASE WHEN event_type = 'HIRE' THEN 1 END) as hire_events,
        COUNT(CASE WHEN event_type = 'TERMINATION' THEN 1 END) as termination_events,
        COUNT(CASE WHEN event_type = 'PROMOTION' THEN 1 END) as promotion_events,
        COUNT(CASE WHEN event_type = 'RAISE' THEN 1 END) as raise_events,
        COUNT(*) as total_events,
        COUNT(DISTINCT employee_id) as unique_employees
    FROM fct_yearly_events
    WHERE simulation_year = ?
    """

    df = conn.execute(validation_query, [simulation_year]).df()

    if df.empty:
        print("❌ No results from validation query")
        return None

    result = df.iloc[0]
    print("Validation query results:")
    print(f"  Hire events: {result['hire_events']}")
    print(f"  Termination events: {result['termination_events']}")
    print(f"  Promotion events: {result['promotion_events']}")
    print(f"  Raise events: {result['raise_events']}")
    print(f"  Total events: {result['total_events']}")
    print(f"  Unique employees: {result['unique_employees']}")

    if result['raise_events'] == 0 and result['total_events'] > 0:
        print("🚨 ISSUE DETECTED: Raise events showing as 0 despite other events present!")

    return result

def verify_event_generation(conn, simulation_year=2025):
    """Verify event generation by querying fct_yearly_events directly"""
    print(f"\n🔍 VERIFYING EVENT GENERATION FOR YEAR {simulation_year}")
    print("=" * 70)

    # Direct query of all event types
    direct_query = """
    SELECT
        event_type,
        COUNT(*) as event_count,
        COUNT(DISTINCT employee_id) as unique_employees
    FROM fct_yearly_events
    WHERE simulation_year = ?
    GROUP BY event_type
    ORDER BY event_count DESC
    """

    df = conn.execute(direct_query, [simulation_year]).df()

    if df.empty:
        print(f"❌ No events found for year {simulation_year}")
        return

    print("Direct event counts by type:")
    raise_found = False
    for _, row in df.iterrows():
        print(f"  {row['event_type']}: {row['event_count']} events ({row['unique_employees']} employees)")
        if row['event_type'].upper() == 'RAISE' or 'RAISE' in row['event_type'].upper():
            raise_found = True

    if not raise_found:
        print("🚨 No RAISE events found in direct query!")

        # Check for case sensitivity issues
        case_query = """
        SELECT DISTINCT event_type
        FROM fct_yearly_events
        WHERE simulation_year = ?
            AND (UPPER(event_type) LIKE '%RAISE%' OR LOWER(event_type) LIKE '%raise%')
        """
        case_df = conn.execute(case_query, [simulation_year]).df()

        if not case_df.empty:
            print("Found raise-related events with different casing:")
            for _, row in case_df.iterrows():
                print(f"  '{row['event_type']}'")

def trace_merit_event_pipeline(conn, simulation_year=2025):
    """Trace merit event generation through the pipeline"""
    print(f"\n🔗 TRACING MERIT EVENT PIPELINE FOR YEAR {simulation_year}")
    print("=" * 70)

    # Check if int_merit_events exists and has data
    merit_check_query = """
    SELECT COUNT(*) as merit_count
    FROM int_merit_events
    WHERE simulation_year = ?
    """

    try:
        merit_df = conn.execute(merit_check_query, [simulation_year]).df()
        merit_count = merit_df.iloc[0]['merit_count']
        print(f"Merit events in intermediate table: {merit_count}")

        if merit_count == 0:
            print("🚨 No merit events found in int_merit_events!")

            # Check merit eligibility
            eligibility_query = """
            SELECT
                COUNT(*) as total_employees,
                COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees
            FROM int_workforce_previous_year_v2
            WHERE simulation_year = ?
            """

            elig_df = conn.execute(eligibility_query, [simulation_year]).df()
            if not elig_df.empty:
                elig_result = elig_df.iloc[0]
                print(f"Base workforce: {elig_result['total_employees']} total, {elig_result['active_employees']} active")

                if elig_result['active_employees'] == 0:
                    print("🚨 No active employees found for merit eligibility!")

    except Exception as e:
        print(f"❌ Could not query int_merit_events: {e}")

def check_event_type_consistency(conn, simulation_year=2025):
    """Check for event type consistency issues"""
    print(f"\n🔧 CHECKING EVENT TYPE CONSISTENCY FOR YEAR {simulation_year}")
    print("=" * 70)

    # Check all unique event types and their variations
    consistency_query = """
    SELECT
        event_type,
        UPPER(event_type) as upper_type,
        LOWER(event_type) as lower_type,
        COUNT(*) as count
    FROM fct_yearly_events
    WHERE simulation_year = ?
    GROUP BY event_type, UPPER(event_type), LOWER(event_type)
    ORDER BY count DESC
    """

    df = conn.execute(consistency_query, [simulation_year]).df()

    print("Event type variations:")
    for _, row in df.iterrows():
        print(f"  '{row['event_type']}' -> Upper: '{row['upper_type']}', Lower: '{row['lower_type']}' ({row['count']} events)")

def validate_database_connection(conn):
    """Validate database connection and file consistency"""
    print(f"\n🔌 VALIDATING DATABASE CONNECTION")
    print("=" * 70)

    # Check database file info
    db_info_query = """
    SELECT
        current_database() as database_name,
        version() as duckdb_version
    """

    db_df = conn.execute(db_info_query).df()
    print("Database connection info:")
    for _, row in db_df.iterrows():
        print(f"  Database: {row['database_name']}")
        print(f"  DuckDB version: {row['duckdb_version']}")

    # Check table existence
    tables_query = """
    SELECT table_name, table_type
    FROM information_schema.tables
    WHERE table_name IN ('fct_yearly_events', 'int_merit_events', 'fct_workforce_snapshot')
    ORDER BY table_name
    """

    tables_df = conn.execute(tables_query).df()
    print("\nRelevant tables found:")
    for _, row in tables_df.iterrows():
        print(f"  {row['table_name']} ({row['table_type']})")

def test_parameter_resolution(conn):
    """Test parameter resolution system that might affect merit event generation"""
    print(f"\n⚙️  TESTING PARAMETER RESOLUTION")
    print("=" * 70)

    # Test if parameter tables exist and have expected values
    try:
        # Check comp_levers.csv data
        comp_levers_query = """
        SELECT * FROM comp_levers
        LIMIT 5
        """

        comp_df = conn.execute(comp_levers_query).df()
        print("Sample comp_levers data:")
        print(comp_df.to_string(index=False))

    except Exception as e:
        print(f"❌ Could not query comp_levers: {e}")

    # Check if effective parameters table exists
    try:
        params_query = """
        SELECT parameter_name, parameter_value
        FROM int_effective_parameters
        WHERE parameter_name LIKE '%merit%' OR parameter_name LIKE '%raise%'
        LIMIT 10
        """

        params_df = conn.execute(params_query).df()
        if not params_df.empty:
            print("\nMerit/raise related parameters:")
            for _, row in params_df.iterrows():
                print(f"  {row['parameter_name']}: {row['parameter_value']}")
        else:
            print("❌ No merit/raise parameters found in int_effective_parameters")

    except Exception as e:
        print(f"❌ Could not query int_effective_parameters: {e}")

def simulate_python_validation_function(conn, simulation_year=2025):
    """Simulate how the Python validation function processes the data"""
    print(f"\n🐍 SIMULATING PYTHON VALIDATION FUNCTION")
    print("=" * 70)

    # This simulates the logic from multi_year_simulation.py validate_year_transition()
    try:
        # First, test the exact query structure
        query_components = [
            "COUNT(CASE WHEN event_type = 'HIRE' THEN 1 END)",
            "COUNT(CASE WHEN event_type = 'TERMINATION' THEN 1 END)",
            "COUNT(CASE WHEN event_type = 'PROMOTION' THEN 1 END)",
            "COUNT(CASE WHEN event_type = 'RAISE' THEN 1 END)"
        ]

        for component in query_components:
            test_query = f"""
            SELECT {component} as result
            FROM fct_yearly_events
            WHERE simulation_year = ?
            """

            result = conn.execute(test_query, [simulation_year]).df().iloc[0]['result']
            event_type = component.split("'")[1]
            print(f"  {event_type} events: {result}")

        # Test with different case variations
        print("\nTesting case sensitivity:")
        case_variations = ['RAISE', 'raise', 'Raise']
        for variation in case_variations:
            case_query = f"""
            SELECT COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = ? AND event_type = '{variation}'
            """

            count = conn.execute(case_query, [simulation_year]).df().iloc[0]['count']
            print(f"  '{variation}': {count} events")

    except Exception as e:
        print(f"❌ Error in validation simulation: {e}")

def main():
    print("🔍 RAISES REPORTING DEBUG ANALYSIS")
    print("=" * 80)

    try:
        conn = connect_to_database()

        # Run all debugging steps
        validation_result = replicate_validation_query(conn)
        verify_event_generation(conn)
        trace_merit_event_pipeline(conn)
        check_event_type_consistency(conn)
        validate_database_connection(conn)
        test_parameter_resolution(conn)
        simulate_python_validation_function(conn)

        print(f"\n📋 DIAGNOSIS SUMMARY")
        print("=" * 80)

        if validation_result and validation_result['raise_events'] == 0:
            print("🚨 CONFIRMED: Raise events showing as 0 in validation query")
            print("   Possible causes to investigate:")
            print("   1. Case sensitivity mismatch between event generation and validation")
            print("   2. Merit events not being generated due to eligibility rules")
            print("   3. Database connection or transaction timing issues")
            print("   4. Event type naming inconsistencies")
        else:
            print("✅ Raise events appear to be working correctly")

        conn.close()

    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
