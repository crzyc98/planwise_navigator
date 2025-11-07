# E080: Validation Model to Test Conversion (E079 Phase 1A)

**Status**: 📋 Ready for Implementation
**Priority**: P1 (High Impact, Low Risk)
**Owner**: Claude Code
**Created**: 2025-11-06
**Target Completion**: 2025-11-08
**Estimated Effort**: 4-6 hours
**Expected Savings**: 55-77 seconds per simulation run

---

## Executive Summary

PlanWise Navigator currently runs **24 validation models as regular dbt models**, materializing tables on every simulation run. This creates significant overhead:
- **Current overhead**: 195-273 seconds total (65-91s with threading)
- **After conversion**: 20-39 seconds total (7-13s with threading)
- **Net savings**: **55-77 seconds per simulation** (1 minute faster!)

This epic converts validation models to **dbt tests** - a pure refactoring with **zero logic changes** and **low risk**. Tests execute queries without materializing tables, providing identical validation with 90% less overhead.

**Why This Is E079 Phase 1A:**
- ✅ **Lowest risk** - no business logic changes
- ✅ **Highest impact** - 55-77s savings for minimal effort
- ✅ **Quick wins** - can be completed in one afternoon
- ✅ **Foundation** - enables future optimizations

---

## Problem Statement

### Current State: Validation as Models (Slow ❌)

```bash
# Current validation execution (dbt run)
$ dbt run --select tag:data_quality

Building dq_new_hire_match_validation ................. [5.2s]
Building dq_employee_contributions_simple .............. [6.1s]
Building dq_deferral_escalation_validation ............. [4.8s]
... (21 more models)

Total: 24 models × 5-7s avg = 120-168s sequential
With threading (÷3): 40-56s overhead
```

**What's happening:**
1. Each validation model **creates a table** in DuckDB
2. Data is **written to disk** (unnecessary I/O)
3. Transactions and materialization add overhead
4. Tables persist in database (clutters schema)
5. Must be manually cleaned up

**Example: dq_deferral_escalation_validation.sql**
```sql
{{ config(materialized='table', tags=['data_quality']) }}

WITH escalation_events AS (
    SELECT * FROM {{ ref('int_deferral_rate_escalation_events') }}
),
validation_failures AS (
    SELECT * FROM escalation_events
    WHERE escalation_amount > 0.01 OR new_deferral_rate > 0.10
)
SELECT * FROM validation_failures  -- Creates table (slow!)
```

**Runtime:** ~5 seconds per model × 24 models = **120s+ overhead**

---

### Desired State: Validation as Tests (Fast ✅)

```bash
# After conversion (dbt test)
$ dbt test --select tag:data_quality

Running test new_hire_match_validation ................ [PASS in 0.6s]
Running test employee_contributions_validation ........ [PASS in 0.7s]
Running test deferral_escalation_validation ........... [PASS in 0.5s]
... (21 more tests)

Total: 24 tests × 0.5-1s avg = 12-24s sequential
With threading (÷3): 4-8s overhead
```

**What happens:**
1. Test **executes query** (no table creation)
2. Result set checked: 0 rows = pass, >0 rows = fail
3. No disk I/O, minimal transaction overhead
4. Results discarded after validation
5. Clean database schema

**Example: tests/data_quality/test_deferral_escalation_validation.sql**
```sql
WITH escalation_events AS (
    SELECT * FROM {{ ref('int_deferral_rate_escalation_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
validation_failures AS (
    SELECT * FROM escalation_events
    WHERE escalation_amount > 0.01 OR new_deferral_rate > 0.10
)
SELECT * FROM validation_failures  -- Returns failures (fast!)
```

**Runtime:** ~0.5 seconds per test × 24 tests = **12s overhead** (90% faster!)

---

## Performance Impact Analysis

### Measured Performance (from E079 benchmarks)

| Configuration | Validation Models | Validation Tests | Savings |
|---------------|------------------|------------------|---------|
| **Sequential** | 195-273s | 20-39s | **155-234s** |
| **Threading (÷3)** | 65-91s | 7-13s | **55-77s** ✅ |
| **Per-model avg** | 5-7s | 0.5-1s | **4.5-6s** |

### Before/After Comparison (5-year simulation)

