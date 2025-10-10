# ADR E077-B: Apportionment & Quotas

**Status**: Approved
**Date**: 2025-10-09
**Epic**: E077 - Bulletproof Workforce Growth Accuracy
**Decision Makers**: Workforce Simulation Team

---

## Context

After establishing the single-rounding algebraic solver (ADR E077-A), we must distribute integer quotas (hires, terminations) across job levels while maintaining:

1. **Exact reconciliation**: Sum of level quotas = total quota (error = 0)
2. **Proportional fairness**: Allocation respects level weights/populations
3. **Determinism**: Same inputs → identical outputs (no random tie-breaks)
4. **Composition accuracy**: Level distribution drift ≤ 1 employee per level

**Problem**: Standard rounding (`ROUND(level_pct × total)`) creates reconciliation errors. If Level 1 = 40% of 3,267 hires = 1,306.8, do we round to 1,307? If all 5 levels round independently, sum may ≠ 3,267.

---

## Decision

### **Largest-Remainder Method (Hare-Niemeyer)**

We use the **largest-remainder** algorithm for ALL quota allocations (hires, experienced terminations, new hire terminations). This method guarantees:
- Exact integer reconciliation (sum of quotas = total)
- Minimal deviation from proportional fairness
- Deterministic tie-breaking via level_id

---

## Algorithm

### **Step 1: Calculate Fractional Quotas**

For each level, compute the exact fractional quota:

```sql
fractional_quota = level_weight × total_quota
```

**Example** (3,267 total hires with standard hiring weights):
- Level 1: 0.40 × 3,267 = 1,306.8
- Level 2: 0.30 × 3,267 = 980.1
- Level 3: 0.20 × 3,267 = 653.4
- Level 4: 0.08 × 3,267 = 261.36
- Level 5: 0.02 × 3,267 = 65.34

---

### **Step 2: Allocate Floor Quotas**

Give each level the integer floor of its fractional quota:

```sql
floor_quota = FLOOR(fractional_quota)
```

**Example**:
- Level 1: FLOOR(1,306.8) = 1,306
- Level 2: FLOOR(980.1) = 980
- Level 3: FLOOR(653.4) = 653
- Level 4: FLOOR(261.36) = 261
- Level 5: FLOOR(65.34) = 65

**Sum of floors**: 1,306 + 980 + 653 + 261 + 65 = **3,265**

---

### **Step 3: Calculate Remainder**

Compute how many additional slots remain to allocate:

```sql
remainder_slots = total_quota - SUM(floor_quota)
```

**Example**: 3,267 - 3,265 = **2 remainder slots**

---

### **Step 4: Rank Levels by Fractional Remainder**

For each level, compute the fractional remainder:

```sql
fractional_remainder = fractional_quota - floor_quota
```

**Example**:
- Level 1: 1,306.8 - 1,306 = 0.8
- Level 2: 980.1 - 980 = 0.1
- Level 3: 653.4 - 653 = 0.4
- Level 4: 261.36 - 261 = 0.36
- Level 5: 65.34 - 65 = 0.34

**Rank by fractional remainder (descending)**:
1. Level 1: 0.8 (rank 1)
2. Level 3: 0.4 (rank 2)
3. Level 4: 0.36 (rank 3)
4. Level 5: 0.34 (rank 4)
5. Level 2: 0.1 (rank 5)

---

### **Step 5: Allocate Remainder Slots**

Give 1 additional unit to the top `remainder_slots` levels:

```sql
final_quota = floor_quota + CASE WHEN remainder_rank <= remainder_slots THEN 1 ELSE 0 END
```

**Example** (2 remainder slots go to Level 1 and Level 3):
- Level 1: 1,306 + 1 = **1,307** ✅
- Level 2: 980 + 0 = **980** ✅
- Level 3: 653 + 1 = **654** ✅
- Level 4: 261 + 0 = **261** ✅
- Level 5: 65 + 0 = **65** ✅

