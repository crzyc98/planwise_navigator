# Epic E078: Complete Polars Mode Integration

## 🎯 Epic Overview

**Problem Statement**: Polars event generation works and produces Parquet files successfully, but approximately 10 intermediate dbt models still reference event-specific models (`int_enrollment_events`, `int_hiring_events`, `int_employer_eligibility`) that don't exist when Polars mode is enabled. These models need to be updated to read from `fct_yearly_events` instead.

**Discovery Context**: This epic was scoped after hands-on debugging of Polars mode revealed that:
1. ✅ Polars event generation already works (`EventGenerationExecutor` creates Parquet files)
2. ✅ `fct_yearly_events` already reads Polars Parquet files (Polars mode support confirmed)
3. ✅ Pattern for fixing models is proven (updated 2 models successfully)
4. ❌ ~10 intermediate models still use old references

**Current State** (October 2025):
- ✅ Polars event generation creates Parquet files successfully
- ✅ `fct_yearly_events` has full Polars mode support (`event_mode == 'polars'`)
- ✅ `int_enrollment_state_accumulator.sql` - **FIXED** (reads from `fct_yearly_events`)
- ✅ `int_deferral_rate_state_accumulator_v2.sql` - **FIXED** (reads from `fct_yearly_events`)
- ❌ `int_employer_core_contributions.sql` - references `int_employer_eligibility` (in `eligibility_check` CTE)
- ❌ Estimated 5-8 additional models need updates (E078-01 will determine exact count)
- ⚙️ Polars mode **temporarily disabled** in config to maintain system stability

**Target State**:
- ✅ All intermediate models read from `fct_yearly_events` with event_type filters
- ✅ Polars mode can be enabled without breaking the pipeline
- ✅ Multi-year simulation works in both SQL and Polars modes
- ✅ **Runtime improvement**: Achieve ≥2× performance improvement (estimated 2-5× faster)
- ✅ **100% backward compatibility** - SQL mode continues to work unchanged

**Business Impact**:
- **Performance**: Unlock Polars performance benefits for faster scenario planning
- **Flexibility**: Teams can choose SQL mode (stability) or Polars mode (speed)
- **Consumer Impact**: If you already use `fct_yearly_events`, nothing changes; performance improves automatically

**Implementation Timeline**: 1 day (6-8 hours focused work)

---

## 📋 Data Contract

**Single Interface**: All downstream models read from `fct_yearly_events` with `event_type` and `simulation_year` filters. No references to `int_*_events` or `int_employer_eligibility`.

**Required Columns**: `simulation_year`, `employee_id`, `event_type`, `event_timestamp`, plus domain-specific fields used by downstream models (e.g., `eligible_for_core`, `annual_compensation`, `enrollment_date`).

**Event Types**: `hire`, `termination`, `promotion`, `raise`, `enrollment`, `enrollment_change`, `eligibility_determination`.

**Partitioning**: Events are written under `data/parquet/events/simulation_year=YYYY/` in Polars mode.

---

## ✅ Acceptance Criteria

1. **Zero Legacy References**: No remaining references to `int_*_events` or `int_employer_eligibility` in intermediate models
2. **Polars Mode Works**: End-to-end simulation (2025-2027) completes with zero errors in Polars mode
3. **Data Parity**: Row counts by `simulation_year × event_type` match within 2% vs. SQL mode (looser tolerance acceptable for event counts; strict parity expected for financial metrics)
4. **Performance**: ≥2× faster for standard 3-year run compared to SQL mode
5. **Escape Hatch**: SQL mode toggle works instantly if issues arise

**Operational Validation**:
- ✅ Parquet files exist for all simulated years under `data/parquet/events/simulation_year=YYYY/`
- ✅ Total employer core contributions within 0.5% tolerance vs. SQL mode (financial precision)

---

## 🔍 Root Cause Analysis

### What We Discovered During Debugging

**The Pipeline Already Works (Mostly)**:
```
Year N-1 Snapshot
    ↓
int_workforce_needs (algebraic solver)
    ↓
[PYTHON] EventGenerationExecutor
    ↓
data/parquet/events/simulation_year=2025/events_2025.parquet ← Polars writes here
    ↓
fct_yearly_events.sql (reads Parquet when event_mode='polars') ← This already works!
    ↓
❌ BREAKS HERE: Some models still try to read int_enrollment_events (doesn't exist)
```

**The Real Problem**:
When `event_mode = 'polars'`, the SQL event models (`int_enrollment_events`, `int_hiring_events`, etc.) are **skipped entirely**. Downstream models that reference these tables fail with "table does not exist" errors.