```
Current (with validation models):
├─ Foundation: 10s
├─ Event Generation: 130s
├─ State Accumulation: 35s
├─ ⚠️ VALIDATION: 65s (overhead!)
└─ Reporting: 5s
Total: 245s

After (with tests):
├─ Foundation: 10s
├─ Event Generation: 130s
├─ State Accumulation: 35s
├─ ✅ VALIDATION: 8s (optimized!)
└─ Reporting: 5s
Total: 188s (23% faster!)
```

---

## Goals & Success Criteria

### Primary Goals
1. ✅ Convert all 24 validation models to dbt tests
2. ✅ Achieve 55-77 second performance improvement
3. ✅ Maintain 100% validation logic parity
4. ✅ Zero false positives/negatives in test results

### Success Criteria
- [ ] **Performance**: Validation overhead reduced from 65-91s → 7-13s (90% improvement)
- [ ] **Correctness**: All tests pass/fail identically to previous models
- [ ] **Integration**: Tests integrate with Navigator Orchestrator pipeline
- [ ] **Documentation**: All tests documented with clear failure messages
- [ ] **Zero Regression**: No impact on simulation accuracy or determinism

### Key Metrics
- **Implementation time**: 4-6 hours
- **Performance improvement**: 55-77 seconds per simulation
- **ROI**: Pays for itself after ~4-5 simulation runs
- **Risk level**: Low (pure refactoring, no logic changes)

---

## Technical Approach

### Conversion Strategy

#### Pattern 1: Simple Validation → Test

**Before (Model):**
```sql
-- dbt/models/marts/data_quality/dq_xxx.sql
{{ config(materialized='table', tags=['data_quality']) }}

WITH source AS (SELECT * FROM {{ ref('fct_yearly_events') }}),
failures AS (
    SELECT * FROM source
    WHERE invalid_condition = true
)
SELECT * FROM failures
```

**After (Test):**
```sql
-- dbt/tests/data_quality/test_xxx.sql
WITH source AS (
    SELECT * FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}  -- Filter by year!
),
failures AS (
    SELECT * FROM source
    WHERE invalid_condition = true
)
SELECT * FROM failures  -- Returns failures for dbt to count
```

**Key changes:**
1. ✅ Remove `{{ config() }}`
2. ✅ Move file from `models/` to `tests/`
3. ✅ Add year filter for performance
4. ✅ Keep all validation logic identical

---

#### Pattern 2: Complex Multi-Table Validation → Test

**Before (Model):**
```sql
-- dbt/models/marts/data_quality/dq_multi_table.sql
{{ config(materialized='table') }}

WITH events AS (SELECT * FROM {{ ref('fct_yearly_events') }}),
snapshot AS (SELECT * FROM {{ ref('fct_workforce_snapshot') }}),
validation AS (
    SELECT e.*
    FROM events e
    LEFT JOIN snapshot s USING (employee_id)
    WHERE s.employee_id IS NULL  -- Orphan check
)
SELECT * FROM validation
```

**After (Test):**
```sql
-- dbt/tests/data_quality/test_orphaned_events.sql
WITH events AS (
    SELECT * FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
snapshot AS (
    SELECT * FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
validation AS (
    SELECT e.*
    FROM events e
    LEFT JOIN snapshot s USING (employee_id, simulation_year)
    WHERE s.employee_id IS NULL
)
SELECT * FROM validation
```

---

#### Pattern 3: Analysis Validation → Test

**Before (Model):**
```sql
-- dbt/models/analysis/validate_xxx.sql
{{ config(materialized='table', tags=['analysis']) }}

SELECT COUNT(*) as error_count
FROM {{ ref('int_baseline_workforce') }}
WHERE annual_compensation < 20000 OR annual_compensation > 500000
HAVING COUNT(*) > 0
```

**After (Test):**
```sql
-- dbt/tests/analysis/test_compensation_bounds.sql
SELECT *
FROM {{ ref('int_baseline_workforce') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND (annual_compensation < 20000 OR annual_compensation > 500000)
```

**Note:** Convert `HAVING COUNT(*) > 0` to return actual failing rows.

---

### Test Configuration

Create `dbt/tests/schema.yml` to configure test behavior:

