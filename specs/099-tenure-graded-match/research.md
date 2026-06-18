# Phase 0 Research: Tenure-Graded Multi-Tier Employer Match Formula

No `NEEDS CLARIFICATION` markers remained in the Technical Context after spec clarification — this document records the implementation-pattern decisions made by studying the existing, analogous match-mode implementations already in the codebase, rather than open unknowns.

## Decision 1: Reuse the existing 4-mode `employer_match_status` branching pattern

**Decision**: Add a new mode value `'tenure_graded'` to `employer_match_status`, following the exact branching structure already used by `deferral_based` / `graded_by_service` / `tenure_based` / `points_based` in `int_employee_match_calculations.sql`.

**Rationale**: The model already uses `{% if employer_match_status == ... %}` / `{% elif %}` Jinja branches per mode, each producing a `formula_type`-tagged `all_matches` CTE feeding a shared downstream eligibility/cap/audit pipeline (`final_match` CTE). Adding a fifth branch is the path of least disruption and keeps the audit trail (`formula_type`, `years_of_service`, `irs_401a17_limit_applied`) consistent across all modes.

**Alternatives considered**: A wholly separate model dedicated to tenure-graded match. Rejected — would duplicate the eligibility filtering, IRS 401(a)(17) capping, and event-emission logic that `final_match` already centralizes, violating single-responsibility in the other direction (duplicated logic instead of one extra branch).

## Decision 2: Supersede `tenure_match_tiers: List[TenureMatchTier]` with a per-band tier-list model

**Decision**: Per clarification, the existing single-tier-per-band `TenureMatchTier` (fields: `min_years`, `max_years`, `match_rate`, `max_deferral_pct`) is replaced by a new `TenureGradedMatchBand` (fields: `min_years`, `max_years`, `tiers: List[TenureBandMatchTier]`), where each `TenureBandMatchTier` carries `employee_min`, `employee_max`, `match_rate` — identical shape to the existing `match_tiers` var already used by `deferral_based` mode.

**Rationale**: A single-tier band is just a one-element `tiers` list (`[{employee_min: 0, employee_max: max_deferral_pct, match_rate: match_rate}]`), satisfying FR-003a's backward-representability requirement without keeping two parallel schemas alive.

**Alternatives considered**: Add a new, separate `tenure_graded_tiers` field alongside the untouched `tenure_match_tiers`, keeping both selectable. Rejected per clarification answer (Q1: supersede, not coexist) — avoids maintaining two config schemes for what is structurally the same concept at different generality.

## Decision 3: Two-level contiguity validation, reusing `validate_tier_contiguity()`

**Decision**: Validate contiguity at two levels using the existing `planalign_orchestrator/config/workforce.py::validate_tier_contiguity()` helper: (a) across tenure bands (`min_years`/`max_years`, identical to today's tenure_based check), and (b) within each band's own `tiers` list (`employee_min`/`employee_max`), so a band's tiers must start at 0% deferral and be gap/overlap-free.

**Rationale**: `validate_tier_contiguity()` is already generic (parameterized `min_key`/`max_key`/`label`) and used for both tenure and points tiers today — reusing it for the inner tier-list check requires no new logic, just a second call site.

**Alternatives considered**: A bespoke nested-validator. Rejected — the existing helper already does exactly this with zero modification needed.

## Decision 4: Save-time warning + run-time hard block (FR-008) split across Studio UI and dbt

**Decision**: Implement the save-time warning in the Studio UI (`TenureGradedMatchEditor.tsx`, reusing the existing `validateMatchTiers()` warning function already used elsewhere in `DCPlanSection.tsx` for analogous tier editors) and the run-time hard block as a Pydantic `model_validator` raising `ValueError` (which the API layer surfaces back to the UI) plus a dbt data-quality test that fails the build if a malformed config ever reaches dbt directly (e.g., via CLI `--vars`, bypassing the UI).

**Rationale**: Matches the clarified two-point validation requirement exactly, and reuses three already-existing validation surfaces (UI warning function, Pydantic validator, dbt test pattern) rather than inventing a new one.

**Alternatives considered**: Validate only in Pydantic (skip the dbt test). Rejected — `simulate`/`batch` CLI workflows can invoke dbt with raw `--vars` bypassing the Pydantic config object entirely, so the dbt-level test is the actual last line of defense the spec's "zero silent failures" (SC-003) requires.

## Decision 5: Tier expansion via a new dbt macro, not inline SQL

**Decision**: Write `get_tenure_graded_match_tiers.sql`, a macro that takes the nested `tenure_graded_bands` var (list of bands, each with a `tiers` list) and renders the flattened `SELECT ... UNION ALL` tier table (with `band_min_years`/`band_max_years` columns carried alongside each tier row), used in a `CROSS JOIN (...) AS tier` clause filtered by `WHERE ec.years_of_service >= tier.band_min_years AND ec.years_of_service < tier.band_max_years`.

**Rationale**: Keeps `int_employee_match_calculations.sql` from growing by the full nested-loop Jinja needed to flatten bands × tiers inline (Constitution II size guidance), and matches the existing convention of factoring tier-lookup logic into dedicated macros (`get_tiered_match_rate.sql`, `get_tiered_match_max_deferral.sql`, `get_points_based_match_rate.sql`).

**Alternatives considered**: Inline the nested `{% for band %}{% for tier %}` loop directly in the model. Rejected — adds ~30-40 lines of nested Jinja directly into an already 474-line model, pushing it further toward the 600-line guidance for no reuse benefit.

## Decision 6: Dedicated `TenureGradedMatchEditor.tsx` component

**Decision**: New Studio component rather than extending the already-1023-line `DCPlanSection.tsx` with another inline tier-editor block.

**Rationale**: `DCPlanSection.tsx` is already well past the Constitution's ~600-line module guidance; the new "band of tiers" editor is meaningfully more complex UI (nested add/remove: bands containing tiers) than the existing flat tier lists, making extraction both a size and a clarity win. `DCPlanSection.tsx` only needs a thin conditional render hook for `dcMatchMode === 'tenure_graded'`.

**Alternatives considered**: Inline in `DCPlanSection.tsx` alongside the existing (soon-superseded) `tenure_based` block. Rejected — compounds an existing modularity violation instead of containing it.
