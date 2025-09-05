# Epic E068F: Determinism & Developer Ergonomics (Debug Mode, RNG, Ordering)

## Goal
Keep outputs reproducible and make the fused design easy to debug.

## Scope
- **In**: hash-based RNG macro; explicit ORDER BY in writers; debug wrappers per event branch; dev_subset flags.
- **Out**: Changing core hazard math.

## Deliverables
- `macros/rand_uniform.sql` (row-stable RNG); documented key: (employee_id, sim_year, event_type[, salt]).
- Debug models `models/debug/debug_<event>_events.sql` materializing one branch.
- Flags: debug_event, dev_employee_limit / dev_subset_pct.

## Acceptance Criteria
- Byte-identical outputs with fixed seed.
- Each debug branch builds in < 5s on 5k×1yr slice.
- Uniqueness tests pass: (employee_id, sim_year, event_type[, event_seq]).

## Implementation Details

### Hash-based RNG Macro
```sql
-- macros/utils/rand_uniform.sql
{% macro hash_rng(employee_id, simulation_year, event_type, salt='') %}
  {#-
    Generate deterministic random number between 0 and 1 using hash function

    Parameters:
    - employee_id: Employee identifier
    - simulation_year: Year of simulation
    - event_type: Type of event (hire, termination, promotion, etc.)
    - salt: Additional randomization salt (optional)

    Returns: Uniform random number between 0.0 and 1.0

    The hash key ensures deterministic results across runs while providing
    independent random numbers for each employee/year/event combination.
  #}

  (
    -- Use DuckDB's hash function for deterministic random generation
    -- Combine all input parameters into a single hash key
    hash(
      CONCAT(
        CAST({{ employee_id }} AS VARCHAR),
        '|',
        CAST({{ simulation_year }} AS VARCHAR),
        '|',
        '{{ event_type }}',
        {% if salt %}
        '|',
        '{{ salt }}'
        {% endif %}
      )
    ) % 2147483647  -- Use large prime to avoid modulo bias
  ) / 2147483647.0  -- Normalize to [0, 1)

{% endmacro %}


-- macros/utils/hash_shard.sql
{% macro hash_shard(employee_id, total_shards) %}
  {#-
    Assign employee to shard using consistent hash function

    Parameters:
    - employee_id: Employee identifier
    - total_shards: Total number of shards

    Returns: Shard number (0 to total_shards-1)
  #}

  hash(CAST({{ employee_id }} AS VARCHAR)) % {{ total_shards }}

{% endmacro %}


-- macros/utils/generate_event_uuid.sql
{% macro generate_event_uuid() %}
  {#-
    Generate deterministic UUID for events based on content hash
    Ensures same events get same UUIDs across runs for reproducibility
  #}

  CONCAT(
    'evt-',
    SUBSTR(
      hash(
        CONCAT(
          CAST(scenario_id AS VARCHAR),
          '|',
          CAST(plan_design_id AS VARCHAR),
          '|',
          CAST(employee_id AS VARCHAR),
          '|',
          CAST(simulation_year AS VARCHAR),
          '|',
          event_type,
          '|',
          CAST(event_date AS VARCHAR)
        )
      )::VARCHAR,
      1, 16
    )
  )

{% endmacro %}
```