```yaml
version: 2

tests:
  # Global test configuration
  +severity: warn  # Don't fail pipeline on validation errors
  +store_failures: true  # Store failures for debugging
  +schema: test_failures  # Schema for failure tables

  # Data quality tests
  - name: test_new_hire_match_validation
    description: "Validates new hire employer match calculations"
    config:
      severity: error  # Fail pipeline if this fails

  - name: test_deferral_escalation_validation
    description: "Validates deferral escalation increments"
    config:
      severity: warn
```

---

## Implementation Plan

### Phase 1: Audit & Inventory (30 minutes)

**Goal**: Identify all validation models and categorize by type

**Tasks**:
1. [ ] Run inventory query to list all validation models
2. [ ] Categorize models by validation type (data quality, analysis, monitoring)
3. [ ] Identify dependencies (which models reference which)
4. [ ] Prioritize by criticality (error vs warning vs info)
5. [ ] Document current runtime for each model (baseline)

**Deliverable**: `VALIDATION_INVENTORY.md` with complete list and categorization

**Commands**:
```bash
# List all validation models
find dbt/models -name "dq_*.sql" -o -name "validate_*.sql"

# Get model sizes
find dbt/models \( -name "dq_*.sql" -o -name "validate_*.sql" \) -exec wc -l {} +

# Check model dependencies
cd dbt && dbt ls --select tag:data_quality --resource-type model
```

---

### Phase 2: Create Test Infrastructure (1 hour)

**Goal**: Set up test directory structure and configuration

**Tasks**:
1. [ ] Create `dbt/tests/` directory structure:
   ```
   dbt/tests/
   ├── data_quality/          # Critical data quality tests
   ├── analysis/              # Analysis validations
   ├── intermediate/          # Intermediate model tests
   └── schema.yml            # Test configuration
   ```

2. [ ] Create test configuration template:
   ```yaml
   # dbt/tests/schema.yml
   version: 2
   tests:
     +severity: warn
     +store_failures: true
     +schema: test_failures
   ```

3. [ ] Create conversion script template:
   ```bash
   # scripts/convert_validation_to_test.sh
   #!/bin/bash
   # Converts a validation model to a test
   ```

4. [ ] Document test naming convention:
   ```
   Model: dq_xxx.sql → Test: test_xxx.sql
   Model: validate_xxx.sql → Test: test_xxx.sql
   ```

**Deliverable**: Complete test infrastructure ready for conversions

---

### Phase 3: Convert Critical Validations (1 hour)

**Goal**: Convert high-priority data quality validations first

**Priority List** (must not fail in production):
1. [ ] `dq_new_hire_match_validation.sql` → `test_new_hire_match_validation.sql`
2. [ ] `dq_new_hire_core_proration_validation.sql` → `test_new_hire_core_proration.sql`
3. [ ] `dq_e057_new_hire_termination_validation.sql` → `test_new_hire_termination.sql`
4. [ ] `dq_employee_contributions_simple.sql` → `test_employee_contributions.sql`
5. [ ] `dq_deferral_escalation_validation.sql` → `test_deferral_escalation.sql`

**Conversion Checklist** (per model):
- [ ] Copy model SQL to `dbt/tests/data_quality/`
- [ ] Remove `{{ config() }}` block
- [ ] Add `WHERE simulation_year = {{ var('simulation_year') }}`
- [ ] Rename file: `dq_xxx.sql` → `test_xxx.sql`
- [ ] Run test: `dbt test --select test_xxx`
- [ ] Compare results with old model
- [ ] Document test in `schema.yml`
- [ ] Delete old model file

**Validation Command**:
```bash
# Run both old model and new test, compare results
dbt run --select dq_new_hire_match_validation
dbt test --select test_new_hire_match_validation

# Query both and compare
duckdb dbt/simulation.duckdb "
SELECT 'model' as source, COUNT(*) FROM dq_new_hire_match_validation
UNION ALL
SELECT 'test', COUNT(*) FROM test_failures.test_new_hire_match_validation
"
```

---

### Phase 4: Convert Data Quality Checks (1 hour)

**Goal**: Convert remaining data quality validations

