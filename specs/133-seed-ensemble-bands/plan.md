# Implementation Plan: Seed Ensembles — Distribution Bands, Exceedance Risk, and Variance Attribution

**Branch**: `133-seed-ensemble-bands` | **Date**: 2026-08-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/133-seed-ensemble-bands/spec.md`

## Summary

Turn every headline simulation number into a distribution. Run N seeds per scenario through the existing bounded run pool (one isolated database each), aggregate the per-seed results into `fct_metric_distributions` in a dedicated ensemble database, and report P10/P50/P90 bands, per-year threshold exceedance probabilities, and a ranked one-factor-at-a-time variance attribution table — via CLI output and workbook export.

The technical approach is mostly *adoption* rather than construction: `ScenarioRunPool` already provides memory-bounded parallel seed execution with clean cancellation, `ScenarioJob` already carries a per-job seed and database path, `compute_config_fingerprint` already computes a seed-independent configuration identity, and `planalign_backtest` already demonstrates per-seed isolated runs. The genuinely new work is the aggregation layer, the presentation, and — the one substantial risk — per-subsystem seed plumbing in dbt for attribution.

**Phase 0 changed the shape of the attribution work.** An inventory of every production randomness site found that only three of the four subsystems the issue names are actually seed-variant: enrollment's ten hash sites omit the seed entirely (identical draws at every seed), and merit contains no randomness at all. Attribution therefore ships for **termination, hiring, and promotion**; enrollment seeding is carved out as a separate, explicitly-flagged behavior change. See `research.md` D1.

## Technical Context

**Language/Version**: Python 3.11; SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated `.sql`)
**Primary Dependencies**: `planalign_orchestrator` (`ScenarioRunPool`, `ScenarioJob`, `resolve_worker_count`, `ConstructionSpec`/`build_orchestrator`, `run_metadata`, `excel_exporter`); NumPy ≥1.24 (percentiles — already declared); Typer + Rich (CLI); Pydantic v2 (config); `duckdb` Python client
**Storage**: DuckDB. One database per seed plus one dedicated ensemble database per ensemble, under a timestamped directory in `var/ensembles/`. Per-seed databases are read-only inputs to aggregation and are never mutated after their run. The shared `dbt/simulation.duckdb` is never an ensemble target.
**Testing**: pytest with the existing marker scheme (`fast`, `integration`) and the E075 fixture library
**Target Platform**: macOS / Linux work laptop, on-premises
**Project Type**: CLI + orchestration library (no frontend work in this feature — Studio band charts are explicitly deferred)
**Performance Goals**: A 25-seed × 5-year ensemble completes without memory exhaustion under the existing worker budget (~1296 MiB/worker, `min(jobs, cpu-1, mem/1536MiB)`). Aggregation itself is negligible (~750 values at N=25).
**Constraints**: Bit-stable aggregates across repeat runs (SC-002); no per-seed database mutated post-run (FR-011a); no band-shaped number from a sample below the configured minimum (FR-013); default simulation behavior byte-identical after the seed refactor
**Scale/Scope**: N up to ~50 seeds; 6 headline metrics × horizon years; 3 attributable subsystems in v1

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Assessment | Verdict |
|---|---|---|
| **I. Event Sourcing & Immutability** | Adds no events and mutates none. Reinforces reproducibility: the whole feature rests on "same seed + same config ⇒ same world," and SC-002 makes that a tested property. FR-011a forbids writing to a completed run's database. | **PASS** |
| **II. Modular Architecture** | New code lands in a dedicated `planalign_ensemble/` package with one responsibility per module (seed planning, execution, extraction, aggregation, risk, attribution, reporting), each well under the ~600-line ceiling. No layer inversion: aggregation reads marts and writes a separate database. | **PASS** |
| **III. Test-First Development** | Aggregation, percentile, exceedance, and sufficiency logic are pure functions over small inputs — fast unit tests written first, no simulation required. The byte-identical seed-refactor gate is itself a test written before the refactor. Full-ensemble runs are `integration`. | **PASS** |
| **IV. Enterprise Transparency** | FR-023 stamps seed list, per-seed paths, fingerprint, and attribution flag into `run_metadata`. FR-019c reports reused vs. freshly-executed baselines. FR-013/027 make thin samples loud. Research D1's honest "not stochastic" reporting is this principle applied to a place where a plausible number would have been misleading. | **PASS** |
| **V. Type-Safe Configuration** | Ensemble settings (seed count, thresholds, minimum sample, attribution seeds) become Pydantic v2 models validated at load. dbt access stays `{{ ref() }}`/`{{ var() }}`; the new `subsystem_seed()` macro is a var lookup, not string concatenation of table names. | **PASS** |
| **VI. Performance & Scalability** | Concurrency delegated to the already-measured `resolve_worker_count` budget; serial (`--parallel 1`) remains available and is the comparison baseline. Aggregation is O(seeds × years × metrics) in memory over a trivially small set. | **PASS** |

**Initial gate: PASS — no violations, Complexity Tracking not required.**

**Post-Phase-1 re-evaluation: PASS.** The design added one dbt macro and a set of optional dbt vars, which strengthens rather than strains Principle V (a named macro replaces ten scattered inline literals). The one item worth flagging under Principle I is that seeding enrollment *would* change existing results — which is exactly why the design carves it out of this feature rather than bundling it.

## Project Structure

### Documentation (this feature)

```text
specs/133-seed-ensemble-bands/
├── plan.md              # This file
├── spec.md              # Feature specification (clarified 2026-08-03)
├── research.md          # Phase 0 output — includes the D1 randomness inventory
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md           # Command surface + exit codes
│   └── fct_metric_distributions.md  # Table contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
planalign_ensemble/                 # NEW — the feature's home
├── __init__.py                     # Public surface
├── models.py                       # Pydantic: EnsembleSpec, Threshold, SeedPlan, results
├── planner.py                      # Seed derivation, duplicate rejection, run-count disclosure
├── runner.py                       # ScenarioJob construction + pool submission; module-level worker
├── extract.py                      # Per-seed metric extraction (read-only connections)
├── aggregate.py                    # Percentiles, sufficiency gate, fct_metric_distributions write
├── risk.py                         # Threshold exceedance
├── attribution.py                  # OFAT freeze/pair/reuse orchestration + variance shares
├── provenance.py                   # run_metadata ensemble columns
└── report.py                       # Rich tables for CLI

