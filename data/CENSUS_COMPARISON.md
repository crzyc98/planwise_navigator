# Census Dataset Comparison: OLD vs NEW

**Date**: 2025-10-07
**Purpose**: Fresh census dataset to help isolate bugs that may be masked by original data

---

## Summary

| Metric | OLD Census | NEW Census | Change |
|--------|-----------|-----------|---------|
| **Employees** | 5,000 | 7,505 | +50% |
| **Active** | 4,368 (87%) | 6,764 (90%) | +55% |
| **Terminated** | 632 (13%) | 741 (10%) | +17% |
| **Employee ID Prefix** | `EMP_2024_` | `EMP_2025_` | Different pattern |
| **SSN Prefix** | `SSN-100...` | `SSN-200...` | Different range |
| **Random Seed** | Unknown | 99999 | Reproducible |

---

## Salary Distribution

| Statistic | OLD Census | NEW Census | Change |
|-----------|-----------|-----------|---------|
| **Minimum** | $50,000 | $40,000 | Lower floor |
| **25th %ile** | ~$60,000 | $53,500 | Broader range |
| **Median** | ~$75,000 | $80,600 | +7% |
| **75th %ile** | ~$95,000 | $121,700 | +28% |
| **Maximum** | $349,600 | $500,000 | +43% |
| **Mean** | ~$85,000 | $97,374 | +15% |

**Key Differences**:
- NEW has **wider salary range** ($40k-$500k vs $50k-$350k)
- NEW uses **lognormal distribution** (more realistic)
- NEW tests IRS compensation cap edge cases ($350k cap)

---

## Deferral Rate Distribution

| Statistic | OLD Census | NEW Census | Change |
|-----------|-----------|-----------|---------|
| **Non-participants (0%)** | ~750 (15%) | 1,150 (15.3%) | Consistent |
| **Median Rate** | ~6% | 6.0% | Consistent |
| **Maximum Rate** | 15.0% | 20.0% | Higher |
| **Mean Rate** | ~6.5% | 6.6% | Consistent |

**Key Differences**:
- NEW has **realistic distribution** with peaks at common rates (3%, 5%, 6%, 8%, 10%, 15%)
- NEW includes **auto-enrollment default** (30% at 6%)
- NEW has **extreme savers** (up to 20%)

---

## Hire Date Patterns

| Pattern | OLD Census | NEW Census |
|---------|-----------|-----------|
| **Date Range** | Unknown | 2005-01-01 to 2024-12-31 |
| **Distribution** | Likely uniform | **Bimodal** (30% tenured 2005-2015, 70% recent 2020-2024) |
| **Tenured Employees (10+ years)** | Unknown | ~2,250 (30%) |
| **Recent Hires (<5 years)** | Unknown | ~5,250 (70%) |

**Key Differences**:
- NEW has **realistic tenure distribution** (not uniform)
- NEW tests **edge cases** with very recent hires (2024-12-31)

---

## Age Distribution

| Statistic | OLD Census | NEW Census |
|-----------|-----------|-----------|
| **Age Range** | Unknown | 25-61 years |
| **Mean Age** | Unknown | 40.5 years |
| **Distribution** | Unknown | **Bimodal** (60% young 25-40, 40% experienced 40-60) |

**Key Differences**:
- NEW has **younger workforce profile** (60% under 40)
- NEW reflects **modern demographics**

---

## Edge Cases Included in NEW Census

The NEW census includes **5 intentional edge cases** to flush out bugs:

### Edge Case 1: Very Recent Hire
- **ID**: `EMP_2025_9999991`
- **Hire Date**: 2024-12-31 (hired yesterday relative to simulation start)
- **Purpose**: Test proration logic for employees hired at year-end

### Edge Case 2: Maximum Compensation
- **ID**: `EMP_2025_9999992`
- **Gross Comp**: $500,000 (above IRS cap)
- **Capped Comp**: $350,000
- **Purpose**: Test IRS compensation cap enforcement

### Edge Case 3: Zero Deferral Rate
- **ID**: `EMP_2025_9999993`
- **Deferral Rate**: 0.0%
- **Purpose**: Test non-participant logic (should get core but no match)

### Edge Case 4: Mid-Year Termination
- **ID**: `EMP_2025_9999994`
- **Termination**: 2024-06-30 (mid-year)
- **Purpose**: Test contribution proration for partial-year employment

### Edge Case 5: Minimum Compensation
- **ID**: `EMP_2025_9999995`
- **Gross Comp**: $40,000 (minimum)
- **Purpose**: Test low-income edge cases

---

## Why This Helps Debug

### 1. **Different Data Patterns**
- If bug appears with BOTH datasets → likely core logic issue
- If bug only appears with ONE dataset → data-dependent bug

### 2. **Wider Range Testing**
- NEW tests extreme values (min/max compensation)
- NEW tests edge cases (recent hires, terminations)
- NEW has more realistic distributions

### 3. **Known Edge Cases**
- 5 intentional edge cases with IDs `EMP_2025_9999991` through `EMP_2025_9999995`
- Easy to query and inspect specific problem scenarios

### 4. **Fresh Start**
- Different random seed (99999 vs unknown)
- Different ID patterns (2025 vs 2024)
- Eliminates any corruption/drift from original dataset

---

## Testing Strategy

### Step 1: Run with NEW Census
```bash
# Use new census (already active)
python -m planalign_orchestrator run --years 2025 --verbose
```

### Step 2: Compare Results
```bash
# Check for differences in event generation
duckdb dbt/simulation.duckdb "
SELECT simulation_year, event_type, COUNT(*) as event_count
FROM fct_yearly_events
GROUP BY simulation_year, event_type
ORDER BY simulation_year, event_type
"
```

### Step 3: Inspect Edge Cases
```bash
# Query specific edge case employees
duckdb dbt/simulation.duckdb "
SELECT *
FROM fct_workforce_snapshot
WHERE employee_id IN (
  'EMP_2025_9999991',
  'EMP_2025_9999992',
  'EMP_2025_9999993',
  'EMP_2025_9999994',
  'EMP_2025_9999995'
)
ORDER BY employee_id
"
```

### Step 4: Compare with OLD Census (if needed)
```bash
# Restore old census
cp data/census_preprocessed_OLD_backup_*.parquet data/census_preprocessed.parquet

# Re-run simulation
python -m planalign_orchestrator run --years 2025 --verbose --force-restart

# Compare results
```

---

## Key Files

- **NEW Census**: `data/census_preprocessed.parquet` (393 KB, 7,505 employees)
- **OLD Census Backup**: `data/census_preprocessed_OLD_backup_20251007_191811.parquet` (393 KB, 5,000 employees)
- **Generator Script**: `scripts/generate_fresh_census.py` (reproducible with seed 99999)

---

## Next Steps

1. ✅ **NEW census created** with 7,505 employees
2. ✅ **OLD census backed up** for comparison
3. 🔄 **Run simulation** with new census
4. 🔍 **Monitor for bugs** that appear/disappear
5. 🎯 **Focus on edge cases** if issues persist

---

## Notes

- The NEW census is **intentionally different** to help isolate data-dependent bugs
- All edge cases are **documented and queryable**
- Generator script is **reproducible** (random seed 99999)
- Can easily switch back to OLD census if needed for comparison
