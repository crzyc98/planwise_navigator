#!/usr/bin/env python3
"""Check if the deferral rate fix resolved the data quality issues."""

import duckdb

def check_data_quality():
    # Connect to the database where dbt models are materialized
    conn = duckdb.connect('/Users/nicholasamaral/planwise_navigator/simulation.duckdb')

    print('=== CHECKING DATA QUALITY ISSUES ===')
    print()

    # Check for ZERO_DEFERRAL_WITH_CONTRIBUTIONS flag
    query1 = """
    SELECT
        COUNT(*) as total_records,
        SUM(CASE WHEN data_quality_flag = 'ZERO_DEFERRAL_WITH_CONTRIBUTIONS' THEN 1 ELSE 0 END) as zero_deferral_with_contributions,
        SUM(CASE WHEN data_quality_flag = 'VALID' THEN 1 ELSE 0 END) as valid_records,
        SUM(CASE WHEN data_quality_flag NOT IN ('VALID', 'ZERO_DEFERRAL_WITH_CONTRIBUTIONS') THEN 1 ELSE 0 END) as other_issues
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    """
    result = conn.execute(query1).fetchone()
    print(f'Total records: {result[0]}')
    print(f'Zero deferral with contributions: {result[1]}')
    print(f'Valid records: {result[2]}')
    print(f'Other data quality issues: {result[3]}')
    print()

    # Check carried forward rates
    query2 = """
    SELECT
        COUNT(*) as employees_with_carried_rates,
        SUM(CASE WHEN deferral_rate_source LIKE 'enrollment_event_year_%' THEN 1 ELSE 0 END) as from_enrollment_events,
        SUM(CASE WHEN deferral_rate_source LIKE 'accumulator_from_year_%' THEN 1 ELSE 0 END) as from_accumulator,
        SUM(CASE WHEN deferral_rate_source = 'census_data' THEN 1 ELSE 0 END) as from_census,
        SUM(CASE WHEN deferral_rate_source = 'default_zero' THEN 1 ELSE 0 END) as default_zero
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    """
    result = conn.execute(query2).fetchone()
    print('Deferral rate sources:')
    print(f'  From enrollment events: {result[1]}')
    print(f'  From accumulator: {result[2]}')
    print(f'  From census data: {result[3]}')
    print(f'  Default zero: {result[4]}')
    print()

    # Check if carried forward rates are working
    query3 = """
    SELECT
        COUNT(*) as carried_forward_count,
        AVG(current_deferral_rate) as avg_deferral_rate,
        MIN(current_deferral_rate) as min_deferral_rate,
        MAX(current_deferral_rate) as max_deferral_rate
    FROM int_employee_contributions
    WHERE simulation_year = 2025
        AND is_rate_carried_forward = true
    """
    result = conn.execute(query3).fetchone()
    print('Carried forward rates:')
    print(f'  Count: {result[0]}')
    if result[1]:
        print(f'  Average rate: {result[1]:.2%}')
        print(f'  Min rate: {result[2]:.2%}')
        print(f'  Max rate: {result[3]:.2%}')
    print()

    # Show sample of any remaining issues
    query4 = """
    SELECT
        employee_id,
        current_deferral_rate,
        prorated_annual_contributions,
        data_quality_flag,
        deferral_rate_source
    FROM int_employee_contributions
    WHERE simulation_year = 2025
        AND data_quality_flag = 'ZERO_DEFERRAL_WITH_CONTRIBUTIONS'
    LIMIT 5
    """
    results = conn.execute(query4).fetchall()
    if results:
        print('Sample of employees with ZERO_DEFERRAL_WITH_CONTRIBUTIONS:')
        for row in results:
            print(f'  {row[0]}: rate={row[1]:.2%}, contributions=${row[2]:.2f}, flag={row[3]}, source={row[4]}')
    else:
        print('✅ NO employees with ZERO_DEFERRAL_WITH_CONTRIBUTIONS issue!')

    # Check distribution of data quality flags
    query5 = """
    SELECT
        data_quality_flag,
        COUNT(*) as count
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    GROUP BY data_quality_flag
    ORDER BY count DESC
    """
    print()
    print('Data quality flag distribution:')
    results = conn.execute(query5).fetchall()
    for flag, count in results:
        print(f'  {flag}: {count}')

    conn.close()

if __name__ == '__main__':
    check_data_quality()