planalign_orchestrator/
└── excel_exporter.py               # MODIFIED — distribution + attribution sheets

planalign_cli/commands/
├── simulate.py                     # MODIFIED — --seeds/--seed-list/--attribution (BOTH definitions)
└── batch.py                        # MODIFIED — batch equivalent

dbt/macros/utils/
└── subsystem_seed.sql              # NEW — var('random_seed_<name>', var('random_seed', 42))

dbt/models/intermediate/events/     # MODIFIED — seed call sites only, byte-identical at defaults
├── int_termination_events.sql      #   3 sites
├── int_new_hire_termination_events.sql  # 4 sites
├── int_hiring_events.sql           #   2 sites
└── int_promotion_events.sql        #   1 site

tests/
├── test_ensemble_aggregate.py      # fast — percentiles, sufficiency, determinism
├── test_ensemble_planner.py        # fast — seed derivation, duplicates, run counts
├── test_ensemble_risk.py           # fast — exceedance boundaries
├── test_ensemble_attribution.py    # fast — pairing, reuse guard, variance shares
├── test_subsystem_seed_identity.py # integration — byte-identical gate (blocks the refactor)
└── test_ensemble_end_to_end.py     # integration — full ensemble in isolated DBs
```

**Structure Decision**: a new top-level `planalign_ensemble/` package, mirroring how `planalign_fit/` and `planalign_backtest/` are organized. Ensembles are a distinct capability with their own lifecycle, not an extension of the per-run orchestrator, and keeping them separate avoids growing `planalign_orchestrator` (Principle II). Only three existing modules are touched — the exporter and the two CLI command files.

## Implementation Sequencing

Ordered so each stage is independently landable and the risky work comes after the safe work is proven.

| Stage | Delivers | Gate before proceeding |
|---|---|---|
| **1. Aggregation core** | `models`, `planner`, `extract`, `aggregate` + fast tests | Percentiles match independent recomputation; repeat runs bit-identical (SC-002/003) |
| **2. Ensemble runner** | `runner`, provenance, CLI `--seeds`, Rich output — **User Story 1 complete** | 25-seed ensemble completes within the worker budget; provenance stamped (SC-005) |
| **3. Risk statements** | `risk` + thresholds config — **User Story 2 complete** | Boundary thresholds report exactly 100%/0% (SC-004) |
| **4. Export** | Exporter sheets — **User Story 4 complete** | Sheets match stored values; absent when no ensemble (FR-025) |
| **5. Seed refactor** | `subsystem_seed()` macro + 10 call sites, **no attribution logic yet** | **Hard gate**: full pipeline before/after is byte-identical at defaults |
| **6. Attribution** | `attribution` + CLI `--attribution` — **User Story 3 complete (3 subsystems)** | Dominant subsystem ranked first; unfrozen ensemble ≡ plain ensemble (SC-006/007) |

Stage 5 is the risk concentration. It ships as a pure refactor with a byte-identical gate and *no behavioral consumer*, so it can be validated and landed on its own evidence before any attribution logic depends on it.

**Deliberately not in this feature**: seeding enrollment's ten hash sites. It changes results for every existing scenario and belongs in its own change with its own before/after evidence (research.md D1).

## Validation Strategy

Per the isolated-database rule (CLAUDE.md §8, and the standing project memory on this), **no stage validates against `dbt/simulation.duckdb`.**

- Fast unit tests operate on synthetic per-seed metric values — no simulation, no database.
- The Stage 5 byte-identical gate builds the same isolated database twice (pre- and post-refactor) and compares `fct_yearly_events` and `fct_workforce_snapshot` exactly.
- End-to-end ensemble tests run small-census, few-seed ensembles into `tmp_path` databases.
- Attribution correctness (SC-006) uses a purpose-built scenario with one subsystem configured dominant and another effectively deterministic, rather than asserting against numbers from a production config.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.

## Open Risks

| Risk | Mitigation |
|---|---|
| Stage 5 refactor is not byte-identical (e.g. a rendered-string difference) | The fallback chain `var('random_seed_<n>', var('random_seed', 42))` renders the same characters when unset; the gate catches any deviation before attribution depends on it |
| Attribution shares are noisy at the default K | FR-020 requires reporting seed count and method with every share; SC-006 validates *ranking*, which is what the feature promises, not point precision |
| Disk footprint at large N | FR-028 discard option; footprint estimated before the run starts |
| Enrollment's non-stochasticity surprises a reader of the attribution table | Reported explicitly as "not stochastic", never as 0% (research.md D1) |
