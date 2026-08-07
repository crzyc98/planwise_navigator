# Implementation Plan: Plan-Design Optimizer

**Branch**: `135-plan-design-optimizer` | **Date**: 2026-08-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/135-plan-design-optimizer/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`planalign optimize <spec.yaml>` inverts the plan-design workflow from one-scenario-at-a-time hand tuning into a budget-bounded search: the user declares which config levers may vary (match formula tiers, auto-enrollment default rate, eligibility rules, vesting schedule — up to ~6-8 levers, discrete and/or bounded-continuous), one objective to minimize/maximize (or two as a Pareto tradeoff), and hard constraints on other metrics. The optimizer evaluates each candidate as a fully isolated, independently re-runnable scenario run over the existing `ScenarioRunPool`, ranks feasible candidates by objective value, and exports a candidate table (+ Pareto frontier for the two-objective case) with every candidate's underlying `.duckdb` retained for drill-down. The search strategy is grid seeding + local coordinate-descent refinement — never exhaustive enumeration at this scale — and is hard-capped by a mandatory `--max-runs N`, deterministic under a seed, and honest about failed/non-evaluable candidates and unsatisfiable constraints.

## Technical Context

**Language/Version**: Python 3.11 (matches `planalign_fit`, `planalign_ensemble`, `planalign_orchestrator`)
**Primary Dependencies**: Pydantic v2 (spec models), `planalign_orchestrator` (`ScenarioRunPool`, `ScenarioJob`, `resolve_worker_count`, `ConstructionSpec`/`build_orchestrator`, `config/export.to_dbt_vars`, `run_metadata`), `planalign_ensemble` (`CANONICAL_METRICS`, headline-metric extraction from `fct_workforce_snapshot`, `fct_metric_distributions` percentile reads), NumPy (already declared — Latin-hypercube-style continuous sampling, percentile lookups), Typer + Rich (CLI, matching `planalign fit`/`planalign backtest`), PyYAML (spec file parsing), `duckdb` Python client (read-only metric reads and compliance-mart checks), `planalign_orchestrator.excel_exporter` patterns (candidate table / frontier export)
**Storage**: DuckDB — one isolated `.duckdb` per evaluated candidate (never `dbt/simulation.duckdb`), plus a small optimizer-run metadata store (candidate ledger) under the run's output directory, mirroring the `planalign_fit` "pack directory" and `planalign_ensemble` "aggregate database" conventions rather than inventing a new persistence style
**Testing**: pytest (`-m fast` for spec validation, dedup, budget accounting, Pareto ranking with a mocked pool worker; `-m integration` for a small end-to-end 2-lever run against isolated `DATABASE_PATH` databases, per the project's isolated-DB validation rule)
**Target Platform**: Same as the rest of the CLI — macOS/Linux work laptops and analytics servers, single-threaded dbt by default, `ScenarioRunPool` sized from measured per-run peak RSS
**Project Type**: CLI + shared library package (`planalign_optimizer/`), consumed by `planalign_cli` — no new service; a Studio panel is explicitly out of scope for v1 (matches #460's own frontend deferral pattern, issue #554)
**Performance Goals**: No new performance target beyond the existing per-run cost baseline (`docs/perf/run_cost_profile_production.md`, ~90-120s/run for a 5-year horizon); the optimizer's own overhead (spec validation, sampling, dedup, ranking) must be negligible next to scenario-run cost — sub-second for a run-budget ≤ 200
**Constraints**: Every candidate run budget is a hard cap (FR-005, mandatory input, no default); design space bounded to ~6-8 levers in v1 (spec Clarifications); continuous-lever dedup is exact-match only, no tolerance; failed candidate runs are not retried and still consume budget (spec Clarifications); percentile-based constraint evaluation only activates when the user explicitly names a percentile (spec Clarifications)
**Scale/Scope**: Single-user CLI invocation; run-budget realistically 10-200 candidate evaluations per run (bounded by wall-clock: N runs / parallel workers × ~90-120s/run); reuses `ScenarioRunPool`'s existing memory-bounded worker sizing unchanged

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Event Sourcing & Immutability | PASS — every candidate is a normal isolated scenario run through the existing pipeline; no event-store changes. Reproducibility satisfied by FR-010 (search seed) plus the platform's existing per-scenario seed/config reproducibility. |
| II. Modular Architecture | PASS — new `planalign_optimizer/` package mirrors the proven `planalign_fit`/`planalign_ensemble` shape (small, single-responsibility modules: spec models, design-space sampling, search loop, candidate evaluation, Pareto ranking, export). No module is expected to exceed ~600 lines; each stays within 6-8 public functions/methods. |
| III. Test-First Development | PASS — fast unit tests planned for spec validation, dedup, budget accounting, and Pareto ranking (pure logic, mockable pool); integration test for one small end-to-end run in an isolated DB, matching the `planalign_ensemble` test suite's own split (`test_ensemble_planner.py` etc. vs `test_ensemble_end_to_end.py`). |
| IV. Enterprise Transparency | PASS — every candidate's config delta, objective value, and constraint status (including "non-evaluable"/"failed") is recorded; infeasible specs name the binding constraint (FR-011, SC-006); reused `run_metadata` conventions apply per candidate scenario. |
| V. Type-Safe Configuration | PASS — design-space spec, objective/constraint spec, and candidate records are Pydantic v2 models; config deltas resolve through the existing `to_dbt_vars` export path, no raw SQL string concatenation for table references. |
| VI. Performance & Scalability | PASS — no change to per-scenario execution; concurrency reuses `ScenarioRunPool`'s existing memory-bounded default. The optimizer adds no new heavy dbt models. Single-threaded dbt remains the per-worker default. |

No violations. Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/135-plan-design-optimizer/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md         # Phase 1 output (/speckit.plan command)
├── quickstart.md         # Phase 1 output (/speckit.plan command)
├── contracts/            # Phase 1 output (/speckit.plan command)
│   ├── spec-schema.md    # Design-space + objective/constraint YAML spec contract
│   └── cli-contract.md   # `planalign optimize` command contract
└── tasks.md              # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_optimizer/                    # New package (mirrors planalign_fit / planalign_ensemble)
├── __init__.py                         # Public API surface
├── models.py                           # Pydantic v2: LeverSpec, DesignSpaceSpec,
│                                        #   ObjectiveSpec, ConstraintSpec, Candidate,
│                                        #   OptimizerRun, ParetoPoint
├── spec_io.py                          # Load + validate a spec.yaml; loud, specific
│                                        #   validation errors (FR-003, FR-004)
├── design_space.py                     # Grid seeding + coordinate-descent local
│                                        #   refinement sampler bounded by run budget
│                                        #   (FR-001); exact-match candidate dedup (FR-012)
├── metrics.py                          # Metric vocabulary + evaluation: reuses
│                                        #   planalign_ensemble.extract for point-estimate
│                                        #   reads from a single candidate's snapshot mart,
│                                        #   and planalign_ensemble fct_metric_distributions
│                                        #   reads for percentile-based constraints (FR-015);
│                                        #   IRS-compliance pass/fail from dq_compliance_monitoring
├── evaluate.py                         # Resolves one candidate's effective config
│                                        #   (baseline + lever overrides via to_dbt_vars),
│                                        #   builds a ScenarioJob, records config delta,
│                                        #   classifies result: feasible / infeasible /
│                                        #   non-evaluable / failed (FR-007, FR-016)
├── search.py                           # Bounded search loop over ScenarioRunPool:
│                                        #   enforces mandatory run-budget cap (FR-005),
│                                        #   seeds deterministically (FR-010), reports
│                                        #   best-found-so-far (FR-011)
├── pareto.py                           # Pareto-efficient subset for two-objective specs
│                                        #   (FR-009)
├── export.py                           # Candidate table + frontier export (reuses
│                                        #   planalign_orchestrator.excel_exporter
│                                        #   conventions) (FR-013)
└── report.py                           # Human-readable run report (mirrors
│                                        #   planalign_fit's fit_report.md pattern)

planalign_cli/commands/optimize.py      # `planalign optimize <spec.yaml> --max-runs N
                                         #   [--database ...] [--output ...]` Typer command

tests/
├── test_optimizer_spec_io.py           # Spec validation: valid specs, invalid lever/
│                                        #   metric names fail loudly (FR-003, FR-004)
├── test_optimizer_design_space.py      # Sampling within budget, exact-match dedup,
│                                        #   degenerate 0/1-lever cases
├── test_optimizer_evaluate.py          # Config delta resolution, candidate
│                                        #   classification (feasible/infeasible/
│                                        #   non-evaluable/failed), no-retry-on-failure
├── test_optimizer_search.py            # Budget enforcement, determinism (same spec +
│                                        #   seed → same sequence), best-found-so-far
│                                        #   reporting, infeasible-spec reporting
├── test_optimizer_pareto.py            # Pareto-efficient subset correctness
├── test_optimizer_export.py            # Export completeness (every candidate present
│                                        #   regardless of feasibility)
├── test_optimizer_metrics.py           # Point-estimate vs percentile evaluation mode
│                                        #   selection (explicit-only activation, FR-015)
└── test_optimizer_end_to_end.py        # Small 2-lever run, isolated DATABASE_PATH,
                                         #   integration-marked
```

**Structure Decision**: New standalone library package `planalign_optimizer/` at the repo root, following the established `planalign_fit`/`planalign_ensemble` sibling-package pattern (not folded into `planalign_orchestrator`, which stays the execution/construction layer these packages consume). A single new CLI command module in `planalign_cli/commands/`. No API/Studio surface in this feature — a Studio panel is explicitly deferred (see #554 precedent for #460's own frontend split).

## Complexity Tracking

*No violations — table omitted.*