**Models to Convert**:
1. [ ] `dq_deferral_rate_state_audit_validation.sql` → `test_deferral_state_audit.sql`
2. [ ] `dq_deferral_rate_state_audit_validation_v2.sql` → `test_deferral_state_audit_v2.sql`
3. [ ] `dq_integrity_violations.sql` → `test_integrity_violations.sql`
4. [ ] `dq_integrity_summary.sql` → `test_integrity_summary.sql`
5. [ ] `dq_violation_details.sql` → `test_violation_details.sql`
6. [ ] `dq_compliance_monitoring.sql` → `test_compliance_monitoring.sql`
7. [ ] `dq_contribution_audit_trail.sql` → `test_contribution_audit.sql`
8. [ ] `dq_executive_dashboard.sql` → Test not needed (reporting model, not validation)
9. [ ] `dq_performance_monitoring.sql` → Test not needed (metrics model, not validation)

**Note**: Some "dq_" models may be dashboards/reports, not validations. Keep those as models.

---

### Phase 5: Convert Analysis Validations (1 hour)

**Goal**: Convert analysis and intermediate validations

**Models to Convert**:

**Analysis Layer**:
1. [ ] `validate_compensation_bounds.sql` → `test_compensation_bounds.sql`
2. [ ] `validate_deferral_rate_source_of_truth_v2.sql` → `test_deferral_source_of_truth.sql`
3. [ ] `validate_e058_business_logic.sql` → `test_e058_business_logic.sql`
4. [ ] `validate_enrollment_continuity.sql` → `test_enrollment_continuity.sql`
5. [ ] `validate_escalation_bug_fix.sql` → `test_escalation_bug_fix.sql`
6. [ ] `validate_opt_out_rates.sql` → `test_opt_out_rates.sql`

**Intermediate Layer**:
1. [ ] `validate_enrollment_deferral_consistency_v2.sql` → `test_enrollment_deferral_consistency.sql`
2. [ ] `validate_s042_01_source_of_truth_fix.sql` → `test_s042_source_of_truth.sql`

**Marts Layer**:
1. [ ] `validate_deferral_rate_orphaned_states.sql` → `test_deferral_orphaned_states.sql`
2. [ ] `validate_deferral_rate_state_continuity.sql` → `test_deferral_state_continuity.sql`

---

### Phase 6: Integration Testing (30 minutes)

**Goal**: Ensure tests integrate with Navigator Orchestrator pipeline

**Tasks**:
1. [ ] Run full simulation with tests:
   ```bash
   planwise simulate 2025-2027 --verbose
   ```

2. [ ] Verify test execution in pipeline logs:
   ```bash
   grep "Running test" artifacts/runs/*/run.log
   ```

3. [ ] Check test pass/fail rates:
   ```bash
   dbt test --select tag:data_quality
   ```

4. [ ] Validate test results stored properly:
   ```sql
   SELECT * FROM test_failures.information_schema.tables
   ```

5. [ ] Test failure scenarios:
   ```bash
   # Inject known error, verify test catches it
   dbt test --select test_new_hire_match_validation
   ```

**Integration Checklist**:
- [ ] Tests run automatically in VALIDATION stage
- [ ] Test failures don't block pipeline (severity: warn)
- [ ] Test results logged to artifacts
- [ ] Failed test details stored in `test_failures` schema
- [ ] Navigator Orchestrator reports test summary

---

### Phase 7: Performance Benchmarking (30 minutes)

**Goal**: Measure actual performance improvement

**Benchmark Plan**:
```bash
# 1. Baseline with validation models (before)
time planwise simulate 2025-2027

# 2. After conversion to tests
time planwise simulate 2025-2027

# 3. Extract validation timing
grep "stage:validation" artifacts/runs/*/performance.json
```

**Expected Results**:
```json
{
  "before": {
    "validation_stage_duration_s": 65.2,
    "total_duration_s": 198.9
  },
  "after": {
    "validation_stage_duration_s": 8.1,
    "total_duration_s": 141.8,
    "improvement_s": 57.1,
    "improvement_pct": 28.7
  }
}
```

**Success Criteria**:
- ✅ Validation stage: 65s → 8s (87% faster)
- ✅ Total simulation: 199s → 142s (28% faster)
- ✅ Savings: 55-77 seconds achieved

---

### Phase 8: Cleanup & Documentation (30 minutes)

**Goal**: Remove old models, update documentation

**Tasks**:
1. [ ] Delete converted validation models:
   ```bash
   # After verifying tests work
   rm dbt/models/marts/data_quality/dq_*.sql
   rm dbt/models/analysis/validate_*.sql
   ```

