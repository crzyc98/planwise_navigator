# Promotion Events Data Propagation Fix

## Problem Description

### Root Cause
The promotion events model (`int_promotion_events.sql`) was experiencing a classic data propagation issue where employees were repeatedly promoted from their original baseline levels instead of their current levels. This occurred because the model was using `int_workforce_active_for_events` as its data source, which provides stale employee data from the baseline workforce snapshot rather than the current employee state.

### Specific Issue Manifestation
- **Employee EMP_000011** was being promoted from Level 1 to Level 2 multiple times across different simulation years
- Instead of progressing from Level 1 → Level 2 → Level 3 → Level 4, the employee was stuck in a loop of Level 1 → Level 2 promotions
- This pattern affected all promoted employees, causing incorrect workforce progression and compensation calculations

### Relationship to Previous Issues
This issue mirrors the merit raise problem that was previously resolved in `int_merit_events.sql`. Both models initially used `int_workforce_active_for_events` and suffered from the same stale data propagation issue.

## Solution Overview

### Data Source Migration
The fix involves switching from `int_workforce_active_for_events` to `int_employee_compensation_by_year` as the workforce data source. This change ensures that:

1. **Current State Visibility**: The promotion logic sees each employee's current level from the previous year's final snapshot
2. **Proper Progression**: Employees advance through levels sequentially (1→2→3→4→5) instead of being stuck at their baseline level
3. **Data Consistency**: All workforce events use the same up-to-date employee state reference

### Pattern Consistency
This fix follows the proven pattern established in the `int_merit_events.sql` resolution, ensuring consistency across all event generation models.

### Anti-Duplication Logic
Additional safeguards were implemented to prevent duplicate promotion events:
- **Anti-join logic**: LEFT JOIN against existing promotion events for the same employee and year
- **DISTINCT clause**: Handles any remaining JOIN fan-out issues from hazard table lookups

## Technical Implementation

### Modified Files

#### 1. `dbt/models/intermediate/events/int_promotion_events.sql`
**Changes Made:**
- **Data Source**: Replaced `int_workforce_active_for_events` with `int_employee_compensation_by_year`
- **Field Mapping**: Updated to use `employee_compensation` as `employee_gross_compensation` and direct `level_id` reference
- **Filtering**: Added `employment_status = 'active'` filter to maintain active workforce constraint
- **Anti-Join Logic**: Added LEFT JOIN against `{{ this }}` to prevent duplicate events within the same year
- **DISTINCT Clause**: Added to final SELECT to handle JOIN fan-out issues
- **Comments**: Updated to document the fix and reference the merit events pattern

#### 2. `tests/validation/test_promotion_events_duplicate_prevention.sql` (NEW)
**Purpose**: Regression test to ensure no employee receives multiple promotion events in the same year
**Logic**: Groups by `employee_id` and `simulation_year`, fails if any group has COUNT(*) > 1

#### 3. `tests/validation/test_promotion_events_level_progression.sql` (NEW)
**Purpose**: Validates proper level progression and data consistency
**Validations**:
- Promotions are exactly one level up (`to_level = from_level + 1`)
- No level skipping or demotions
- Level boundaries are respected (1-5 range)
- No promotions from maximum level (5)
- `from_level` matches employee's actual previous year level

## Data Flow Architecture

### Before Fix (Problematic Flow)
```
int_baseline_workforce → int_workforce_active_for_events → int_promotion_events
```
**Issue**: `int_workforce_active_for_events` always provides baseline employee levels, ignoring previous promotions.

### After Fix (Corrected Flow)
```
int_baseline_workforce → int_employee_compensation_by_year ← fct_workforce_snapshot
                                    ↓
                            int_promotion_events
```
**Solution**: `int_employee_compensation_by_year` reflects the employee's current state from the previous year's final workforce snapshot.

### Dependency Chain
1. **Year 1**: `int_baseline_workforce` → `int_employee_compensation_by_year` → promotion events → `fct_workforce_snapshot`
2. **Year 2+**: Previous year's `fct_workforce_snapshot` → `int_employee_compensation_by_year` → promotion events → current year's `fct_workforce_snapshot`

### Circular Dependency Prevention
The architecture prevents circular dependencies by:
- Using previous year's final state for current year event generation
- Ensuring `int_employee_compensation_by_year` depends on the previous year's `fct_workforce_snapshot`
- Maintaining clear temporal separation between event generation and state updates

## Validation Strategy

### Existing Framework Integration
The fix leverages the existing validation framework documented in `tests/validation/test_promotion_events_fix_validation.py` which includes:
- Employee-level progression tracking
- Event count validation
- Rate consistency checks

### New Validation Tests
1. **Duplicate Prevention Test**: Ensures one promotion per employee per year
2. **Level Progression Test**: Validates sequential level advancement and data consistency

### Before/After Testing Scenarios
**Test Scenario**: Multi-year simulation with known promotion candidates
- **Before Fix**: Employee EMP_000011 promoted Level 1→2 in years 2, 3, 4
- **After Fix**: Employee EMP_000011 promoted Level 1→2→3→4 across years 2, 3, 4

## Monitoring and Maintenance

### Ongoing Monitoring Recommendations
1. **Event Count Tracking**: Monitor promotion event counts per year for unusual spikes or drops
2. **Rate Validation**: Ensure promotion rates remain within expected ranges (typically 5-15% annually)
3. **Level Distribution**: Track workforce level distribution over time to detect progression anomalies
4. **Zero Event Detection**: Alert if any simulation year produces zero promotion events (potential model failure)

### Maintenance Alerts
- **Duplicate Events**: Any failure of the duplicate prevention test indicates regression
- **Level Progression**: Violations of the level progression test suggest data integrity issues
- **Rate Anomalies**: Promotion rates outside 0-25% range warrant investigation

### Troubleshooting Guide
**Issue**: Promotion events suddenly drop to zero
- **Check**: Verify `int_employee_compensation_by_year` has active employees for the simulation year
- **Check**: Confirm hazard promotion table has rates for the simulation year

**Issue**: Duplicate promotion events appear
- **Check**: Ensure anti-join logic is functioning correctly
- **Check**: Verify `{{ this }}` reference resolves properly in incremental builds

**Issue**: Level progression violations
- **Check**: Confirm `int_employee_compensation_by_year` reflects accurate previous year state
- **Check**: Validate workforce snapshot integrity from previous simulation year

### Future Enhancement Considerations
1. **Performance Optimization**: Consider indexing strategies for large workforce simulations
2. **Business Rule Evolution**: Monitor for changes in promotion eligibility criteria
3. **Advanced Validation**: Implement statistical tests for promotion rate distribution consistency
4. **Audit Trail Enhancement**: Consider adding promotion reason codes for enhanced transparency

## References
- **Merit Events Fix**: `dbt/models/intermediate/events/int_merit_events.sql` (similar pattern)
- **Employee Compensation Model**: `dbt/models/intermediate/int_employee_compensation_by_year.sql`
- **Validation Framework**: `docs/validation/promotion_events_fix_validation_results.md`
- **Architecture Documentation**: `/docs/architecture.md`
