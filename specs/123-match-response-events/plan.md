# Implementation Plan: Match-Response Deferral Events in Client/Studio Simulations

**Branch**: `123-match-response-events` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/123-match-response-events/spec.md`

## Summary

Match-responsive deferral adjustments (feature 058) are absent from PlanAlign Studio / workspace client simulations. Root-cause investigation (see [research.md](./research.md)) confirms the **dbt model and event export are already correct** — the failure is purely a **configuration-propagation and transparency gap in the Studio/workspace layer**:

- `SimulationConfig.deferral_match_response` is a **top-level** typed block that defaults to `enabled=False` (`config/loader.py:55`, `config/workforce.py:475`).
- The CLI's `config/simulation_config.yaml` carries this block; **Studio `base_config.yaml` files do not** (verified: 0 occurrences), and there is **no `dc_plan` → `deferral_match_response` bridge** and no `dc_plan` match-response field.
- Therefore the merged Studio config has no `deferral_match_response` key → Pydantic applies the disabled default → the exporter emits `deferral_match_response_enabled = False` (`config/export.py:1259`) → the (correct) model returns its empty branch.

The fix is confined to the workspace configuration-resolution layer plus tests: give the Studio/workspace path a supported, discoverable way to carry the match-response enabled state to the simulation, guarantee the resolved config the run consumes **explicitly** exposes that state (never silently absent), and add regression coverage for the config path and the fact-table integration. **No dbt model changes and no behavioral-model changes.**

## Technical Context

**Language/Version**: Python 3.11 (config + FastAPI workspace layer). SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 — **read-only for this feature** (no model edits).
**Primary Dependencies**: Pydantic v2 (`DeferralMatchResponseSettings`), FastAPI workspace storage/merge (`planalign_api/storage/workspace_storage.py`), config export (`planalign_orchestrator/config/export.py::to_dbt_vars`), DuckDB.
**Storage**: DuckDB, one `.duckdb` per scenario/run. No schema or table changes; events already flow through `fct_yearly_events`.
**Testing**: pytest — fast unit tests for the config-resolution/export path; an integration test against an **isolated** scenario DB for the fact-table assertion.
**Target Platform**: On-prem macOS/Linux; PlanAlign Studio (FastAPI + React) and CLI share the same orchestrator.
**Project Type**: Web-service (FastAPI backend) + CLI + dbt transformation project. The change lands in the backend/config layer.
**Performance Goals**: Negligible — config-layer resolution only; the gated model already exists and runs first-year-only.
**Constraints**: Preserve CLI parity (top-level YAML block must keep working). Default MUST remain **disabled** (no silent behavior change for existing scenarios). Validate only in isolated DBs, never the shared dev DB.
**Scale/Scope**: Reference workload 60,040 employees, 2025–2029; the feature fires only in the first year for eligible below-threshold participants.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| **I. Event Sourcing & Immutability** | ✅ Events remain immutable, UUID-stamped, in `fct_yearly_events`. No event schema/semantics change; deterministic-by-seed generation preserved (the model's hashing is unchanged). |
| **II. Modular Architecture** | ✅ Change is localized to the workspace config-resolution path. A focused private helper (single responsibility: resolve/expose the match-response block) keeps `workspace_storage.py` within limits; no circular deps introduced (config layer only). |
| **III. Test-First Development** | ✅ Plan writes failing tests first: (a) fast config-path tests proving the flag survives merge/resolution and exports true/false; (b) an integration test proving first-year events reach `fct_yearly_events`. |
| **IV. Enterprise Transparency** | ✅ **Strengthened.** The core deliverable makes the enabled/disabled state explicit in the resolved config the run consumes and persists, replacing a silent no-op with a self-explaining state. |
| **V. Type-Safe Configuration** | ✅ Resolution funnels into the existing Pydantic `DeferralMatchResponseSettings`; no raw SQL string building; dbt vars produced by the existing typed exporter. |
| **VI. Performance & Scalability** | ✅ No measurable cost; no new heavy models or connections. |

**Result**: PASS — no violations. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/123-match-response-events/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — root cause + design decisions
├── data-model.md        # Phase 1 output — entities & resolution rules
├── quickstart.md        # Phase 1 output — reproduce & verify
├── contracts/
│   └── config-resolution.md   # Phase 1 output — resolution + dbt-var + event contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (already complete)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
planalign_api/
└── storage/
    └── workspace_storage.py        # PRIMARY: resolve/expose deferral_match_response
                                     # in _merge_config; explicit enabled state in the
                                     # merged config the run consumes.

planalign_orchestrator/
└── config/
    ├── export.py                   # VERIFY ONLY: _export_deferral_match_response_vars
    │                               # already reads cfg.deferral_match_response (no change
    │                               # expected; add assertion coverage).
    ├── loader.py                   # VERIFY ONLY: top-level block already typed.
    └── workforce.py                # VERIFY ONLY: DeferralMatchResponseSettings defaults.

dbt/
└── models/intermediate/events/
    └── int_deferral_match_response_events.sql   # NO CHANGE — already correct.

tests/
├── unit/…                          # NEW: Studio config-path resolution/export tests.
└── integration/…                   # NEW: isolated-DB fact-table integration test.
```

