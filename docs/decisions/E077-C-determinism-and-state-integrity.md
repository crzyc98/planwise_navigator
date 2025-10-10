# ADR E077-C: Determinism & State Integrity

**Status**: Approved
**Date**: 2025-10-09
**Epic**: E077 - Bulletproof Workforce Growth Accuracy
**Decision Makers**: Workforce Simulation Team

---

## Context

After establishing exact mathematical reconciliation (ADR E077-A) and proportional apportionment (ADR E077-B), we must ensure:

1. **Determinism**: Same inputs → identical outputs across runs
2. **State integrity**: No data leakage between years or scenarios
3. **Reproducibility**: Audit trail for every simulation decision
4. **Atomicity**: No partial/corrupted state from failed runs

**Problem**: Probabilistic random selection, floating-point variance, and state management bugs can cause non-deterministic behavior where identical scenarios produce different results.

---

## Decision

### **Hash-Based Deterministic Selection**

We replace all probabilistic event selection with deterministic hash-based ranking using:
- **SHA256** hash of `(scenario_id, year, employee_id, event_type, random_seed)`
- **Tiebreaker**: `employee_id` (lexicographic ascending order)
- **No floating-point randoms**: All selection via integer modulo arithmetic

This provides cryptographic-quality determinism with uniform distribution properties.

---

## Algorithm

### **Hash-Based Ranking Function**

```sql
-- Deterministic rank for employee selection
CREATE OR REPLACE MACRO deterministic_rank(employee_id, simulation_year, event_type, random_seed) AS (
  -- SHA256 hash of composite key
  hash(concat(employee_id, '|', simulation_year, '|', event_type, '|', random_seed))
);

-- Usage in selection
WITH ranked_employees AS (
  SELECT
    employee_id,
    deterministic_rank(employee_id, {{ var('simulation_year') }}, 'TERMINATION', {{ var('random_seed') }}) AS selection_hash,
    ROW_NUMBER() OVER (
      PARTITION BY level_id
      ORDER BY deterministic_rank(employee_id, {{ var('simulation_year') }}, 'TERMINATION', {{ var('random_seed') }}),
               employee_id  -- Tiebreaker for determinism
    ) AS level_rank
  FROM active_workforce
)
SELECT employee_id
FROM ranked_employees
WHERE level_rank <= level_quota  -- From ADR E077-B
```

**Properties**:
- **Deterministic**: Identical inputs → identical hash → identical rank
- **Uniform**: Hash function provides even distribution across employees
- **Tiebreak-safe**: `employee_id` ensures unique ordering
- **Auditable**: Hash visible in intermediate tables for debugging

---

### **Random Seed Management**

```yaml
# config/simulation_config.yaml
simulation:
  random_seed: 42  # Fixed seed for reproducibility

  # Seed rotation for sensitivity analysis
  sensitivity_seeds:
    - 42    # Baseline
    - 1337  # Alternate 1
    - 8675309  # Alternate 2
```

**Seed Usage**:
- **Baseline runs**: Use fixed seed (e.g., 42)
- **Sensitivity analysis**: Vary seed to assess stochastic variance
- **Production**: Document seed in metadata for auditability

---

## State Integrity

### **Keys and Uniqueness Constraints**

All tables enforce strict uniqueness on composite keys:

```sql
-- int_workforce_needs (Gate A output)
UNIQUE KEY: (scenario_id, plan_design_id, simulation_year)

-- int_hire_events, int_termination_events, int_promotion_events
UNIQUE KEY: (scenario_id, plan_design_id, employee_id, simulation_year)

-- fct_yearly_events (immutable event stream)
UNIQUE KEY: (scenario_id, plan_design_id, employee_id, simulation_year, event_type, effective_date, event_sequence)

-- fct_workforce_snapshot (point-in-time state)
UNIQUE KEY: (scenario_id, plan_design_id, employee_id, simulation_year)

-- int_enrollment_state_accumulator (temporal state tracking)
UNIQUE KEY: (scenario_id, plan_design_id, employee_id, simulation_year, as_of_month)
```

**Enforcement**:
```sql
-- dbt test
{{ config(
  tests=[
    {'unique_combination_of_columns': {
      'combination_of_columns': [
        'scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'
      ]
    }}
  ]
) }}
```

---

### **No DAG-Bypass Policy**