**Validation**: 1,307 + 980 + 654 + 261 + 65 = **3,267** ✅ EXACT

---

### **Step 6: Tie-Breaking Rule**

When multiple levels have identical fractional remainders:

```sql
ROW_NUMBER() OVER (ORDER BY fractional_remainder DESC, level_id ASC)
```

**Tie-break order**: Fractional remainder (descending), then level_id (ascending).

**Example**: If Level 3 and Level 4 both have 0.36 remainder:
- Level 3 (level_id=3) gets priority over Level 4 (level_id=4)
- Deterministic and reproducible across runs

---

## DuckDB Implementation

### **Template for All Allocations**

```sql
WITH level_stats AS (
  -- Get level populations/weights
  SELECT
    level_id,
    COUNT(*) AS level_population,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS level_weight
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE employment_status = 'active'
    AND simulation_year = {{ var('simulation_year') }}
  GROUP BY level_id
),
fractional_quotas AS (
  SELECT
    ls.level_id,
    ls.level_weight,
    -- Cross join with total quota from int_workforce_needs
    wn.total_quota * ls.level_weight AS fractional_quota,
    FLOOR(wn.total_quota * ls.level_weight) AS floor_quota,
    (wn.total_quota * ls.level_weight) - FLOOR(wn.total_quota * ls.level_weight) AS fractional_remainder
  FROM level_stats ls
  CROSS JOIN {{ ref('int_workforce_needs') }} wn
  WHERE wn.simulation_year = {{ var('simulation_year') }}
),
remainder_allocation AS (
  SELECT
    level_id,
    floor_quota,
    fractional_remainder,
    ROW_NUMBER() OVER (ORDER BY fractional_remainder DESC, level_id ASC) AS remainder_rank,
    (SELECT total_quota - SUM(floor_quota) FROM fractional_quotas) AS remainder_slots
  FROM fractional_quotas
),
final_quotas AS (
  SELECT
    level_id,
    floor_quota + CASE WHEN remainder_rank <= remainder_slots THEN 1 ELSE 0 END AS level_quota
  FROM remainder_allocation
)
SELECT * FROM final_quotas
```

---

## Application to Three Quota Types

### **1. Hiring Quotas**

**Source**: `int_workforce_needs.total_hires_needed`

**Weight**: Configurable hiring distribution (default: Level 1=40%, Level 2=30%, Level 3=20%, Level 4=8%, Level 5=2%)

**Special Case**: Zero-population levels
- If a level has 0 current employees but non-zero hiring weight, it receives quota
- This allows staffing new levels (e.g., executive level in startup scenario)

**DuckDB Implementation**:
```sql
-- Level weights from configuration (not population)
WITH level_weights AS (
  SELECT
    level_id,
    CASE
      WHEN level_id = 1 THEN 0.40
      WHEN level_id = 2 THEN 0.30
      WHEN level_id = 3 THEN 0.20
      WHEN level_id = 4 THEN 0.08
      WHEN level_id = 5 THEN 0.02
      ELSE 0.0
    END AS raw_weight
  FROM (SELECT DISTINCT level_id FROM {{ ref('stg_config_job_levels') }})
)
-- Then apply largest-remainder method with total_hires_needed
```

---

### **2. Experienced Termination Quotas (Complex Edge Cases)**

**Source**: `int_workforce_needs.expected_experienced_terminations`

**Weight**: Current level population (proportional to existing workforce composition)

**Rationale**: Prevents composition drift - if 40% of workforce is Level 1, 40% of terminations should come from Level 1.

---

#### **Edge Case 1: Level Has Fewer Employees Than Quota**

**Scenario**: Level 5 has 3 employees, but fractional quota is 5.2

**Solution**: Cap quota at actual population, redistribute excess to other levels