**Structure Decision**: Existing web-service + orchestrator + dbt layout. The behavioral change is confined to `planalign_api/storage/workspace_storage.py` (config resolution) plus new tests; the orchestrator export/loader and the dbt model are verified, not modified. This keeps the fix minimal, matches the established E091/E101 reconciliation pattern already present in `_merge_config` (dc_plan → employer_match), and preserves CLI parity.

## Complexity Tracking

> No Constitution violations — table intentionally empty.

## Phase 0 — Research

See [research.md](./research.md). All unknowns resolved; no `NEEDS CLARIFICATION` remain. Key decisions:

- **D1** — The bug is config propagation + transparency, not the model or exporter (evidence-backed).
- **D2** — Resolution approach: a Studio/workspace `dc_plan.deferral_match_response` bridge reconciled into the typed top-level block in `_merge_config`, defaulting to **disabled**; keep the legacy top-level block working for CLI parity. (Alternatives — base-config template injection; default-on injection — considered and rejected.)
- **D3** — Transparency: the merged config the run consumes always carries an explicit `deferral_match_response.enabled` value, so "enabled vs disabled" is never inferred from absence.
- **D4** — Determinism/tolerance: the ~40% responder assertion is validated as an exact expected count for a fixed seed + fixture census, not a fuzzy percentage, to keep the regression test non-flaky.
- **D5** — UI toggle to surface the setting in the DC Plan page is **out of scope** for this feature (follow-up); the bridge is delivered at the API/config layer.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — the match-response event contract, the resolved-configuration entity and its resolution rules, and the eligible-population definition.
- [contracts/config-resolution.md](./contracts/config-resolution.md) — the resolution contract (inputs → resolved `deferral_match_response`), the exported dbt-var contract, and the `fct_yearly_events` record contract.
- [quickstart.md](./quickstart.md) — reproduce the empty-events defect and verify the fix in an isolated DB.

## Phase 2 — Task planning approach (preview only; produced by `/speckit.tasks`)

Tasks will be ordered test-first and by user-story priority:

1. **US2 / config transparency (P2)** — failing fast tests: merged Studio config exposes explicit `enabled`; export yields `deferral_match_response_enabled` true/false; then implement the `_merge_config` bridge/normalization.
2. **US1 / events appear (P1)** — failing integration test on an isolated DB: enabled Studio-shaped scenario with eligible below-threshold participants produces first-year `deferral_match_response` rows in `fct_yearly_events` with the correct `event_category`/`event_details`; verify green after the config fix (no model change).
3. **US3 / suppression (P2)** — assertions: zero events in later years, zero when disabled, new-hires excluded — folded into the integration test.
4. **Regression hardening** — CLI-parity check (top-level block still works) and the exact-count determinism assertion.
