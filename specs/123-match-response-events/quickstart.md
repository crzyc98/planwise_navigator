# Quickstart: Verify Match-Response Deferral Events (Studio path)

**Feature**: 123-match-response-events | **Date**: 2026-07-23

Reproduce the defect, then verify the fix. All validation uses an **isolated** database, never the shared `dbt/simulation.duckdb`.

## 1. Reproduce (current defect)

A Studio/workspace scenario with no `deferral_match_response` block produces zero match-response events even with an eligible population.

```bash
# Build an isolated scenario DB from a Studio-shaped config that has a match
# formula (so a below-threshold population exists) but no deferral_match_response block.
DATABASE_PATH=/tmp/mr/iso.duckdb \
  planalign simulate 2025-2026 --config /tmp/mr/studio_no_block.yaml --database /tmp/mr/iso.duckdb

# Expect: 0 rows (the bug)
duckdb /tmp/mr/iso.duckdb \
  "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'deferral_match_response'"
```

## 2. Confirm the config signal

```bash
# The resolved dbt vars should show the feature OFF (and, after the fix, always be explicit).
python - <<'PY'
from planalign_orchestrator.config.loader import load_simulation_config
from planalign_orchestrator.config.export import to_dbt_vars
cfg = load_simulation_config("/tmp/mr/studio_no_block.yaml")
print("enabled var:", to_dbt_vars(cfg).get("deferral_match_response_enabled"))
PY
```

## 3. Verify the fix

With the resolution fix, a Studio scenario that enables match response (top-level block **or** `dc_plan.deferral_match_response.enabled: true`) generates first-year events.

```bash
DATABASE_PATH=/tmp/mr/iso_on.duckdb \
  planalign simulate 2025-2026 --config /tmp/mr/studio_enabled.yaml --database /tmp/mr/iso_on.duckdb

# C1/C2: first-year events exist with the correct category/details
duckdb /tmp/mr/iso_on.duckdb "
  SELECT simulation_year, COUNT(*) AS n,
         MIN(event_category) AS cat,
         BOOL_AND(event_details LIKE 'Match response:%') AS details_ok
  FROM fct_yearly_events
  WHERE event_type = 'deferral_match_response'
  GROUP BY simulation_year ORDER BY simulation_year"
# Expect: only 2025 has n > 0, cat = 'match_response', details_ok = true

# C3: later years produce none  → the 2026 row above must be absent.
# C5: no current-year new hires among responders
duckdb /tmp/mr/iso_on.duckdb "
  SELECT COUNT(*) AS nh_leak FROM fct_yearly_events
  WHERE event_type = 'deferral_match_response'
    AND employee_id LIKE 'NH_2025_%'"   # Expect: 0
```

## 4. Regression suite

```bash
# Config-path + export contracts (fast)
pytest -m fast -k "match_response and (resolution or config_export)"

# Fact-table integration (isolated DB, deterministic exact count)
pytest tests/integration/test_match_response_fact_integration.py -v
```

## Pass criteria (maps to spec Success Criteria)

- **SC-001/002**: step 3 shows ≥1 first-year event with `event_category='match_response'` and `Match response:` details.
- **SC-003**: step 4 integration test asserts the exact expected responder count for the fixed seed.
- **SC-004**: no 2026 events; a disabled run yields zero in all years.
- **SC-005**: step 2 prints an explicit `True`/`False` for both enabled and omitted configs.
- **SC-006**: the `pytest` runs in step 4 exist in the standard suite and fail if the flag is dropped or events don't reach `fct_yearly_events`.