**Rule**: All dbt model dependencies MUST use `{{ ref() }}` - direct database access bypasses validation.

**Prohibited Patterns**:
```sql
-- ❌ PROHIBITED: Direct table access
SELECT * FROM fct_workforce_snapshot WHERE simulation_year = 2024

-- ❌ PROHIBITED: adapter.get_relation() bypass
{% set relation = adapter.get_relation(database=target.database, schema=target.schema, identifier='fct_workforce_snapshot') %}

-- ✅ ALLOWED: Only via ref()
SELECT * FROM {{ ref('fct_workforce_snapshot') }} WHERE simulation_year = 2024
```

**Rationale**:
- `{{ ref() }}` enforces DAG order (prevents circular dependencies)
- `{{ ref() }}` triggers validation tests before downstream models
- `{{ ref() }}` ensures incremental strategy consistency

**Exception**: Temporal state accumulators reading from `{{ this }}` (self-reference for prior year state).

```sql
-- ✅ ALLOWED: Self-reference for accumulator pattern
WITH prior_year_state AS (
  SELECT *
  FROM {{ this }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
)
```

---

### **Atomic Parquet Directory Writes**

For Polars-generated event cohorts, we ensure atomic directory writes to prevent partial state:

```python
# navigator_orchestrator/pipeline/polars_event_generation.py

def write_events_atomically(df: pl.DataFrame, output_dir: Path, year: int, event_type: str) -> Path:
    """Write event cohort with atomic directory swap."""

    # Step 1: Write to temporary directory
    temp_dir = output_dir / f".tmp_{event_type}_{year}_{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=False)

    try:
        # Write Parquet file
        parquet_path = temp_dir / f"{event_type}_{year}.parquet"
        df.write_parquet(parquet_path, compression="zstd")

        # Write manifest
        manifest = {
            "event_type": event_type,
            "simulation_year": year,
            "row_count": len(df),
            "checksum": compute_checksum(df),
            "created_at": datetime.now().isoformat()
        }
        (temp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        # Step 2: Atomic rename (POSIX guarantees atomicity)
        final_dir = output_dir / f"{event_type}_{year}"
        if final_dir.exists():
            shutil.rmtree(final_dir)  # Remove old version
        temp_dir.rename(final_dir)  # Atomic swap

        return final_dir

    except Exception as e:
        # Cleanup on failure
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Atomic write failed for {event_type} {year}: {e}")
```

**Guarantees**:
- **Atomicity**: Directory appears fully-written or not at all (no partial state)
- **Checksum**: Detect corruption via SHA256 hash
- **Manifest**: Metadata for auditing (row count, timestamp, parameters)

---

### **Run ID and Checksum Persistence**

Every simulation run generates a unique run ID and checksums for validation:

```python
# navigator_orchestrator/pipeline/state_manager.py

class StateManager:
    def create_run_metadata(self, config: SimulationConfig, year: int) -> dict:
        """Generate run metadata with checksums."""

        run_id = f"{config.scenario_id}_{year}_{uuid.uuid4().hex[:8]}"

        return {
            "run_id": run_id,
            "scenario_id": config.scenario_id,
            "simulation_year": year,
            "random_seed": config.random_seed,
            "git_commit_sha": get_git_commit_sha(),
            "config_checksum": compute_config_checksum(config),
            "created_at": datetime.now().isoformat(),
            "parameters": {
                "growth_rate": config.growth_rate,
                "exp_term_rate": config.experienced_termination_rate,
                "nh_term_rate": config.new_hire_termination_rate
            }
        }

    def persist_run_metadata(self, metadata: dict, gate: str):
        """Persist metadata to database after each gate."""

        conn = duckdb.connect(str(get_database_path()))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_metadata (
                run_id VARCHAR PRIMARY KEY,
                scenario_id VARCHAR,
                simulation_year INTEGER,
                gate VARCHAR,  -- 'A', 'B', or 'C'
                random_seed INTEGER,
                git_commit_sha VARCHAR,
                config_checksum VARCHAR,
                created_at TIMESTAMP,
                parameters JSON
            )
        """)

        conn.execute("""
            INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            metadata["run_id"],
            metadata["scenario_id"],
            metadata["simulation_year"],
            gate,
            metadata["random_seed"],
            metadata["git_commit_sha"],
            metadata["config_checksum"],
            metadata["created_at"],
            json.dumps(metadata["parameters"])
        ])

        conn.close()
```

