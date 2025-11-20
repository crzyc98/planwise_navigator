# dbt Tests Directory

**Purpose**: Data quality, business logic, and compliance validation tests converted from materialized validation models for 90% faster execution.

**Epic**: E080 - Validation Model to Test Conversion
**Performance**: 7-13 seconds (vs 65-91 seconds as models)
**Impact**: 55-77 seconds saved per simulation run

---

## Directory Structure

```
dbt/tests/
├── data_quality/          # Critical data quality tests (converted from dq_*.sql)
├── analysis/              # Analysis validations (converted from validate_*.sql)
├── intermediate/          # Intermediate model tests
├── schema.yml            # Global test configuration
└── README.md             # This file
```

---

## Purpose

This directory contains **dbt tests** that validate data quality, business logic, and compliance **without materializing tables**. These tests were converted from validation models (previously in `dbt/models/marts/data_quality/` and `dbt/models/analysis/`) to achieve significant performance improvements.

### Why Tests Instead of Models?

**Previous Approach (Models)**:
- Validation logic materialized as tables in DuckDB
- Required disk I/O and transaction overhead
- Cluttered database schema with temporary validation tables
- 65-91 seconds to run 24 validations (with threading)

**Current Approach (Tests)**:
- Validation logic executes as queries without table creation
- No disk I/O, minimal transaction overhead
- Clean database schema
- 7-13 seconds to run 24 validations (with threading)
- **90% performance improvement**

---

## Naming Conventions

### Test File Naming

All tests follow a consistent naming pattern:

| Original Model | Test Name | Location |
|----------------|-----------|----------|
| `dq_new_hire_match_validation.sql` | `test_new_hire_match_validation.sql` | `dbt/tests/data_quality/` |
| `validate_compensation_bounds.sql` | `test_compensation_bounds.sql` | `dbt/tests/analysis/` |
| `dq_deferral_escalation_validation.sql` | `test_deferral_escalation_validation.sql` | `dbt/tests/data_quality/` |

**Rules**:
1. Remove `dq_` prefix → add `test_` prefix
2. Remove `validate_` prefix → add `test_` prefix
3. Keep descriptive portion of name unchanged
4. Place in corresponding test subdirectory

### Test SQL Structure

All test files must follow this structure:

```sql
-- Converted from validation model to test (E080)
-- Original model: dq_xxx.sql
--
-- Test behavior:
--   PASS: 0 rows returned (no validation failures)
--   FAIL: >0 rows returned (violations stored in test_failures.test_xxx)

WITH source AS (
    SELECT * FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}  -- REQUIRED: Filter by year!
),
validation_failures AS (
    SELECT *
    FROM source
    WHERE invalid_condition = true  -- Define failure condition
)
SELECT * FROM validation_failures  -- Return failing rows
```

**Key Requirements**:
1. Add year filter: `WHERE simulation_year = {{ var('simulation_year') }}`
2. Return failing rows (not a count)
3. Remove all `{{ config() }}` blocks
4. Keep validation logic identical to original model

---

## How to Run Tests

### Run All Tests

```bash
cd dbt

# Run all tests
dbt test

# Run all data quality tests
dbt test --select path:tests/data_quality

# Run all analysis tests
dbt test --select path:tests/analysis
```

### Run Specific Test

```bash
cd dbt

# Run single test by name
dbt test --select test_new_hire_match_validation

# Run test with year filter
dbt test --select test_new_hire_match_validation --vars "simulation_year: 2025"

# Run test with verbose output
dbt test --select test_new_hire_match_validation --verbose
```

### Run Tests in Pipeline

Tests are automatically executed by Navigator Orchestrator during the VALIDATION stage:

```bash
planwise simulate 2025-2027  # Tests run automatically
```

### Debug Test Failures

When a test fails, results are stored in the `test_failures` schema:

```bash
# Connect to DuckDB
duckdb dbt/simulation.duckdb

# View failed test results
SELECT * FROM test_failures.test_new_hire_match_validation
WHERE simulation_year = 2025
LIMIT 10;

# Count failures by type
SELECT
    issue_type,
    COUNT(*) as failure_count
FROM test_failures.test_new_hire_match_validation
GROUP BY issue_type;
```

---

## How to Add New Tests

### Step 1: Create Test File

Create a new `.sql` file in the appropriate subdirectory:

```bash
# For data quality tests
touch dbt/tests/data_quality/test_my_new_validation.sql

# For analysis tests
touch dbt/tests/analysis/test_my_analysis.sql
```

### Step 2: Write Test SQL

```sql
-- Description of what this test validates
-- Failure condition: [describe when this test should fail]

WITH source AS (
    SELECT * FROM {{ ref('source_model') }}
    WHERE simulation_year = {{ var('simulation_year') }}  -- Always filter by year!
),
validation_failures AS (
    SELECT
        employee_id,
        scenario_id,
        plan_design_id,
        simulation_year,
        'Specific issue description' as issue_type,
        actual_value,
        expected_value
    FROM source
    WHERE actual_value != expected_value  -- Define failure condition
)
SELECT * FROM validation_failures
```

### Step 3: Document Test in schema.yml

