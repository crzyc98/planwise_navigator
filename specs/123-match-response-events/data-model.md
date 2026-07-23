# Phase 1 Data Model: Match-Response Deferral Events in Client/Studio Simulations

**Feature**: 123-match-response-events | **Date**: 2026-07-23

No new tables, columns, or schema migrations. This feature reuses existing entities; the "data model" here documents the entities the feature reasons about and the resolution rules that must hold. The only *behavioral* change is how the `deferral_match_response` configuration is **resolved and exposed** in the Studio/workspace path.

## Entity 1 — Resolved match-response configuration

The effective `deferral_match_response` settings the run consumes after workspace base/override merge and reconciliation. Typed by the existing `DeferralMatchResponseSettings` (Pydantic v2, `config/workforce.py:466`).

| Field | Type | Default | Rule |
|-------|------|---------|------|
| `enabled` | bool | `False` | Master toggle. MUST be present and explicit in the merged config (transparency). |
| `upward_participation_rate` | Decimal [0,1] | `0.40` | Fraction of below-max responders. Unchanged from 058. |
| `upward_maximize_rate` | Decimal [0,1] | `0.60` | Share of upward responders jumping to the ceiling. |
| `upward_partial_increase_factor` | Decimal [0,1] | `0.50` | Gap-closing factor for partial responders. |
| `downward_enabled` | bool | `True` | Governs above-max response (not asserted by this feature; must not regress). |
| `downward_*` | Decimal | 058 defaults | Unchanged. |

**Resolution rules** (new, in `WorkspaceStorage._merge_config`):

- R1: If a top-level `deferral_match_response` block is present in base or overrides, it is preserved and typed (CLI/legacy parity).
- R2: If a Studio-native `dc_plan.deferral_match_response` sub-block is present, its values reconcile into the top-level block. When both R1 and R2 are present, the `dc_plan` (UI) values take precedence, consistent with the `to_dbt_vars` E101 ordering (UI overrides legacy).
- R3: If neither is present, the merged config MUST still carry an explicit `deferral_match_response.enabled = false` (transparency; never silently absent).
- R4: Resolution never enables the feature implicitly — the default is `false`.

## Entity 2 — Eligible below-threshold population

The set of participants that can generate first-year match-response events. Defined by the existing model, not changed.

| Criterion | Rule | Source |
|-----------|------|--------|
| Active | Employment status active in the first year | model join to workforce |
| Enrolled | Has a valid enrollment event (`event_type = 'enrollment'`, `simulation_year <= start_year`) | model lines 93-96 |
| Below threshold | `current_deferral_rate < match_max_rate` (`employer_match_max_deferral_rate`) | model line 199 |
| Not a current-year new hire | `employee_id NOT LIKE 'NH_{start_year}_%'` | model line 180 |
| First year only | `simulation_year == start_year` | model line 49 |

**Edge state**: enabled but `employer_match_max_deferral_rate` absent → eligible population empty → zero events. Distinguishable from disabled because the resolved config shows `enabled=true`.

## Entity 3 — Match-response deferral event (immutable, existing)

One row per responding participant in the first year, unioned into `fct_yearly_events`. Contract values are fixed strings the acceptance tests assert verbatim.

| Field | Value / Rule | Source |
|-------|--------------|--------|
| `event_type` | `'deferral_match_response'` | model lines 208, 258, 321 |
| `event_category` | `'match_response'` | model lines 313, 336 |
| `event_details` | begins with `'Match response: '` (e.g. `Match response: 3.0% → 6.0%`) | model line 297 |
| `simulation_year` | equals `start_year` (first year only) | model line 209 |
| `effective_date` | `DATE '{start_year}-01-01'` | model line 210 |
| audit fields | previous rate, new rate, target (match-maximizing) rate, response type (maximize/partial), match mode | 058 model |

**Invariants** (must hold and be tested):

- I1: Rows exist only when `enabled=true` AND `simulation_year == start_year` AND eligible population is nonempty.
- I2: Zero rows in any year > `start_year`.
- I3: Zero rows in every year when `enabled=false`.
- I4: No current-year new hire (`NH_{year}_%`) appears.
- I5: For a fixed seed + fixture census, the responder set and count are identical across runs (deterministic hashing).

## State / flow

```text
workspace base_config + scenario overrides
  → _merge_config (+ R1–R4 reconciliation)          [CHANGED: resolve + expose enabled]
  → SimulationConfig (typed, deferral_match_response) [unchanged]
  → to_dbt_vars → deferral_match_response_enabled     [unchanged; now receives true]
  → int_deferral_match_response_events (gated)        [unchanged; now fires in year 1]
  → int_current_year_events → fct_yearly_events       [unchanged]
```