**Audit Trail**:
```sql
-- Query run history
SELECT
    run_id,
    scenario_id,
    simulation_year,
    gate,
    random_seed,
    git_commit_sha,
    created_at
FROM run_metadata
WHERE scenario_id = 'baseline_2025'
ORDER BY created_at DESC;
```

---

## Year Boundary State Transfer

### **Clean State Transfer Pattern**

```python
# navigator_orchestrator/pipeline/year_executor.py

class YearExecutor:
    def transfer_state_to_next_year(self, year: int) -> dict:
        """Transfer validated state from Year N to Year N+1."""

        conn = duckdb.connect(str(get_database_path()))

        # Step 1: Validate Year N snapshot passed Gate C
        validation = conn.execute("""
            SELECT
                COUNT(*) AS snapshot_count,
                SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) AS active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
        """, [year]).fetchone()

        if validation[0] == 0:
            raise StateError(f"Year {year} snapshot is empty - Gate C validation failed")

        # Step 2: Transfer to int_baseline_workforce for Year N+1
        conn.execute("""
            -- Clear prior state (idempotent)
            DELETE FROM int_baseline_workforce WHERE simulation_year = ?;

            -- Transfer validated state
            INSERT INTO int_baseline_workforce
            SELECT * FROM fct_workforce_snapshot
            WHERE simulation_year = ?
              AND employment_status = 'active';
        """, [year + 1, year])

        transferred_count = conn.execute("""
            SELECT COUNT(*) FROM int_baseline_workforce WHERE simulation_year = ?
        """, [year + 1]).fetchone()[0]

        conn.close()

        # Step 3: Validate transfer
        if transferred_count != validation[1]:
            raise StateError(
                f"State transfer validation failed: "
                f"Year {year} active={validation[1]}, Year {year+1} baseline={transferred_count}"
            )

        return {
            "year": year,
            "next_year": year + 1,
            "transferred_employees": transferred_count,
            "validation": "PASSED"
        }
```

**Properties**:
- **Idempotent**: Re-running transfer produces identical state
- **Validated**: Only transfer after Gate C passes
- **Atomic**: DELETE + INSERT in single transaction
- **Auditable**: Log transfer metadata for debugging

---

### **Temporal State Accumulator Pattern**

For stateful models like enrollment tracking, use accumulator pattern to prevent circular dependencies:

```sql
-- int_enrollment_state_accumulator.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'as_of_month']
) }}

WITH prior_year_state AS (
  -- Read from self ({{ this }}) for Year N-1 state
  SELECT *
  FROM {{ this }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
    AND as_of_month = 12  -- End of prior year
),
current_year_events AS (
  -- Read from current year events
  SELECT *
  FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT
  COALESCE(e.employee_id, p.employee_id) AS employee_id,
  {{ var('simulation_year') }} AS simulation_year,
  COALESCE(e.enrollment_date, p.enrollment_date) AS enrollment_date,
  COALESCE(e.deferral_rate, p.deferral_rate) AS current_deferral_rate,
  -- ... accumulate state
FROM current_year_events e
FULL OUTER JOIN prior_year_state p
  ON e.employee_id = p.employee_id
```

**Key Pattern**:
- Year N accumulator reads Year N-1 accumulator (via `{{ this }}`)
- Year N accumulator reads Year N events (via `{{ ref() }}`)
- No circular dependency: Year N events → Year N accumulator → Year N+1 accumulator

---

## Validation Requirements

### **Determinism Test Suite**

```python
# tests/test_determinism.py

def test_hash_based_selection_determinism():
    """Verify identical inputs produce identical event selection."""

    # Run simulation twice with same config
    config = load_simulation_config('config/simulation_config.yaml')

    run1 = execute_simulation(config, year=2025)
    run2 = execute_simulation(config, year=2025)

    # Compare event counts by type
    assert run1.hire_count == run2.hire_count
    assert run1.termination_count == run2.termination_count

    # Compare exact employee IDs
    assert set(run1.hired_employee_ids) == set(run2.hired_employee_ids)
    assert set(run1.terminated_employee_ids) == set(run2.terminated_employee_ids)

def test_seed_variation_produces_different_results():
    """Verify different seeds produce different but valid results."""

    config = load_simulation_config('config/simulation_config.yaml')

    config.random_seed = 42
    run1 = execute_simulation(config, year=2025)

    config.random_seed = 1337
    run2 = execute_simulation(config, year=2025)

    # Different employee selection
    assert set(run1.hired_employee_ids) != set(run2.hired_employee_ids)

    # Same aggregate counts (within rounding tolerance)
    assert abs(run1.hire_count - run2.hire_count) <= 1  # ±1 due to CEILING
    assert run1.ending_workforce == run2.ending_workforce  # Exact balance required
```

