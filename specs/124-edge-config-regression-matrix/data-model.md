# Data Model: Edge-Configuration Regression Matrix

## EdgeConfigScenario

A frozen test-catalog record; not persisted by the product.

| Field | Type | Rules |
|---|---|---|
| name | string | Stable unique identifier; exactly four names initially. |
| config_path | repository path | YAML loaded through load_simulation_config. |
| census_path | repository path | Small CSV with stable IDs and explicit boundary labels/expected values. |
| start_year, end_year | integer | One or two projection years; end is not before start. |
| boundary | string | Human-readable configuration rule under test. |
| expected_groups | mapping | Non-empty groups on both sides of the relevant boundary. |
| assertion_kind | enum/string | cutoff enrollment, eligibility suppression, tenure match, or escalation cap. |
| sample_limit | integer | Positive and bounded at 20. |

Initial records:

1. broad_auto_enrollment_cutoff: all-eligible auto-enrollment with employees before and after an early hire-date cutoff; enrollment must respect the cutoff.
2. new_hire_eligibility_suppression: non-zero new-hire ineligible rate plus auto-enrollment; suppressed labeled new hires remain unenrolled while controls follow normal enrollment.
3. tenure_graded_employer_match: tenure-graded match bands with at least two completed-service groups; match treatment differs according to configured band.
4. auto_escalation_low_cap: escalation enabled with a low cap and employees below, equal to, and above the cap; final rates never exceed the cap.

## FixturePopulation

A checked-in CSV plus harness metadata.

All four initial cases use the 2025–2026 horizon. Their fixture groups are
`before_cutoff`/`after_cutoff`, `suppressed_new_hire`/`eligible_control`,
`short_service`/`long_service`, and `below_cap`/`at_cap`/`above_cap`. Effective
overrides are a 2015-01-01 enrollment cutoff, 50% new-hire ineligibility,
distinct tenure match treatment, and a 6% escalation cap.

- Required census fields are those accepted by the existing census loader.
- Metadata labels each employee's expected group (before_cutoff, after_cutoff, suppressed_new_hire, eligible_control, below_cap, at_cap, above_cap) without changing the product census schema.
- Validation requires all declared groups to be non-empty and checks relevant dates, tenure, enrollment, eligibility, and initial deferral values before simulation.

## ScenarioRun

A disposable run result containing scenario name, database path, config identity, horizon, and either completed status or a captured simulation exception. Assertions consume only completed runs. Failed database files are retained when the test session fails.

## TargetedAssertionResult

An in-memory result with case name, boundary, expected value/rule, observed value/rule, violations, and bounded sample rows. Empty violations pass; non-empty violations fail. Full-output equality is not involved.