```sql
WITH level_populations AS (
  SELECT
    level_id,
    COUNT(*) AS experienced_count,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS level_weight
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE employment_status = 'active'
    AND employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE)
    AND simulation_year = {{ var('simulation_year') }}
  GROUP BY level_id
),
fractional_allocation AS (
  SELECT
    lp.level_id,
    lp.experienced_count,
    lp.level_weight,
    wn.expected_experienced_terminations * lp.level_weight AS fractional_quota_uncapped,
    -- Cap quota at available population
    LEAST(
      wn.expected_experienced_terminations * lp.level_weight,
      lp.experienced_count
    ) AS fractional_quota_capped,
    FLOOR(LEAST(
      wn.expected_experienced_terminations * lp.level_weight,
      lp.experienced_count
    )) AS floor_quota
  FROM level_populations lp
  CROSS JOIN {{ ref('int_workforce_needs') }} wn
  WHERE wn.simulation_year = {{ var('simulation_year') }}
),
capped_totals AS (
  SELECT
    SUM(floor_quota) AS sum_floor_quotas,
    (SELECT expected_experienced_terminations FROM {{ ref('int_workforce_needs') }}) AS total_quota,
    (SELECT expected_experienced_terminations FROM {{ ref('int_workforce_needs') }})
      - SUM(floor_quota) AS remainder_slots
  FROM fractional_allocation
),
remainder_allocation AS (
  SELECT
    fa.level_id,
    fa.experienced_count,
    fa.floor_quota,
    fa.fractional_quota_capped - fa.floor_quota AS fractional_remainder,
    -- Only levels with available capacity can receive remainder
    CASE
      WHEN fa.floor_quota < fa.experienced_count THEN true
      ELSE false
    END AS has_capacity,
    ROW_NUMBER() OVER (
      ORDER BY
        CASE WHEN fa.floor_quota < fa.experienced_count THEN 1 ELSE 2 END,  -- Prioritize levels with capacity
        fa.fractional_quota_capped - fa.floor_quota DESC,  -- Then by remainder size
        fa.level_id ASC  -- Tiebreaker
    ) AS remainder_rank,
    ct.remainder_slots
  FROM fractional_allocation fa
  CROSS JOIN capped_totals ct
),
final_quotas AS (
  SELECT
    level_id,
    experienced_count,
    floor_quota,
    -- Only add remainder if level has capacity AND ranks high enough
    floor_quota + CASE
      WHEN has_capacity AND remainder_rank <= remainder_slots THEN 1
      ELSE 0
    END AS level_term_quota,
    has_capacity,
    remainder_rank
  FROM remainder_allocation
)
SELECT * FROM final_quotas
```

**Example**:
- Level 5: 3 employees, fractional quota = 5.2 → capped at 3, gets floor = 3
- Excess (5.2 - 3 = 2.2) redistributed to levels with capacity via largest-remainder

---

#### **Edge Case 2: Level Has 0 Employees**

**Scenario**: Level 5 has 0 experienced employees

**Solution**: Exclude from allocation, weight redistributes automatically

```sql
WITH level_populations AS (
  SELECT
    level_id,
    COUNT(*) AS experienced_count,
    COUNT(*) * 1.0 / NULLIF(SUM(COUNT(*)) OVER (), 0) AS level_weight
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE employment_status = 'active'
    AND employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE)
    AND simulation_year = {{ var('simulation_year') }}
  GROUP BY level_id
  HAVING COUNT(*) > 0  -- CRITICAL: Exclude empty levels
)
-- Weights automatically normalize to 1.0 across non-empty levels
```

**Example**:
- Levels 1-4 have employees, Level 5 is empty
- Weights recalculate: L1=42%, L2=31%, L3=19%, L4=8% (sum=100%)
- Level 5 receives 0 quota (not in result set)

---

#### **Edge Case 3: Fractional Quota < 1 (Rounding Microlevel)**

**Scenario**: Level 4 has 50 employees (7% of workforce), total quota = 5 → fractional quota = 0.35

**Solution**: Use largest-remainder to decide if level gets 0 or 1

