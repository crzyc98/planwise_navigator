# Phase 1 Data Model: New Hires Voluntarily Enroll in Their Hire Year

**Feature**: 096-newhire-voluntary-enroll
**Date**: 2026-06-15

This is a dbt/SQL behavior fix. No schema migration is required — no new tables and no new persisted
columns. The "data model" below describes the entities and the column-level contract changes within
existing models that the fix relies on.

## Entities

### New-Hire Voluntary Enrollment Candidate (logical, within `int_voluntary_enrollment_decision`)

A current-year new hire who is eligible during the hire year and is added to the voluntary enrollment
evaluation population.

| Attribute | Source | Notes |
|-----------|--------|-------|
| `employee_id` | hire events / `int_new_hire_compensation_staging` | Current-year new hire |
| `employee_ssn` | same | |
| `employee_hire_date` | same | Hire date within current simulation year |
| `eligibility_date` | `employee_hire_date + eligibility_waiting_days` | Derived; default waiting 0 |
| `simulation_year` | `var('simulation_year')` | Hire year |
| `current_age` | new-hire demographics | For age segmentation |
| `current_tenure` | `0` | New hire |
| `level_id` | new-hire demographics | For job-level segmentation |
| `employee_compensation` | new-hire compensation | For income segmentation + match |
| `employment_status` | `'active'` | New hires are active in hire year |

**Inclusion rule**: included only when `eligibility_date` falls within the current simulation year
(`EXTRACT(YEAR FROM eligibility_date) <= simulation_year` and the employee is active). Not-yet-eligible
new hires are excluded and re-evaluated in the year they become eligible.

### Voluntary Enrollment Decision (existing output of `int_voluntary_enrollment_decision`)

Unchanged output contract; the candidate population is widened to include the entity above. Fields:
`will_enroll` (probabilistic, demographic rate), `selected_deferral_rate` (0.01–0.10),
`proposed_effective_date`, plus audit fields (`enrollment_random`, `deferral_random`, etc.).

**Contract change**: for current-year new hires, `proposed_effective_date` MUST equal the eligibility
date (`employee_hire_date + eligibility_waiting_days`) rather than `hire_date + auto_enrollment_window_days`.

### Voluntary Enrollment Event (existing, in `int_enrollment_events` → `fct_yearly_events`)

Immutable enrollment event. No structural change. The fix causes the event to be **generated in the
hire year** for selected new hires, with `effective_date = eligibility_date` and
`event_category = 'voluntary_enrollment'`.

### Annual Snapshot Record (existing, `fct_workforce_snapshot`)

No structural change. Already propagates voluntary enrollment (feature 095). The fix ensures the
hire-year record reflects participation, deferral rate, and employer match for hire-year enrollees.

## State Transitions

```
New hire (hire year Y, eligible in Y)
  └─ evaluated in int_voluntary_enrollment_decision for year Y   [NEW: previously skipped until Y+1]
       ├─ will_enroll = false  → not participating in Y snapshot (correct, per configured rate)
       └─ will_enroll = true   → voluntary enrollment event, effective = eligibility date in Y
                                  → Y snapshot: participating, deferral rate, employer match
                                  → carried forward to Y+1, Y+2, … (no duplicate enrollment event)
```

## Validation Rules (enforced by tests)

- VR-1: For each current-year new hire with `will_enroll = true`, exactly one `voluntary_enrollment`
  event exists, dated within the hire year (FR-006, SC-005).
- VR-2: The enrollment event `effective_date` equals `employee_hire_date + eligibility_waiting_days`
  (FR-003).
- VR-3: The hire-year share of eligible new hires who enroll is > 0 and ≈ the configured demographic
  voluntary rate, and < 100% of eligible new hires (FR-002, SC-001).
- VR-4: No eligible new-hire enrollee has its first participating snapshot year later than its
  enrollment event year (SC-003).
- VR-5: Hire-year enrollees appear as participating with their deferral rate, and (non-zero match
  formula) with employer match > 0, in the hire-year snapshot (FR-004, SC-002, SC-004).
</content>
