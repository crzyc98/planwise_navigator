# Epic: Census-Based Deferral Rate Integration - Implementation Guide

## Quick Context
We're fixing the unrealistic 6% clustering by using actual census deferral rates through synthetic baseline events, while maintaining full event-sourcing.

## Critical Path for Today

### Hour 1-2: Foundation Setup
**Goal**: Get census rates flowing through the system

1. **Update `int_baseline_workforce.sql`** (line ~53)
   - Add `employee_deferral_rate` and `is_enrolled_at_census` fields from staging
   - Ensure rates are preserved as-is from census

2. **Create macros file** `dbt/macros/deferral_rate_macros.sql`
   - `default_deferral_rate()` → returns 0.02 (or var)
   - `plan_deferral_cap()` → returns 0.75 (or var)
   - `normalize_deferral_rate()` → handles percentage vs decimal detection
   - Keep it simple - these just return configured values

3. **Update config variables**
   - Set `auto_enrollment_default_deferral_rate: 0.02`
   - Set `plan_deferral_cap: 0.75` (IRS limit)
   - Add `use_census_rates: true` flag

### Hour 3-4: Synthetic Event Generation
**Goal**: Create baseline events from census

1. **Create `int_synthetic_baseline_enrollment_events.sql`**
   - Query pre-2025 enrolled employees from `int_baseline_workforce`
   - Generate one enrollment event per employee with their census rate
   - Set `event_source='synthetic_baseline'`
   - Use exact census rates (normalized to 0-1 range)
   - Include all required event fields

2. **Quick validation query**:
   ```sql
   SELECT COUNT(*), AVG(employee_deferral_rate), MIN(employee_deferral_rate), MAX(employee_deferral_rate)
   FROM int_synthetic_baseline_enrollment_events;
   -- Should show ~4000-5000 records with realistic distribution
   ```

### Hour 5-6: Accumulator Integration
**Goal**: Make accumulator purely event-driven

1. **Update `int_deferral_rate_state_accumulator_v2.sql`**
   - Add CTE to UNION synthetic baseline events with real enrollment events
   - Remove ALL hard-coded 6% fallback logic (lines ~180-200)
   - Ensure baseline rates come only from events
   - Add `rate_source` field to track origin

2. **Critical sections to modify**:
   - `baseline_pre_enrolled` CTE - must pull from unified events
   - Remove any `COALESCE(rate, 0.06)` patterns
   - Keep carry-forward logic intact

### Hour 7: Testing & Validation
**Goal**: Verify it works

1. **Run key validation queries**:
   ```sql
   -- Check distribution (should NOT see 96% at 6%)
   SELECT
       simulation_year,
       current_deferral_rate,
       COUNT(*) as count,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*) OVER(PARTITION BY simulation_year), 1) as pct
   FROM int_deferral_rate_state_accumulator_v2
   WHERE simulation_year = 2025
   GROUP BY simulation_year, current_deferral_rate
   ORDER BY count DESC
   LIMIT 20;

   -- Check parity
   SELECT COUNT(*) as mismatches
   FROM int_deferral_rate_state_accumulator_v2 a
   JOIN int_employee_contributions c
       ON a.employee_id = c.employee_id
       AND a.simulation_year = c.simulation_year
   WHERE ABS(a.current_deferral_rate - c.final_deferral_rate) > 0.0001;
   ```

2. **Run dbt test suite**:
   ```bash
   dbt test --select int_deferral_rate_state_accumulator_v2
   dbt test --select int_employee_contributions
   ```

### Hour 8: Quick Fixes & Documentation
**Goal**: Handle issues and document

1. **Common issues to watch for**:
   - NULL handling in anti-joins (use NOT EXISTS instead of NOT IN)
   - Rate normalization (rates >1 are percentages, need /100)
   - Event ordering (use ROW_NUMBER to get first event per employee)
   - Missing employees (ensure synthetic events cover all pre-enrolled)

2. **Create simple validation report**:
   - 2025 distribution stats
   - Comparison to census averages
   - Count of employees at each rate
   - Parity check results

## Key Decision Points

### What to Punt Until Later
- Sophisticated escalation logic changes
- Same-year escalation guards
- Extensive lineage tracking
- Performance optimization
- Historical migration

### What Must Work Today
- Census rates flow through correctly
- No 6% clustering
- Synthetic events generate properly
- Accumulator uses events only
- Basic parity between models

## Configuration Decisions

### Use These Values
```yaml
# Start conservative - we can tune later
auto_enrollment_default_deferral_rate: 0.02  # 2% for new hires
plan_deferral_cap: 0.75                       # IRS max
use_census_rates: true                        # Enable the feature
enrollment_maturity_years: 1                  # Keep existing escalation logic for now
```

### Handle Missing Census Rates
- If census rate is NULL but employee is enrolled → use 3% fallback
- If census rate is 0 but enrolled → treat as 1% (data quality issue)
- Log these cases for review but don't fail

## Quick Testing Checklist

- [ ] Synthetic events created for all pre-enrolled
- [ ] No 96% clustering at 6%
- [ ] Average rate between 5-9% (depending on your census)
- [ ] Fractional rates preserved (1.3%, 2.3%, etc.)
- [ ] Accumulator matches contributions
- [ ] New hires show 2% rate (if auto-enrolled)
- [ ] dbt tests pass

## SQL Snippets for Debugging

```sql
-- Find employees stuck at 6%
SELECT employee_id, rate_source, current_deferral_rate
FROM int_deferral_rate_state_accumulator_v2
WHERE simulation_year = 2025
  AND current_deferral_rate = 0.06
LIMIT 100;

-- Check synthetic event coverage
SELECT
    (SELECT COUNT(DISTINCT employee_id) FROM int_synthetic_baseline_enrollment_events) as synthetic_count,
    (SELECT COUNT(DISTINCT employee_id) FROM int_baseline_workforce
     WHERE simulation_year = 2025 AND employee_enrollment_date < '2025-01-01') as should_have_count;

-- Distribution comparison
WITH census AS (
    SELECT AVG(employee_deferral_rate) as avg_rate,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY employee_deferral_rate) as median_rate
    FROM int_baseline_workforce
    WHERE simulation_year = 2025 AND employee_deferral_rate > 0
),
simulated AS (
    SELECT AVG(current_deferral_rate) as avg_rate,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_deferral_rate) as median_rate
    FROM int_deferral_rate_state_accumulator_v2
    WHERE simulation_year = 2025
)
SELECT 'Census' as source, * FROM census
UNION ALL
SELECT 'Simulated' as source, * FROM simulated;
```

## If Things Go Wrong

### Rollback Plan
1. Comment out synthetic event UNION in accumulator
2. Restore hard-coded 6% fallback temporarily
3. Debug with smaller employee subset

### Most Likely Issues
1. **Wrong rate format**: Census might have 7.5 instead of 0.075
2. **Missing joins**: Accumulator might not find synthetic events
3. **NULL propagation**: Anti-joins with NOT IN fail on NULLs
4. **Event duplication**: Multiple events per employee without proper dedup

## Success Indicators by End of Day

✅ **Must Have**:
- Natural distribution in 2025 (not 96% at one value)
- Census rates actually being used
- System still runs end-to-end

🎯 **Nice to Have**:
- Clean parity between all models
- Proper event sourcing for audit trail
- Configuration fully parameterized

❌ **Don't Worry About Today**:
- Perfect escalation logic
- Performance optimization
- Complete documentation
- Edge case handling

Remember: The goal is to get census rates flowing through the system today. Everything else can be refined later.