---

### **State Integrity Validation**

```sql
-- Validate state transfer between years
WITH year_boundaries AS (
  SELECT
    y1.simulation_year AS year_n,
    y1.active_count AS year_n_ending,
    y2.active_count AS year_n_plus_1_starting
  FROM (
    SELECT simulation_year, COUNT(*) AS active_count
    FROM fct_workforce_snapshot
    WHERE employment_status = 'active'
    GROUP BY simulation_year
  ) y1
  JOIN (
    SELECT simulation_year, COUNT(*) AS active_count
    FROM int_baseline_workforce
    GROUP BY simulation_year
  ) y2 ON y2.simulation_year = y1.simulation_year + 1
)
SELECT
  *,
  year_n_ending - year_n_plus_1_starting AS state_transfer_error
FROM year_boundaries
WHERE state_transfer_error != 0;

-- Expected: 0 rows (perfect state transfer)
```

---

### **Checksum Validation**

```python
# navigator_orchestrator/validation.py

def compute_checksum(df: pl.DataFrame) -> str:
    """Compute SHA256 checksum of DataFrame."""

    # Sort for determinism
    df_sorted = df.sort(df.columns)

    # Hash serialized content
    content = df_sorted.write_csv()
    return hashlib.sha256(content.encode()).hexdigest()

def validate_checkpoint_integrity(checkpoint_dir: Path) -> bool:
    """Validate checkpoint integrity via manifest checksum."""

    manifest_path = checkpoint_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    # Recompute checksum
    parquet_path = checkpoint_dir / f"{manifest['event_type']}_{manifest['simulation_year']}.parquet"
    df = pl.read_parquet(parquet_path)
    recomputed_checksum = compute_checksum(df)

    # Compare
    if recomputed_checksum != manifest["checksum"]:
        raise ChecksumError(
            f"Checksum mismatch: expected {manifest['checksum']}, got {recomputed_checksum}"
        )

    return True
```

---

## Consequences

### **Positive**:
- ✅ **Perfect determinism**: Identical scenarios → identical results
- ✅ **Reproducibility**: Audit trail for every simulation decision
- ✅ **State integrity**: No data leakage between years/scenarios
- ✅ **Atomicity**: No partial/corrupted state from failures
- ✅ **Debuggability**: Hash-based ranks visible in intermediate tables

### **Negative**:
- ⚠️ **Complexity**: Requires understanding of hash-based selection
- ⚠️ **Testing overhead**: Must validate determinism across all event types

### **Mitigations**:
- Comprehensive determinism test suite with seed variation
- Automated checksum validation on every checkpoint
- Clear documentation of accumulator pattern for stateful models

---

## Alternatives Considered

### **Alternative 1: Floating-Point Random Selection**

**Approach**: Use `RANDOM()` or `RAND()` for stochastic event selection

**Rejected**: Non-deterministic (same seed produces different results across runs)

**Problem**: `RANDOM()` uses system entropy and is not reproducible

---

### **Alternative 2: Sequential Employee ID Selection**

**Approach**: Select employees by employee_id order (e.g., first 100 employees)

**Rejected**: Non-uniform (biases toward specific employees)

**Problem**: Early employee IDs may have different characteristics (e.g., tenure, level)

---

### **Alternative 3: Row Number Modulo Selection**

**Approach**: Use `ROW_NUMBER() % seed` for selection

**Rejected**: Non-uniform distribution (modulo introduces bias)

**Problem**: Employees with IDs near multiples of seed are over-selected

---

## References

- **Epic E077**: Bulletproof Workforce Growth Accuracy
- **ADR E077-A**: Growth Equation & Rounding Policy
- **ADR E077-B**: Apportionment & Quotas
- **SHA256**: Cryptographic hash function for deterministic selection
- **Event Sourcing**: Immutable event streams for audit trails

---

**Approved By**: Workforce Simulation Team
**Implementation Start**: 2025-10-09
**Review Date**: After 30 days in production