### Debug Model Templates
```sql
-- models/debug/debug_hire_events.sql
{{ config(
  materialized='table' if var('debug_event') == 'hire' else 'ephemeral',
  tags=['DEBUG', 'EVENT_GENERATION'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('debug_event', '') == 'hire' or var('enable_debug_models', false) %}

WITH cohort_debug AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    level,
    department,
    hire_date,
    -- Debug: Show RNG calculation step by step
    {{ hash_rng('employee_id', var('simulation_year'), 'hire') }} AS hire_rng,
    {{ var('hire_rate', 0.15) }} AS hire_threshold,
    CASE
      WHEN {{ hash_rng('employee_id', var('simulation_year'), 'hire') }} < {{ var('hire_rate', 0.15) }}
      THEN 'HIRED'
      ELSE 'NO_HIRE'
    END AS hire_decision
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    {% if var('debug_employee_id') %}
      AND employee_id = '{{ var("debug_employee_id") }}'
    {% endif %}
    {% if var('dev_employee_limit') %}
      LIMIT {{ var('dev_employee_limit') }}
    {% endif %}
),

hire_events_debug AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    'hire' AS event_type,
    DATE('{{ var("simulation_year") }}-06-15') AS event_date,  -- Mid-year assumption
    JSON_OBJECT(
      'level', level,
      'department', department,
      'starting_salary', 50000  -- Simplified for debug
    ) AS event_payload,
    -- Debug fields
    hire_rng,
    hire_threshold,
    hire_decision,
    'DEBUG: hire_rng=' || CAST(hire_rng AS VARCHAR) ||
    ', threshold=' || CAST(hire_threshold AS VARCHAR) ||
    ', decision=' || hire_decision AS debug_info
  FROM cohort_debug
  WHERE hire_decision = 'HIRED'
)

SELECT
  {{ generate_event_uuid() }} AS event_id,
  scenario_id,
  plan_design_id,
  employee_id,
  event_type,
  event_date,
  event_payload,
  {{ var('simulation_year') }} AS simulation_year,
  CURRENT_TIMESTAMP AS created_at,
  -- Debug information
  hire_rng,
  hire_threshold,
  debug_info
FROM hire_events_debug
ORDER BY employee_id

{% else %}

-- Placeholder when debug not enabled
SELECT
  NULL AS event_id,
  NULL AS scenario_id,
  NULL AS plan_design_id,
  NULL AS employee_id,
  NULL AS event_type,
  NULL AS event_date,
  NULL AS event_payload,
  NULL AS simulation_year,
  NULL AS created_at
WHERE 1=0

{% endif %}
```

```sql
-- models/debug/debug_termination_events.sql
{{ config(
  materialized='table' if var('debug_event') == 'termination' else 'ephemeral',
  tags=['DEBUG', 'EVENT_GENERATION'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('debug_event', '') == 'termination' or var('enable_debug_models', false) %}

WITH cohort_debug AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    level,
    tenure_months,
    performance_tier,
    -- Debug termination probability calculation
    {{ hash_rng('employee_id', var('simulation_year'), 'termination') }} AS term_rng,

    -- Simplified termination rate for debug (replace with actual hazard logic)
    CASE
      WHEN tenure_months < 12 THEN 0.15  -- High for new employees
      WHEN performance_tier = 'low' THEN 0.25
      ELSE 0.08  -- Base rate
    END AS termination_probability,

    CASE
      WHEN {{ hash_rng('employee_id', var('simulation_year'), 'termination') }} <
           CASE
             WHEN tenure_months < 12 THEN 0.15
             WHEN performance_tier = 'low' THEN 0.25
             ELSE 0.08
           END
      THEN 'TERMINATED'
      ELSE 'RETAINED'
    END AS termination_decision

  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND hire_date IS NOT NULL  -- Only existing employees can terminate
    {% if var('debug_employee_id') %}
      AND employee_id = '{{ var("debug_employee_id") }}'
    {% endif %}
    {% if var('dev_employee_limit') %}
      LIMIT {{ var('dev_employee_limit') }}
    {% endif %}
)

SELECT
  {{ generate_event_uuid() }} AS event_id,
  scenario_id,
  plan_design_id,
  employee_id,
  'termination' AS event_type,
  DATE('{{ var("simulation_year") }}-09-15') AS event_date,  -- Fall assumption
  JSON_OBJECT(
    'reason', 'voluntary',
    'level', level,
    'tenure_months', tenure_months
  ) AS event_payload,
  {{ var('simulation_year') }} AS simulation_year,
  CURRENT_TIMESTAMP AS created_at,
  -- Debug fields
  term_rng,
  termination_probability,
  termination_decision,
  'DEBUG: term_rng=' || CAST(term_rng AS VARCHAR) ||
  ', prob=' || CAST(termination_probability AS VARCHAR) ||
  ', decision=' || termination_decision AS debug_info
FROM cohort_debug
WHERE termination_decision = 'TERMINATED'
ORDER BY employee_id

{% else %}

SELECT
  NULL AS event_id,
  NULL AS scenario_id,
  NULL AS plan_design_id,
  NULL AS employee_id,
  NULL AS event_type,
  NULL AS event_date,
  NULL AS event_payload,
  NULL AS simulation_year,
  NULL AS created_at
WHERE 1=0

{% endif %}
```