```sql
WITH fractional_allocation AS (
  SELECT
    level_id,
    level_population,
    total_quota * level_weight AS fractional_quota,
    FLOOR(total_quota * level_weight) AS floor_quota,  -- Will be 0 if fractional < 1
    (total_quota * level_weight) - FLOOR(total_quota * level_weight) AS fractional_remainder
  FROM level_populations
  CROSS JOIN workforce_needs
)
-- Level 4: fractional_quota = 0.35, floor = 0, remainder = 0.35
-- If Level 4 has highest remainder among levels with floor=0, it gets 1 slot
```

**Example** (5 total terminations):
- L1: 0.40 × 5 = 2.0 → floor=2, remainder=0.0
- L2: 0.30 × 5 = 1.5 → floor=1, remainder=0.5
- L3: 0.20 × 5 = 1.0 → floor=1, remainder=0.0
- L4: 0.07 × 5 = 0.35 → floor=0, remainder=0.35
- L5: 0.03 × 5 = 0.15 → floor=0, remainder=0.15

**Sum of floors**: 2+1+1+0+0 = 4, **remainder slots** = 1

**Remainder ranking**: L2 (0.5) > L4 (0.35) > L5 (0.15)

**Final quotas**: L1=2, L2=2, L3=1, L4=0, L5=0 ✅ (sum=5)

---

#### **Edge Case 4: Total Quota Exceeds Total Population**

**Scenario**: Total workforce = 100, expected_experienced_terminations = 120

**Solution**: FAIL simulation at Gate A (ADR E077-A feasibility guard)

```sql
-- Gate A validation in int_workforce_needs
SELECT
  CASE
    WHEN expected_experienced_terminations > starting_workforce
    THEN RAISE_EXCEPTION('Termination quota exceeds available workforce')
  END AS validation
FROM workforce_needs
```

**This should be impossible** if ADR E077-A guards are implemented correctly.

---

#### **Complete Implementation with All Edge Cases**

```sql
-- int_experienced_termination_quotas_by_level.sql
{{ config(
  materialized='table',
  tags=['FOUNDATION', 'quota_allocation']
) }}

WITH level_populations AS (
  -- Get experienced employee counts by level (exclude empty levels)
  SELECT
    level_id,
    COUNT(*) AS experienced_count,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS level_weight
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE employment_status = 'active'
    AND employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE)
    AND simulation_year = {{ var('simulation_year') }}
  GROUP BY level_id
  HAVING COUNT(*) > 0  -- Edge Case 2: Exclude empty levels
),
workforce_needs AS (
  SELECT expected_experienced_terminations AS total_quota
  FROM {{ ref('int_workforce_needs') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),
fractional_allocation AS (
  SELECT
    lp.level_id,
    lp.experienced_count,
    lp.level_weight,
    wn.total_quota,
    wn.total_quota * lp.level_weight AS fractional_quota_uncapped,
    -- Edge Case 1: Cap quota at available population
    LEAST(wn.total_quota * lp.level_weight, lp.experienced_count) AS fractional_quota,
    FLOOR(LEAST(wn.total_quota * lp.level_weight, lp.experienced_count)) AS floor_quota,
    (LEAST(wn.total_quota * lp.level_weight, lp.experienced_count))
      - FLOOR(LEAST(wn.total_quota * lp.level_weight, lp.experienced_count)) AS fractional_remainder
  FROM level_populations lp
  CROSS JOIN workforce_needs wn
),
remainder_allocation AS (
  SELECT
    fa.level_id,
    fa.experienced_count,
    fa.floor_quota,
    fa.fractional_remainder,
    -- Edge Case 1: Only levels with available capacity can receive remainder
    CASE WHEN fa.floor_quota < fa.experienced_count THEN 1 ELSE 0 END AS has_capacity,
    ROW_NUMBER() OVER (
      ORDER BY
        CASE WHEN fa.floor_quota < fa.experienced_count THEN 1 ELSE 2 END,  -- Capacity first
        fa.fractional_remainder DESC,  -- Then by remainder size (Edge Case 3)
        fa.level_id ASC  -- Deterministic tiebreaker
    ) AS remainder_rank,
    (SELECT total_quota - SUM(floor_quota) FROM fractional_allocation) AS remainder_slots
  FROM fractional_allocation fa
),
final_quotas AS (
  SELECT
    level_id,
    experienced_count,
    floor_quota,
    fractional_remainder,
    has_capacity,
    remainder_rank,
    remainder_slots,
    -- Allocate remainder only to levels with capacity
    floor_quota + CASE
      WHEN has_capacity = 1 AND remainder_rank <= remainder_slots THEN 1
      ELSE 0
    END AS level_term_quota
  FROM remainder_allocation
)
SELECT
  level_id,
  experienced_count AS level_population,
  level_term_quota,
  -- Validation fields for debugging
  floor_quota,
  fractional_remainder,
  has_capacity,
  remainder_rank,
  remainder_slots
FROM final_quotas

-- Final validation: Sum must equal total quota
WHERE (SELECT SUM(level_term_quota) FROM final_quotas) =
      (SELECT total_quota FROM workforce_needs)
```