**The Solution Pattern** (Already Proven):
```sql
-- ❌ OLD (SQL-only):
FROM {{ ref('int_enrollment_events') }}

-- ✅ NEW (both SQL and Polars):
FROM {{ ref('fct_yearly_events') }}
WHERE event_type IN ('enrollment', 'enrollment_change')
  AND simulation_year = {{ var('simulation_year') }}
```

**Why This Works**:
- `fct_yearly_events` exists in **both** SQL and Polars modes
- SQL mode: `fct_yearly_events` = UNION ALL of `int_*_events` models
- Polars mode: `fct_yearly_events` = `read_parquet(...)` from event files
- Schema is identical in both modes

---

## 📋 Implementation Stories

### **Story E078-01: Identify All Models Needing Updates**
**Priority**: P0 (Foundation)
**Effort**: 1 hour

**Description**: Create a checkbox list of all models that reference intermediate event tables or eligibility tables, noting the event types each model needs.

**Implementation**:

```bash
# 1. Find models referencing intermediate event tables
rg "ref\('int_.*_events'\)" dbt/models/ -g "*.sql"

# 2. Find models referencing eligibility tables
rg "ref\('int_employer_eligibility'\)" dbt/models/ -g "*.sql"

# 3. For each model, identify the CTE/section and required event types
```

**Deliverable**:

Create `docs/epics/E078_model_updates_checklist.md`:
```markdown
# E078 Model Update Checklist

## Already Fixed (Before E078)
- ✅ int_enrollment_state_accumulator.sql → event_type IN ('enrollment', 'enrollment_change')
- ✅ int_deferral_rate_state_accumulator_v2.sql → event_type IN ('enrollment', 'enrollment_change')

## Identified During E078-01
- ❌ int_employer_core_contributions.sql (eligibility_check CTE) → event_type = 'eligibility_determination'
- ❌ [Model name] ([CTE name]) → event_type = '[type]'
- ❌ [Model name] ([CTE name]) → event_type IN ('[type1]', '[type2]')

## Pattern
Replace: `FROM {{ ref('int_*_events') }}` or `FROM {{ ref('int_employer_eligibility') }}`
With: `FROM {{ ref('fct_yearly_events') }} WHERE event_type = '...' AND simulation_year = {{ var('simulation_year') }}`
```

**Acceptance Criteria**:
- ✅ Checkbox list created with model name + CTE/section + required event types
- ✅ One line per model, no line number references
- ✅ Event type mapping documented for each model

**Files Created**:
- `docs/epics/E078_model_updates_checklist.md` (NEW)

---

### **Story E078-02: Update Models to Use fct_yearly_events Pattern**
**Priority**: P0 (Critical Path)
**Effort**: 3-4 hours

**Description**: Apply the proven `fct_yearly_events` pattern to all models identified in S078-01.

**Implementation Pattern** (Proven from prior fixes):

```sql
-- Example: int_employer_core_contributions.sql

-- BEFORE (line 172):
eligibility_check AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_for_core,
        eligible_for_contributions,
        annual_hours_worked
    FROM {{ ref('int_employer_eligibility') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
),

-- AFTER:
eligibility_check AS (
    SELECT
        employee_id,
        simulation_year,
        eligible_for_core,
        eligible_for_contributions,
        annual_hours_worked
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND event_type = 'eligibility_determination'  -- Add event type filter
        AND employee_id IS NOT NULL
),
```

**For Each Model**:

1. **Read the current model** to understand context
2. **Identify the int_*_events reference**
3. **Determine the appropriate event_type filter**:
   - `int_enrollment_events` → `WHERE event_type IN ('enrollment', 'enrollment_change')`
   - `int_hiring_events` → `WHERE event_type = 'hire'`
   - `int_termination_events` → `WHERE event_type = 'termination'`
   - `int_promotion_events` → `WHERE event_type = 'promotion'`
   - `int_merit_events` → `WHERE event_type = 'raise'` (or `merit` if exists)
   - `int_employer_eligibility` → `WHERE event_type = 'eligibility_determination'`
4. **Update the SQL** with the new pattern
5. **Test the model individually**:
   ```bash
   cd dbt
   dbt run --select <model_name> --vars "simulation_year: 2025" --threads 1
   ```
6. **Update checklist** with ✅ status

**Event Type Reference** (from fct_yearly_events schema):
```sql
-- Common event types in fct_yearly_events:
-- - 'hire'
-- - 'termination'
-- - 'promotion'
-- - 'raise' (includes COLA and merit)
-- - 'enrollment'
-- - 'enrollment_change'
-- - 'eligibility_determination' (if tracked)
```