Add test configuration to `dbt/tests/schema.yml`:

```yaml
tests:
  - name: test_my_new_validation
    description: |
      Validates [what this test checks]

      **Failure Condition**: [when it fails]
      **Severity**: warn/error
      **Owner**: [team name]

    config:
      severity: warn  # or 'error' for critical tests
      store_failures: true
      tags: ['data_quality', 'custom_tag']
```

### Step 4: Test the Test

```bash
cd dbt

# Run your new test
dbt test --select test_my_new_validation --vars "simulation_year: 2025"

# Verify it passes/fails as expected
# Check test_failures schema if it fails
```

---

## Test Configuration

### Global Configuration (schema.yml)

All tests inherit these global settings:

```yaml
tests:
  +severity: warn          # Don't fail pipeline on validation errors
  +store_failures: true    # Store failures for debugging
  +schema: test_failures   # Schema for failure tables
```

### Override for Critical Tests

Some tests are configured with `severity: error` to fail the pipeline:

```yaml
tests:
  - name: test_new_hire_match_validation
    config:
      severity: error  # FAIL PIPELINE if this test fails
```

### Test Severity Levels

| Severity | Behavior | Use Case |
|----------|----------|----------|
| `error` | Fail pipeline if test fails | Critical financial/compliance validations |
| `warn` | Log warning, continue pipeline | Data quality checks, analysis validations |
| `info` | Log only | Informational checks, monitoring |

---

## Converting Validation Models to Tests

### Automated Conversion Script

Use the conversion script to automate most of the work:

```bash
# Convert a validation model to test
./scripts/convert_validation_to_test.sh dbt/models/marts/data_quality/dq_xxx.sql

# Follow the script's output for next steps:
# 1. Review converted SQL
# 2. Add year filters
# 3. Test the conversion
# 4. Validate results match
# 5. Document in schema.yml
# 6. Delete original model (only after validation!)
```

### Manual Conversion Steps

If converting manually:

1. **Copy model to test directory**:
   ```bash
   cp dbt/models/marts/data_quality/dq_xxx.sql \
      dbt/tests/data_quality/test_xxx.sql
   ```

2. **Remove config block**:
   ```sql
   -- DELETE THESE LINES:
   {{ config(
       materialized='table',
       tags=['data_quality']
   ) }}
   ```

3. **Add year filter**:
   ```sql
   -- ADD THIS TO EVERY CTE:
   WHERE simulation_year = {{ var('simulation_year') }}
   ```

4. **Test conversion**:
   ```bash
   cd dbt
   dbt test --select test_xxx --vars "simulation_year: 2025"
   ```

5. **Validate results match**:
   ```bash
   # Run old model
   dbt run --select dq_xxx --vars "simulation_year: 2025"

   # Run new test
   dbt test --select test_xxx --vars "simulation_year: 2025"

   # Compare in DuckDB
   duckdb dbt/simulation.duckdb "
   SELECT 'model' as source, COUNT(*) FROM dq_xxx
   UNION ALL
   SELECT 'test', COUNT(*) FROM test_failures.test_xxx
   "
   # Counts should match exactly!
   ```

6. **Document in schema.yml**:
   Add test configuration with description

7. **Delete original model** (only after validation passes):
   ```bash
   rm dbt/models/marts/data_quality/dq_xxx.sql
   ```

---

## Validation Logic Patterns

### Pattern 1: Simple Validation

Check for invalid values:

```sql
WITH source AS (
    SELECT * FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
failures AS (
    SELECT *
    FROM source
    WHERE compensation_amount < 0  -- Invalid negative compensation
)
SELECT * FROM failures
```

### Pattern 2: Multi-Table Validation

Check consistency across tables:

```sql
WITH events AS (
    SELECT * FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
snapshot AS (
    SELECT * FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
orphaned_events AS (
    SELECT e.*
    FROM events e
    LEFT JOIN snapshot s USING (employee_id, simulation_year)
    WHERE s.employee_id IS NULL  -- Event without matching employee
)
SELECT * FROM orphaned_events
```

### Pattern 3: Threshold Validation

Check for values exceeding acceptable ranges:

```sql
WITH source AS (
    SELECT * FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
out_of_bounds AS (
    SELECT
        employee_id,
        annual_compensation,
        CASE
            WHEN annual_compensation < 20000 THEN 'Below minimum'
            WHEN annual_compensation > 500000 THEN 'Above maximum'
        END as issue_type
    FROM source
    WHERE annual_compensation < 20000
       OR annual_compensation > 500000
)
SELECT * FROM out_of_bounds
```

### Pattern 4: Business Logic Validation

Validate complex business rules:

```sql
WITH new_hires AS (
    SELECT * FROM {{ ref('int_new_hire_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
match_calculations AS (
    SELECT
        employee_id,
        prorated_compensation,
        deferral_rate,
        employer_match,
        -- Expected match: 3% of prorated comp
        prorated_compensation * 0.03 * deferral_rate as expected_match
    FROM new_hires
),
match_errors AS (
    SELECT
        employee_id,
        employer_match,
        expected_match,
        ABS(employer_match - expected_match) as variance,
        'Match calculation error' as issue_type
    FROM match_calculations
    WHERE ABS(employer_match - expected_match) > 0.01  -- Allow $0.01 tolerance
)
SELECT * FROM match_errors
```