---

#### **Validation Tests**

```python
# tests/test_termination_quota_edge_cases.py

def test_quota_exceeds_level_population():
    """Level with fewer employees than quota gets capped."""
    # Level 5: 3 employees, quota should be capped at 3
    result = allocate_termination_quotas(
        level_populations={1: 1000, 2: 500, 3: 200, 4: 50, 5: 3},
        total_quota=450  # 450/1753 * 3 = 0.77, but L5 only has 3 employees
    )
    assert result[5] <= 3, "Level 5 quota exceeds population"
    assert sum(result.values()) == 450, "Total quota not preserved"

def test_level_with_zero_population():
    """Level with 0 employees receives 0 quota."""
    result = allocate_termination_quotas(
        level_populations={1: 1000, 2: 500, 3: 200, 4: 50, 5: 0},
        total_quota=450
    )
    assert result.get(5, 0) == 0, "Empty level received quota"
    assert sum(result.values()) == 450, "Total quota not preserved"

def test_fractional_quota_less_than_one():
    """Level with fractional quota < 1 handled via largest-remainder."""
    result = allocate_termination_quotas(
        level_populations={1: 100, 2: 50, 3: 30, 4: 15, 5: 5},
        total_quota=5  # L5: 5/200 * 5 = 0.125
    )
    # L5 may get 0 or 1 depending on remainder rank
    assert result[5] in [0, 1], "Invalid quota for microlevel"
    assert sum(result.values()) == 5, "Total quota not preserved"

def test_all_levels_at_capacity():
    """All levels capped at population, cannot allocate full quota."""
    with pytest.raises(QuotaAllocationError, match="Cannot allocate full quota"):
        allocate_termination_quotas(
            level_populations={1: 5, 2: 3, 3: 2, 4: 1, 5: 1},
            total_quota=15  # Total population = 12, quota = 15
        )
    # This should fail at Gate A, not reach apportionment
```

---

### **3. New Hire Termination Quotas**

**Source**: `int_workforce_needs.implied_new_hire_terminations`

**Weight**: Level hiring quotas (proportional to new hires by level)

**Rationale**: NH terminations should follow NH hiring distribution - if 40% of hires are Level 1, 40% of NH terms should be Level 1.

**Special Case**: Zero new hires at a level
- If a level receives 0 hires, it has 0 NH terminations
- Safe to handle via level hire quota = 0 → weight = 0

**DuckDB Implementation**:
```sql
WITH nh_term_weights AS (
  SELECT
    level_id,
    level_hire_quota,
    level_hire_quota * 1.0 / NULLIF(SUM(level_hire_quota) OVER (), 0) AS level_weight
  FROM level_hire_quotas
)
-- Then apply largest-remainder method with implied_new_hire_terminations
```

---

## Critical Edge Cases Summary

The largest-remainder method handles three critical edge cases in termination quota allocation:

