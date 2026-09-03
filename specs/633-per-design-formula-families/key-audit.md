# Plan-Design Key Audit

The in-scope formula path was audited at every join, aggregation, window, and
publication boundary. The required calculation grain is
`(employee_id, plan_design_id, simulation_year)`.

| Model | Audit result |
|---|---|
| `int_employee_match_calculations` | PASS. Eligibility, workforce, family-arm, resolution, and final joins carry employee, design, and year. Family-arm aggregations group by the same grain. The guard evaluates eligible employees before publication. |
| `int_employer_core_contributions` | PASS after correction. Starting compensation groups by employee/design; schedule joins use design plus half-open band bounds; rate multiplicity and `ROW_NUMBER` partition by employee/design/year. The schema uniqueness expression now carries all three keys. |
| `int_deferral_match_response_events` | PASS. Design is assigned before parameter resolution and the parameter join is design-keyed. Enrollment history is employee-keyed because its source contract has no design column; no formula-family aggregation or dedup follows that can merge assigned designs. |
| `int_voluntary_enrollment_decision` | PASS. Assignment and eligibility joins carry employee/year and eligibility additionally carries design. Per-design match-magnet resolution reads the assigned design. Source `DISTINCT` operations occur before design assignment and cannot merge two assigned-design rows. |
| `int_proactive_voluntary_enrollment` | PASS. Assignment, parameters, and eligibility are joined before formula resolution; all design-sensitive joins carry the assigned design. Source `DISTINCT` occurs before the single sticky assignment is attached. |

The public schemas remain unchanged. `design_formula_families_json` is an
additive nullable column on append-only `run_metadata`; legacy rows therefore
remain readable as `NULL`. The inline scalar relation contains both family
selectors, match template, and four integration values. Graded, age, and points
schedule relations are design-keyed and use `[min, max)` bounds. The singular
tests `test_match_formula_arm_coverage` and `test_core_rate_band_resolution`
provide a second publication-layer net behind the runtime guards.