2. [ ] Update `dbt_project.yml`:
   ```yaml
   # Remove data_quality model configs
   models:
     planwise_navigator:
       marts:
         data_quality:  # DELETE THIS SECTION
   ```

3. [ ] Update CLAUDE.md documentation:
   ```markdown
   ## Data Quality Framework

   ### Validation Tests (NEW!)
   All data quality validations run as dbt tests:
   - `dbt test --select tag:data_quality`
   - Tests execute without materializing tables
   - 90% faster than previous validation models
   ```

4. [ ] Create migration guide:
   ```markdown
   # MIGRATION_GUIDE.md

   ## Validation Models → Tests
   All dq_* models converted to tests...
   ```

5. [ ] Update pipeline stage documentation

---

## Testing Strategy

### Validation Approach

#### Level 1: SQL Logic Parity
Ensure converted tests return identical results to original models.

**Validation Query**:
```sql
-- Compare old model results with new test results
WITH model_results AS (
    SELECT employee_id, issue_type, issue_description
    FROM dq_new_hire_match_validation
    WHERE simulation_year = 2025
),
test_results AS (
    SELECT employee_id, issue_type, issue_description
    FROM test_failures.test_new_hire_match_validation
    WHERE simulation_year = 2025
)
SELECT
    'Only in model' as difference,
    COUNT(*) as count
FROM model_results
WHERE employee_id NOT IN (SELECT employee_id FROM test_results)
UNION ALL
SELECT
    'Only in test',
    COUNT(*)
FROM test_results
WHERE employee_id NOT IN (SELECT employee_id FROM model_results)
UNION ALL
SELECT
    'In both (correct)',
    COUNT(*)
FROM model_results m
INNER JOIN test_results t USING (employee_id, issue_type)
```

**Expected Result**: Only "In both (correct)" with count > 0

---

#### Level 2: Integration Testing
Verify tests integrate with pipeline execution.

**Test Cases**:
1. **Happy Path**: All tests pass
   ```bash
   planwise simulate 2025 --verbose
   # Expected: All tests PASS, no pipeline errors
   ```

2. **Failure Path**: Inject known error
   ```sql
   -- Temporarily break data to test failure detection
   UPDATE fct_yearly_events
   SET compensation_amount = -999999
   WHERE event_type = 'hire' LIMIT 1
   ```
   ```bash
   dbt test --select test_compensation_bounds
   # Expected: Test FAILS with descriptive error
   ```

3. **Performance Path**: Measure timing
   ```bash
   time dbt test --select tag:data_quality
   # Expected: <10 seconds for all tests
   ```

---

#### Level 3: Regression Testing
Ensure no impact on simulation results.

**Test Procedure**:
```bash
# 1. Run full simulation with old models
planwise simulate 2025-2027 > baseline_results.txt

# 2. Convert to tests
# (implementation)

# 3. Run full simulation with tests
planwise simulate 2025-2027 > new_results.txt

# 4. Compare simulation outputs
diff baseline_results.txt new_results.txt
# Expected: ZERO differences in workforce, events, or metrics
```

**Regression Checklist**:
- [ ] Workforce counts identical
- [ ] Event counts identical
- [ ] Termination/hire/promotion numbers unchanged
- [ ] CAGR matches baseline (3.0%)
- [ ] Random seed produces identical results

---

## Rollback Plan

### Immediate Rollback (< 5 minutes)

If tests fail in production, immediately revert to validation models:

```bash
# 1. Restore validation models from git
git checkout HEAD~1 -- dbt/models/marts/data_quality/
git checkout HEAD~1 -- dbt/models/analysis/validate_*.sql

# 2. Remove tests
rm -rf dbt/tests/data_quality/
rm -rf dbt/tests/analysis/

# 3. Rebuild models
cd dbt && dbt run --select tag:data_quality

# 4. Resume normal operations
planwise simulate 2025-2027
```

**Rollback Triggers**:
- ❌ Tests produce different results than models
- ❌ Tests cause pipeline failures
- ❌ Performance degrades instead of improves
- ❌ Tests don't integrate with Navigator Orchestrator

---

### Partial Rollback (10 minutes)

If specific tests fail, revert only those:

```bash
# Revert specific validation
git checkout HEAD~1 -- dbt/models/marts/data_quality/dq_xxx.sql
rm dbt/tests/data_quality/test_xxx.sql

# Rebuild just that model
cd dbt && dbt run --select dq_xxx
```

