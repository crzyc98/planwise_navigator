# API Contract: `cohort` query parameter on DC Plan analytics endpoints

**Feature**: 134-new-hire-cohort
**Date**: 2026-08-06

## Endpoints

### `GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan`
### `GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare`

Both gain one new query parameter. All existing parameters (`active_only`, `effective_rate`, and — for `/compare` — `scenarios`) are unchanged.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cohort` | `"all" \| "new_hires" \| "baseline"` | `"all"` | Filters the population used for participation/contribution metrics. Any other value → `422 Unprocessable Entity` (FastAPI `Literal` validation, no custom handler needed). |

### Request examples

```
GET /api/workspaces/ws1/scenarios/s1/analytics/dc-plan?cohort=new_hires
GET /api/workspaces/ws1/analytics/dc-plan/compare?scenarios=s1,s2&cohort=baseline
GET /api/workspaces/ws1/analytics/dc-plan/compare?scenarios=s1,s2&cohort=bogus   → 422
```

### Response shape changes

`DCPlanAnalytics` (used by both endpoints, directly and inside `DCPlanComparisonResponse.analytics[]`) gains one field:

```jsonc
{
  // ...all existing fields, unchanged shape...
  "resolved_first_simulation_year": 2025   // NEW — always present, independent of `cohort`
}
```

No other field is added or removed. Existing field **values** change when `cohort != "all"`:
- `total_eligible`, `total_enrolled`, `participation_rate`, `participation_by_method` — scoped to the requested cohort's final-simulation-year population.
- Every entry in `contribution_by_year[]` — `participant_count`, `total_eligible_count`, `average_deferral_rate`, `participation_rate`, `total_employer_cost`, `total_compensation`, `employer_cost_rate`, `employee_contribution_rate`, `match_contribution_rate`, `core_contribution_rate`, `total_contribution_rate` — all computed from cohort-scoped totals for that year, not sliced from population-wide totals.
- Grand totals (`total_employee_contributions`, `total_employer_match`, `total_employer_core`, `total_all_contributions`, `total_employer_cost`, `total_compensation`, `average_deferral_rate`, and the four `*_contribution_rate` fields) — derived from the (now cohort-scoped) `contribution_by_year[]` via the existing `_compute_grand_totals`, unchanged logic.
- `deferral_rate_distribution`, `deferral_distribution_by_year`, `escalation_metrics`, `irs_limit_metrics` — **unchanged by `cohort`** in this feature (out of scope; see research.md R3). These always reflect the full population regardless of the requested cohort.

### Invariant (contract test MUST assert this)

For a given `workspace_id`, `scenario_id`, and simulation `year`:

```
contribution_by_year[year].total_employer_cost (cohort=new_hires)
  + contribution_by_year[year].total_employer_cost (cohort=baseline)
  == contribution_by_year[year].total_employer_cost (cohort=all)
```//within floating-point rounding tolerance (e.g. `abs(delta) < 0.01`)

### Regression guard (contract test MUST assert this)

A request with no `cohort` parameter and a request with `cohort=all` MUST produce byte-identical JSON responses, except for the new `resolved_first_simulation_year` field which is present in both (this field is not new *behavior*, only a new *field*, so this is not a violation of "byte-identical" for the fields that existed pre-feature).

### Error contract

```
GET .../analytics/dc-plan?cohort=not_a_real_value
→ 422 Unprocessable Entity
```
(Standard FastAPI/Pydantic validation-error body — no custom error handling required.)