### Developer Subset Controls
```sql
-- macros/utils/apply_dev_subset.sql
{% macro apply_dev_subset(base_query) %}
  {#-
    Apply development subset controls to limit data processing

    Parameters:
    - base_query: Base SQL query to apply subset to

    Variables:
    - dev_employee_limit: Limit to N employees (exact count)
    - dev_subset_pct: Limit to percentage of employees (0.0-1.0)
    - dev_employee_ids: Specific list of employee IDs to include
  #}

  WITH base_data AS (
    {{ base_query }}
  ),

  subset_data AS (
    SELECT *
    FROM base_data
    WHERE 1=1
      {% if var('dev_employee_ids') %}
        AND employee_id IN ({{ var('dev_employee_ids') }})
      {% elif var('dev_subset_pct') %}
        AND {{ hash_rng('employee_id', 0, 'subset') }} < {{ var('dev_subset_pct') }}
      {% endif %}
    {% if var('dev_employee_limit') %}
      LIMIT {{ var('dev_employee_limit') }}
    {% endif %}
  )

  SELECT * FROM subset_data

{% endmacro %}
```

### Deterministic Ordering Utilities
```sql
-- macros/utils/deterministic_order.sql
{% macro deterministic_order_by(primary_keys=[], secondary_keys=[]) %}
  {#-
    Generate deterministic ORDER BY clause for reproducible results

    Parameters:
    - primary_keys: List of primary sort columns
    - secondary_keys: List of secondary sort columns for tie-breaking
  #}

  ORDER BY
    {% for key in primary_keys %}
      {{ key }}{{ ',' if not loop.last or secondary_keys }}
    {% endfor %}
    {% for key in secondary_keys %}
      {{ key }}{{ ',' if not loop.last }}
    {% endfor %}
    {% if not primary_keys and not secondary_keys %}
      1  -- Fallback to constant ordering
    {% endif %}

{% endmacro %}

-- Usage:
-- {{ deterministic_order_by(['employee_id', 'simulation_year'], ['event_type', 'event_date']) }}
```

### Debug Configuration and Testing
```yaml
# Debug configuration in dbt_project.yml
vars:
  # Debug mode controls
  enable_debug_models: false
  debug_event: null  # Set to 'hire', 'termination', 'promotion', etc.
  debug_employee_id: null  # Focus on specific employee

  # Development subset controls
  dev_employee_limit: null  # Limit to N employees
  dev_subset_pct: null     # Limit to percentage (0.0-1.0)
  dev_employee_ids: null   # Specific employee ID list

  # Determinism controls
  random_seed: 12345      # Fixed seed for reproducibility
  preserve_order: true    # Ensure deterministic ordering
```

```bash
# Debug usage examples

# Debug hire events for specific employee
dbt run --select debug_hire_events \
  --vars '{"debug_event": "hire", "debug_employee_id": "EMP_001", "simulation_year": 2025}'

# Debug termination with small employee subset
dbt run --select debug_termination_events \
  --vars '{"debug_event": "termination", "dev_employee_limit": 100, "simulation_year": 2025}'

# Test determinism across runs
for i in {1..3}; do
  echo "Run $i:"
  dbt run --select fct_yearly_events \
    --vars '{"simulation_year": 2025, "random_seed": 12345}' \
    --full-refresh > run_$i.log

  # Compare event counts
  duckdb dbt/simulation.duckdb "SELECT event_type, COUNT(*) FROM fct_yearly_events GROUP BY event_type ORDER BY event_type"
done

# All runs should produce identical results
```

