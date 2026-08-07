# Contract: Design-Space / Objective-Constraint Spec File

The user-authored input to `planalign optimize` is one YAML file combining a `design_space` block and an `objective` block, validated against `planalign_optimizer.models.DesignSpaceSpec` and `ObjectiveConstraintSpec` (see data-model.md) before any candidate is evaluated (FR-003).

## Shape

```yaml
design_space:
  levers:
    - name: employer_match.tier_1_rate       # discrete or continuous config lever
      kind: continuous
      bounds: [0.03, 0.06]
    - name: auto_enrollment.default_deferral_rate
      kind: continuous
      bounds: [0.03, 0.08]
    - name: vesting_schedule
      kind: discrete
      choices: [immediate, qaca_2_year, graded_5_year]

objective:
  objectives:
    - metric: total_employer_plan_cost
      direction: minimize
  constraints:
    - metric: participation_rate
      operator: ">="
      threshold: 0.85
      # percentile omitted → point-estimate evaluation (the default)
    - metric: total_employer_plan_cost
      operator: "<="
      threshold: 2400000
      percentile: 90                          # explicit → percentile-based evaluation
    - metric: irs_compliance_pass
      operator: "=="
      threshold: 1                             # 1 = pass, 0 = fail

baseline:
  config_path: config/simulation_config.yaml   # required; every undeclared lever is pinned here
```

## Two-objective (Pareto) form

```yaml
objective:
  objectives:
    - metric: total_employer_plan_cost
      direction: minimize
    - metric: participation_rate
      direction: maximize
```

## Validation contract

| Failure | Behavior |
|---|---|
| Unknown lever `name` | Fails before any scenario run starts; error names the exact bad lever string (FR-003). |
| Lever `kind` doesn't match populated `choices`/`bounds` | Fails validation; error identifies the lever and the mismatch. |
| More than ~8 levers declared | Fails validation with a message stating the v1 lever-count ceiling (spec Clarifications: ~6-8 levers). |
| Unknown `metric` in `objective`/`constraints` | Fails validation; error names the exact bad metric string and lists the supported vocabulary (FR-004). |
| More than 2 `objectives` entries | Fails validation — v1 supports single-objective or exactly a two-objective Pareto tradeoff, not N-objective. |
| `percentile` outside 1-99 | Fails validation. |
| No `max_runs` supplied (CLI flag, not this file) | Command refuses to start (FR-005) — see cli-contract.md. |

## Non-goals for this file

- It does not name a run budget (`--max-runs`) or a search seed — those are invocation-time CLI inputs (see cli-contract.md), not part of the reusable spec, so the same spec file can be run under different budgets without editing it.
- It does not name an output directory or export format — also CLI-level.