---

## Risks & Mitigations

### Risk 1: Test Logic Divergence

**Risk**: Converted tests might not match original model logic
**Probability**: Low
**Impact**: High (false positives/negatives)

**Mitigation**:
- ✅ Copy SQL logic verbatim (no changes)
- ✅ Run side-by-side comparison before deleting models
- ✅ Keep models for 1 week after conversion for validation
- ✅ Automated regression testing in CI/CD

---

### Risk 2: Performance Degradation

**Risk**: Tests might run slower than expected
**Probability**: Very Low
**Impact**: Medium

**Mitigation**:
- ✅ Benchmark before/after conversion
- ✅ Add year filters to all test queries
- ✅ Monitor test execution times
- ✅ Rollback if performance regresses

---

### Risk 3: Pipeline Integration Failure

**Risk**: Tests might not integrate with Navigator Orchestrator
**Probability**: Low
**Impact**: Medium

**Mitigation**:
- ✅ Test integration in development first
- ✅ Run full simulation with tests before deleting models
- ✅ Configure test severity properly (warn vs error)
- ✅ Ensure test failures don't block pipeline

---

### Risk 4: Lost Validation Context

**Risk**: Test failures might be harder to debug than model output
**Probability**: Low
**Impact**: Low

**Mitigation**:
- ✅ Configure `store_failures: true` for all tests
- ✅ Add descriptive failure messages in test SQL
- ✅ Document test purpose in schema.yml
- ✅ Create debugging queries for common failures

---

## Appendix A: Complete Inventory

### Validation Models to Convert (24 total)

#### Analysis Layer (6 models)
1. `validate_compensation_bounds.sql` - 45 lines
2. `validate_deferral_rate_source_of_truth_v2.sql` - 132 lines
3. `validate_e058_business_logic.sql` - 87 lines
4. `validate_enrollment_continuity.sql` - 198 lines
5. `validate_escalation_bug_fix.sql` - 76 lines
6. `validate_opt_out_rates.sql` - 54 lines

#### Data Quality Layer (3 models)
1. `dq_integrity_summary.sql` - 245 lines
2. `dq_integrity_violations.sql` - 312 lines
3. `dq_violation_details.sql` - 178 lines

#### Intermediate Layer (2 models)
1. `validate_enrollment_deferral_consistency_v2.sql` - 89 lines
2. `validate_s042_01_source_of_truth_fix.sql` - 123 lines

#### Marts Data Quality Layer (13 models)
1. `dq_compliance_monitoring.sql` - 567 lines (⚠️ May be dashboard, not validation)
2. `dq_contribution_audit_trail.sql` - 489 lines (⚠️ May be dashboard, not validation)
3. `dq_deferral_escalation_validation.sql` - 112 lines
4. `dq_deferral_rate_state_audit_validation.sql` - 398 lines
5. `dq_deferral_rate_state_audit_validation_v2.sql` - 287 lines
6. `dq_e057_new_hire_termination_validation.sql` - 445 lines
7. `dq_employee_contributions_simple.sql` - 234 lines
8. `dq_executive_dashboard.sql` - 678 lines (⚠️ Dashboard, NOT validation - keep as model)
9. `dq_new_hire_core_proration_validation.sql` - 389 lines
10. `dq_new_hire_match_validation.sql` - 276 lines
11. `dq_performance_monitoring.sql` - 534 lines (⚠️ Metrics, NOT validation - keep as model)
12. `validate_deferral_rate_orphaned_states.sql` - 156 lines
13. `validate_deferral_rate_state_continuity.sql` - 201 lines

**Total Lines**: ~5,459 lines of validation SQL

**Models to Keep** (not validations):
- `dq_executive_dashboard.sql` - Reporting dashboard
- `dq_performance_monitoring.sql` - Metrics collection
- *(Possibly)* `dq_compliance_monitoring.sql` - May be dashboard
- *(Possibly)* `dq_contribution_audit_trail.sql` - May be audit log

**Net Conversion**: ~20-22 models → tests

---

## Appendix B: Conversion Script