### Reproducibility Testing Framework
```python
# tests/determinism_test.py
import subprocess
import hashlib
from pathlib import Path
import pytest

class DeterminismTester:
    def __init__(self, simulation_year: int = 2025, random_seed: int = 12345):
        self.simulation_year = simulation_year
        self.random_seed = random_seed

    def run_simulation(self, run_id: str) -> str:
        """Run simulation and return hash of results."""

        # Run dbt with fixed seed
        cmd = [
            "dbt", "run",
            "--select", "fct_yearly_events",
            "--vars", f'{{"simulation_year": {self.simulation_year}, "random_seed": {self.random_seed}}}',
            "--full-refresh"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd="dbt")
        if result.returncode != 0:
            raise RuntimeError(f"dbt run failed: {result.stderr}")

        # Get results hash
        return self.compute_results_hash()

    def compute_results_hash(self) -> str:
        """Compute hash of simulation results for comparison."""

        import duckdb

        conn = duckdb.connect("dbt/simulation.duckdb")

        # Get deterministic result set
        query = """
        SELECT
          employee_id,
          event_type,
          event_date,
          simulation_year,
          -- Hash event_payload for consistent comparison
          hash(event_payload) as payload_hash
        FROM fct_yearly_events
        WHERE simulation_year = ?
        ORDER BY employee_id, event_type, event_date
        """

        results = conn.execute(query, [self.simulation_year]).fetchall()
        conn.close()

        # Create reproducible hash of all results
        results_str = '|'.join(str(row) for row in results)
        return hashlib.sha256(results_str.encode()).hexdigest()

    def test_reproducibility(self, num_runs: int = 3) -> bool:
        """Test that multiple runs produce identical results."""

        hashes = []
        for i in range(num_runs):
            print(f"Running simulation {i+1}/{num_runs}...")
            run_hash = self.run_simulation(f"run_{i+1}")
            hashes.append(run_hash)
            print(f"Results hash: {run_hash[:16]}...")

        # All hashes should be identical
        if len(set(hashes)) == 1:
            print("✅ All runs produced identical results - determinism verified!")
            return True
        else:
            print("❌ Runs produced different results - determinism failure!")
            for i, h in enumerate(hashes):
                print(f"  Run {i+1}: {h}")
            return False

def test_event_determinism():
    """Test that event generation is deterministic."""
    tester = DeterminismTester(simulation_year=2025, random_seed=42)
    assert tester.test_reproducibility(num_runs=3)

def test_cross_seed_independence():
    """Test that different seeds produce different results."""
    tester1 = DeterminismTester(simulation_year=2025, random_seed=12345)
    tester2 = DeterminismTester(simulation_year=2025, random_seed=54321)

    hash1 = tester1.run_simulation("seed1")
    hash2 = tester2.run_simulation("seed2")

    assert hash1 != hash2, "Different seeds should produce different results"
    print("✅ Different seeds produce independent results")

if __name__ == "__main__":
    print("Testing determinism...")
    test_event_determinism()
    test_cross_seed_independence()
    print("All determinism tests passed!")
```

### Production Ordering Enforcement
```sql
-- macros/utils/enforce_deterministic_output.sql
{% macro enforce_deterministic_output(model_sql) %}
  {#-
    Wrap model SQL to enforce deterministic output ordering
    Used in production models to ensure consistent results
  #}

  WITH model_output AS (
    {{ model_sql }}
  )

  SELECT *
  FROM model_output
  {{ deterministic_order_by(['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'], ['event_type', 'event_date']) }}

{% endmacro %}

-- Usage in fct_yearly_events.sql:
-- SELECT ... FROM final_events
-- becomes:
-- {{ enforce_deterministic_output('SELECT ... FROM final_events') }}
```

## Success Metrics
- Determinism: 100% identical results across runs with same seed
- Debug performance: Debug models complete in <5s for 5k employees
- Developer productivity: Debug/subset modes reduce development cycle time by 60%
- Reproducibility: Cross-environment result consistency maintained

## Dependencies
- DuckDB hash() function for deterministic random generation
- dbt variable system for debug controls
- Python testing framework for determinism validation

## Risk Mitigation
- **RNG quality**: Use well-tested hash functions, validate distribution properties
- **Performance impact**: Debug modes disabled by default in production
- **Ordering consistency**: Explicit ORDER BY in all final writers
- **Seed management**: Document seed usage and provide seed rotation utilities

---

**Epic**: E068F
**Parent Epic**: E068 - Database Query Optimization
**Status**: ✅ COMPLETED
**Priority**: High (Critical for other epics)
**Estimated Effort**: 3 story points
**Target Performance**: Maintain determinism while enabling debug capabilities
**Completion Date**: 2025-01-05
**Implementation Summary**: See `/E068F_IMPLEMENTATION_SUMMARY.md` for complete details