**Acceptance Criteria**:
- ✅ All models in checklist updated to use `fct_yearly_events`
- ✅ Each model tested individually with `dbt run --select <model_name> --vars "simulation_year: 2025" --threads 1`
- ✅ Zero references to `int_*_events` or `int_employer_eligibility` remain
- ✅ Checklist updated with ✅ for each completed model

**Files Modified**:
- `dbt/models/intermediate/int_employer_core_contributions.sql`
- `dbt/models/intermediate/<additional models from E078-01>`
- `docs/epics/E078_model_updates_checklist.md` (status updates)

---

### **Story E078-03: Re-enable Polars Mode and Integration Test**
**Priority**: P0 (Validation)
**Effort**: 2 hours

**Description**: Re-enable Polars mode in the configuration and run comprehensive multi-year simulation tests.

**Implementation**:

1. **Update configuration** (`config/simulation_config.yaml`):
```yaml
# Line 410: Re-enable Polars mode
event_generation:
  mode: "polars"  # Changed from "sql" - E078 POLARS MODE RE-ENABLED

  # Polars-specific configuration
  polars:
    enabled: true  # Changed from false - E078 POLARS MODE RE-ENABLED
    max_threads: 16
    batch_size: 10000
    output_path: "data/parquet/events"
    enable_compression: true
    # ... rest of config unchanged
```

2. **Clean database for fresh test**:
```bash
# IMPORTANT: Verify you're in a sandbox/test environment before deleting the database
# The database will be recreated during simulation, but any manual work will be lost
rm dbt/simulation.duckdb
```

3. **Run single-year test**:
```bash
planwise simulate 2025
```

**Expected Output**:
```
✅ Polars event generation creates Parquet file
✅ fct_yearly_events loads from Parquet
✅ All intermediate models run without errors
✅ fct_workforce_snapshot builds successfully
✅ Simulation completes
```

4. **Run multi-year test**:
```bash
planwise simulate 2025-2027
```

**Parity Check** (compare Polars vs SQL mode):
```bash
# 1. Run SQL mode baseline
# Update config to mode: "sql", enabled: false
rm dbt/simulation.duckdb
time planwise simulate 2025-2027

# Capture SQL mode metrics
duckdb dbt/simulation.duckdb "
SELECT simulation_year, event_type, COUNT(*) as count
FROM fct_yearly_events
GROUP BY simulation_year, event_type
ORDER BY simulation_year, event_type
" > sql_mode_events.txt

duckdb dbt/simulation.duckdb "
SELECT SUM(employer_core_contribution) as total_core
FROM fct_workforce_snapshot
WHERE simulation_year IN (2025, 2026, 2027)
" > sql_mode_core.txt

# 2. Run Polars mode
# Update config to mode: "polars", enabled: true
rm dbt/simulation.duckdb
time planwise simulate 2025-2027

# Capture Polars mode metrics
duckdb dbt/simulation.duckdb "
SELECT simulation_year, event_type, COUNT(*) as count
FROM fct_yearly_events
GROUP BY simulation_year, event_type
ORDER BY simulation_year, event_type
" > polars_mode_events.txt

duckdb dbt/simulation.duckdb "
SELECT SUM(employer_core_contribution) as total_core
FROM fct_workforce_snapshot
WHERE simulation_year IN (2025, 2026, 2027)
" > polars_mode_core.txt

# 3. Compare results (manually verify within 5% tolerance)
```

**Acceptance Criteria**:
- ✅ Multi-year simulation (2025-2027) completes with zero errors in Polars mode
- ✅ Event counts by `simulation_year × event_type` within 2% tolerance vs. SQL mode
- ✅ Total employer core contributions within 0.5% tolerance vs. SQL mode
- ✅ Performance: ≥2× faster wall-time for Polars mode (measured with `time` command)
- ✅ Parquet files exist under `data/parquet/events/simulation_year=YYYY/`

**Files Modified**:
- `config/simulation_config.yaml` (re-enable Polars mode)

---

### **Story E078-04: Documentation and Validation**
**Priority**: P1 (Documentation)
**Effort**: 30 minutes

**Description**: Add minimal Polars mode documentation to CLAUDE.md.

**Implementation**:

1. **Update CLAUDE.md** with Polars mode section:

Add to Development Workflow section:

```markdown
### **Polars Mode (High Performance)**

Polars mode uses vectorized event generation for 2-5× performance improvement.

**Enable Polars Mode**:
```yaml
# config/simulation_config.yaml
event_generation:
  mode: "polars"
  polars:
    enabled: true
```

**Run Simulation**:
```bash
planwise simulate 2025-2027
```

**Disable Polars Mode** (revert to SQL):
```yaml
event_generation:
  mode: "sql"
  polars:
    enabled: false
```

**Verify Active**:
- Check for Parquet files: `ls data/parquet/events/simulation_year=2025/`
- If issues arise, toggle back to SQL mode
```

