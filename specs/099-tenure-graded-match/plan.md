# Implementation Plan: Tenure-Graded Multi-Tier Employer Match Formula

**Branch**: `099-tenure-graded-match` | **Date**: 2026-06-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/099-tenure-graded-match/spec.md`

## Summary

Add a new employer match calculation mode where each tenure band carries its own ordered, cumulative list of deferral-rate match tiers (not just one flat rate + one max-deferral cap). This generalizes — and per clarification, **supersedes** — the existing single-tier `tenure_based` mode (`employer_match_status: 'tenure_based'`). The example design (under 10 years: 100% on first 2% + 50% on next 6%; 10+ years: 100% on first 2% + 50% on next 8%) becomes directly configurable. Technical approach: extend the existing `EmployerMatchSettings` Pydantic config to carry per-band tier lists instead of a single rate/cap pair, extend the existing dbt match-calculation model with a new branch that reuses the proven cumulative-tier SUM/CASE pattern already used by `deferral_based` mode (just scoped per tenure band via an added join), and extend the existing Studio UI/validation/export plumbing that already handles tenure-band tiers today.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator/config/API), SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1, TypeScript/React (Studio UI)
**Primary Dependencies**: Pydantic v2 (config validation), DuckDB 1.0.0 (storage/engine), FastAPI (workspace config API), React/Vite + Tailwind (Studio)
**Storage**: DuckDB (`dbt/simulation.duckdb`) — match contribution events land in `fct_employer_match_events`; no new tables required
**Testing**: pytest (`tests/test_match_modes.py` pattern) for config/export validation; dbt schema + data-quality SQL tests for tier contiguity and event correctness
**Target Platform**: Existing on-prem analytics server / work-laptop dbt+DuckDB stack
**Project Type**: Existing monorepo — extends config layer, dbt intermediate model, FastAPI workspace routes, and Studio React UI (no new services)
**Performance Goals**: No measurable regression vs. existing match modes — tier cross-join stays in the tens-of-rows range regardless of employee count; must not change the dashboard <2s p95 budget (Constitution VI)
**Constraints**: Single-threaded dbt execution (`--threads 1`); no new circular dependencies (`int_*` may only read `fct_yearly_events` among fact tables); no module may grow past ~600 lines (Constitution II)
**Scale/Scope**: Must remain correct at 100K+ employee records (Constitution VI); no fixed cap on number of tenure bands or tiers per band (per clarification)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Event Sourcing & Immutability | ✅ Pass. Match amounts continue to flow into the existing immutable `fct_employer_match_events`; no event mutation. Reproducibility unaffected (deterministic tier math, no randomness). |
| II. Modular Architecture | ⚠️ Watch. `int_employee_match_calculations.sql` (474 lines) and `DCPlanSection.tsx` (1023 lines, already over the ~600-line guidance) would grow further if the new mode is inlined. Mitigation: (a) push the tier-expansion/lookup logic into a new dbt macro rather than inlining SQL in the model; (b) extract a new `TenureGradedMatchEditor.tsx` component rather than adding more branches to the already-oversized `DCPlanSection.tsx`. No circular dependencies introduced. |
| III. Test-First Development | ✅ Plan requires Pydantic validation tests (extending `test_match_modes.py` patterns) and dbt data-quality tests (tier contiguity) written before/alongside the SQL branch, following existing `test_age_band_no_gaps.sql`-style pattern. |
| IV. Enterprise Transparency | ✅ Pass. New mode reuses the existing `formula_type`/audit-trail columns on `fct_employer_match_events`; FR-008's save-time warning + run-time hard-block gives full audit visibility into rejected configs. |
| V. Type-Safe Configuration | ✅ Pass. New config is a Pydantic v2 model with `model_validator` contiguity checks (mirrors existing `TenureMatchTier`/`validate_tier_contiguity`); dbt reads only `{{ ref() }}`/`{{ var() }}`, no string concatenation. |
| VI. Performance & Scalability | ✅ Pass. Cross-join tier table stays tiny (bands × tiers, typically <20 rows); identical complexity class to the existing `tiered_match` deferral-based CTE which already runs at 100K+ scale. |

No unjustified violations — proceeding without Complexity Tracking entries. The Principle II mitigations above are carried into Phase 1 design as concrete file-extraction decisions, not deferred trade-offs.

## Project Structure

### Documentation (this feature)

```text
specs/099-tenure-graded-match/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output (config schema + dbt var contract)
└── tasks.md              # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

This feature extends four existing layers of the monorepo; no new top-level projects.

```text
planalign_orchestrator/config/
├── workforce.py                      # EXTEND: replace single-tier TenureMatchTier usage in
│                                      #   EmployerMatchSettings with new per-band tier-list model
└── tenure_graded_match.py            # NEW: TenureBandMatchTier + TenureGradedMatchBand Pydantic
│                                      #   models + contiguity validators (kept separate to avoid
│                                      #   pushing workforce.py over the modular size guidance)

planalign_orchestrator/config/export.py  # EXTEND: _export_employer_match_vars() emits the new
                                          #   nested band/tier structure as dbt vars

dbt/macros/
└── get_tenure_graded_match_tiers.sql  # NEW: expands nested band/tier config into the flattened
                                        #   SELECT ... UNION ALL tier table consumed by the SQL CTE
                                        #   (keeps int_employee_match_calculations.sql lean)

dbt/models/intermediate/events/
└── int_employee_match_calculations.sql  # EXTEND: new `{% elif employer_match_status ==
                                          #   'tenure_graded' %}` branch reusing the existing
                                          #   cumulative SUM/CASE tier pattern, scoped per band

dbt/tests/data_quality/
└── test_tenure_graded_tier_no_gaps_overlaps.sql  # NEW: contiguity check across bands AND across
                                                    #   each band's own tier list (mirrors
                                                    #   test_age_band_no_gaps.sql pattern)

planalign_studio/components/config/
└── TenureGradedMatchEditor.tsx        # NEW: dedicated tier-of-tiers editor (per band: add/remove
                                        #   tiers; add/remove bands), reusing validateMatchTiers()
                                        #   gap/overlap warning logic already in DCPlanSection.tsx
DCPlanSection.tsx                      # EXTEND minimally: render TenureGradedMatchEditor when
                                        #   dcMatchMode === 'tenure_graded'; remove the old
                                        #   single-tier tenure_based editor block (superseded)

planalign_api/routers/workspaces.py    # EXTEND: default config payload includes empty
                                        #   tenure_graded_bands list (parallels existing
                                        #   tenure_match_tiers: [] default)

tests/test_match_modes.py              # EXTEND: new test classes for TenureGradedMatchBand
                                        #   validation + cumulative match-amount calculation,
                                        #   following existing T017/T024-T027 patterns
```

**Structure Decision**: No new services or projects. The feature is plumbed through the same four layers every existing match mode (`graded_by_service`, `tenure_based`, `points_based`) already uses: Pydantic config → dbt var export → dbt SQL model branch → Studio UI editor. The only structural additions are two new small, single-responsibility files (`tenure_graded_match.py`, `get_tenure_graded_match_tiers.sql`, `TenureGradedMatchEditor.tsx`) introduced specifically to satisfy Constitution Principle II rather than growing already-large existing files.

## Complexity Tracking

> No Constitution Check violations require justification — table omitted.