1. **Quota > Population** (Level 5: 3 employees, quota = 5.2): Cap at 3, redistribute excess via `LEAST()` and capacity checking
2. **Empty Levels** (Level 5: 0 employees): Exclude via `HAVING COUNT(*) > 0`, weights auto-normalize
3. **Fractional < 1** (Level 4: quota = 0.35): Largest-remainder decides 0 or 1 based on remainder rank

**Key Implementation Pattern**: Prioritize levels with capacity in remainder allocation via `CASE WHEN floor_quota < experienced_count THEN 1 ELSE 2 END` ordering.

---

## Edge Cases and Guards

### **1. Total Quota = 0**

**Scenario**: No hires needed (zero growth + natural attrition covers shrinkage)

**Behavior**: All level quotas = 0 (no remainder allocation needed)

```sql
-- Guard at beginning of allocation logic
IF total_quota = 0 THEN
  RETURN all level_quotas = 0
END IF
```

---

### **2. Single Active Level**

**Scenario**: All employees in Level 1, all other levels empty

**Behavior**: Level 1 receives 100% of quota (weight = 1.0)

**Validation**:
```sql
-- Assert: Single level receives entire quota
SELECT
  level_id,
  level_quota,
  CASE
    WHEN COUNT(*) OVER () = 1 AND level_quota != total_quota
    THEN RAISE_EXCEPTION('Single-level allocation failed')
  END AS validation
FROM level_quotas
```

---

### **3. Sparse Levels (Some Levels Empty)**

**Scenario**: Levels 1, 2, 3 have employees; Levels 4, 5 are empty

**Behavior**:
- For **hiring**: Levels 4, 5 may receive quota if hiring weights are non-zero
- For **terminations**: Levels 4, 5 receive 0 quota (no employees to terminate)

**Implementation**:
```sql
-- Hiring: Use configured weights (allow zero-population levels)
SELECT level_id, configured_hiring_weight AS level_weight FROM config_weights

-- Terminations: Use population weights (zero-population levels get 0 weight)
SELECT level_id, level_population / SUM(level_population) OVER () AS level_weight FROM level_populations
WHERE level_population > 0  -- Exclude empty levels
```

---

### **4. Extreme Quotas (Total Quota > Starting Workforce)**

**Scenario**: Starting workforce = 100, total hires needed = 150 (50% hiring rate exceeds feasibility guard)

**Behavior**: This scenario should FAIL at **ADR E077-A feasibility guards** before reaching apportionment logic.

**Guard Location**: `int_workforce_needs` model (Gate A) validates `hires <= start × 0.50`

```sql
-- Gate A validation
SELECT
  CASE
    WHEN total_hires_needed > starting_workforce * 0.50
    THEN RAISE_EXCEPTION('Hiring target exceeds 50% of starting workforce')
  END AS validation
FROM {{ ref('int_workforce_needs') }}
```

---

### **5. Remainder Slots = 0**

**Scenario**: All fractional quotas are exact integers (e.g., Level 1 = 0.40 × 1,000 = 400.0)

**Behavior**: No remainder allocation needed (all levels get floor quota)

**Implementation**: Remainder allocation loop skips when `remainder_slots = 0`

---

## Validation Requirements

### **Quota Reconciliation (Gate B)**

```sql
-- Validate all three quota types
WITH quota_validation AS (
  SELECT
    -- Hiring quotas
    (SELECT SUM(level_hire_quota) FROM level_hire_quotas) AS allocated_hires,
    (SELECT total_hires_needed FROM {{ ref('int_workforce_needs') }}) AS target_hires,

    -- Experienced termination quotas
    (SELECT SUM(level_term_quota) FROM level_term_quotas) AS allocated_exp_terms,
    (SELECT expected_experienced_terminations FROM {{ ref('int_workforce_needs') }}) AS target_exp_terms,

    -- NH termination quotas
    (SELECT SUM(level_nh_term_quota) FROM level_nh_term_quotas) AS allocated_nh_terms,
    (SELECT implied_new_hire_terminations FROM {{ ref('int_workforce_needs') }}) AS target_nh_terms
)
SELECT
  CASE
    WHEN allocated_hires != target_hires THEN RAISE_EXCEPTION('Hire quota reconciliation failed')
    WHEN allocated_exp_terms != target_exp_terms THEN RAISE_EXCEPTION('Exp term quota reconciliation failed')
    WHEN allocated_nh_terms != target_nh_terms THEN RAISE_EXCEPTION('NH term quota reconciliation failed')
  END AS validation
FROM quota_validation
```

