# Implementation Plan: Voluntary-Enrollment Match-Magnet Dial & Match-Ceiling Fidelity

**Branch**: `102-match-magnet-dial` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/102-match-magnet-dial/spec.md`

## Summary

Make the voluntary-enrollment "match magnet" behave correctly and become analyst-controllable. Three threads:

1. **Ceiling fidelity (P1)**: The deferral rate that voluntary enrollees snap to (`match_max_rate`) must track the active employer-match formula's ceiling, independent of whether `deferral_match_response` is enabled. For non-deferral-based modes (graded/tenure/points) the ceiling is resolved per-employee from the applicable tier's `max_deferral_pct`.
2. **Expose the dial (P2)**: Surface match-magnet controls (`enabled`, `snap_probability`) end-to-end — Pydantic config → dbt-var export → Studio UI → scenario copy — with defaults preserving current behavior.
3. **Configurable deferral cap (P3)**: Replace the hard-coded `LEAST(0.10, …)` clamp in both voluntary-enrollment models with a per-scenario "maximum employee deferral %" (`voluntary_max_deferral_rate`), defaulting to 0.10 for backward compatibility.

Technical approach: the magnet logic is duplicated in `int_voluntary_enrollment_decision.sql` and `int_proactive_voluntary_enrollment.sql`; both are updated identically (a shared macro is the preferred deduplication). The ceiling computation already has a reusable macro (`get_tiered_match_max_deferral`) for graded/points modes. Config and export wiring follow the existing dc_plan / Pydantic dual-path pattern in `planalign_orchestrator/config/`.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator/config/API); SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1; TypeScript/React (Studio UI)
**Primary Dependencies**: Pydantic v2 (config validation), DuckDB 1.0.0, FastAPI (workspace config API), React/Vite + Tailwind (Studio)
**Storage**: DuckDB (`dbt/simulation.duckdb`); no new tables — behavior changes flow through existing `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment`, `fct_yearly_events`, `fct_workforce_snapshot`
**Testing**: pytest (fast + integration) for config/export; dbt schema tests + isolated-DB multi-year integration runs
**Target Platform**: On-prem analytics workstation (macOS/Ubuntu), single-threaded dbt default
**Project Type**: Existing monorepo — dbt models + Python orchestrator/config + FastAPI + React Studio (no new project)
**Performance Goals**: No regression to multi-year runtime; per-employee ceiling resolution via SQL CASE (vectorized, negligible)
**Constraints**: Deterministic/reproducible for fixed seed; backward compatible (unset controls reproduce prior results); validate in isolated DBs (never the shared `dbt/simulation.duckdb`)
**Scale/Scope**: 100K+ employee records; change is confined to voluntary-enrollment deferral selection — no new event types, no AE/escalation behavior introduced

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|------------|--------|
| I. Event Sourcing & Immutability | No event mutation; enrollment events remain immutable. Deferral selection stays deterministic (hash-based), so same seed → same events. | ✅ Pass |
| II. Modular Architecture | Changes localized to existing modules; magnet logic deduplicated into a shared macro instead of copy-pasting across the two voluntary models. No module exceeds limits. No new layer crossings (int_* reads vars/macros only). | ✅ Pass |
| III. Test-First Development | Plan sequences failing tests first: config-export unit tests for new vars, dbt schema/data tests for ceiling + cap, and an isolated-DB integration comparison (6% vs 10%). | ✅ Pass |
| IV. Enterprise Transparency | New controls are version-controlled config; existing audit fields (`raw_deferral_rate`, `match_optimized_rate`) preserved and extended to record the resolved ceiling. | ✅ Pass |
| V. Type-Safe Configuration | New settings added as Pydantic v2 fields with bounds (ge/le); dbt refs unchanged; no raw SQL string concat for refs. | ✅ Pass |
| VI. Performance & Scalability | Per-employee ceiling via CASE/macros is vectorized; no new full scans (year-filtered models unchanged); single-thread default preserved. | ✅ Pass |

**Result**: PASS — no violations, Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/102-match-magnet-dial/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (config + dbt-var contracts)
│   ├── config-schema.md
│   └── dbt-vars.md
└── checklists/
    └── requirements.md  # From /speckit.specify
```

### Source Code (repository root)

```text
dbt/
├── models/intermediate/
│   ├── int_voluntary_enrollment_decision.sql      # magnet ceiling + configurable cap
│   └── int_proactive_voluntary_enrollment.sql     # same changes (duplicated logic)
├── macros/
│   ├── resolve_match_magnet_ceiling.sql           # NEW: per-employee ceiling across all match modes
│   ├── get_tiered_match_rate.sql                  # existing — get_tiered_match_max_deferral reused
│   └── (apply_voluntary_deferral_bounds — optional shared cap/snap macro)
└── dbt_project.yml                                # default vars: magnet enabled/probability (exist), + voluntary_max_deferral_rate

planalign_orchestrator/config/
├── workforce.py                                   # NEW MatchMagnetSettings on EnrollmentSettings (+ max_deferral)
└── export.py                                      # export magnet vars; always-compute match ceiling (not gated on DMR)

planalign_studio/components/config/
├── DCPlanSection.tsx                              # UI controls (toggle, snap %, max deferral %)
├── buildConfigPayload.ts                          # serialize dc_plan keys
├── CopyScenarioModal.tsx                          # carry new fields on copy (FR-005)
├── types.ts / constants.ts                        # form field types + defaults
└── ConfigContext.tsx                              # form state wiring

tests/
├── test_config_export_match_magnet.py             # NEW unit: var export + always-on ceiling
└── (integration) isolated-DB 6% vs 10% comparison per quickstart.md
```

**Structure Decision**: Existing monorepo layout. No new top-level projects. New code is one dbt macro, edits to two dbt models + `dbt_project.yml`, two Python config files, five Studio config files, and one new Python test module. The dbt-var contract is the integration seam between the Python/UI config layer and the SQL layer.

## Phase 0 — Research

See [research.md](./research.md). Key resolved decisions:

- **Ceiling source must be always-on**: move/duplicate the match-max computation out of `_export_deferral_match_response_vars` so it is exported whenever a match is configured (satisfies FR-003). SQL prefers the exported scalar for deferral-based modes.
- **Non-deferral modes** reuse `get_tiered_match_max_deferral(years_of_service, schedule, default)` (graded/tenure) and the points equivalent to resolve a **per-employee** ceiling in SQL; a new `resolve_match_magnet_ceiling` macro dispatches by `employer_match_status`.
- **Deduplication**: the two voluntary models carry identical magnet+cap logic today; extract the snap + bounds into a shared macro to avoid divergence (Principle II).
- **Cap default**: `voluntary_max_deferral_rate` defaults to `0.10` (current hard cap) for backward compatibility.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — `MatchMagnetSettings` entity, dc_plan keys, validation rules, audit columns.
- [contracts/config-schema.md](./contracts/config-schema.md) — Pydantic + dc_plan (UI) schema additions.
- [contracts/dbt-vars.md](./contracts/dbt-vars.md) — the dbt-var contract (names, types, defaults, consuming models).
- [quickstart.md](./quickstart.md) — isolated-DB validation recipe (6% vs 10% comparison, dial sweep, regression check).

## Complexity Tracking

> No constitution violations — table intentionally omitted.
