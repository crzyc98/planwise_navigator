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

## Per-design benefits in 3.0.0

Assignment and benefit terms are separate. `plan_design_parameters` maps design
IDs to complete parameter sets for match, employer core, auto-enrollment,
deferral escalation, and eligibility. When enabling this map, supply definitions
for every assignable design; an assignment rule by itself does not change a
formula. The typed fields and units are defined in
[`plan_design.py`](../planalign_orchestrator/config/plan_design.py).

Supported match families are deferral-based, service-graded, tenure-graded, and
age-plus-service points-based. Core families are flat, service-graded,
age-banded, and points-based. Match rates and flat/service core rates are
fractions; age/points core schedule rates are percentages. Bands use lower
inclusive, upper exclusive bounds. Per-design auto-enrollment controls the
default deferral, window, and scope; eligibility controls waiting days;
escalation controls increment and cap. Other global rules still apply.

Employee-level `fct_yearly_events` and `fct_workforce_snapshot` facts expose the
assigned design ID. Review contributions and participation by this ID when
comparing grandfathered cohorts: scenario totals combine their outcomes.
These configurations estimate benefits under supplied terms; they do not
validate the terms against a plan document or determine legal compliance.