```bash
#!/bin/bash
# scripts/convert_validation_to_test.sh
#
# Converts a validation model to a dbt test
# Usage: ./convert_validation_to_test.sh dbt/models/marts/data_quality/dq_xxx.sql

set -e

MODEL_PATH="$1"
MODEL_NAME=$(basename "$MODEL_PATH" .sql)

# Determine target directory based on source
if [[ "$MODEL_PATH" == *"/analysis/"* ]]; then
    TARGET_DIR="dbt/tests/analysis"
elif [[ "$MODEL_PATH" == *"/data_quality/"* ]]; then
    TARGET_DIR="dbt/tests/data_quality"
elif [[ "$MODEL_PATH" == *"/intermediate/"* ]]; then
    TARGET_DIR="dbt/tests/intermediate"
else
    TARGET_DIR="dbt/tests/marts"
fi

# Create target directory
mkdir -p "$TARGET_DIR"

# Determine test name
if [[ "$MODEL_NAME" == dq_* ]]; then
    TEST_NAME="test_${MODEL_NAME#dq_}"
elif [[ "$MODEL_NAME" == validate_* ]]; then
    TEST_NAME="test_${MODEL_NAME#validate_}"
else
    TEST_NAME="test_$MODEL_NAME"
fi

TARGET_PATH="$TARGET_DIR/${TEST_NAME}.sql"

echo "Converting $MODEL_NAME → $TEST_NAME"
echo "  Source: $MODEL_PATH"
echo "  Target: $TARGET_PATH"

# Copy file, removing config block
grep -v "{{ config(" "$MODEL_PATH" | \
grep -v "materialized=" | \
grep -v "tags=" | \
grep -v ")}}" > "$TARGET_PATH"

# Add year filter comment at top
sed -i '' '1i\
-- Converted from validation model to test\
-- Added simulation_year filter for performance\
' "$TARGET_PATH"

echo "✅ Conversion complete!"
echo ""
echo "Next steps:"
echo "  1. Review $TARGET_PATH"
echo "  2. Add year filter: WHERE simulation_year = {{ var('simulation_year') }}"
echo "  3. Test: dbt test --select $TEST_NAME"
echo "  4. Validate: Compare results with original model"
echo "  5. Delete: rm $MODEL_PATH"
```

---

## Appendix C: Validation Query Library

### Query 1: Compare Model vs Test Results

```sql
-- Compare old model output with new test output
WITH model_failures AS (
    SELECT
        employee_id,
        issue_type,
        issue_description,
        'model' as source
    FROM {{ old_model_name }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
test_failures AS (
    SELECT
        employee_id,
        issue_type,
        issue_description,
        'test' as source
    FROM test_failures.{{ test_name }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
comparison AS (
    SELECT
        COALESCE(m.employee_id, t.employee_id) as employee_id,
        COALESCE(m.issue_type, t.issue_type) as issue_type,
        m.source as in_model,
        t.source as in_test,
        CASE
            WHEN m.employee_id IS NOT NULL AND t.employee_id IS NOT NULL THEN 'MATCH'
            WHEN m.employee_id IS NOT NULL THEN 'MODEL_ONLY'
            ELSE 'TEST_ONLY'
        END as match_status
    FROM model_failures m
    FULL OUTER JOIN test_failures t
        ON m.employee_id = t.employee_id
        AND m.issue_type = t.issue_type
)
SELECT
    match_status,
    COUNT(*) as count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as pct
FROM comparison
GROUP BY match_status
ORDER BY count DESC
```

**Expected Result**: 100% in 'MATCH' status

---

### Query 2: Test Performance Analysis

```sql
-- Measure test execution performance
SELECT
    test_name,
    execution_time_s,
    rows_returned,
    test_status,
    CASE
        WHEN execution_time_s < 1 THEN 'EXCELLENT'
        WHEN execution_time_s < 2 THEN 'GOOD'
        WHEN execution_time_s < 5 THEN 'ACCEPTABLE'
        ELSE 'NEEDS_OPTIMIZATION'
    END as performance_rating
FROM test_execution_log
WHERE test_run_date = CURRENT_DATE
ORDER BY execution_time_s DESC
```

---

### Query 3: Validation Coverage Report

```sql
-- Report on validation test coverage
SELECT
    'Total validation models' as metric,
    COUNT(*) as value
FROM information_schema.tables
WHERE table_schema = 'main'
  AND (table_name LIKE 'dq_%' OR table_name LIKE 'validate_%')

UNION ALL

SELECT
    'Converted to tests',
    COUNT(*)
FROM information_schema.tables
WHERE table_schema = 'test_failures'

UNION ALL

SELECT
    'Remaining models',
    (SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = 'main'
       AND (table_name LIKE 'dq_%' OR table_name LIKE 'validate_%'))
    -
    (SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = 'test_failures')
```

