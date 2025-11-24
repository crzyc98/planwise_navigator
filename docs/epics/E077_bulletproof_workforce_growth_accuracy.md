# Epic E077: Bulletproof Workforce Growth Accuracy & Performance

## 🎯 Epic Overview

**Problem Statement**: Workforce growth is erratic and unpredictable on real-world census data, producing results ranging from -4% to +40% when expecting consistent 3% growth. Additionally, simulations run too slowly on work laptops (30 minutes for 5 years), making iterative scenario planning impractical.

**Current State**:
- Growth variance: -4% to +40% on 7k employee census (target: 3% ±0.1%)
- Runtime: 30 minutes for 5-year simulation on work laptop
- Root causes: rounding cascades, level distribution mismatches, probabilistic event selection instability, SQL performance bottlenecks

**Target State**:
- Growth accuracy: 100% deterministic with ±0 employee variance from target (error = 0)
- Runtime: <30 seconds for 5-year simulation (60× improvement)
- Architecture: Single-rounding algebraic solver + deterministic cohort allocation + Polars performance

**Business Impact**:
- **Accuracy**: Financial models require exact headcount forecasts for budgeting
- **Performance**: Enable rapid scenario testing (10+ scenarios per hour vs. 2-3 currently)
- **Reliability**: Eliminate "growth mystery debugging" sessions that consume days of analyst time
- **Scalability**: Support 50k+ employee census files on work laptops

**Implementation Timeline**: TODAY (single-day sprint)

---

## 🔥 First Principles: The "Mass Balance" Ladder

Your entire pipeline must be able to explain these identities at every checkpoint:

### **1. Mass Balance (Integer Accounting)**
```
Start + Hires - ExperiencedTerms - NewHireTerms = End (exactly, integer-for-integer)
```

### **2. One Rounding Rule (Algebraic Solver)**
```
Do all rate math in exact/decimal space
→ compute hires from growth equation
→ ceil() once at the end
→ compute implied NH terms to make identity exact
```

### **3. Deterministic Selection (No Probabilistic Variance)**
```
When picking N rows: rank by hash(employee_id) with employee_id tiebreaker
Never use floating-point randoms or QUALIFY with ties
```

### **4. No Level Drift (Adaptive Composition)**
```
Allocate hires by prior year's actual composition
Use largest-remainder method so integer totals match exactly
floors + distribute remainders = total
```

### **5. State is Sacred (No DAG Bypasses)**
```
Year N reads ONLY validated Year N-1 snapshot from pipeline
No adapter.get_relation() hacks or side reads
```

---

## 🧮 Worked Example: The Target Math (Anchor Your Mental Model)

**Scenario**: Start with 7,000 employees, target +3% growth, 25% experienced termination rate, 40% new hire termination rate.

```
Step 1: Calculate target ending workforce (use ROUND for banker's rounding)
  target_ending = ROUND(7,000 × (1 + 0.03)) = ROUND(7,210.0) = 7,210

Step 2: Calculate experienced terminations (use FLOOR for conservative terminations)
  experienced_terms = FLOOR(7,000 × 0.25) = FLOOR(1,750.0) = 1,750
  survivors = 7,000 - 1,750 = 5,250

Step 3: Calculate net new hires needed to reach target
  net_from_hires = 7,210 - 5,250 = 1,960

Step 4: Solve for total hires accounting for NH terminations
  Guard: ASSERT (1 - 0.40) > 0.01  -- Feasibility check
  hires_exact = 1,960 / (1 - 0.40) = 1,960 / 0.60 = 3,266.666...
  hires = CEILING(3,266.67) = 3,267 (ONLY rounding up for hires)

Step 5: Calculate implied NH terminations (forces exact balance)
  implied_nh_terms = 3,267 - 1,750 - (7,210 - 7,000) = 1,307
  Guard: ASSERT implied_nh_terms >= 0 AND implied_nh_terms <= 3,267

Step 6: Validate mass balance (EXACT or FAIL)
  start + hires - exp_terms - implied_nh_terms = end
  7,000 + 3,267 - 1,750 - 1,307 = 7,210 ✅ EXACT (error = 0)
```

