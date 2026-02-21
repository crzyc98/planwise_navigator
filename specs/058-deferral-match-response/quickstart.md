# Quickstart: Match-Responsive Deferral Adjustments

**Feature**: `058-deferral-match-response`

## Prerequisites

```bash
source .venv/bin/activate
planalign health  # Verify environment
```

## Implementation Order

### Step 1: Configuration (Python)

1. Add `DeferralMatchResponseSettings` to `planalign_orchestrator/config/workforce.py`
2. Add export function to `planalign_orchestrator/config/export.py`
3. Add `deferral_match_response:` section to `config/simulation_config.yaml`
4. Verify: `python -c "from planalign_orchestrator.config import load_simulation_config; c = load_simulation_config('config/simulation_config.yaml'); print(c.deferral_match_response)"`

### Step 2: Event Model (dbt SQL)

1. Create `dbt/models/intermediate/events/int_deferral_match_response_events.sql`
2. Add to pipeline: `planalign_orchestrator/pipeline/workflow.py` (EVENT_GENERATION stage, after enrollment events)
3. Add schema tests to `dbt/models/intermediate/events/schema.yml`
4. Verify: `cd dbt && dbt run --select int_deferral_match_response_events --vars "simulation_year: 2025" --threads 1`

### Step 3: State Accumulator Integration (dbt SQL)

1. Modify `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql`:
   - Add `match_response_events` CTE
   - Add `employee_match_response_summary` CTE
   - Update `final_state` COALESCE with additive escalation logic
   - Add LEFT JOIN for match-response summary
2. Verify: `cd dbt && dbt run --select int_deferral_rate_state_accumulator_v2+ --vars "simulation_year: 2025" --threads 1`

### Step 4: Tests

1. Create `dbt/tests/data_quality/test_deferral_match_response.sql`
2. Create `tests/test_match_response_events.py`
3. Update `fct_yearly_events` accepted_values test to include `'deferral_match_response'`
4. Verify: `cd dbt && dbt test --select test_deferral_match_response --threads 1`
5. Verify: `pytest tests/test_match_response_events.py -v`

### Step 5: End-to-End Validation

```bash
# Run full simulation with feature enabled
planalign simulate 2025 --verbose

# Check events generated
python3 -c "
import duckdb
conn = duckdb.connect('dbt/simulation.duckdb', read_only=True)
print(conn.execute(\"\"\"
  SELECT event_type, COUNT(*) as count,
         AVG(employee_deferral_rate) as avg_new_rate,
         AVG(prev_employee_deferral_rate) as avg_prev_rate
  FROM fct_yearly_events
  WHERE event_type = 'deferral_match_response'
  GROUP BY event_type
\"\"\").fetchdf())
conn.close()
"

# Verify disabled mode produces no events
# (set enabled: false in config, re-run, check count = 0)
```

## Key Files Reference

| File | Role |
|------|------|
| `planalign_orchestrator/config/workforce.py` | Pydantic config model |
| `planalign_orchestrator/config/export.py` | Config → dbt variable export |
| `config/simulation_config.yaml` | YAML configuration |
| `dbt/models/intermediate/events/int_deferral_match_response_events.sql` | Event generation (NEW) |
| `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql` | State merge (MODIFIED) |
| `planalign_orchestrator/pipeline/workflow.py` | Pipeline ordering (MODIFIED) |
| `dbt/models/intermediate/events/schema.yml` | Schema tests (MODIFIED) |
| `dbt/tests/data_quality/test_deferral_match_response.sql` | Data quality tests (NEW) |
| `tests/test_match_response_events.py` | Python integration tests (NEW) |

## Reference Patterns

- **Escalation events**: `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql` — same materialization, config access, and accumulator integration pattern
- **Enrollment optimization**: `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` line 199 — deterministic hash and match cap clustering logic
- **Config export**: `planalign_orchestrator/config/export.py` `_export_employer_match_vars()` — pattern for exporting nested config to flat dbt variables
