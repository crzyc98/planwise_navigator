# Phase 0 Research: Match-Magnet Dial & Ceiling Fidelity

All Technical Context items are known from the existing codebase; no external technology choices required. Research focused on resolving the design unknowns from the spec + clarifications.

## R1 — Why does changing the match ceiling not affect deferral distribution?

**Decision**: Compute the match-magnet ceiling whenever a match is configured, not only when `deferral_match_response` is enabled.

**Findings**:
- `int_voluntary_enrollment_decision.sql` and `int_proactive_voluntary_enrollment.sql` resolve `match_max_rate` as: (1) `var('deferral_match_response_match_max_rate')` if present, else (2) `max(employee_max)` over `var('match_tiers')`, and only when `employer_match_status == 'deferral_based'`.
- `var('match_tiers')` is populated from `dc_plan.match_tiers` (`export.py:574`). The `employer_match.formulas.*` / `active_formula` block (where "stretch 50% up to 6/10" lives) does **not** populate `match_tiers` on its own.
- The precomputed override `deferral_match_response_match_max_rate` **is** derived from the active formula's tiers — but only inside `_export_deferral_match_response_vars` (`export.py:1188-1212`), gated on `cfg.deferral_match_response` being configured.
- Net: with DMR disabled and the ceiling configured only via the `employer_match` formula block, `match_max_rate` falls back to the hard-coded default tiers `[0.03, 0.05]` → 0.05 regardless of the configured 6%/10%. Both scenarios snap to the same rate ⇒ identical distributions. **Confirms the analyst report.**

**Resolution**: Extract the formula→ceiling computation into an always-run helper used by `_export_employer_match_vars`, exporting a stable var (proposed `employer_match_max_deferral_rate`). SQL prefers this scalar for deferral-based modes; keep `deferral_match_response_match_max_rate` as a backward-compatible alias if still referenced elsewhere.

**Alternatives considered**:
- *Populate `match_tiers` from the formula block.* Rejected: `match_tiers` is a UI/dc_plan concept; overloading it risks colliding with UI-driven tiers and muddies precedence.
- *Leave gated on DMR and document.* Rejected: violates FR-003 and silently invalidates match-design comparisons.

## R2 — How to resolve the ceiling for non-deferral-based match modes (clarification B)

**Decision**: Resolve a **per-employee** ceiling from the applicable tier's `max_deferral_pct`, dispatching by `employer_match_status`, reusing existing macros.

**Findings**:
- `int_employee_match_calculations.sql` already resolves per-employee tier values for every mode: `graded_by_service` and `tenure_graded` via `get_tiered_match_max_deferral(years_of_service, employer_match_graded_schedule, default)`, and `points_based` via the points-tier equivalent over `points_match_tiers`.
- These macros emit a SQL CASE expression keyed on a per-row column (years_of_service or points), so the ceiling is naturally per-employee and vectorized.

**Resolution**: Add a macro `resolve_match_magnet_ceiling(status, years_of_service_col, points_col, deferral_scalar_default)` that returns:
- `deferral_based` → the exported scalar ceiling (R1).
- `graded_by_service` / `tenure_graded` → `get_tiered_match_max_deferral(years_of_service_col, employer_match_graded_schedule, default)`.
- `points_based` → points-tier max-deferral macro over `points_match_tiers`.
- match disabled / unknown → `0` (magnet inactive — see edge cases).

The voluntary models join the workforce rows they already have (which include tenure/age → service/points are derivable) and apply the magnet against this per-row ceiling.

**Alternatives considered**:
- *Single scalar = max over all tiers.* Rejected: overstates the ceiling for low-service employees and contradicts clarification B (applicable tier per employee).

## R3 — Deduplicating the magnet logic across two models

**Decision**: Extract the snap decision and the bounds clamp into shared macro(s); both voluntary models call them.

**Findings**: `int_voluntary_enrollment_decision.sql` (match_optimization CTE, final `GREATEST(0.01, LEAST(0.10, …))`) and `int_proactive_voluntary_enrollment.sql` (identical lines ~287-294, ~336) carry byte-for-byte duplicate logic — a divergence hazard (Principle II).

**Resolution**: One macro for ceiling resolution (R2) and one for the bounded snap (`apply_match_magnet(selected_rate, ceiling, snap_random, enabled, snap_prob, floor, cap)` returning the final deferral). Keeps each model thin and guarantees both paths stay consistent.

**Alternatives considered**: *Leave duplicated, edit both.* Rejected: future drift risk; the bug being fixed partly stems from parallel logic.

## R4 — Configurable deferral cap (FR-013) and backward compatibility

**Decision**: Introduce `voluntary_max_deferral_rate` dbt var (decimal), default **0.10**; replace both `LEAST(0.10, …)` clamps with `LEAST({{ var('voluntary_max_deferral_rate', 0.10) }}, …)`. Floor remains `0.01`.

**Rationale**: 0.10 reproduces today's behavior exactly (SC-004); raising it lets a configured ceiling ≥10% populate the 10%+ band (US3/FR-009). Bounds: `ge=0.01, le=1.0` in Pydantic; UI sends percent → divide by 100.

## R5 — Config + UI wiring pattern

**Decision**: Follow the existing dual-path pattern. Pydantic: new `MatchMagnetSettings` (enabled, snap_probability, max_deferral_rate) under `EnrollmentSettings`. UI: new `dc_plan` keys mapped in `_apply_dc_plan_enrollment_overrides`; both converge on the same dbt vars in `_export_enrollment_vars`.

**Findings**: `voluntary_enrollment_rate` already demonstrates the full path (Pydantic field on `AutoEnrollmentSettings`, dc_plan passthrough at `export.py:249-255`, UI at `buildConfigPayload.ts:95`). Recent commit #326/#327 fixed Copy-from-Scenario dropping `voluntary_enrollment_rate` — **the new fields MUST be added to `CopyScenarioModal` (FR-005) to avoid the same regression.**

**dbt var names** (existing, keep): `enrollment_match_magnet_enabled`, `enrollment_match_magnet_probability` (`dbt_project.yml:313-314`). New: `voluntary_max_deferral_rate`, `employer_match_max_deferral_rate`.

## R6 — Validation strategy

**Decision**: Per constitution + project memory, validate in **isolated** databases, never the shared `dbt/simulation.duckdb`. Use `planalign batch --scenarios … --clean` or `DATABASE_PATH=…` with explicit edge configs (no-AE + stretch match), running the **full multi-year** horizon to surface cross-year deferral drift. Detailed recipe in quickstart.md.

## Open items deferred to implementation/tasks

- Exact snap semantics remain a per-enrollee probability draw on a deterministic hash (unchanged) — directional acceptance criteria (SC-001/002) are robust to this.
- Whether `deferral_match_response_match_max_rate` can be fully replaced by `employer_match_max_deferral_rate` or must remain as an alias depends on `int_deferral_match_response_events.sql` usage — confirm during implementation and keep an alias if needed.