---

## Performance Best Practices

### Always Filter by Year

**Critical**: Every test must filter by `simulation_year` to avoid scanning all data:

```sql
-- CORRECT (fast):
SELECT * FROM {{ ref('fct_yearly_events') }}
WHERE simulation_year = {{ var('simulation_year') }}

-- INCORRECT (slow - scans all years):
SELECT * FROM {{ ref('fct_yearly_events') }}
```

### Filter Early in CTEs

Apply filters as early as possible in your CTE chain:

```sql
-- CORRECT (filter early):
WITH source AS (
    SELECT * FROM {{ ref('large_table') }}
    WHERE simulation_year = {{ var('simulation_year') }}  -- Filter immediately
),
processed AS (
    SELECT * FROM source  -- Work with filtered data
    WHERE additional_condition
)

-- INCORRECT (filter late):
WITH source AS (
    SELECT * FROM {{ ref('large_table') }}  -- Loads all data
),
processed AS (
    SELECT * FROM source
    WHERE simulation_year = {{ var('simulation_year') }}  -- Filter too late
)
```

### Use Appropriate Joins

Join on all key columns including year:

```sql
-- CORRECT (efficient join):
SELECT e.*
FROM events e
JOIN snapshot s
  ON e.employee_id = s.employee_id
 AND e.simulation_year = s.simulation_year  -- Include year in join!

-- INCORRECT (inefficient join):
SELECT e.*
FROM events e
JOIN snapshot s
  ON e.employee_id = s.employee_id  -- Missing year in join
WHERE e.simulation_year = {{ var('simulation_year') }}
```

---

## Troubleshooting

### Test Fails Unexpectedly

1. Check test SQL logic:
   ```bash
   # View test results
   duckdb dbt/simulation.duckdb "
   SELECT * FROM test_failures.test_xxx
   LIMIT 10
   "
   ```

2. Compare with original model (if still exists):
   ```bash
   # Run both and compare
   dbt run --select dq_xxx --vars "simulation_year: 2025"
   dbt test --select test_xxx --vars "simulation_year: 2025"
   ```

3. Check for missing year filter

### Test Runs Slowly

1. Verify year filter is present:
   ```sql
   -- Add if missing:
   WHERE simulation_year = {{ var('simulation_year') }}
   ```

2. Check join conditions include year

3. Filter early in CTE chain

### Test Results Don't Match Original Model

1. Check for removed config affecting logic
2. Verify all CTEs have proper filters
3. Compare SQL line-by-line with original model
4. Check for changes in referenced models

### Pipeline Fails on Test

1. Check test severity in schema.yml:
   ```yaml
   # Change from error to warn if needed
   config:
     severity: warn  # Don't fail pipeline
   ```

2. Review failure details:
   ```sql
   SELECT * FROM test_failures.test_xxx
   ```

3. Fix underlying data issue or adjust test logic

---

## Frequently Asked Questions

### When should I use a test vs a model?

**Use a test** when:
- Validating data quality
- Checking business logic constraints
- Compliance/audit checks
- Results are pass/fail (no downstream use)

**Use a model** when:
- Creating reusable data transformations
- Building dimensional models
- Results are consumed by other models or reports
- Creating metrics dashboards

### What's the difference between severity levels?

- `error`: Test failure blocks pipeline (use for critical validations)
- `warn`: Test failure logged but pipeline continues (use for most validations)
- `info`: Test result logged (use for monitoring/informational checks)

### How do I debug a failing test?

1. View failure details:
   ```sql
   SELECT * FROM test_failures.test_xxx
   WHERE simulation_year = 2025
   ```

2. Run test with verbose output:
   ```bash
   dbt test --select test_xxx --verbose
   ```

3. Check source data:
   ```sql
   -- Inspect source table
   SELECT * FROM {{ ref('source_model') }}
   WHERE simulation_year = 2025
   ```

### Can I run tests for multiple years?

Tests run per year by default. To run for multiple years:

```bash
# Run simulation for multiple years (tests run each year)
planwise simulate 2025-2027

# Or run tests manually for each year
for year in 2025 2026 2027; do
    dbt test --vars "simulation_year: $year"
done
```

### What if a test takes too long?

1. Add `simulation_year` filter (if missing)
2. Move filters earlier in CTE chain
3. Add year to join conditions
4. Consider splitting into multiple focused tests
5. Check query plan in DuckDB:
   ```sql
   EXPLAIN SELECT * FROM {{ test_sql }}
   ```

---

## Additional Resources

- **Epic Document**: `/docs/epics/E080_validation_model_to_test_conversion.md`
- **Conversion Script**: `/scripts/convert_validation_to_test.sh`
- **dbt Test Documentation**: https://docs.getdbt.com/docs/building-a-dbt-project/tests
- **CLAUDE.md**: Project-level documentation and standards

---

**Last Updated**: 2025-11-06
**Epic**: E080 - Validation Model to Test Conversion
**Status**: Infrastructure complete, ready for conversions