2. **Record performance metrics in epic completion summary**

**Acceptance Criteria**:
- ✅ CLAUDE.md updated with Polars mode section
- ✅ Performance metrics recorded (SQL vs Polars wall-time)
- ✅ Epic marked complete with lean summary

**Files Modified**:
- `CLAUDE.md` (Polars mode documentation)
- `docs/epics/E078_cohort_pipeline_integration.md` (completion summary)

---

## 🎯 Success Metrics

| Metric | Baseline (SQL Mode) | Target (Polars Mode) | Measurement Method | Actual |
|--------|--------------------|--------------------|-------------------|--------|
| **3-Year Runtime** | ~2 minutes | <1 minute | `time planwise simulate 2025-2027` | TBD |
| **Performance Improvement** | 1× | 2-5× | Compare wall-time (SQL vs Polars) | TBD |
| **Model Updates Required** | N/A | ~10 models | Count files modified in E078-02 | TBD |
| **Backward Compatibility** | N/A | 100% (SQL mode still works) | Run SQL mode after Polars validation | TBD |
| **Event Count Parity** | N/A | Within 2% | DuckDB query comparison | TBD |
| **Financial Parity** | N/A | Within 0.5% | Core contribution comparison | TBD |

---

## 🚨 Risks & Mitigation

### **Risk 1: More Models Than Expected Need Updates**
**Likelihood**: Medium | **Impact**: Low (just takes longer)

**Mitigation**: Systematic search in E078-01 finds all issues upfront. Pattern is proven and simple to apply. Each model can be updated and tested independently.

---

### **Risk 2: Event Type Mapping Mistakes**
**Likelihood**: Low | **Impact**: Medium (incorrect event filtering)

**Mitigation**: Parity check (row counts by `simulation_year × event_type` + total employer core contributions) validates correctness. SQL mode toggle provides instant fallback.

---

## 📋 Implementation Timeline (1 Day)

### **Morning (3 hours)**
- E078-01: Identify models and create checklist (1h)
- E078-02: Update models to use `fct_yearly_events` (2h)

### **Afternoon (3 hours)**
- E078-02: Finish model updates and test (1h)
- E078-03: Re-enable Polars mode and parity check (1.5h)
- E078-04: Documentation (0.5h)

**Total Effort**: 6 hours (1 focused day)

---

## 🎓 Lessons Learned from Debugging

**What We Discovered**:
1. ✅ Polars pipeline mostly works - only downstream models need updates
2. ✅ `fct_yearly_events` is the universal interface for both modes
3. ✅ Pattern is simple: replace `int_*_events` → `fct_yearly_events` + WHERE filter
4. ✅ Two models already fixed prove the pattern works

**What We Avoided**:
1. ❌ Creating parallel pipeline architectures (not needed)
2. ❌ Conditional macros and complex mode switching (not needed)
3. ❌ Schema enrichment and cohort loaders (not needed)
4. ❌ 29 hours of work (reduced to 6-8 hours)

**Key Insight**:
The Polars integration is **almost complete**. We just need to update ~10 models to use the existing `fct_yearly_events` table instead of intermediate event tables that don't exist in Polars mode.

---

## 📚 References

### **Evidence from Debugging Session**:
- ✅ `int_enrollment_state_accumulator.sql` line 77 updated successfully
- ✅ `int_deferral_rate_state_accumulator_v2.sql` comprehensive refactor successful
- ✅ `fct_yearly_events.sql` lines 20-96 have full Polars mode support
- ❌ `int_employer_core_contributions.sql` line 172 needs update

### **Related Files**:
- `navigator_orchestrator/pipeline/event_generation_executor.py` (Polars event generation)
- `dbt/models/marts/fct_yearly_events.sql` (event aggregation for both modes)
- `config/simulation_config.yaml` (mode configuration)

### **Related Epics**:
- E077: Bulletproof Workforce Growth Accuracy (algebraic solver)
- E068G: Polars Event Factory (Parquet generation)
- E072: Pipeline Modularization (orchestrator architecture)

---

## ✅ Completion Summary

**Status**: Not started

**Timeline**: TBD

**Results**:
- Models updated: TBD
- SQL mode runtime (2025-2027): TBD
- Polars mode runtime (2025-2027): TBD
- Speedup: TBD
- Event count parity: TBD
- Core contribution parity: TBD

---

**Epic Owner**: Workforce Simulation Team
**Created**: 2025-10-09
**Revised**: 2025-10-10 (streamlined based on ChatGPT-5 feedback)
**Target Completion**: 6 hours (1 focused day)
**Priority**: Medium - Enables Polars performance benefits
**Status**: Ready to Execute