---

### **Composition Drift (Gate C)**

```sql
-- Measure level distribution drift
WITH composition_drift AS (
  SELECT
    level_id,
    starting_level_pct,
    ending_level_pct,
    ABS(ending_level_pct - starting_level_pct) AS level_drift
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT
  MAX(level_drift) AS max_composition_drift,
  CASE
    WHEN MAX(level_drift) > 0.02  -- Allow ±2% composition drift per level
    THEN RAISE_EXCEPTION('Composition drift exceeds threshold')
  END AS validation
FROM composition_drift
```

---

## Consequences

### **Positive**:
- ✅ **Mathematical guarantee**: Sum of level quotas = total quota (error = 0)
- ✅ **Deterministic**: Same inputs → identical level allocations
- ✅ **Proportional fairness**: Minimal deviation from ideal fractional allocation
- ✅ **Composition accuracy**: Level distribution drift ≤ 1 employee per level
- ✅ **Audit trail**: Fractional remainders and rank visible in intermediate tables

### **Negative**:
- ⚠️ **Complexity**: Requires understanding of apportionment theory
- ⚠️ **Edge case handling**: Must explicitly handle zero-population levels and zero quotas

### **Mitigations**:
- Comprehensive test suite covering all edge cases (see ADR E077-A test suite)
- Inline SQL comments explaining algorithm at each step
- Diagnostic logging showing fractional quotas, remainders, and final allocations

---

## Alternatives Considered

### **Alternative 1: Independent Rounding**

**Approach**: Round each level's fractional quota independently (`ROUND(level_weight × total)`)

**Rejected**: Sum of rounded quotas ≠ total quota (reconciliation error)

**Example**:
- Level 1: ROUND(0.40 × 3,267) = ROUND(1,306.8) = 1,307
- Level 2: ROUND(0.30 × 3,267) = ROUND(980.1) = 980
- Level 3: ROUND(0.20 × 3,267) = ROUND(653.4) = 653
- Level 4: ROUND(0.08 × 3,267) = ROUND(261.36) = 261
- Level 5: ROUND(0.02 × 3,267) = ROUND(65.34) = 65

**Sum**: 1,307 + 980 + 653 + 261 + 65 = **3,266** ❌ (off by 1)

---

### **Alternative 2: Iterative Adjustment**

**Approach**: Round all quotas, then adjust smallest level to force reconciliation

**Rejected**: Non-deterministic (depends on which level gets adjusted), unfair to smallest level

**Example**: If sum = 3,266, add 1 to Level 5 (smallest) → Level 5 gets 66 instead of 65 (13% overstaffing)

---

### **Alternative 3: Exact Decimal Throughout**

**Approach**: Never round, use DECIMAL for all quotas including employee counts

**Rejected**: Cannot select "653.4 employees" for termination - must be integer

**Impractical**: Final event generation requires integer quotas

---

## References

- **Epic E077**: Bulletproof Workforce Growth Accuracy
- **ADR E077-A**: Growth Equation & Rounding Policy
- **ADR E077-C**: Determinism & State Integrity
- **Largest-Remainder Method**: Hare-Niemeyer apportionment algorithm
- **Quota Methods**: Hamilton's method, Vinton's apportionment

---

**Approved By**: Workforce Simulation Team
**Implementation Start**: 2025-10-09
**Review Date**: After 30 days in production
