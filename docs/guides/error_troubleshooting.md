# Error Troubleshooting

## Enrollment decision projection

Before every event-generation year, PlanAlign rebuilds the disposable
`enrollment_decision_projection` from `int_baseline_workforce` and prior,
scenario/plan-scoped `fct_yearly_events`. This is the only supported source of
post-census enrollment history for enrollment decision models.

If dbt reports that `enrollment_decision_projection` is missing, rerun through
the orchestrator. It creates the empty source relation immediately after reset
and replaces it atomically before event generation. Do not manually create or
edit the relation.

If a later year fails dependency validation, the prior year's accumulator state
is absent or incomplete. Rerun the simulation from its configured start year,
or restore the prior successful state; do not bypass the error by treating the
employee as unenrolled.

## Safe reruns

`setup.clear_mode: all` clears configured tables once before a new simulation
run. It does not authorize a later-year full refresh. Omit `clear_mode` or use
`year` for idempotent year-scoped cleanup that preserves earlier years.

## Audit trace

To audit an employee, compare the census row, prior `fct_yearly_events`, the
projection's `latest_event_*` provenance and `current_deferral_rate`, the
accumulator, and the workforce snapshot in chronological order. The projection
must only contain facts from years before its `decision_year` and must match
the active scenario and plan design.
