# Research: Tenure-Based and Points-Based Employer Match Modes

**Feature Branch**: `046-tenure-points-match`
**Date**: 2026-02-11

## Research Questions & Findings

### R1: How does the existing `graded_by_service` mode work, and can `tenure_based` reuse it?

**Decision**: `tenure_based` will be a new branch in `int_employee_match_calculations.sql` that reuses the existing `get_tiered_match_rate` and `get_tiered_match_max_deferral` macros but reads from a new dbt variable `tenure_match_tiers`.

**Rationale**: The existing `graded_by_service` mode (E010) already implements service-tier-based matching with the correct formula: `tier_rate × min(deferral%, tier_max_deferral_pct) × capped_compensation`. The macros `get_tiered_match_rate()` and `get_tiered_match_max_deferral()` in `dbt/macros/get_tiered_match_rate.sql` generate CASE expressions from tier arrays. The `tenure_based` mode uses an identical formula structure — only the config key differs.

**Alternatives considered**:
- **Aliasing `tenure_based` to `graded_by_service`**: Rejected because the spec requires distinct config keys (`tenure_match_tiers` vs `employer_match_graded_schedule`) and the two may diverge in future behavior.
- **New macros for tenure**: Rejected because the existing macros already accept a generic `years_of_service_col` parameter and tier array — fully reusable.

### R2: Where does `current_age` come from in the dbt model chain?

**Decision**: `current_age` is available via `int_employee_contributions` (which sources it from `int_employee_compensation_by_year`). The match calculation model already joins `int_employee_contributions` as the `ec` alias.

**Rationale**: The existing `int_employee_match_calculations.sql` joins `int_employee_contributions ec` at line 98. The `ec` relation includes `current_age` from upstream `int_employee_compensation_by_year`. For points-based matching, we need to add `ec.current_age` to the select and calculate `FLOOR(ec.current_age) + years_of_service` as `applied_points`.

**Alternatives considered**:
- **Join `int_workforce_snapshot_optimized` for age**: Rejected because `current_age` is already available from the existing `ec` join. No additional join needed.

### R3: How should points-based tier lookup work in SQL?

**Decision**: Create a new macro `get_points_based_match_rate(points_col, points_schedule, default_rate)` in `dbt/macros/get_points_based_match_rate.sql` following the same pattern as `get_tiered_match_rate`.

**Rationale**: The existing tier macro generates a CASE expression sorted by min_years descending. The points macro will generate an equivalent CASE sorted by `min_points` descending, returning the match rate for the first tier where `points >= min_points`. A corresponding `get_points_based_max_deferral()` macro returns the `max_deferral_pct`.

**Alternatives considered**:
- **Generic macro accepting any column and tier fields**: Rejected because the field names differ (`min_points` vs `min_years`, `rate` vs `match_rate`) and making a fully generic macro adds complexity for little gain. Two focused macros are clearer.
- **Inline CASE in the model**: Rejected because the tier array is variable-length and must be generated at compile time via Jinja.

### R4: How are new dbt variables exported from Python config?

**Decision**: Extend `_export_employer_match_vars()` in `planalign_orchestrator/config/export.py` to export `tenure_match_tiers`, `points_match_tiers`, and extended `employer_match_status` values.

**Rationale**: The export function at lines 275-447 already handles `employer_match_status` and `employer_match_graded_schedule`. The same pattern applies for the new variables. The field name transformation logic (UI field names → dbt field names) must also be added for the new tier schemas:
- Tenure: `min_years`, `max_years`, `rate` (percentage), `max_deferral_pct` (percentage)
- Points: `min_points`, `max_points`, `rate` (percentage), `max_deferral_pct` (percentage)

**Alternatives considered**:
- **Separate export function**: Rejected because all match variables are logically grouped in `_export_employer_match_vars()`.

### R5: What Pydantic validation is needed for tier configs?

**Decision**: Add `TenureMatchTier` and `PointsMatchTier` Pydantic models in `planalign_orchestrator/config/workforce.py`, plus a `validate_tier_contiguity()` validator that checks for gaps, overlaps, and start-at-zero.

**Rationale**: The existing `EmployerMatchSettings` model validates basic match config. Tier validation needs:
1. Each tier's `max > min` (or `max` is null for unbounded)
2. First tier starts at 0
3. Consecutive tiers are contiguous (tier N's max == tier N+1's min)
4. At least one tier defined when mode is active
5. No overlapping ranges

A reusable `validate_tier_contiguity()` function serves both tenure and points tiers since the validation logic is identical (just field names differ).

**Alternatives considered**:
- **dbt-level validation only**: Rejected because config errors should be caught at load time, not mid-simulation. Pydantic validation provides immediate feedback.
- **Separate validators per tier type**: Rejected because the contiguity logic is identical for both types.

### R6: Studio UI pattern for tier editing

**Decision**: Extend the existing match configuration UI to support a mode selector dropdown (deferral_based, graded_by_service, tenure_based, points_based) and a dynamic tier table editor that adapts columns based on mode.

**Rationale**: The Studio already has components for editing service-tier match schedules (E084). The UI pattern (editable table with add/remove rows, inline validation) can be extended with:
- A mode selector that shows/hides the appropriate tier editor
- Column labels that adapt: "Min Years"/"Max Years" for tenure, "Min Points"/"Max Points" for points
- Real-time validation using the same contiguity rules as the backend

**Alternatives considered**:
- **Separate pages per mode**: Rejected because all modes share the same configuration location and switching should be seamless.

### R7: Impact on existing modes and backward compatibility

**Decision**: Existing `deferral_based` and `graded_by_service` modes are completely unaffected. The new modes are additive branches in the Jinja conditional.

**Rationale**: The `int_employee_match_calculations.sql` model uses `{% if employer_match_status == 'graded_by_service' %}...{% else %}...{% endif %}` to select the calculation path. Adding `{% elif employer_match_status == 'tenure_based' %}` and `{% elif employer_match_status == 'points_based' %}` branches preserves the existing logic. The default (`deferral_based`) falls through to the else branch unchanged.

The new dbt variables (`tenure_match_tiers`, `points_match_tiers`) default to empty arrays and are only read when their respective mode is active.
