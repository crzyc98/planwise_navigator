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

## Setting it up in Studio

On the DC Plan page, turn on **Grandfathered plan design (advanced)**. It is
off by default and adds nothing to the saved configuration until you use it.

- **Hire-date cutoff.** Employees hired on or after this date get the new-hire
  design. Everyone hired earlier keeps the plan set on the page.
- **Design names.** The plan design IDs shown in results (defaults
  `existing_employees` and `new_hires`).
- **What is different for new hires.** The employer match, the core
  contribution, or both. Each uses the same editor as the plan-wide formula.
  Eligibility rules, automatic enrollment, automatic increases and employee
  behavior stay the same for both designs.
- **Who gets which design** previews both cohorts and their formulas before a
  run. Problems that would stop a run (a missing or invalid cutoff or name,
  identical designs, empty or overlapping tiers, match rates above 100%, a
  missing integration level) block saving with a message.

Studio saves `plan_design_assignment` with one `hire_date_cutoff` rule and two
complete `plan_design_parameters` entries. Turning the panel off asks first if
the setup was saved; saving then writes `null` for both keys, so everyone uses
the plan on the page, including when the setup came from the workspace. A setup
Studio didn't write in this shape (more than one cutoff, designs differing in
more than match and core, or an existing-employee design that differs from the
page) loads read-only and is kept exactly as saved. A scenario adds to its
workspace's designs rather than replacing them, so when the workspace already
defines designs, a scenario must use the same design names.

This is not Cost Comparison's **Grandfather existing employees** option, which
combines results from two separately completed runs. Here both designs run
inside one simulation.

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
