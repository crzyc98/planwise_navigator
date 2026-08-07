# Phase 1 Data Model: Plan-Design Optimizer

All entities are Pydantic v2 models living in `planalign_optimizer/models.py`, except the candidate ledger, which is persisted (per research.md §8) as structured rows in the run's output directory rather than a shared database table. No `fct_*`/`int_*`/`dim_*` dbt model changes.

## LeverSpec

One searchable config lever, declared in the design-space spec.

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | Stable identifier for the lever, e.g. `employer_match.tier_1_rate`, `auto_enrollment.default_deferral_rate`, `vesting_schedule`. Validated against the v1 supported lever registry (match tiers/caps, AE default rate + scope, auto-escalation params, eligibility rules, vesting schedule choice). |
| `kind` | `Literal["discrete", "continuous"]` | Determines which of the two value fields below is populated. |
| `choices` | `list[str \| float] \| None` | Required and non-empty when `kind == "discrete"`; e.g. named vesting schedules, or a fixed set of AE-scope enum values. |
| `bounds` | `tuple[float, float] \| None` | Required when `kind == "continuous"`; `(min, max)` inclusive. |

**Validation rules**:
- Exactly one of `choices`/`bounds` populated, matching `kind`.
- `name` must resolve to a config path the optimizer knows how to overlay onto the baseline `SimulationConfig` (FR-001); an unresolvable name fails spec validation with the specific bad name (FR-003).
- `bounds.min < bounds.max` for continuous levers.

## DesignSpaceSpec

The full set of searchable levers for one optimizer invocation.

| Field | Type | Notes |
|---|---|---|
| `levers` | `list[LeverSpec]` | 0 to ~8 entries (spec Clarifications: v1 supports up to ~6-8 levers). 0 or 1 levers are valid degenerate cases (Edge Cases). |

**Validation rules**:
- No duplicate `LeverSpec.name` values.
- Levers not listed here are implicitly pinned to baseline — this is a behavioral guarantee of the evaluation code (research.md §4), not a field on this model.

## ConstraintSpec

One hard constraint on a metric.

| Field | Type | Notes |
|---|---|---|
| `metric` | `str` | Must be in the supported vocabulary: `CANONICAL_METRICS` from `planalign_ensemble` (`active_headcount`, `total_compensation`, `employer_match_cost`, `total_employer_plan_cost`, `participation_rate`, `avg_deferral_rate`), or `irs_compliance_pass` (boolean pass/fail from `dq_compliance_monitoring`). Unsupported names fail validation loudly (FR-004). |
| `operator` | `Literal["<=", ">=", "<", ">", "=="]` | |
| `threshold` | `float` | Compared against the metric's evaluated value. |
| `percentile` | `int \| None` | 1-99. When set, activates percentile-based evaluation for *this constraint only* (spec Clarifications: explicit-only, never auto-applied). When unset, evaluation is point-estimate (the default). |

## ObjectiveConstraintSpec

The objective(s) plus every hard constraint for one run.

| Field | Type | Notes |
|---|---|---|
| `objectives` | `list[ObjectiveTerm]` (1 or 2 entries) | 1 entry = single minimize/maximize target. 2 entries = tradeoff pair triggering Pareto-frontier reporting (FR-009). More than 2 is rejected at validation (out of v1 scope). |
| `constraints` | `list[ConstraintSpec]` | 0 or more. |

### ObjectiveTerm (nested)

| Field | Type | Notes |
|---|---|---|
| `metric` | `str` | Same supported vocabulary as `ConstraintSpec.metric`, excluding `irs_compliance_pass` (a pass/fail flag is not a sensible optimization target). |
| `direction` | `Literal["minimize", "maximize"]` | |

## Candidate

One evaluated point in the design space. Written as one row of the run's candidate ledger; the full evaluation detail (per-constraint status) is nested/serialized alongside it.

