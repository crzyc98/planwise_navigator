# Implementation Plan: Social Security Integrated Employer Core Contribution

**Branch**: `126-ss-integrated-core` | **Date**: 2026-07-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/126-ss-integrated-core/spec.md`

## Summary

Add a Social Security taxable wage base to the year-indexed statutory limits seed, then layer a **permitted-disparity modifier** on the employer core contribution: the existing status (`flat`, `graded_by_service`, `points_based`, `age_banded`) continues to resolve the **base rate**, and integration adds a **disparity rate** on recognized compensation above an integration level.

The technical approach mirrors the age-banded core (#522, `ec8043a`) almost exactly, because that feature established every seam this one needs: a rate expression assembled in Jinja and used once, a Pydantic tier model plus a load-time validator wired into `SimulationConfig.validate_core_age_schedules`, dual validation of the direct-YAML and Studio config shapes, and an isolated-DB integration suite. This feature adds one seed column, one macro, one config group, one validator, and five audit columns — no new models, no new events, no orchestration change.

Two decisions carry the design:

1. **§401(l) legality is validated in Python at config load, not in SQL.** The disparity factor depends only on configuration values and the wage base for each year, both available without a database. This keeps the failure loud and early (FR-012) and unit-testable in the fast suite (Assumption 8).
2. **When integration is disabled, the Jinja emits today's amount expression verbatim.** Byte-identical output (FR-007) is guaranteed by textual identity of the SQL, not by arithmetic reasoning about rounding.

## Technical Context

**Language/Version**: Python 3.11 (config validation, tests); SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated `.sql`); TypeScript/React (Studio)
**Primary Dependencies**: Pydantic v2 (`CoreIntegrationSettings`, reusing the `AgeCoreTier` pattern in `planalign_orchestrator/config/workforce.py`); existing dbt macros + seeds; React/Vite + Tailwind (Studio); pytest
**Storage**: DuckDB. **No new tables and no schema change to any `fct_*` model.** One column added to the `config_irs_limits` seed; five audit columns added to the existing `int_employer_core_contributions` table materialization.
**Testing**: `pytest -m fast` for §401(l) validation (no database); `pytest -m integration` against isolated per-run DuckDB files built through `ConstructionSpec`/`build_orchestrator`, reusing the harness shape of `tests/integration/test_age_banded_core_contributions.py`. The shared dev database is never built into.
**Target Platform**: macOS/Linux work laptops, single-threaded dbt (`--threads 1`)
**Project Type**: Simulation engine (dbt/SQL transformation layer + Python orchestrator + FastAPI/React Studio)
**Performance Goals**: No measurable change. Integration adds a scalar column to an existing ~12-row seed join plus two arithmetic terms in a per-employee `CASE`. No new model, no new dbt invocation, no change to the run schedule.
**Constraints**: `integration.enabled: false` must produce byte-identical output for all four core rate shapes; illegal disparity rates must fail before any simulation work begins; the integration level must not be threaded through the mid-year proration at `int_employer_core_contributions.sql:~103-128`.
**Scale/Scope**: ~12 seed rows; per-employee arithmetic across the existing eligible population (100K+ employees supported unchanged). Roughly 8 files changed in the engine, 6 in Studio, 4 test files added.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — see "Post-Design Re-check" below.*

| Principle | Assessment | Verdict |
|---|---|---|
| **I. Event Sourcing & Immutability** | No new event types. Employer core contributions are a derived calculation over `fct_yearly_events` and the workforce state accumulator, not an event stream. Determinism is preserved: the calculation is pure arithmetic over existing inputs plus a year-indexed constant. | ✅ Pass |
| **II. Modular Architecture** | The disparity arithmetic goes in a dedicated macro (`get_integrated_core_amounts`), mirroring `get_age_banded_core_rate`, rather than inlining a third rate concept into an already-long model. Validation lands in the existing `config/workforce.py` validator module. No module approaches the ~600-line limit; no new layer, no circular dependency (`seeds → intermediate`, unchanged direction). | ✅ Pass |
| **III. Test-First Development** | §401(l) validation is pure-Python and belongs in the fast suite (<10s), so validation tests are written before the validator. The three ordering decisions each get a named integration test written against the fixture before the SQL changes. | ✅ Pass |
| **IV. Enterprise Transparency** | This principle is the feature's motivation. Five audit columns expose the integration level applied, the excess, both contribution components, and the wage base — so a number can be checked line-by-line against a plan document. Validation failures name the applicable limit and the violating value (FR-014). | ✅ Pass |
| **V. Type-Safe Configuration** | New settings are validated by a Pydantic v2 model (`CoreIntegrationSettings`) with explicit constraints, invoked from the existing `@model_validator(mode="after")`. All SQL references use `{{ ref() }}`. **Inherited deviation**: `employer_core_contribution` is an untyped dict extra on `SimulationConfig`; this feature follows that established shape rather than restructuring it, exactly as #522 did with `AgeCoreTier`. Not a new violation. | ✅ Pass |
| **VI. Performance & Scalability** | Adds one scalar seed column to a CTE that already reads that seed, plus two multiply-add terms per employee row. No new model, no new dbt command, no change to `run_execution_metadata` schedule length. | ✅ Pass |

**Gate result**: PASS, no violations to justify. The Complexity Tracking table is intentionally absent.

## Project Structure

### Documentation (this feature)

```text
specs/126-ss-integrated-core/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── configuration-and-ui.md   # Phase 1 output
├── checklists/
│   └── requirements.md  # /speckit.specify output
└── tasks.md             # /speckit.tasks output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
dbt/
├── seeds/
│   ├── config_irs_limits.csv                      # + social_security_wage_base column
│   └── schema.yml                                 # + column type declaration
├── dbt_project.yml                                # + column type declaration
├── macros/
│   └── get_integrated_core_amounts.sql            # NEW: base/disparity split
└── models/intermediate/
    └── int_employer_core_contributions.sql        # + integration CTE, + 5 audit columns

