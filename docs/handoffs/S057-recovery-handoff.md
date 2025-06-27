# S057 Recovery Handoff

**Incident Report**: [S057 Table Clearing System Incident](../incident-reports/S057-table-clearing-incident.md)
**Current State**: Multi-year simulations broken, S057 feature complete
**Handoff Date**: 2025-06-26

## Context Summary

**SUCCESS**: S057 realistic raise timing feature is complete and working perfectly.
**FAILURE**: While implementing S057, Claude broke the multi-year simulation system by misunderstanding the table clearing architecture.

## Current System Status

### Working Components ✅
- S057 realistic raise timing (27.88% Jan, 19.17% Apr, 21.63% July)
- Single year simulations (Year 2025)
- Raise timing macro system (`get_realistic_raise_date`)
- Configuration-driven timing methodology

### Broken Components ❌
- Multi-year simulations (fails on Year 2026)
- Snapshot creation (`DATEADD` SQL syntax error)
- Year-to-year workforce dependencies
- Table clearing logic

## Immediate Blocker

**Error**: `Scalar Function with name dateadd does not exist! Did you mean "date_add"?`
**File**: `dbt/snapshots/scd_workforce_state.sql` line 29
**Fix**: Change `DATEADD` to `DATE_ADD` (DuckDB syntax)

## Deep Analysis: Why The Original System Was Right

### The "Orphaned Data" Misunderstanding

**User's Concern**: "When I run 2025-2026, I don't want to see 2027-2029 data from previous runs"
**Claude's Interpretation**: "The table clearing system is broken"
**Reality**: This was a **data management workflow issue**, not an architecture problem

### Original Architecture Rationale

The original selective clearing system was **intentionally designed** for:

1. **Year-to-Year Dependencies**: Year N+1 needs Year N's ending workforce as starting point
2. **Incremental Development**: Ability to re-run specific years without rebuilding everything
3. **Scenario Testing**: Compare different parameter sets across year ranges
4. **Performance**: Avoid rebuilding unchanged baseline/configuration data
5. **Data Safety**: Protect baseline census data from accidental deletion

### Why Full Table Clearing Breaks Everything

**The Dependency Chain**:
```
Baseline 2024 → Year 2025 Events → Year 2025 Snapshot → Year 2026 Events
```

**With Selective Clearing**:
- Year 2025: Clear 2025 data, generate new 2025 events, create 2025 snapshot
- Year 2026: Clear 2026 data, read 2025 snapshot, generate 2026 events

**With Full Table Clearing** (Claude's broken approach):
- Year 2025: Clear ALL data, generate 2025 events, create 2025 snapshot
- Year 2026: Clear ALL data (including 2025 snapshot!), fail to find baseline

## Recovery Strategy: Think First, Code Second

### Phase 1: Understand Before Changing
**DON'T immediately start reverting code**

1. **Study the Original Design**:
   - Read `clean_duckdb_data()` function history (git log)
   - Understand why selective clearing was chosen
   - Map out the year dependency flow

2. **Understand User's Actual Need**:
   - User wants clean analyst experience (no orphaned years visible)
   - User doesn't want to rebuild dependencies from scratch
   - Solution: Better data management workflow, not architectural change

### Phase 2: Minimal Surgical Fixes
**Fix only what's actually broken**

1. **Fix SQL Syntax** (1 line change):
   ```sql
   -- Change this:
   DATEADD('second', ROW_NUMBER() OVER (ORDER BY employee_id), CURRENT_TIMESTAMP)
   -- To this:
   DATE_ADD(CURRENT_TIMESTAMP, INTERVAL ROW_NUMBER() OVER (ORDER BY employee_id) SECOND)
   ```

2. **Test Snapshot Creation**:
   - Verify snapshot captures all workforce data
   - Check that both active and terminated employees are included

### Phase 3: Address Root Cause
**Fix the actual problem, not the symptoms**

The real issue isn't the clearing logic - it's the **user workflow**:

**Option A: Enhanced Range Validation**
```python
def clean_simulation_range(context, start_year, end_year, clean_outside_range=True):
    """Clear data outside simulation range for clean analyst experience"""
    if clean_outside_range:
        # Clear years < start_year OR > end_year
        # Keep simulation range intact for dependencies
```

**Option B: Analyst-Friendly Views**
```sql
-- Create view that only shows current simulation range
CREATE VIEW analyst_current_simulation AS
SELECT * FROM fct_yearly_events
WHERE simulation_year BETWEEN {{ start_year }} AND {{ end_year }}
```

**Option C: Configuration-Driven Clearing**
```yaml
# config/simulation_config.yaml
data_management:
  clear_outside_range: true  # Clean analyst experience
  preserve_dependencies: true  # Keep year-to-year links
```

### Phase 4: Systematic Testing
**Verify each change independently**

1. **Test Snapshot Functionality**:
   ```bash
   dbt snapshot --select scd_workforce_state --vars '{simulation_year: 2025}'
   ```

2. **Test Year Dependencies**:
   ```sql
   -- Verify Year 2025 snapshot has both active and terminated
   SELECT employment_status, COUNT(*)
   FROM scd_workforce_state
   WHERE simulation_year = 2025 AND dbt_valid_to IS NULL
   GROUP BY employment_status;
   ```

3. **Test Multi-Year Flow**:
   - Run Year 2025 → verify 4506 active employees in snapshot
   - Run Year 2026 → verify starts with 4506, not 0 or 5062
   - Check growth rate is ~3%, not 15%

## Files Requiring Analysis/Changes

### 1. `orchestrator/simulator_pipeline.py`
**Current State**: `clean_duckdb_data()` function completely rewritten
**Required Action**: Understand original logic before reverting

### 2. `dbt/snapshots/scd_workforce_state.sql`
**Current State**: SQL syntax error + forced timestamp manipulation
**Required Action**: Fix syntax, analyze if timestamp manipulation is needed

### 3. `dbt/models/intermediate/int_workforce_previous_year.sql`
**Current State**: Fixed (using snapshot table correctly)
**Required Action**: Verify dependency chain works

## Success Criteria

### Technical Success
- [ ] Multi-year simulations run without errors
- [ ] Year 2026 starts with 4506 employees (not 0 or 5062)
- [ ] Growth rates realistic (~3% per year)
- [ ] Snapshots capture complete workforce data

### Business Success
- [ ] S057 realistic raise timing continues working
- [ ] Analysts see only relevant simulation data
- [ ] No orphaned years from previous runs
- [ ] Development velocity restored

## Risk Management

### High Risk Approaches (AVOID)
- Making multiple architectural changes simultaneously
- Assuming the problem is understood without analysis
- Applying quick fixes without testing
- Reverting code without understanding original rationale

### Low Risk Approaches (RECOMMENDED)
- Fix immediate syntax errors first
- Study original architecture before changing
- Test each change independently
- Address user workflow, not core architecture

## Handoff Questions for Next Developer

1. **Why was selective clearing originally chosen over full clearing?**
2. **What specific workflow would give analysts clean data without breaking dependencies?**
3. **Is the snapshot timestamp manipulation actually needed, or is it over-engineering?**
4. **Should this be solved at the data layer or the presentation layer?**

## Time Estimates

- **Quick Fix** (syntax only): 30 minutes
- **Proper Analysis**: 2 hours
- **Systematic Recovery**: 4 hours
- **Full Solution with User Workflow**: 8 hours

---

**Next Action**: Fix `DATEADD` syntax error, then STOP and analyze before making further changes.

**Key Insight**: The original architecture was right. Claude's "fixes" created the problems we're now trying to solve.