---

## Appendix D: Test Configuration Templates

### Template 1: Basic Data Quality Test

```yaml
# dbt/tests/schema.yml
version: 2

tests:
  - name: test_{{ validation_name }}
    description: |
      Validates {{ description }}

      **Failure Condition**: {{ failure_condition }}
      **Severity**: {{ error|warn|info }}
      **Owner**: {{ team_name }}

    config:
      severity: {{ error|warn }}
      store_failures: true
      fail_calc: count(*)
      error_if: ">= 1"  # Fail if any violations found
      warn_if: ">= 1"   # Warn if any violations found
```

### Template 2: Critical Validation Test

```yaml
tests:
  - name: test_new_hire_match_validation
    description: |
      **CRITICAL**: Validates new hire employer match calculations

      Ensures new hires receive properly prorated match based on
      partial year employment, not full annual compensation.

      **Failure Modes**:
      - Match > 3% of prorated compensation
      - Match percentage doesn't align with deferral rate
      - Duplicate employee records

      **Impact**: Financial accuracy, IRS compliance
      **Owner**: Compensation Engine Team

    config:
      severity: error  # FAIL PIPELINE if this test fails
      store_failures: true
      tags: ['critical', 'financial', 'compliance']
```

### Template 3: Analysis Validation Test

```yaml
tests:
  - name: test_compensation_bounds
    description: |
      Validates employee compensation within reasonable bounds

      **Bounds**:
      - Minimum: $20,000 annual
      - Maximum: $500,000 annual

      **Note**: This is a data quality check, not a hard constraint.
      Legitimate executives may exceed upper bound.

    config:
      severity: warn  # Don't fail pipeline
      store_failures: true
      tags: ['data_quality', 'analysis']
```

---

## Success Metrics Dashboard

Track implementation progress and performance impact:

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| **Models Converted** | 24 | 0 | 🟡 Not Started |
| **Tests Created** | 24 | 0 | 🟡 Not Started |
| **Validation Time (s)** | 7-13s | 65-91s | 🟡 Not Started |
| **Total Sim Time (s)** | 140-150s | 198s | 🟡 Not Started |
| **Performance Gain** | 55-77s | 0s | 🟡 Not Started |
| **Test Pass Rate** | 100% | - | 🟡 Not Started |
| **Logic Parity** | 100% | - | 🟡 Not Started |

**Update this dashboard** after each phase to track progress!

---

## Next Steps

### Immediate Actions (Start Implementation)
1. [ ] Review this epic document
2. [ ] Create implementation branch: `feature/e080-validation-to-test`
3. [ ] Run Phase 1 audit to confirm scope
4. [ ] Set up test infrastructure (Phase 2)
5. [ ] Convert first test as proof of concept
6. [ ] Validate proof of concept results
7. [ ] Continue with remaining conversions

### Success Checkpoints
- ✅ **Phase 1 Complete**: All 24 models identified and prioritized
- ✅ **Phase 2 Complete**: Test infrastructure created
- ✅ **Phase 3 Complete**: 5 critical validations converted
- ✅ **Phase 4 Complete**: All data quality checks converted
- ✅ **Phase 5 Complete**: All analysis validations converted
- ✅ **Phase 6 Complete**: Integration tests pass
- ✅ **Phase 7 Complete**: Performance targets achieved (55-77s savings)
- ✅ **Phase 8 Complete**: Cleanup finished, documentation updated

### Definition of Done
- [ ] All 24 validation models converted to tests
- [ ] All tests passing in development environment
- [ ] Performance improvement measured: 55-77s savings confirmed
- [ ] Integration with Navigator Orchestrator validated
- [ ] Regression testing shows zero impact on simulation results
- [ ] Documentation updated (CLAUDE.md, README.md)
- [ ] Old validation models deleted
- [ ] Epic marked complete with performance report

---

**Document Version**: 1.0
**Last Updated**: 2025-11-06
**Status**: Ready for Implementation
**Estimated Completion**: 2025-11-08 (2 days)
**Expected ROI**: Pays for itself after 4-5 simulation runs
