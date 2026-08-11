# Contract: Employer Contribution Service Credit

## Canonical provider

For each `(scenario_id, plan_design_id, employee_id, simulation_year)`, `int_workforce_state_accumulator.current_tenure` is the canonical completed-years-of-service value for employer contribution decisions.

- Continuing active employee: the accepted prior-year value advances once.
- Hire in the decision year: `0` completed years.
- Termination in the decision year: completed years through `termination_date`, as defined by `calculate_tenure`.
- Reset, rehire, or broken prior service: consumers use the value recorded by the workforce accumulator and do not reconstruct missing credit.

## Consumer obligations

`int_employer_eligibility` must:

- expose `current_tenure` equal to the canonical provider value;
- compare that value with both configured service requirements;
- preserve existing hours, status, and exception rules; and
- record an auditable reason without changing the service value when an exception applies.

`int_employer_core_contributions` and `int_employee_match_calculations` must:

- consume the eligibility flags produced from the canonical value;
- use that same value for service-graded tier lookup;
- use that same value in points-based calculations;
- expose the same value as `applied_years_of_service` where the existing formula contract audits service; and
- never infer service from a prior-year benefit or snapshot record.

## Required invariants

For the current build year:

```text
eligibility.current_tenure
  = workforce.current_tenure

core.applied_years_of_service
  = FLOOR(workforce.current_tenure)

service_dependent_match.applied_years_of_service
  = FLOOR(workforce.current_tenure)
```

When an eligibility requirement is enforced:

```text
eligible AND NOT explicit_exception
  => canonical_service >= configured_minimum_service
```

Equality is exact. A tolerance of one year is not permitted.

## Compatibility

- No YAML/Pydantic setting, default, or export key changes.
- No event type, API, CLI, Studio, public mart, or saved-run format changes.
- Flat and age-banded core rates do not acquire a service dependency.
- Match backward-compatibility mode remains available when `apply_eligibility: false`.
- Existing saved results are not rewritten; corrected values appear only after rerun.
- No database migration or public contract version change is required because
  the correction changes values in existing internal fields only.

## Validation fixtures

- `tests/fixtures/employer_eligibility_tenure/wait_0.yaml` through
  `wait_3.yaml` drive the isolated 2025–2029 wait matrix.
- `tests/fixtures/employer_eligibility_tenure.py` injects the synthetic census,
  asserts non-empty service boundaries, and builds the allowed experienced
  termination tier case.
- `baseline_characterization.json` pins the pre-fix opening-year waits 1/2/3
  and all-year zero-wait aggregates without retaining sensitive row data.

## Requirement traceability

| Contract behavior | Automated evidence | Requirements |
|---|---|---|
| Eligibility copies workforce service exactly | `assert_employer_eligibility_service_matches_workforce`; fast deliberate-offset query test | FR-001, FR-002, FR-004, FR-007; SC-003, SC-006 |
| Below-threshold employees remain ineligible except for explicit exceptions | `assert_employer_tenure_requirements_enforced`; 2-/3-year isolated scenarios | FR-003, FR-005, FR-008; SC-002 |
| Core and match rate decisions use the same service | strict core/match audit tests; termination boundary scenario | FR-006; SC-003 |
| Opening year and zero wait retain characterized outputs | aggregate synthetic baseline characterization | FR-005, FR-009; SC-004, SC-005 |
| Multi-year waiting periods produce distinct results | isolated 1-/2-/3-year five-year cost comparison | SC-001 |
