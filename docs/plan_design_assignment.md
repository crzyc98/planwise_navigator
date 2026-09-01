# Plan-design assignment

`plan_design_assignment` assigns every employee exactly one design without
changing any plan formula. Rules are evaluated in list order only when the
employee first enters the simulation; the resulting assignment is then carried
forward by `int_plan_design_assignment_accumulator`.

```yaml
plan_design_id: legacy_design  # retained for backward compatibility
plan_design_assignment:
  default_plan_design_id: legacy_design
  rules:
    - type: hire_date_cutoff
      cutoff: 2026-01-01
      plan_design_id: current_design
```

Employees hired on or after the cutoff receive `current_design`; all others
receive `legacy_design`. Existing employees are never reevaluated in later
years. If the block is omitted, the legacy scalar `plan_design_id` is used and
the generated results retain the prior single-design behavior.

The config fingerprint covers the complete ordered assignment block. The
append-only `run_metadata.design_set_json` column also records the sorted set of
design IDs that the run can assign.

Existing reporting marts remain aggregated across plan designs for Layer 2's
foundation. The employee-level `fct_yearly_events` and
`fct_workforce_snapshot` facts expose the real design ID, so later cohort-aware
reports can group by it explicitly without silently changing today's totals.