| Field | Type | Notes |
|---|---|---|
| `candidate_id` | `str` | Stable within the run (e.g. `candidate-0007`). |
| `lever_values` | `dict[str, str \| float]` | The resolved value of every declared lever for this candidate — the full config delta versus baseline, since undeclared levers never vary (FR-007). |
| `db_path` | `Path` | The candidate's isolated `.duckdb`, retained after the run for drill-down (FR-014). `None` only when `status == "failed"` and no database was ever produced. |
| `status` | `Literal["feasible", "infeasible", "non_evaluable", "failed"]` | Mutually exclusive, exhaustive classification (FR-008, FR-016). `"failed"` = the scenario run itself crashed/timed out/produced no usable output, never retried (spec Clarifications). `"non_evaluable"` = the run succeeded but the objective or a constraint's metric was unavailable from the mart. `"infeasible"` = evaluated successfully but failed ≥1 constraint. `"feasible"` = evaluated successfully and satisfied every constraint. |
| `objective_values` | `dict[str, float \| None]` | Keyed by objective metric name; `None` when non-evaluable for that metric. |
| `constraint_results` | `list[ConstraintResult]` | One entry per declared constraint. |
| `is_duplicate_of` | `str \| None` | Set to another candidate's `candidate_id` when this point was recognized as an exact-match repeat (FR-012) and its result was reused rather than re-evaluated; such candidates do not consume additional run-budget count. |
| `duration_seconds` | `float` | Wall time for this candidate's scenario run (0.0 for duplicates). |

### ConstraintResult (nested)

| Field | Type | Notes |
|---|---|---|
| `metric` | `str` | Matches the parent `ConstraintSpec.metric`. |
| `evaluation_mode` | `Literal["point_estimate", "percentile"]` | Always labeled explicitly (FR-015), even when the outcome is the default point-estimate mode. |
| `evaluated_value` | `float \| None` | `None` when non-evaluable. |
| `satisfied` | `bool \| None` | `None` when non-evaluable (never a fabricated true/false). |

## OptimizerRun

Ties one invocation together; this is the top-level object written to `report.md` / the export file.

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | Timestamped, matching the output directory name convention used by `planalign batch`/ensembles. |
| `design_space` | `DesignSpaceSpec` | As submitted. |
| `objective_constraint_spec` | `ObjectiveConstraintSpec` | As submitted. |
| `max_runs` | `int` | The mandatory run-budget cap (FR-005) — required at construction, no default. |
| `search_seed` | `int` | Deterministic search-path seed (FR-010), independent of per-candidate simulation seeds (research.md §7). |
| `baseline_config_fingerprint` | `str` | Hash of the baseline `SimulationConfig` this run was resolved against, for stale-baseline detection on re-run (Edge Cases). |
| `candidates` | `list[Candidate]` | Every evaluated candidate, including duplicates, failures, and non-evaluable ones — never filtered on write (FR-008, FR-013). |
| `ranked_feasible` | `list[str]` | `candidate_id`s of feasible candidates, ordered by objective value (single-objective case only). |
| `pareto_frontier` | `list[str] \| None` | `candidate_id`s on the Pareto-efficient frontier; populated only for the two-objective case (FR-009), `None` otherwise. |
| `binding_infeasible_constraints` | `list[str] \| None` | When zero candidates are feasible, the constraint metric name(s) that no evaluated candidate satisfied (FR-011, SC-006). |

**State transitions**: `OptimizerRun` has no in-place mutation once written — like every other artifact in this platform, a run's output directory is a finished, immutable record. A "re-run" is a new `OptimizerRun` (new `run_id`), not an update to a prior one, even when it reuses the same spec and seed (FR-010's determinism claim is about reproducing an equivalent run, not resuming one).

## Relationships

```
DesignSpaceSpec ──┐
                   ├──> OptimizerRun ──1:N──> Candidate ──1:N──> ConstraintResult
ObjectiveConstraintSpec ──┘                        │
                                                     └──1:1──> isolated .duckdb (via ScenarioJob)
```