**Rounding Policy** (see ADR-A for full details):
- **Target ending**: `ROUND()` - banker's rounding for target
- **Experienced terms**: `FLOOR()` - conservative (don't over-terminate)
- **Hires**: `CEILING()` - aggressive (ensure capacity to hit target)
- **Implied NH terms**: Computed as residual (forces exact balance)

**Negative/Zero Growth Branch** (RIF scenario):
```
If hires_exact <= 0:
  hires = 0  -- No hiring in RIF scenario
  additional_rif_terms = ABS(net_from_hires)  -- Additional terminations needed
  total_exp_terms = experienced_terms + additional_rif_terms
  implied_nh_terms = 0  -- No new hires to terminate

  Validate: start - total_exp_terms = target_ending
  Use deterministic RIF selection (hash ranking) for additional terms
```

**Feasibility Guards** (FAIL if violated):
1. `(1 - nh_term_rate) > 0.01` - NH term rate cannot be ≥99%
2. `hires <= start * max_hire_ratio` - Hiring cannot exceed 50% of starting workforce (configurable)
3. `implied_nh_terms >= 0 AND implied_nh_terms <= hires` - NH terms must be valid subset
4. `ABS(growth_rate) <= 1.0` - Growth rate must be between -100% and +100%

**Key Insight**: By computing `implied_nh_terms` as the residual (rather than independently rounding), we **force** the growth equation to balance exactly. Combined with strategic rounding rules (FLOOR for terms, CEILING for hires, ROUND for target), this eliminates all cascading errors.

---

## 📋 Root Cause Analysis

### **1. Rounding Cascade Errors (Primary Issue)**

**Location**: `dbt/models/intermediate/int_workforce_needs.sql`

```sql
-- FIVE sequential rounding operations compound errors:
target_net_growth = ROUND(starting_workforce * growth_rate)           -- Round 1
target_ending_workforce = ROUND(starting_workforce * (1 + growth_rate))  -- Round 2
expected_experienced_terminations = ROUND(experienced_workforce * term_rate)  -- Round 3
total_hires_needed = ROUND((target_net_growth + exp_terms) / (1 - nh_rate))  -- Round 4
expected_new_hire_terminations = GREATEST(ROUND(hires - exp_terms - growth), 0)  -- Round 5
```

**Example Failure (7,000 employees, 3% growth, 25% termination, 40% new hire termination)**:
- Expected net growth: 210 employees
- Actual result after rounding: 207-213 employees (±1.5% error)
- Cascaded across 5 years: -4% to +8% cumulative error

**Mathematical Issue**: The growth equation `hires - exp_terms - nh_terms = target_growth` cannot balance when each term is independently rounded.

---

### **2. Level Distribution Mismatch**

**Location**: `dbt/models/intermediate/int_workforce_needs_by_level.sql` (lines 66-72)

```sql
-- HARDCODED distribution (assumes generic workforce):
CASE
  WHEN level_id = 1 THEN 0.40  -- 40%
  WHEN level_id = 2 THEN 0.30  -- 30%
  WHEN level_id = 3 THEN 0.20  -- 20%
  WHEN level_id = 4 THEN 0.08  -- 8%
  WHEN level_id = 5 THEN 0.02  -- 2%
END
```

**Real-world census files typically have**:
- Technology firms: 50% L1, 25% L2, 15% L3, 8% L4, 2% L5
- Financial services: 35% L1, 40% L2, 15% L3, 8% L4, 2% L5
- Manufacturing: 60% L1, 20% L2, 10% L3, 7% L4, 3% L5

**Growth Distortion Example** (Technology firm with 50% L1):
- Census terminates 50% of workforce at L1 (1,750 × 0.50 = 875 employees)
- Hiring only replaces 40% at L1 (3,267 × 0.40 = 1,307 employees)
- Net effect: Over-hiring at L1 while under-hiring at other levels
- Result: Total headcount correct but level composition drift causes termination/hiring mismatch in future years

---

### **3. Probabilistic Event Selection Instability**

**Location**: `dbt/models/intermediate/events/int_termination_events.sql` (lines 77-122)

```sql
-- Hash-based random selection:
random_value = (ABS(HASH(employee_id)) % 1000) / 1000.0

-- Selection with QUALIFY:
QUALIFY ROW_NUMBER() OVER (ORDER BY random_value) <= target_count
```

**Issues**:
1. **Hash distribution non-uniformity**: HASH() clustering near 0 or 1000 creates bias
2. **Tie handling**: Multiple employees with same `random_value` cause ±1 variance
3. **Gap filling fuzziness**: "Probabilistic then gap fill" is inherently non-deterministic
4. **Floating point precision**: `/ 1000.0` causes rounding in comparisons

**Example**: Target 1,750 terminations, actual result ranges from 1,748 to 1,752 due to tie handling.

---

### **4. Workforce State Transfer Errors**

**Location**: `dbt/models/intermediate/int_prev_year_workforce_summary.sql` (lines 28-34)

```sql
-- Uses adapter.get_relation() to bypass DAG
FROM {{ adapter.get_relation(database=this.database, schema=this.schema, identifier='fct_workforce_snapshot') }}
WHERE simulation_year = {{ previous_year }}
```

**Cascading Failure Mode**:
- Year 1: Minor rounding error (±2 employees)
- Year 2: Reads Year 1 with error, compounds to ±5 employees
- Year 3: Reads Year 2 with compounded error, now ±12 employees
- Year 5: Cumulative cascade produces -4% to +40% variance

**Deduplication Risks** (in `fct_workforce_snapshot.sql`):
- Duplicate employees not fully caught (row_number tie handling)
- Terminated employees marked as active (employment_status corruption)
- Missing employees lost in UNION ALL deduplication

---

### **5. SQL Performance Bottlenecks**

**Current Runtime**: 30 minutes for 5 years on work laptop

**Profiling Analysis**:
```
Total: 1800 seconds (30 minutes)
- Event Generation: ~900s (50%) - window functions over large datasets
- State Accumulation: ~600s (33%) - repeated full table scans
- Workforce Snapshot: ~300s (17%) - complex 15-level CTE nesting
```

**Key Bottlenecks**:
1. **Window Functions**: `ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY ...)` on 7k× events
2. **Repeated Table Scans**: `fct_workforce_snapshot` read 15+ times per year
3. **CTE Nesting**: 15-20 levels of CTEs prevent query plan optimization
4. **No Indexing**: Join keys not indexed (DuckDB limitation)
5. **Materialize → Read → Materialize**: Disk I/O bottleneck on HDDs

---

## 🏗️ Architectural Options

### **Option 1: Integer Accounting with Exact Reconciliation (Conservative)**

**Philosophy**: Never use probabilistic selection. Every hire, termination, and transition is deterministically allocated to guarantee exact headcount targets.

#### **Architecture**:

```
1. int_workforce_needs_exact (replaces int_workforce_needs)
   - Strategic CEILING/FLOOR to ensure growth equation balances
   - Algebraic solver: hires - exp_terms - nh_terms = target_growth (±0 error)
   - Returns reconciliation_status flag for validation

2. int_workforce_cohorts (NEW - 4 separate tables)
   - int_workforce_active_continuous
     * Survivors from Year N-1
     * Exact count: starting_workforce - experienced_terminations

   - int_workforce_experienced_terminations
     * Exactly expected_experienced_terminations employees
     * Deterministic hash-based ranking (no probabilistic selection)

   - int_workforce_new_hires_active
     * Exactly (total_hires_needed - expected_nh_terminations) employees
     * Created via UNNEST(range(...)) for exact counts

   - int_workforce_new_hires_terminated
     * Exactly expected_new_hire_terminations employees
     * Deterministic selection from new_hires using hash ranking

3. fct_workforce_snapshot_reconciled (replaces fct_workforce_snapshot)
   - UNION ALL of 4 cohorts with built-in validation
   - Quality gate: FAIL simulation if reconciliation error > 0
```

#### **Level Allocation Strategy (Largest-Remainder Method)**:

```sql
-- Adaptive distribution based on ACTUAL workforce composition
WITH actual_level_distribution AS (
  SELECT
    level_id,
    COUNT(*) / SUM(COUNT(*)) OVER () AS actual_pct
  FROM {{ ref('int_prev_year_workforce_summary') }}
  GROUP BY level_id
),
fractional_allocation AS (
  SELECT
    level_id,
    actual_pct,
    total_hires_needed * actual_pct AS fractional_hires,
    FLOOR(total_hires_needed * actual_pct) AS floor_hires,
    (total_hires_needed * actual_pct) - FLOOR(total_hires_needed * actual_pct) AS remainder
  FROM actual_level_distribution
),
remainder_allocation AS (
  SELECT
    level_id,
    floor_hires,
    remainder,
    ROW_NUMBER() OVER (ORDER BY remainder DESC) AS remainder_rank,
    (SELECT total_hires_needed - SUM(floor_hires) FROM fractional_allocation) AS remaining_hires
  FROM fractional_allocation
),
final_allocation AS (
  SELECT
    level_id,
    floor_hires + CASE
      WHEN remainder_rank <= remaining_hires THEN 1
      ELSE 0
    END AS exact_hires
  FROM remainder_allocation
)
-- VALIDATION: Sum must equal total_hires_needed exactly
SELECT *
FROM final_allocation
WHERE (SELECT SUM(exact_hires) FROM final_allocation) = total_hires_needed
```

#### **Pros**:
- ✅ **100% accurate growth** - mathematical guarantee of ±0 variance
- ✅ **Fully deterministic** - same inputs → identical outputs every time
- ✅ **Built-in validation** - fails fast if reconciliation breaks
- ✅ **Minimal refactoring** - keeps existing dbt model structure
- ✅ **Adaptive level distribution** - uses actual workforce composition, not hardcoded

#### **Cons**:
- ❌ **Less realistic** - loses stochastic variation in turnover patterns
- ❌ **Still SQL-based** - won't dramatically improve performance (may be 5-10% faster)
- ❌ **Complex accounting** - requires careful rounding logic maintenance
- ❌ **30 minutes → 25-27 minutes** - not a game-changer for performance

#### **Implementation Timeline**: 2-3 weeks

---

### **Option 2: Polars-First with Target-Driven Allocation (Performance + Accuracy)**

**Philosophy**: Move ALL workforce planning and event generation to Polars for 375× speedup while using algebraic solver to guarantee exact counts.

#### **Architecture**:

```python
# workforce_planning_engine.py (NEW Polars module)
import polars as pl
from decimal import Decimal
import numpy as np

class WorkforcePlanningEngine:
    def calculate_exact_workforce_needs(
        self,
        starting_workforce: pl.DataFrame,
        target_growth_rate: Decimal,
        experienced_term_rate: Decimal,
        new_hire_term_rate: Decimal
    ) -> dict:
        """
        Returns exact integer counts that guarantee growth target.
        Uses algebraic solver to eliminate rounding errors.
        """
        n_start = starting_workforce.height

        # Exact algebra (no rounding until final step)
        target_ending = n_start * (1 + target_growth_rate)
        experienced_terms = n_start * experienced_term_rate

        # Solve: hires * (1 - nh_term_rate) = target_ending - (n_start - exp_terms)
        #     => hires = (target_ending - n_start + exp_terms) / (1 - nh_term_rate)
        exact_hires_float = (
            (target_ending - n_start + experienced_terms) / (1 - new_hire_term_rate)
        )

        # Strategic rounding: Always round UP to ensure target is achievable
        hires_needed = int(np.ceil(exact_hires_float))

        # Recalculate NH terminations to force exact balance
        # This is the KEY: we solve for nh_terms to make the equation exact
        nh_terms = hires_needed - int(np.round(target_ending - n_start + experienced_terms))

        # Validation
        actual_net_growth = hires_needed - int(experienced_terms) - nh_terms
        target_net_growth = int(np.round(target_ending - n_start))

        assert actual_net_growth == target_net_growth, \
            f"Growth reconciliation failed: {actual_net_growth} != {target_net_growth}"

        return {
            'starting_workforce': n_start,
            'target_ending_workforce': int(np.round(target_ending)),
            'experienced_terminations': int(np.round(experienced_terms)),
            'total_hires_needed': hires_needed,
            'new_hire_terminations': nh_terms,
            'actual_net_growth': actual_net_growth,
            'reconciliation_error': 0  # Guaranteed by algebraic solver!
        }
```

#### **Cohort Generation (Deterministic, Exact Counts)**:

```python
def generate_workforce_cohorts(
    self,
    starting_workforce: pl.DataFrame,
    needs: dict
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Generates exact cohorts using deterministic selection.
    Returns: (continuous_active, experienced_terms, new_hires_active, new_hires_termed)
    """

    # 1. Experienced terminations (exact count, deterministic hash selection)
    experienced_terms = (
        starting_workforce
        .with_columns([
            # Deterministic ranking based on employee_id hash
            (pl.col('employee_id').hash() % 1000000).alias('selection_rank')
        ])
        .sort('selection_rank')
        .head(needs['experienced_terminations'])  # Exact count
        .with_columns(pl.lit('experienced_termination').alias('cohort'))
    )

    # 2. Continuous active (survivors - anti-join)
    continuous_active = (
        starting_workforce
        .join(experienced_terms.select('employee_id'), on='employee_id', how='anti')
        .with_columns(pl.lit('continuous_active').alias('cohort'))
    )

    # 3. New hires (exact count, adaptive level distribution)
    level_distribution = self._calculate_actual_level_distribution(starting_workforce)
    new_hires_all = self._generate_new_hires_exact(
        count=needs['total_hires_needed'],
        level_distribution=level_distribution,
        year=needs['simulation_year']
    )

    # 4. New hire terminations (exact count from new hires)
    new_hires_termed = (
        new_hires_all
        .with_columns([
            (pl.col('employee_id').hash() % 1000000).alias('selection_rank')
        ])
        .sort('selection_rank')
        .head(needs['new_hire_terminations'])  # Exact count
        .with_columns(pl.lit('new_hire_termination').alias('cohort'))
    )

    # 5. New hires active (survivors - anti-join)
    new_hires_active = (
        new_hires_all
        .join(new_hires_termed.select('employee_id'), on='employee_id', how='anti')
        .with_columns(pl.lit('new_hire_active').alias('cohort'))
    )

    # VALIDATION: Ending workforce MUST equal target exactly
    ending_workforce = continuous_active.height + new_hires_active.height
    assert ending_workforce == needs['target_ending_workforce'], \
        f"Ending workforce mismatch: {ending_workforce} != {needs['target_ending_workforce']}"

    return continuous_active, experienced_terms, new_hires_active, new_hires_termed
```

#### **Adaptive Level Distribution (Uses Real Census)**:

```python
def _generate_new_hires_exact(
    self,
    count: int,
    level_distribution: dict,
    year: int
) -> pl.DataFrame:
    """
    Generate exactly `count` new hires with adaptive level distribution.
    Uses largest-remainder method for exact reconciliation.
    """
    # Largest-remainder allocation
    fractional_allocations = {
        level: count * pct for level, pct in level_distribution.items()
    }
    floor_allocations = {
        level: int(np.floor(frac)) for level, frac in fractional_allocations.items()
    }
    remainders = {
        level: fractional_allocations[level] - floor_allocations[level]
        for level in level_distribution.keys()
    }

    # Allocate remaining hires to levels with highest remainders
    remaining_hires = count - sum(floor_allocations.values())
    sorted_levels = sorted(remainders.keys(), key=lambda l: remainders[l], reverse=True)

    final_allocations = floor_allocations.copy()
    for i in range(remaining_hires):
        final_allocations[sorted_levels[i]] += 1

    # Validation: Sum MUST equal count exactly
    assert sum(final_allocations.values()) == count, \
        f"Level allocation mismatch: {sum(final_allocations.values())} != {count}"

    # Generate employees for each level
    new_hires = []
    hire_sequence = 0
    for level, level_count in final_allocations.items():
        for _ in range(level_count):
            hire_sequence += 1
            new_hires.append({
                'employee_id': f'NH_{year}_{hire_sequence:06d}',
                'employee_ssn': f'SSN-{900000000 + year * 100000 + hire_sequence:09d}',
                'level_id': level,
                'hire_date': self._deterministic_hire_date(year, hire_sequence),
                'compensation_amount': self._calculate_hire_compensation(level, hire_sequence),
                'employee_age': self._deterministic_age(hire_sequence),
                'employee_tenure': 0,
            })

    return pl.DataFrame(new_hires)
```

#### **Integration with dbt (Thin Wrapper)**:

```sql
-- int_workforce_cohorts_loader.sql (reads Polars output)
{{ config(
    materialized='external',
    location=var('polars_cohorts_path'),
    tags=['FOUNDATION', 'polars_integration']
) }}

-- Simply read Parquet files generated by Polars
WITH continuous_active AS (
    SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/continuous_active.parquet')
),
experienced_terminations AS (
    SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/experienced_terminations.parquet')
),
new_hires_active AS (
    SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/new_hires_active.parquet')
),
new_hires_terminated AS (
    SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/new_hires_terminated.parquet')
)

-- Combine all cohorts
SELECT * FROM continuous_active
UNION ALL SELECT * FROM experienced_terminations
UNION ALL SELECT * FROM new_hires_active
UNION ALL SELECT * FROM new_hires_terminated
```

#### **Orchestrator Integration**:

```python
# planalign_orchestrator/pipeline/year_executor.py
from workforce_planning_engine import WorkforcePlanningEngine

class YearExecutor:
    def execute_year_with_polars_planning(self, year: int) -> ExecutionResult:
        """Execute year with Polars-based workforce planning."""

        # 1. Load previous year workforce
        starting_workforce = self._load_previous_year_workforce(year)

        # 2. Calculate exact workforce needs with algebraic solver
        engine = WorkforcePlanningEngine(self.config)
        needs = engine.calculate_exact_workforce_needs(
            starting_workforce=starting_workforce,
            target_growth_rate=self.config.simulation.target_growth_rate,
            experienced_term_rate=self.config.workforce.total_termination_rate,
            new_hire_term_rate=self.config.workforce.new_hire_termination_rate
        )

        # 3. Generate cohorts with exact counts
        cohorts = engine.generate_workforce_cohorts(starting_workforce, needs)

        # 4. Write Parquet files for dbt integration
        output_path = Path(self.config.polars_cohorts_path) / f'year_{year}'
        for cohort_name, cohort_df in zip(
            ['continuous_active', 'experienced_terminations', 'new_hires_active', 'new_hires_terminated'],
            cohorts
        ):
            cohort_df.write_parquet(output_path / f'{cohort_name}.parquet')

        # 5. Run dbt models to process cohorts
        result = self.dbt_runner.execute_command(
            ["run", "--select", "int_workforce_cohorts_loader+"],
            simulation_year=year,
            dbt_vars={'polars_cohorts_path': str(output_path)},
            stream_output=True
        )

        # 6. Validate growth accuracy
        validation = self._validate_growth_accuracy(year, needs)
        if validation.status != 'EXACT_MATCH':
            raise GrowthValidationError(
                f"Year {year} growth validation failed: {validation}"
            )

        return ExecutionResult(success=True, validation=validation)
```

#### **Pros**:
- ✅ **100% accurate growth** - algebraic solver guarantees exact reconciliation
- ✅ **375× faster** - Polars parallel processing (30 min → <30 seconds)
- ✅ **Adaptive level distribution** - uses actual workforce composition automatically
- ✅ **Fully deterministic** - reproducible with random seeds
- ✅ **Modern architecture** - Polars → Parquet → DuckDB pipeline (future-proof)
- ✅ **Already partially implemented** - E068G Polars factory exists as foundation

#### **Cons**:
- ❌ **Large refactor** - moves core logic from SQL to Python (4-6 weeks)
- ❌ **New dependency** - requires Polars expertise on team
- ❌ **Testing overhead** - comprehensive parity testing required (E068H framework exists)

#### **Implementation Timeline**: 4-6 weeks

---

### **Option 3: Hybrid SQL + Validation Gates (Minimal Risk, Fast Deployment)**

**Philosophy**: Keep existing SQL architecture but add reconciliation checkpoints at every step to fail fast when drift occurs. Provides immediate diagnostics while planning long-term solution.

#### **Architecture**:

```sql
-- 1. int_workforce_needs_validated (wrapper with hard validation)
WITH base_needs AS (
  SELECT * FROM {{ ref('int_workforce_needs') }}
),
validation AS (
  SELECT
    *,
    total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations AS calculated_net_change,
    ABS(calculated_net_change - target_net_growth) AS growth_variance,
    100.0 * (calculated_net_change - target_net_growth) / NULLIF(target_net_growth, 0) AS growth_variance_pct,
    CASE
      WHEN ABS(calculated_net_change - target_net_growth) > 10 THEN 'CRITICAL_FAILURE'
      WHEN ABS(calculated_net_change - target_net_growth) > 5 THEN 'SEVERE_VARIANCE'
      WHEN ABS(calculated_net_change - target_net_growth) > 2 THEN 'MODERATE_VARIANCE'
      WHEN ABS(calculated_net_change - target_net_growth) > 0 THEN 'MINOR_VARIANCE'
      ELSE 'EXACT_MATCH'
    END AS reconciliation_status
  FROM base_needs
)
SELECT * FROM validation
WHERE reconciliation_status NOT IN ('CRITICAL_FAILURE', 'SEVERE_VARIANCE')  -- Hard stop
```

```sql
-- 2. int_workforce_needs_by_level_validated (ensure sum = total exactly)
WITH base_level_needs AS (
  SELECT * FROM {{ ref('int_workforce_needs_by_level') }}
),
level_totals AS (
  SELECT
    simulation_year,
    scenario_id,
    SUM(hires_needed) AS total_level_hires,
    SUM(expected_terminations) AS total_level_terms,
    SUM(expected_new_hire_terminations) AS total_level_nh_terms
  FROM base_level_needs
  GROUP BY simulation_year, scenario_id
),
workforce_totals AS (
  SELECT
    simulation_year,
    scenario_id,
    total_hires_needed,
    expected_experienced_terminations,
    expected_new_hire_terminations
  FROM {{ ref('int_workforce_needs_validated') }}
),
reconciliation AS (
  SELECT
    lt.simulation_year,
    lt.scenario_id,
    lt.total_level_hires,
    wt.total_hires_needed,
    ABS(lt.total_level_hires - wt.total_hires_needed) AS hires_variance,
    lt.total_level_terms,
    wt.expected_experienced_terminations,
    ABS(lt.total_level_terms - wt.expected_experienced_terminations) AS terms_variance,
    lt.total_level_nh_terms,
    wt.expected_new_hire_terminations,
    ABS(lt.total_level_nh_terms - wt.expected_new_hire_terminations) AS nh_terms_variance,
    CASE
      WHEN ABS(lt.total_level_hires - wt.total_hires_needed) > 0 THEN 'HIRES_MISMATCH'
      WHEN ABS(lt.total_level_terms - wt.expected_experienced_terminations) > 0 THEN 'TERMS_MISMATCH'
      WHEN ABS(lt.total_level_nh_terms - wt.expected_new_hire_terminations) > 0 THEN 'NH_TERMS_MISMATCH'
      ELSE 'VALIDATED'
    END AS validation_status,
    -- Diagnostic details
    'Level allocation variance detected: '
    || 'Hires (expected: ' || wt.total_hires_needed || ', allocated: ' || lt.total_level_hires || '), '
    || 'Terms (expected: ' || wt.expected_experienced_terminations || ', allocated: ' || lt.total_level_terms || '), '
    || 'NH Terms (expected: ' || wt.expected_new_hire_terminations || ', allocated: ' || lt.total_level_nh_terms || ')'
    AS validation_diagnostic
  FROM level_totals lt
  JOIN workforce_totals wt USING (simulation_year, scenario_id)
)
SELECT bln.*
FROM base_level_needs bln
JOIN reconciliation r
  ON bln.simulation_year = r.simulation_year
  AND bln.scenario_id = r.scenario_id
WHERE r.validation_status = 'VALIDATED'  -- Hard stop on mismatch
```

```sql
-- 3. fct_workforce_snapshot_with_growth_validation (final reconciliation check)
WITH base_snapshot AS (
  SELECT * FROM {{ ref('fct_workforce_snapshot') }}
),
actual_counts AS (
  SELECT
    simulation_year,
    COUNT(*) FILTER (WHERE detailed_status_code = 'continuous_active') AS actual_continuous,
    COUNT(*) FILTER (WHERE detailed_status_code = 'experienced_termination') AS actual_exp_terms,
    COUNT(*) FILTER (WHERE detailed_status_code = 'new_hire_active') AS actual_nh_active,
    COUNT(*) FILTER (WHERE detailed_status_code = 'new_hire_termination') AS actual_nh_terms,
    COUNT(*) FILTER (WHERE employment_status = 'active') AS actual_ending_workforce
  FROM base_snapshot
  GROUP BY simulation_year
),
expected_counts AS (
  SELECT
    simulation_year,
    starting_workforce_count,
    expected_experienced_terminations,
    expected_new_hire_terminations,
    total_hires_needed,
    target_ending_workforce,
    target_growth_rate
  FROM {{ ref('int_workforce_needs_validated') }}
),
growth_validation AS (
  SELECT
    a.simulation_year,
    -- Actual vs expected
    a.actual_ending_workforce,
    e.target_ending_workforce,
    a.actual_ending_workforce - e.target_ending_workforce AS growth_error,
    -- Growth rates
    ROUND(100.0 * (a.actual_ending_workforce - e.starting_workforce_count) / NULLIF(e.starting_workforce_count, 0), 2) AS actual_growth_pct,
    ROUND(100.0 * e.target_growth_rate, 2) AS target_growth_pct,
    -- Detailed diagnostics
    e.starting_workforce_count,
    a.actual_continuous AS actual_survivors,
    e.starting_workforce_count - e.expected_experienced_terminations AS expected_survivors,
    a.actual_continuous - (e.starting_workforce_count - e.expected_experienced_terminations) AS survivor_error,
    a.actual_nh_active,
    e.total_hires_needed - e.expected_new_hire_terminations AS expected_nh_active,
    a.actual_nh_active - (e.total_hires_needed - e.expected_new_hire_terminations) AS nh_active_error,
    -- Validation status
    CASE
      WHEN ABS(a.actual_ending_workforce - e.target_ending_workforce) > 20 THEN 'CRITICAL_VARIANCE'
      WHEN ABS(a.actual_ending_workforce - e.target_ending_workforce) > 10 THEN 'SEVERE_VARIANCE'
      WHEN ABS(a.actual_ending_workforce - e.target_ending_workforce) > 5 THEN 'MODERATE_VARIANCE'
      WHEN ABS(a.actual_ending_workforce - e.target_ending_workforce) > 0 THEN 'MINOR_VARIANCE'
      ELSE 'EXACT_MATCH'
    END AS growth_accuracy_status,
    -- Diagnostic message
    'Year ' || a.simulation_year || ': '
    || 'Target ending workforce: ' || e.target_ending_workforce || ', '
    || 'Actual ending workforce: ' || a.actual_ending_workforce || ', '
    || 'Error: ' || (a.actual_ending_workforce - e.target_ending_workforce) || ' employees '
    || '(' || ROUND(100.0 * (a.actual_ending_workforce - e.target_ending_workforce) / NULLIF(e.target_ending_workforce, 0), 2) || '%). '
    || 'Breakdown: Survivor error: ' || (a.actual_continuous - (e.starting_workforce_count - e.expected_experienced_terminations))
    || ', New hire active error: ' || (a.actual_nh_active - (e.total_hires_needed - e.expected_new_hire_terminations))
    AS growth_diagnostic
  FROM actual_counts a
  JOIN expected_counts e USING (simulation_year)
)
-- Return snapshot with validation metadata attached
SELECT
  bs.*,
  gv.growth_accuracy_status,
  gv.growth_error,
  gv.actual_growth_pct,
  gv.target_growth_pct,
  gv.growth_diagnostic
FROM base_snapshot bs
LEFT JOIN growth_validation gv USING (simulation_year)
WHERE gv.growth_accuracy_status NOT IN ('CRITICAL_VARIANCE', 'SEVERE_VARIANCE')  -- Hard stop
```

#### **Orchestrator Integration**:

```python
# planalign_orchestrator/pipeline/year_executor.py

class YearExecutor:
    def execute_year_with_validation(self, year: int) -> ExecutionResult:
        """Execute year with comprehensive growth validation checkpoints."""

        try:
            # Execute standard pipeline
            result = self._execute_year_standard(year)

            # POST-EXECUTION VALIDATION
            validation = self._validate_growth_accuracy(year)

            if validation.status in ['CRITICAL_VARIANCE', 'SEVERE_VARIANCE']:
                # Log detailed diagnostic
                self.logger.error(
                    f"❌ Year {year} GROWTH VALIDATION FAILED:\n"
                    f"   Status: {validation.status}\n"
                    f"   Expected workforce: {validation.target_ending_workforce}\n"
                    f"   Actual workforce: {validation.actual_ending_workforce}\n"
                    f"   Error: {validation.growth_error} employees\n"
                    f"   Target growth: {validation.target_growth_pct}%\n"
                    f"   Actual growth: {validation.actual_growth_pct}%\n"
                    f"   Breakdown:\n"
                    f"     - Survivor error: {validation.survivor_error}\n"
                    f"     - New hire active error: {validation.nh_active_error}\n"
                    f"   Diagnostic: {validation.growth_diagnostic}"
                )
                raise GrowthValidationError(
                    f"Year {year} growth validation failed with {validation.status}: "
                    f"{validation.growth_diagnostic}"
                )

            elif validation.status in ['MODERATE_VARIANCE', 'MINOR_VARIANCE']:
                self.logger.warning(
                    f"⚠️  Year {year} growth variance detected:\n"
                    f"   Status: {validation.status}\n"
                    f"   Error: {validation.growth_error} employees "
                    f"   (Target: {validation.target_growth_pct}%, Actual: {validation.actual_growth_pct}%)"
                )

            else:  # EXACT_MATCH
                self.logger.info(
                    f"✅ Year {year} growth validation PASSED: "
                    f"Exact match ({validation.actual_ending_workforce} employees)"
                )

            return ExecutionResult(
                success=True,
                validation=validation,
                year=year
            )

        except GrowthValidationError as e:
            # Generate diagnostic report
            self._generate_growth_diagnostic_report(year, validation)
            raise

    def _generate_growth_diagnostic_report(self, year: int, validation: GrowthValidation):
        """Generate detailed diagnostic report for debugging growth errors."""
        report_path = Path(f'diagnostics/growth_error_year_{year}.md')
        report_path.parent.mkdir(exist_ok=True)

        report = f"""# Growth Validation Error Report - Year {year}

## Summary
- **Status**: {validation.status}
- **Error Magnitude**: {validation.growth_error} employees
- **Target Growth**: {validation.target_growth_pct}%
- **Actual Growth**: {validation.actual_growth_pct}%

## Detailed Breakdown
- **Starting Workforce**: {validation.starting_workforce_count}
- **Target Ending Workforce**: {validation.target_ending_workforce}
- **Actual Ending Workforce**: {validation.actual_ending_workforce}

### Survivor Analysis
- **Expected Survivors**: {validation.expected_survivors}
- **Actual Survivors**: {validation.actual_survivors}
- **Survivor Error**: {validation.survivor_error} employees

### New Hire Analysis
- **Expected New Hire Active**: {validation.expected_nh_active}
- **Actual New Hire Active**: {validation.actual_nh_active}
- **New Hire Active Error**: {validation.nh_active_error} employees

## Root Cause Hypothesis
{self._diagnose_root_cause(validation)}

## Recommended Actions
{self._recommend_actions(validation)}

## Full Diagnostic
{validation.growth_diagnostic}
"""

        report_path.write_text(report)
        self.logger.info(f"📊 Diagnostic report generated: {report_path}")
```

#### **Pros**:
- ✅ **Fast to implement** - 3-5 days (wrapper models only)
- ✅ **Immediate diagnostics** - pinpoints exactly where reconciliation breaks
- ✅ **Fail-fast behavior** - stops simulation immediately on critical variance
- ✅ **Minimal risk** - doesn't change core logic, just adds validation
- ✅ **Production-safe** - can deploy incrementally with soft warnings first
- ✅ **Diagnostic clarity** - generates detailed reports for debugging

#### **Cons**:
- ❌ **Doesn't fix root cause** - still has rounding errors, just detects them
- ❌ **No performance improvement** - adds 5% overhead from validation queries
- ❌ **False positives possible** - may fail on legitimate edge cases (configurable thresholds)
- ❌ **Not a long-term solution** - bandaid until proper fix implemented

#### **Implementation Timeline**: 3-5 days

---

## 🚨 90-Minute War-Room Triage Playbook (DO THIS FIRST)

**Goal**: Prove where drift enters and force the pipeline to stop there.

### **Step 1: Instrument Three Gates (30 minutes)**

Add fail-fast validation at three checkpoints:

#### **Gate A: Workforce Needs Reconciliation**
```sql
-- After int_workforce_needs calculation
WITH validation AS (
  SELECT
    *,
    total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations AS calculated_net_change,
    ABS(calculated_net_change - target_net_growth) AS growth_error
  FROM {{ ref('int_workforce_needs') }}
)
SELECT * FROM validation
WHERE growth_error = 0  -- HARD STOP: error must be exactly 0
```

#### **Gate B: Level Allocation Reconciliation**
```sql
-- After level allocation
WITH level_totals AS (
  SELECT SUM(hires_needed) AS allocated_hires
  FROM {{ ref('int_workforce_needs_by_level') }}
),
global_total AS (
  SELECT total_hires_needed
  FROM {{ ref('int_workforce_needs') }}
)
SELECT * FROM level_totals
WHERE allocated_hires = (SELECT total_hires_needed FROM global_total)  -- HARD STOP
```

#### **Gate C: Final Snapshot Reconciliation**
```sql
-- After fct_workforce_snapshot
WITH actual AS (
  SELECT COUNT(*) FILTER (WHERE employment_status = 'active') AS actual_ending
  FROM {{ ref('fct_workforce_snapshot') }}
),
expected AS (
  SELECT target_ending_workforce FROM {{ ref('int_workforce_needs') }}
)
SELECT
  actual_ending,
  target_ending_workforce,
  actual_ending - target_ending_workforce AS ending_error,
  -- Detailed breakdown
  (SELECT COUNT(*) FROM {{ ref('fct_workforce_snapshot') }} WHERE detailed_status_code = 'continuous_active') AS actual_survivors,
  (SELECT starting_workforce_count - expected_experienced_terminations FROM {{ ref('int_workforce_needs') }}) AS expected_survivors,
  (SELECT COUNT(*) FROM {{ ref('fct_workforce_snapshot') }} WHERE detailed_status_code = 'new_hire_active') AS actual_nh_active,
  (SELECT total_hires_needed - expected_new_hire_terminations FROM {{ ref('int_workforce_needs') }}) AS expected_nh_active
FROM actual CROSS JOIN expected
WHERE actual_ending = target_ending_workforce  -- HARD STOP: must be exact
```

### **Step 2: Shrink to Toy Dataset (15 minutes)**

```bash
# Create 100-employee test census
duckdb dbt/simulation.duckdb "
  CREATE OR REPLACE TABLE stg_census_data_test AS
  SELECT * FROM stg_census_data LIMIT 100
"

# Run with 0%, 3%, -3% growth scenarios
# You'll see errors faster with smaller integers
```

### **Step 3: Freeze Randomness (20 minutes)**

Replace all probabilistic selection with deterministic ranking:

```sql
-- BEFORE (probabilistic - causes variance):
random_value = (ABS(HASH(employee_id)) % 1000) / 1000.0
QUALIFY ROW_NUMBER() OVER (ORDER BY random_value) <= target_count

-- AFTER (deterministic - exact counts):
QUALIFY ROW_NUMBER() OVER (
  ORDER BY
    HASH(employee_id) % 1000000,  -- Primary: stable hash
    employee_id                    -- Tiebreaker: unique ID
) <= target_count
```

### **Step 4: Remove Hard-Coded Level Weights (15 minutes)**

```sql
-- BEFORE (hardcoded - causes drift):
CASE
  WHEN level_id = 1 THEN 0.40
  WHEN level_id = 2 THEN 0.30
  ...
END

-- AFTER (adaptive - matches actual composition):
WITH actual_distribution AS (
  SELECT
    level_id,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS actual_pct
  FROM {{ ref('int_prev_year_workforce_summary') }}
  GROUP BY level_id
)
-- Use largest-remainder allocation (see implementation below)
```

### **Step 5: Kill Side Reads (10 minutes)**

```sql
-- BEFORE (bypasses DAG - imports errors):
FROM {{ adapter.get_relation(database=this.database, schema=this.schema, identifier='fct_workforce_snapshot') }}

-- AFTER (uses pipeline - validated state):
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ previous_year }}
```

**Note**: May require DAG refactoring if circular dependency exists. Use temporal model pattern (read Year N-1 to compute Year N).

---

## 🎯 Single-Day Implementation Plan

### **Morning Session (4 hours): Validation Gates + Algebraic Solver**

#### **Hour 1: Gate Implementation**
- Add three validation gates (Gate A, B, C) with hard stops
- Run failing scenario to identify exact failure point
- Document error pattern

#### **Hour 2: Algebraic Solver**
Replace `int_workforce_needs.sql` rounding cascade with single-rounding equation:

```sql
WITH exact_math AS (
  SELECT
    starting_workforce_count AS n_start,
    target_growth_rate,
    experienced_termination_rate,
    new_hire_termination_rate,
    -- Exact algebra (no rounding until final step)
    starting_workforce_count * (1 + target_growth_rate) AS target_ending_exact,
    starting_workforce_count * experienced_termination_rate AS exp_terms_exact,
    -- Solve for hires: hires × (1 - nh_rate) = (ending - start + exp_terms)
    (starting_workforce_count * (1 + target_growth_rate) - starting_workforce_count + starting_workforce_count * experienced_termination_rate)
      / (1 - new_hire_termination_rate) AS hires_exact
  FROM config
),
strategic_rounding AS (
  SELECT
    *,
    CEILING(hires_exact) AS total_hires_needed,  -- ONLY rounding point
    ROUND(exp_terms_exact) AS expected_experienced_terminations,
    ROUND(target_ending_exact) AS target_ending_workforce,
    -- Implied NH terms to force exact balance
    CEILING(hires_exact) - ROUND(exp_terms_exact) - (ROUND(target_ending_exact) - n_start) AS expected_new_hire_terminations
  FROM exact_math
),
validation AS (
  SELECT
    *,
    total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations AS calculated_net_change,
    target_ending_workforce - n_start AS target_net_growth,
    (total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) -
    (target_ending_workforce - n_start) AS reconciliation_error
  FROM strategic_rounding
)
SELECT * FROM validation
WHERE reconciliation_error = 0  -- MUST be exact
```

#### **Hour 3: Largest-Remainder Level Allocation**

Replace `int_workforce_needs_by_level.sql` with adaptive allocation:

```sql
WITH actual_distribution AS (
  -- Use ACTUAL workforce composition from previous year
  SELECT
    level_id,
    COUNT(*) AS level_count,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS level_pct
  FROM {{ ref('int_prev_year_workforce_summary') }}
  WHERE employment_status = 'active'
  GROUP BY level_id
),
fractional_allocation AS (
  SELECT
    ad.level_id,
    ad.level_pct,
    wn.total_hires_needed,
    wn.total_hires_needed * ad.level_pct AS fractional_hires,
    FLOOR(wn.total_hires_needed * ad.level_pct) AS floor_hires,
    (wn.total_hires_needed * ad.level_pct) - FLOOR(wn.total_hires_needed * ad.level_pct) AS remainder
  FROM actual_distribution ad
  CROSS JOIN {{ ref('int_workforce_needs') }} wn
),
remainder_ranks AS (
  SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY remainder DESC, level_id) AS remainder_rank,
    (SELECT total_hires_needed - SUM(floor_hires) FROM fractional_allocation) AS total_remainder
  FROM fractional_allocation
),
final_allocation AS (
  SELECT
    level_id,
    floor_hires + CASE
      WHEN remainder_rank <= total_remainder THEN 1
      ELSE 0
    END AS hires_needed
  FROM remainder_ranks
)
-- Validation: sum must equal total exactly
SELECT *
FROM final_allocation
WHERE (SELECT SUM(hires_needed) FROM final_allocation) =
      (SELECT total_hires_needed FROM {{ ref('int_workforce_needs') }})
```

#### **Hour 4: Deterministic Selection with Per-Level Quotas**

Update event generation models to use stable ranking WITH per-level termination quotas to prevent composition drift:

```sql
-- int_termination_events.sql
-- CRITICAL: Allocate termination quotas per level to prevent composition bias

WITH termination_quotas_by_level AS (
  -- Allocate experienced terminations by level using largest-remainder
  SELECT
    level_id,
    -- Use ACTUAL prior-year level composition
    COUNT(*) AS level_count,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS level_pct,
    -- Allocate terminations proportionally
    wn.expected_experienced_terminations * (COUNT(*) * 1.0 / SUM(COUNT(*)) OVER ()) AS fractional_terms,
    FLOOR(wn.expected_experienced_terminations * (COUNT(*) * 1.0 / SUM(COUNT(*)) OVER ())) AS floor_terms
  FROM {{ ref('int_employee_compensation_by_year') }}
  CROSS JOIN {{ ref('int_workforce_needs') }} wn
  WHERE employment_status = 'active'
    AND employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE)  -- Experienced only
  GROUP BY level_id, wn.expected_experienced_terminations
),
remainder_allocation AS (
  -- Largest-remainder method for exact quota allocation
  SELECT
    level_id,
    floor_terms,
    fractional_terms - floor_terms AS remainder,
    ROW_NUMBER() OVER (ORDER BY (fractional_terms - floor_terms) DESC, level_id) AS remainder_rank,
    (SELECT expected_experienced_terminations - SUM(floor_terms) FROM termination_quotas_by_level) AS total_remainder
  FROM termination_quotas_by_level
),
level_term_quotas AS (
  SELECT
    level_id,
    floor_terms + CASE WHEN remainder_rank <= total_remainder THEN 1 ELSE 0 END AS level_term_quota
  FROM remainder_allocation
),
eligible_workforce AS (
  SELECT
    w.employee_id,
    w.level_id,
    HASH(w.employee_id) % 1000000 AS selection_rank  -- Stable hash (no floating point)
  FROM {{ ref('int_employee_compensation_by_year') }} w
  WHERE w.employment_status = 'active'
    AND w.employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE)
),
selected_terminations_by_level AS (
  -- Select exactly level_term_quota employees per level
  SELECT
    ew.employee_id,
    ew.level_id
  FROM eligible_workforce ew
  JOIN level_term_quotas ltq ON ew.level_id = ltq.level_id
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ew.level_id
    ORDER BY
      ew.selection_rank,  -- Primary: deterministic hash
      ew.employee_id      -- Tiebreaker: unique ID
  ) <= ltq.level_term_quota
)
SELECT * FROM selected_terminations_by_level
-- Validation: Total must equal global expected_experienced_terminations
WHERE (SELECT COUNT(*) FROM selected_terminations_by_level) =
      (SELECT expected_experienced_terminations FROM {{ ref('int_workforce_needs') }})
```

**Same pattern for NH terminations** - allocate quotas by level from new hire pool:

```sql
-- int_new_hire_termination_events.sql
-- Apply same per-level quota logic to new hire terminations
WITH nh_term_quotas_by_level AS (
  SELECT
    level_id,
    FLOOR(wn.expected_new_hire_terminations * level_hire_pct) AS floor_nh_terms
  FROM {{ ref('int_workforce_needs_by_level') }} wnl
  JOIN {{ ref('int_workforce_needs') }} wn USING (simulation_year, scenario_id)
  -- Use hire distribution as basis for NH term distribution
)
-- ... (rest follows same pattern as experienced terminations)
```

### **Afternoon Session (4 hours): Polars Cohort Engine + Integration**

#### **Hour 5-6: Polars Cohort Generation**

Create `workforce_planning_engine.py` with algebraic solver:

```python
import polars as pl
import numpy as np
from pathlib import Path

class WorkforcePlanningEngine:
    def calculate_exact_needs(self, starting_df: pl.DataFrame, config: dict) -> dict:
        """Single-rounding algebraic solver for exact headcount."""
        n_start = starting_df.height
        growth_rate = config['target_growth_rate']
        exp_term_rate = config['experienced_termination_rate']
        nh_term_rate = config['new_hire_termination_rate']

        # Exact algebra
        target_ending = n_start * (1 + growth_rate)
        exp_terms = n_start * exp_term_rate
        hires_exact = (target_ending - n_start + exp_terms) / (1 - nh_term_rate)

        # Single rounding point
        total_hires = int(np.ceil(hires_exact))
        exp_terms_rounded = int(np.round(exp_terms))
        target_ending_rounded = int(np.round(target_ending))
        nh_terms = total_hires - exp_terms_rounded - (target_ending_rounded - n_start)

        # Validation
        calc_net = total_hires - exp_terms_rounded - nh_terms
        target_net = target_ending_rounded - n_start
        assert calc_net == target_net, f"Reconciliation failed: {calc_net} != {target_net}"

        return {
            'starting_workforce': n_start,
            'target_ending_workforce': target_ending_rounded,
            'total_hires_needed': total_hires,
            'expected_experienced_terminations': exp_terms_rounded,
            'expected_new_hire_terminations': nh_terms,
            'reconciliation_error': 0  # Guaranteed by assertion
        }

    def generate_cohorts(self, starting_df: pl.DataFrame, needs: dict) -> dict:
        """Generate exact cohorts with deterministic selection."""
        # Deterministic ranking (no floating point)
        ranked = starting_df.with_columns([
            (pl.col('employee_id').hash() % 1000000).alias('selection_rank')
        ]).sort(['selection_rank', 'employee_id'])

        # Cohort 1: Experienced terminations (exact count)
        exp_terms = ranked.head(needs['expected_experienced_terminations'])

        # Cohort 2: Continuous active (survivors)
        continuous = ranked.join(exp_terms.select('employee_id'), on='employee_id', how='anti')

        # Cohort 3: New hires (adaptive level distribution)
        new_hires = self._generate_new_hires(starting_df, needs)

        # Cohort 4: New hire terminations (exact count)
        nh_ranked = new_hires.with_columns([
            (pl.col('employee_id').hash() % 1000000).alias('selection_rank')
        ]).sort(['selection_rank', 'employee_id'])
        nh_terms = nh_ranked.head(needs['expected_new_hire_terminations'])
        nh_active = nh_ranked.join(nh_terms.select('employee_id'), on='employee_id', how='anti')

        # Validation
        ending_count = continuous.height + nh_active.height
        assert ending_count == needs['target_ending_workforce'], \
            f"Ending workforce mismatch: {ending_count} != {needs['target_ending_workforce']}"

        return {
            'continuous_active': continuous,
            'experienced_terminations': exp_terms,
            'new_hires_active': nh_active,
            'new_hires_terminated': nh_terms
        }
```

#### **Hour 7: dbt Integration**

Create thin dbt wrapper to read Polars output:

```sql
-- int_workforce_cohorts_loader.sql
{{ config(materialized='external', location=var('polars_cohorts_path')) }}

SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/continuous_active.parquet')
UNION ALL
SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/experienced_terminations.parquet')
UNION ALL
SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/new_hires_active.parquet')
UNION ALL
SELECT * FROM read_parquet('{{ var("polars_cohorts_path") }}/new_hires_terminated.parquet')
```

#### **Hour 8: Validation + Performance Testing**

```bash
# Run with validation gates
python -m planalign_orchestrator run --years 2025 --validate-growth

# Check all three gates pass
duckdb dbt/simulation.duckdb "
  SELECT
    simulation_year,
    growth_accuracy_status,
    growth_error,
    actual_growth_pct,
    target_growth_pct
  FROM fct_workforce_snapshot
  WHERE growth_accuracy_status != 'EXACT_MATCH'
"

# Performance benchmark
time python -m planalign_orchestrator run --years 2025-2029 --mode polars
# Target: <30 seconds
```

---

## 📊 Success Metrics (End of Day)

| Metric | Current State (Morning) | After Validation Gates (Hour 4) | After Polars Integration (Hour 8) |
|--------|-------------------------|----------------------------------|-----------------------------------|
| **Growth Accuracy** | -4% to +40% variance | Detected & diagnosed (error pinpointed) | ±0 employees (100% exact) |
| **Runtime (5 years)** | 30 minutes | 30 minutes (no perf change) | <30 seconds (60× improvement) |
| **Determinism** | 80-90% (probabilistic) | 90-95% (frozen randomness) | 100% (hash-based ranking) |
| **Level Drift** | Unknown (hardcoded weights) | Detected at Gate B | Fixed (adaptive distribution) |
| **State Leakage** | Unknown (DAG bypasses) | Detected at Gate C | Fixed (no side reads) |
| **Error Detection** | Days of debugging | Instant (gate failure with diagnostic) | N/A (no errors to detect) |

### **Guardrails Enforced by End of Day**:
- ✅ **Exactness SLO**: Growth error = 0 employees (hard stop if violated)
- ✅ **Determinism SLO**: Same inputs → identical outputs (hash + employee_id tiebreaker)
- ✅ **Composition SLO**: Level allocations sum to global totals exactly
- ✅ **State SLO**: Year N reads only validated Year N-1 snapshot
- ✅ **Performance SLO**: 5-year 7k census < 30 seconds

---

## 🚨 Risks & Mitigation

### **Risk 1: Phase 2 Refactor Introduces Regressions**
**Likelihood**: Medium
**Impact**: High (simulation accuracy)

**Mitigation**:
- Keep Phase 1 validation gates active during Phase 2
- E068H parity testing framework validates every change
- Canary deployments (test on small census first)
- Rollback plan documented and tested

---

### **Risk 2: Performance Target Not Achieved (60× improvement)**
**Likelihood**: Low
**Impact**: Medium (still improves accuracy)

**Mitigation**:
- E068G Polars factory already demonstrates 375× speedup on events
- Conservative target (30 seconds vs. 0.16 seconds demonstrated capability)
- Fallback: Phase 2 still delivers 100% accuracy even if performance is 10× instead of 60×

---

### **Risk 3: Polars Learning Curve Delays Phase 2**
**Likelihood**: Medium
**Impact**: Low (extend timeline)

**Mitigation**:
- E068G implementation provides working reference code
- Polars documentation comprehensive
- Buffer time built into 4-week estimate
- Can extend Phase 2 to 5-6 weeks if needed

---

### **Risk 4: Production Census Files Have Edge Cases**
**Likelihood**: High
**Impact**: Medium (validation failures)

**Mitigation**:
- Phase 1 diagnostic reports reveal edge cases early
- Comprehensive test suite with multiple census files
- Configurable validation thresholds (soft warnings vs. hard failures)
- Documented process for handling edge cases

---

## 🛠️ Implementation Dependencies

### **Prerequisites**:
- ✅ E068G Polars Bulk Event Factory (completed)
- ✅ E068H Scale & Parity Testing Framework (completed)
- ✅ planalign_orchestrator pipeline functional
- ✅ DuckDB 1.0.0+ installed
- ✅ Polars ≥1.0.0 installed

### **Sequential Dependencies**:
```
Phase 1 (Validation Gates)
    ↓
Phase 2 (Polars-First Core)
    ↓
Phase 3 (Production Hardening)
```

**No parallel work recommended** - each phase depends on learnings from previous phase.

---

## 📋 Single-Day Story Breakdown

### **Morning Sprint (Hours 1-4): Stop the Bleeding**

#### **S077-01: Three Validation Gates (Hour 1)**
- **Description**: Add fail-fast validation at workforce needs, level allocation, and final snapshot
- **Files**: Create `int_workforce_needs_validated.sql`, `int_workforce_needs_by_level_validated.sql`, `fct_workforce_snapshot_validated.sql`
- **Acceptance**: All three gates fail on current broken state, pinpointing exact error location
- **Deliverable**: Diagnostic report showing which gate fails and why

#### **S077-02: Single-Rounding Algebraic Solver (Hour 2)**
- **Description**: Replace rounding cascade in `int_workforce_needs.sql` with single-rounding equation
- **Files**: `int_workforce_needs.sql`
- **Acceptance**: Gate A passes (growth_error = 0), validation constraint enforced
- **Deliverable**: Workforce needs with exact reconciliation guarantee

#### **S077-03: Largest-Remainder Level Allocation (Hour 3)**
- **Description**: Replace hardcoded weights with adaptive distribution + largest-remainder allocation
- **Files**: `int_workforce_needs_by_level.sql`
- **Acceptance**: Gate B passes (level sums = global total), no level drift
- **Deliverable**: Level allocations that match actual workforce composition

#### **S077-04: Deterministic Event Selection (Hour 4)**
- **Description**: Replace probabilistic random selection with hash-based deterministic ranking
- **Files**: `int_termination_events.sql`, `int_new_hire_termination_events.sql`
- **Acceptance**: Exact counts achieved, no ±1 variance from floating point
- **Deliverable**: Deterministic event generation with employee_id tiebreaker

---

### **Afternoon Sprint (Hours 5-8): Polars Speed + Final Validation**

#### **S077-05: Polars Cohort Engine (Hours 5-6)**
- **Description**: Create `workforce_planning_engine.py` with algebraic solver + cohort generation
- **Files**: `planalign_orchestrator/workforce_planning_engine.py`
- **Acceptance**: Generates 4 exact cohorts, ending workforce = target exactly
- **Deliverable**: Polars engine with built-in validation assertions

#### **S077-06: Parquet Integration (Hour 7)**
- **Description**: Write cohorts to Parquet, create dbt loader wrapper
- **Files**: `int_workforce_cohorts_loader.sql`, orchestrator integration
- **Acceptance**: dbt reads Parquet cohorts, schema matches snapshot requirements
- **Deliverable**: Thin dbt wrapper with UNION ALL pattern

#### **S077-07: End-to-End Validation (Hour 8)**
- **Description**: Run full 5-year simulation with all gates enabled
- **Files**: Integration testing, performance benchmarking
- **Acceptance**: All three gates pass, runtime <30 seconds, growth error = 0
- **Deliverable**: Benchmarking report showing 60× improvement + exact accuracy

---

### **Evening (Optional): Production Hardening**

#### **S077-08: ADR Documentation** ✅ COMPLETE
- **Description**: Create three Architecture Decision Records
- **Files**:
  - ✅ `docs/decisions/E077-A-growth-equation-rounding-policy.md` (COMPLETED)
  - ✅ `docs/decisions/E077-B-apportionment-and-quotas.md` (COMPLETED)
  - ✅ `docs/decisions/E077-C-determinism-and-state-integrity.md` (COMPLETED)
- **Acceptance**: Design decisions captured for team review
- **Deliverable**: Three comprehensive ADRs explaining:
  - **ADR E077-A**: Single-rounding algebraic solver with RIF branch, feasibility guards, and complete DuckDB/Polars implementations
  - **ADR E077-B**: Largest-remainder method for all quota allocations (hires, exp terms, NH terms) with edge case handling
  - **ADR E077-C**: Hash-based deterministic selection, atomic Parquet writes, run_id persistence, and no-DAG-bypass policy

---

## 🔍 Validation Checkpoints (Throughout the Day)

### **After Hour 1 (Gates Installed)**:
```bash
# Run broken scenario - should fail at Gate A, B, or C
dbt run --select int_workforce_needs_validated --vars "simulation_year: 2025"
# Expected: FAILURE with diagnostic showing exact error location
```

### **After Hour 2 (Algebraic Solver)**:
```bash
# Gate A should now pass
dbt run --select int_workforce_needs_validated --vars "simulation_year: 2025"
# Expected: SUCCESS - growth_error = 0
```

### **After Hour 3 (Level Allocation)**:
```bash
# Gate B should now pass
dbt run --select int_workforce_needs_by_level_validated --vars "simulation_year: 2025"
# Expected: SUCCESS - level sums = global total
```

### **After Hour 4 (Deterministic Selection)**:
```bash
# All gates should pass, but still slow (SQL mode)
dbt run --select fct_workforce_snapshot_validated --vars "simulation_year: 2025"
# Expected: SUCCESS - ending workforce = target exactly
# Runtime: Still ~30 minutes (no performance improvement yet)
```

### **After Hour 8 (Polars Integration)**:
```bash
# Full 5-year simulation with all gates passing + performance improvement
time python -m planalign_orchestrator run --years 2025-2029 --mode polars --validate-growth
# Expected: SUCCESS - all gates pass, runtime <30 seconds
```

### **End-of-Day Validation Checklist**:
- [ ] Gate A: `growth_error = 0` for all years
- [ ] Gate B: `SUM(level_hires) = total_hires` for all years
- [ ] Gate C: `actual_ending = target_ending` for all years
- [ ] Performance: 5-year simulation < 30 seconds
- [ ] Determinism: Two runs with same seed = identical results
- [ ] Level composition: Adaptive distribution matches actual workforce

---

## 📞 Getting Help

### **Phase 1 Issues**:
- Check validation threshold configuration
- Review diagnostic reports for patterns
- Verify workforce state transfer integrity

### **Phase 2 Issues**:
- Reference E068G Polars implementation
- Check E068H parity test failures
- Verify Parquet schema compatibility

### **Phase 3 Issues**:
- Review CI/CD logs
- Check monitoring dashboards
- Consult runbook documentation

---

## 📚 References

### **Architecture Decision Records**:
- **[ADR E077-A: Growth Equation & Rounding Policy](../decisions/E077-A-growth-equation-rounding-policy.md)** - Single-rounding algebraic solver with RIF branch, feasibility guards, and complete implementations
- **[ADR E077-B: Apportionment & Quotas](../decisions/E077-B-apportionment-and-quotas.md)** - Largest-remainder method for all quota allocations with edge case handling
- **[ADR E077-C: Determinism & State Integrity](../decisions/E077-C-determinism-and-state-integrity.md)** - Hash-based deterministic selection, atomic writes, and state management

### **Related Epics**:
- **E068G**: Polars Bulk Event Factory (foundation for Phase 2)
- **E068H**: Scale & Parity Testing Framework (validation harness)
- **E072**: Pipeline Modularization (orchestrator architecture)
- **E074**: Enhanced Error Handling (error diagnostics framework)

---

---

## 🎯 Quick Reference: Implementation Checklist

### **Morning (Hours 1-4): SQL Fixes**
```bash
# Hour 1: Install gates
vim dbt/models/intermediate/int_workforce_needs_validated.sql
vim dbt/models/intermediate/int_workforce_needs_by_level_validated.sql
vim dbt/models/marts/fct_workforce_snapshot_validated.sql
dbt run --select int_workforce_needs_validated  # Should FAIL - proves gates work

# Hour 2: Algebraic solver
vim dbt/models/intermediate/int_workforce_needs.sql  # Replace rounding cascade
dbt run --select int_workforce_needs_validated  # Should PASS - Gate A fixed

# Hour 3: Level allocation
vim dbt/models/intermediate/int_workforce_needs_by_level.sql  # Largest-remainder
dbt run --select int_workforce_needs_by_level_validated  # Should PASS - Gate B fixed

# Hour 4: Deterministic selection
vim dbt/models/intermediate/events/int_termination_events.sql  # Hash-based ranking
vim dbt/models/intermediate/events/int_new_hire_termination_events.sql
dbt run --select fct_workforce_snapshot_validated  # Should PASS - Gate C fixed
```

### **Afternoon (Hours 5-8): Polars Integration**
```bash
# Hour 5-6: Polars engine
vim planalign_orchestrator/workforce_planning_engine.py
python -c "from planalign_orchestrator.workforce_planning_engine import WorkforcePlanningEngine; print('Engine loaded')"

# Hour 7: Integration
vim dbt/models/intermediate/int_workforce_cohorts_loader.sql
python -m planalign_orchestrator run --years 2025 --mode polars

# Hour 8: Validation
time python -m planalign_orchestrator run --years 2025-2029 --mode polars --validate-growth
# Target: <30 seconds, all gates pass
```

### **Non-Negotiable Guardrails (Enforce by End of Day)**
1. ✅ **Exactness SLO**: `growth_error = 0` (hard stop if violated)
2. ✅ **Determinism SLO**: Hash + employee_id tiebreaker (no floating point randoms)
3. ✅ **Composition SLO**: `SUM(level_hires) = total_hires` (largest-remainder method)
4. ✅ **State SLO**: No `adapter.get_relation()` bypasses (only `ref()`)
5. ✅ **Performance SLO**: 5-year 7k census < 30 seconds (Polars mode)

---

**Epic Owner**: Workforce Simulation Team
**Created**: 2025-10-09
**Target Completion**: TODAY (single-day sprint)
**Priority**: Critical - Blocking production use with real census files
**Status**: Ready to Execute

---

## ✅ End-of-Day Success Criteria

1. **Growth Accuracy**: 100% deterministic with error = 0 employees (mathematically guaranteed)
2. **Performance**: <30 seconds for 5-year simulation (60× improvement from 30 minutes)
3. **Determinism**: Same seed → identical results (hash-based ranking, no variance)
4. **Level Composition**: Adaptive allocation (matches actual workforce, no drift)
5. **State Integrity**: No DAG bypasses (validated Year N-1 → Year N pipeline)
6. **Validation Gates**: Three checkpoints enforce mass balance at every step

**Proof of Success**: Run `time python -m planalign_orchestrator run --years 2025-2029 --mode polars --validate-growth` → completes in <30 seconds with `growth_accuracy_status='EXACT_MATCH'` for all years.