planalign_orchestrator/config/
├── workforce.py                                   # + CoreIntegrationSettings,
│                                                  #   validate_core_integration(),
│                                                  #   permitted_disparity_factor()
├── loader.py                                      # + integration branch in the existing
│                                                  #   @model_validator (both config shapes)
└── export.py                                      # + integration vars in
                                                   #   _export_core_contribution_vars and the
                                                   #   dc_plan (Studio) export path

planalign_api/services/
└── ndt_service.py                                 # + column in _ensure_seed_current tuple

planalign_studio/components/
└── ScenarioCostComparison.tsx                     # + derivePlanSummary integration clause
                                                   #   (label fix only — no Studio editor;
                                                   #    User Story 4 removed 2026-07-30)

tests/
├── fixtures/integrated_core/                      # NEW: census + configs spanning the
│                                                  #   wage base, the 401(a)(17) cap, and a
│                                                  #   mid-year hire
├── unit/config/test_core_contribution_validation.py   # + §401(l) validation cases
├── unit/orchestrator/test_config_export.py            # + integration var export
└── integration/test_integrated_core_contributions.py  # NEW: ordering decisions + parity
```

**Structure Decision**: No new packages or directories beyond one test fixture folder. The feature slots into the seams the age-banded core established — dbt macro + model, config validation, config export — which is the strongest available evidence that the "integration as a modifier, not a status" design (FR-005) costs nothing structurally.

**Amendment 2026-07-30 — User Story 4 removed.** Scenario cost comparison is existing functionality, so the feature does not build it. The Studio integration editor is dropped with it; integration is configured in scenario YAML. Two consequences worth recording:

1. The dbt var export is a **User Story 1 dependency**, not a reporting task. It was mis-filed under the removed story while the MVP's SQL reads those vars — without it the vars fall back to defaults and integration silently never activates.
2. `derivePlanSummary` still needs its integration clause (FR-020). It labels both scenarios in the comparison view from one function, so a flat and an integrated design would otherwise appear under identical text while showing different costs. Kept as a cross-cutting fix in Phase 8.

**Amendment 2026-07-30 — §401(l) module placement.** `planalign_orchestrator/config/workforce.py` is already 618 lines, over the ~600-line Principle II ceiling, so the factor table, level resolver, seed reader, and validator go in a new `planalign_orchestrator/config/permitted_disparity.py`. `workforce.py` gains only `CoreIntegrationSettings`, beside the sibling `AgeCoreTier`.

## Phase 0: Research

See [research.md](./research.md). Seven decisions resolved, no open NEEDS CLARIFICATION. Headlines:

- **R1**: Byte-identical disabled output is achieved by Jinja-emitting today's expression verbatim, not by reasoning about rounding equivalence.
- **R2**: The §401(l) factor is derivable without a database for two of three level modes; `fixed_dollar` and the `$10,000` floor clause need the wage base, read from the seed **CSV** (not DuckDB), preserving fast-suite testability.
- **R3**: Validation must run **per simulation year**, because the level-to-wage-base ratio moves with the wage base under `fixed_dollar`.
- **R4**: `_ensure_seed_current`'s fixed-tuple check is sound as written (`count == len(tuple)`); the issue's concern does not reproduce. Only the tuple needs the new member.
- **R5**: `schema.yml` and `dbt_project.yml` already disagree about this seed and both are partial; "declare in both places" is convention, not load-bearing.
- **R6**: The 2026 seed row is flagged `is_estimated=false` but duplicates 2025 verbatim — a pre-existing data smell that constrains how the 2026 wage base may be sourced.
- **R7**: Integration level rounds half-up to whole dollars, with the identical rule applied in Python validation and SQL.

## Phase 1: Design

- **[data-model.md](./data-model.md)** — the seed column, the `CoreIntegrationSettings` shape and its constraints, the five audit columns, and the §401(l) factor derivation as an explicit function.
- **[contracts/configuration-and-ui.md](./contracts/configuration-and-ui.md)** — the direct-YAML config contract, the Studio `dc_plan` contract, the dbt var contract between them, and the validation error-message contract.
- **[quickstart.md](./quickstart.md)** — isolated-DB verification recipe, including the flat-vs-integrated cost reconciliation and the disabled-parity check.

### Post-Design Re-check

Re-evaluated after the Phase 1 artifacts were written. No principle moved from Pass. Two design outputs strengthen the earlier assessment:

- **Principle II** improved rather than held: extracting `get_integrated_core_amounts` means `int_employer_core_contributions.sql` gains an integration CTE and audit columns but no new inline rate arithmetic.
- **Principle III** is now concretely satisfiable: because R2 keeps the wage base reachable from a CSV, every §401(l) boundary in the FR-013 table is a fast-suite unit test with no database, which is what SC-006 demands.

**Gate result after design**: PASS.

## Risks

| Risk | Mitigation |
|---|---|
| Byte-identical parity (FR-007) is quietly broken by refactoring the amount expression | R1: disabled path emits the current expression verbatim. Parity is asserted by a test that runs the same fixture on both sides of the change and compares full result sets, not aggregates. |
| The §401(l) factor table is wrong | It is the highest-uncertainty item and is called out in the spec checklist for expert review. It is isolated in one pure function (`permitted_disparity_factor`) so a correction touches one place and its table-driven tests. |
| Integration is configured but silently never activates | The dbt vars have model-side defaults, so a missing export produces a clean run that computes nothing. T027b is ordered ahead of every SQL task, and the US1 integration tests assert non-zero disparity on a fixture built to produce it — a vacuous pass is not possible. |
| A future Studio editor validates differently from the CLI | The validator is invoked from `SimulationConfig`'s existing `@model_validator` and is shape-agnostic, so adding the `dc_plan` shape later is a wiring change, not a rewrite. #522's commit records a precedence bug where no Studio-configured design ever reached the NDT check — worth reading before adding that shape. |
| 2026 wage base sourced from a stale or invented figure | FR-002 requires the SSA announcement. R6 records that the neighbouring 2026 seed row is itself suspect, so it must not be used as a pattern to copy. |

## Out of Scope (restated from spec, to bound `/speckit.tasks`)

Employer match formulas; non-safe-harbor and offset integration designs; cumulative/multi-plan permitted disparity; any other use of the wage base. Also explicitly out of scope: fixing the pre-existing 2026 seed row for the *other* limit columns (R6), and reconciling the pre-existing `schema.yml`/`dbt_project.yml` column-type divergence beyond adding the new column (R5).
