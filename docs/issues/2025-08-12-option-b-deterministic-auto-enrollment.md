# Issue: Deterministic Auto-Enrollment for In-Scope New Hires (Option B)

- Status: implemented
- Date: 2025-08-12
- Owner: PlanWise Navigator (dbt + orchestrator)

## Summary

We adopted Option B for auto-enrollment semantics: All in-scope new hires are auto-enrolled deterministically; the only behavioral randomness is opt-out. This replaces prior behavior where new-hire auto-enrollment was subject to a demographic probability gate.

Rationale: “Auto-enrollment is inertia” — if a new hire is in scope, they should be enrolled by default; randomness applies to opt-out, not to the auto-enrollment decision.

## Scope

- Applies when `auto_enrollment_scope = 'new_hires_only'`.
- In-scope definition: Hired in `simulation_year` (respecting optional `auto_enrollment_hire_date_cutoff`).

## Changes Implemented

1) int_enrollment_events.sql
- Active population now includes current-year new hires (union with `int_hiring_events`) so first-year NH_YYYY are eligible in their hire year.
- “New hires only” scope check: hire year must equal `simulation_year`; optional cutoff still respected.
- Deterministic AE policy:
  - If `auto_enrollment_scope = 'new_hires_only'`, bypass the demographic probability gate entirely and generate enrollment events for all eligible, in-scope new hires.
  - Event categorization: When scope is `new_hires_only`, set `event_category = 'auto_enrollment'` for all such enrollments (not tied to age segment).
- Opt-out events remain probabilistic and apply to all newly enrolled employees (no longer limited to ‘young’ only).
- Registry lookahead guard: `previous_enrollment_state` ignores future-year enrollments (`first_enrollment_year <= current_year`).

2) int_deferral_rate_state_accumulator.sql (DSA)
- Source of truth for “who is enrolled this year” now comes from `int_enrollment_state_accumulator` (ESA).
- Attributes for enrolled employees are joined from `int_employee_compensation_by_year` with a fill from `int_hiring_events` for first-year new hires.
- Result: newly enrolled (including AE) employees get a positive `current_deferral_rate` so the snapshot marks them as participating.

3) run_multi_year.py
- Vars: Enrollment + eligibility variables are extracted from `config/simulation_config.yaml` and passed into dbt via JSON `--vars`.
- Ensures models receive `auto_enrollment_scope`, `auto_enrollment_hire_date_cutoff`, etc.

## Outcome / Validation

Observed improvements after full run:
- 2025 snapshot now shows non-zero `participating - auto enrollment` for in-scope new hires.
- Participation increased in 2025 (and multi-year) due to deterministic AE.

Targeted validation (example for 2025):
- Enrollment events by category:
  - `SELECT event_category, COUNT(*) FROM fct_yearly_events WHERE simulation_year=2025 AND event_type='enrollment' GROUP BY 1;`
- Snapshot participation detail:
  - `SELECT participation_status_detail, COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year=2025 GROUP BY 1;`
- ESA enrollment method:
  - `SELECT enrollment_method, COUNT(*) FROM int_enrollment_state_accumulator WHERE simulation_year=2025 AND enrollment_status=true GROUP BY 1;`

Expected:
- Increased `auto_enrollment` events in 2025 (NH_2025_*).
- Snapshot contains `participating - auto enrollment` for in-scope new hires.

## Policy Clarification

- Option B semantics (adopted): If `auto_enrollment_scope='new_hires_only'`, all eligible, in-scope new hires are enrolled with method ‘auto’. Opt-out is the only behavioral gate.
- Optional future enhancement: introduce a `deterministic_auto_enrollment` var to toggle this behavior independently of scope, if needed.

## Related Models to Align (Future-Proofing)

If the pipeline uses these models, align them to Option B for consistency:
- `int_enrollment_decision_matrix`:
  - Route all in-scope new hires to auto; remove probabilistic selection.
  - Ensure method/source reflects ‘auto’ deterministically.
- `int_auto_enrollment_window_determination`:
  - Keep timing math; set `eligible_for_auto_enrollment = true` deterministically for in-scope new hires.
- `int_enrollment_timing_coordination`:
  - Use deterministic AE flag to schedule AE; keep opt-out behavior only.

Note: Current production path relies on `int_enrollment_events → fct_yearly_events`; alignment is recommended to prevent drift if other routes are used later.

## Risks / Considerations

- Participation rates will increase for new-hire cohorts under scope (by design).
- Downstream reporting based on event_category should expect more ‘auto_enrollment’ labels for in-scope new hires.
- dbt tests and dashboards may need updates to thresholds/expectations.

## Rollback

- Revert the deterministic AE logic by restoring the probabilistic gate in `int_enrollment_events` when `auto_enrollment_scope='new_hires_only'`.
- Alternatively, add a config var (e.g., `deterministic_auto_enrollment`) to toggle behavior and wrap the deterministic logic in a Jinja condition.

## Appendix: Key Queries

- Verify employee-level outcome:
  - `SELECT * FROM fct_yearly_events WHERE simulation_year=2025 AND employee_id='NH_2025_000005';`
  - `SELECT participation_status, participation_status_detail FROM fct_workforce_snapshot WHERE simulation_year=2025 AND employee_id='NH_2025_000005';`
