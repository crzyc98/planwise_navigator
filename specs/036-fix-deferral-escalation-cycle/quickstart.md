# Quickstart: Fix Deferral Rate Escalation Circular Dependency

**Feature**: 036-fix-deferral-escalation-cycle
**Date**: 2026-02-07

## What This Feature Does

Enables the automatic annual deferral rate escalation feature (Epic E035) by activating the corrected `int_deferral_rate_escalation_events` model. This model was disabled due to a circular dependency with `fct_workforce_snapshot`. The corrected version breaks the cycle by reading prior-year state from `int_deferral_rate_state_accumulator_v2` via a direct table reference.

## Key Files

| File | Role |
|------|------|
| `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql` | Corrected escalation event generator (ephemeral) |
| `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql` | Temporal state accumulator (incremental) |
| `config/simulation_config.yaml` (lines 639-651) | Escalation configuration parameters |
| `planalign_orchestrator/pipeline/workflow.py` (line 169) | Pipeline stage ordering |

## Verification Steps

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Verify dbt compiles without circular dependency errors
cd dbt && dbt compile --threads 1

# 3. Run single-year simulation with escalation enabled
cd .. && planalign simulate 2025

# 4. Check that escalation events were generated
duckdb dbt/simulation.duckdb "
  SELECT COUNT(*) as escalation_count
  FROM fct_yearly_events
  WHERE event_type = 'deferral_escalation'
    AND simulation_year = 2025
"

# 5. Run multi-year simulation
planalign simulate 2025-2027

# 6. Verify rate accumulation across years
duckdb dbt/simulation.duckdb "
  SELECT
    employee_id,
    simulation_year,
    current_deferral_rate,
    escalations_received
  FROM int_deferral_rate_state_accumulator_v2
  WHERE escalations_received > 0
  ORDER BY employee_id, simulation_year
  LIMIT 20
"

# 7. Run tests
cd dbt && dbt test --select tag:escalation --threads 1
cd .. && pytest tests/test_escalation_events.py -v
```

## Configuration

Escalation behavior is controlled via `config/simulation_config.yaml`:

```yaml
deferral_auto_escalation:
  enabled: true              # Master on/off switch
  effective_day: "01-01"     # MM-DD for escalation date
  increment_amount: 0.01     # Annual increment (1%)
  maximum_rate: 0.10         # Rate cap (10%)
  hire_date_cutoff: "2020-01-01"  # Only employees hired on/after this date
  require_active_enrollment: true  # Must be enrolled to escalate
  first_escalation_delay_years: 1  # Years to wait after enrollment
```

## Architecture Notes

**Cycle-breaking pattern**: The escalation model reads Year N-1 state from `int_deferral_rate_state_accumulator_v2` using `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` (direct table reference) instead of `{{ ref() }}`. This hides the dependency from dbt's DAG parser. The orchestrator pipeline guarantees correct execution order:

1. Year N-1: STATE_ACCUMULATION stage builds the accumulator
2. Year N: EVENT_GENERATION stage runs escalation model (reads N-1 accumulator)
3. Year N: STATE_ACCUMULATION stage rebuilds accumulator with N's escalation events
