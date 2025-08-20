#!/usr/bin/env python3
"""
Test script for employer match integration in fct_workforce_snapshot
Validates the SQL changes without running the full model.
"""

import re
from pathlib import Path


def test_workforce_snapshot_integration():
    """Test that the employer match integration is properly implemented."""
    print("Testing employer match integration in fct_workforce_snapshot...")

    # Read the modified fct_workforce_snapshot.sql file
    snapshot_file = Path("dbt/models/marts/fct_workforce_snapshot.sql")
    content = snapshot_file.read_text()

    # Test 1: Check employer_match_contributions CTE exists
    cte_pattern = r"employer_match_contributions AS \(\s*SELECT[^}]+FROM \{\{ ref\('fct_employer_match_events'\) \}\}"
    if re.search(cte_pattern, content, re.DOTALL):
        print("✓ employer_match_contributions CTE found")
    else:
        print("✗ employer_match_contributions CTE NOT found")
        return False

    # Test 2: Check LEFT JOIN to employer match data
    join_pattern = r"LEFT JOIN employer_match_contributions emp_match ON"
    if re.search(join_pattern, content):
        print("✓ LEFT JOIN to employer_match_contributions found")
    else:
        print("✗ LEFT JOIN to employer_match_contributions NOT found")
        return False

    # Test 3: Check employer_match_contribution field in SELECT
    field_pattern = r"COALESCE\(emp_match\.total_employer_match_amount, 0\.00\) AS employer_match_contribution"
    if re.search(field_pattern, content):
        print("✓ employer_match_contribution field found in SELECT")
    else:
        print("✗ employer_match_contribution field NOT found in SELECT")
        return False

    # Test 4: Check CTE structure for proper aggregation
    aggregation_pattern = r"SUM\(amount\) AS total_employer_match_amount"
    if re.search(aggregation_pattern, content):
        print("✓ SUM aggregation found in employer_match_contributions CTE")
    else:
        print("✗ SUM aggregation NOT found in employer_match_contributions CTE")
        return False

    # Test 5: Check GROUP BY clause
    group_by_pattern = r"GROUP BY employee_id, simulation_year"
    if re.search(group_by_pattern, content):
        print("✓ GROUP BY clause found in employer_match_contributions CTE")
    else:
        print("✗ GROUP BY clause NOT found in employer_match_contributions CTE")
        return False

    print("\n✓ All SQL integration tests passed!")
    return True


def test_schema_yml_updates():
    """Test that schema.yml has been properly updated."""
    print("\nTesting schema.yml updates...")

    # Read the schema.yml file
    schema_file = Path("dbt/models/marts/schema.yml")
    content = schema_file.read_text()

    # Test 1: Check column definition exists
    column_pattern = r"name: employer_match_contribution"
    if re.search(column_pattern, content):
        print("✓ employer_match_contribution column definition found")
    else:
        print("✗ employer_match_contribution column definition NOT found")
        return False

    # Test 2: Check data type
    data_type_pattern = r"data_type: double"
    # This should appear after the employer_match_contribution column
    match_section = re.search(
        r"name: employer_match_contribution.*?data_type: double", content, re.DOTALL
    )
    if match_section:
        print("✓ employer_match_contribution data_type set to double")
    else:
        print("✗ employer_match_contribution data_type NOT properly set")
        return False

    # Test 3: Check basic tests
    basic_tests_pattern = (
        r"name: employer_match_contribution.*?not_null.*?accepted_range"
    )
    if re.search(basic_tests_pattern, content, re.DOTALL):
        print("✓ Basic dbt tests (not_null, accepted_range) found")
    else:
        print("✗ Basic dbt tests NOT found")
        return False

    # Test 4: Check model-level validation tests
    match_validation_pattern = r"employer_match_reasonable_relative_to_contributions"
    if re.search(match_validation_pattern, content):
        print("✓ Model-level employer match validation tests found")
    else:
        print("✗ Model-level employer match validation tests NOT found")
        return False

    print("\n✓ All schema.yml tests passed!")
    return True


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("EMPLOYER MATCH INTEGRATION TESTING")
    print("=" * 60)

    sql_success = test_workforce_snapshot_integration()
    schema_success = test_schema_yml_updates()

    print("\n" + "=" * 60)
    if sql_success and schema_success:
        print("🎉 ALL TESTS PASSED! Integration is ready.")
        print("\nNext steps:")
        print("1. Close any database connections in VS Code/IDE")
        print(
            "2. Run: dbt run --select fct_workforce_snapshot --vars 'simulation_year: 2025'"
        )
        print("3. Verify employer_match_contribution column appears in output")
    else:
        print("❌ SOME TESTS FAILED. Please review implementation.")
    print("=" * 60)


if __name__ == "__main__":
    main()
