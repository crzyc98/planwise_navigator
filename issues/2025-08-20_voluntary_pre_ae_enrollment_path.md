# Issue: Voluntary Pre–Auto-Enrollment Path For New Hires (2025-08-20)

- Status: Open
- Owner: Enrollment/Events
- Priority: Medium (adds realism; does not block current runs)

## Summary
With `auto_enrollment.scope = new_hires_only`, the current event generator enrolls eligible new hires via auto-enrollment and prevents duplicates via the enrollment registry. There is no path for a new hire to enroll voluntarily before the auto-enrollment deadline. As a result, “Voluntary” = 0 in the participation method breakdown across years, while Auto and Census appear as expected.

## Current Behavior
- Model: `dbt/models/intermediate/int_enrollment_events.sql`
  - Eligible new hires are classified as `auto_enrollment` when scope is `new_hires_only` or `all_eligible_employees`.
  - Dedupe via registry prevents subsequent duplicate enrollments.
  - No pre-AE voluntary event is generated.
- Reporting: `navigator_orchestrator/reports.py`
  - Methods shown: Auto, Voluntary, Census (now added), Opted Out, Not Auto, Unenrolled.
  - Voluntary remains 0 because no events are generated with method `voluntary` for new hires.

## Desired Behavior
- Some portion of eligible new hires enroll voluntarily before the auto-enrollment window closes.
- Those who voluntarily enrolled do not also get auto-enrolled (registry still prevents duplicates).
- Participation breakdown includes a non-zero “Voluntary” count aligned with demographics and config.

## Proposed Solutions

Option A (Recommended, minimal diff)
- Add a pre-AE voluntary enrollment path to `int_enrollment_events.sql` when:
  - `enrollment.proactive_enrollment.enabled = true`
  - `auto_enrollment.scope = 'new_hires_only'`
- Logic:
  - Window: `hire_date + [min_days, max_days]` where `max_days < hire_date + auto_enrollment.window_days`.
  - Probability: use `enrollment.proactive_enrollment.probability_by_demographics` (age/income) with deterministic hash per employee.
  - Event:
    - `event_type = 'enrollment'`
    - `event_category = 'voluntary_enrollment'`
    - `employee_deferral_rate`: an appropriately conservative voluntary rate (from existing demographics logic) rather than AE default.
  - Dedupe:
    - Reuse `is_already_enrolled = false` to prevent additional AE event for the same employee.

Option B (Alternate)
- Migrate event generation to `int_enrollment_events_optimized.sql` (already contains probabilistic structures) and ensure:
  - Pre-AE voluntary path is enabled per config.
  - Enrollment registry still dedupes against later AE.
  - Orchestrator uses the optimized model for event generation.

## Acceptance Criteria
- For each simulation year with new hires:
  - “Voluntary” > 0 in the Participation Breakdown (Active EOY).
  - Voluntary + Auto + Census ≈ Participating (minor timing differences acceptable).
  - No duplicate enrollments for the same employee in a given year.
- Pre-AE voluntary events occur before the AE effective date.

## Validation Queries
- Participation method breakdown (EOY):
  - `SELECT simulation_year, participation_status_detail, COUNT(*) FROM fct_workforce_snapshot WHERE employment_status='active' GROUP BY 1,2 ORDER BY 1,2;`
- Enrollment event categories (per year):
  - `SELECT simulation_year, event_category, COUNT(*) FROM fct_yearly_events WHERE event_type='enrollment' GROUP BY 1,2 ORDER BY 1,2;`
- Dedupe check:
  - `SELECT employee_id, simulation_year, COUNT(*) FROM fct_yearly_events WHERE event_type='enrollment' GROUP BY 1,2 HAVING COUNT(*)>1;` (expect 0)

## Risks & Mitigations
- Risk: Overlapping voluntary and AE windows could lead to duplicates.
  - Mitigation: Registry/`is_already_enrolled=false` check remains authoritative.
- Risk: Voluntary probabilities may over-inflate participation.
  - Mitigation: Start with conservative voluntary rates and add config toggles.

## Implementation Notes
- Files likely touched:
  - `dbt/models/intermediate/int_enrollment_events.sql` (add voluntary path)
  - `navigator_orchestrator/reports.py` (no change required; already counts methods)
  - Optional: `dbt/macros/enrollment_eligibility.sql` (no change expected)
- Config knobs to honor:
  - `enrollment.proactive_enrollment.enabled`
  - `enrollment.proactive_enrollment.timing_window.{min_days,max_days}`
  - `enrollment.proactive_enrollment.probability_by_demographics`
  - `enrollment.auto_enrollment.window_days`

## Done When
- Code merged with the voluntary pre-AE path.
- CI or local validation demonstrates non-zero Voluntary counts.
- Multi-year summary shows Voluntary alongside Auto and Census, and totals reconcile.
