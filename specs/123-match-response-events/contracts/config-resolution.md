# Contract: Config Resolution → dbt Var → Event

**Feature**: 123-match-response-events | **Date**: 2026-07-23

Three linked contracts define the observable behavior. Each has explicit, testable pre/postconditions. No external HTTP contract changes — this is an internal resolution/export contract plus the existing fact-table record contract.

---

## Contract A — Workspace config resolution

**Surface**: `WorkspaceStorage._merge_config(workspace, scenario) -> dict`

**Precondition inputs** (any combination):

- `workspace.base_config` — may or may not contain a top-level `deferral_match_response` block.
- `scenario.config_overrides` — may contain a top-level `deferral_match_response` block and/or a `dc_plan.deferral_match_response` sub-block.

**Postconditions**:

| # | Given | Then (merged config) |
|---|-------|----------------------|
| A1 | top-level `deferral_match_response.enabled: true` present | merged `deferral_match_response.enabled == true` |
| A2 | `dc_plan.deferral_match_response.enabled: true` present | merged `deferral_match_response.enabled == true` |
| A3 | both present, disagreeing | `dc_plan` value wins (UI overrides legacy) |
| A4 | neither present | merged config **contains** `deferral_match_response.enabled == false` (explicit, not absent) |
| A5 | any of the above | the merged dict validates cleanly as `SimulationConfig` |

**Invariant**: resolution never sets `enabled=true` unless an input explicitly requested it.

---

## Contract B — dbt var export

**Surface**: `to_dbt_vars(SimulationConfig) -> dict` (via `_export_deferral_match_response_vars`, unchanged code — asserted, not modified)

**Postconditions**:

| # | Given | Then |
|---|-------|------|
| B1 | `cfg.deferral_match_response.enabled == true` | `dbt_vars["deferral_match_response_enabled"] == True` |
| B2 | `cfg.deferral_match_response.enabled == false` | `dbt_vars["deferral_match_response_enabled"] == False` |
| B3 | match formula configured | `dbt_vars["employer_match_max_deferral_rate"]` present (defines the ceiling) |

---

## Contract C — `fct_yearly_events` record (existing, asserted)

**Surface**: rows in `fct_yearly_events` after a simulation run.

**Postconditions**:

| # | Given | Then |
|---|-------|------|
| C1 | B1 true, eligible below-threshold population nonempty, `simulation_year == start_year` | ≥1 row with `event_type = 'deferral_match_response'` |
| C2 | any such row | `event_category = 'match_response'` AND `event_details LIKE 'Match response:%'` |
| C3 | `simulation_year > start_year` | 0 match-response rows |
| C4 | B2 true (disabled) | 0 match-response rows in every year |
| C5 | eligible set filtering | no `employee_id LIKE 'NH_{start_year}_%'` among match-response rows |
| C6 | fixed seed + fixture census | responder count equals an exact expected value (deterministic) |

---

## Test mapping

| Contract | Test type | Location (new) |
|----------|-----------|----------------|
| A1–A5 | fast unit | `tests/unit/…/test_workspace_match_response_resolution.py` |
| B1–B3 | fast unit | extend `tests/unit/orchestrator/test_config_export.py` |
| C1–C6 | integration (isolated DB) | `tests/integration/test_match_response_fact_integration.py` |

All integration validation uses an isolated per-scenario `.duckdb` (never the shared dev DB), per project practice and Constitution VI.
