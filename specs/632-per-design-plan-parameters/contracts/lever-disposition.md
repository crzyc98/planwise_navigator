# Contract: Tier 1 Lever Disposition

This matrix is normative. Implementation must also add a machine-checked inventory beside `to_dbt_vars` so new exports cannot enter an unclassified state.

| Lever | Current dbt variables | Tier 1 disposition | Rationale |
|---|---|---|---|
| Match numeric tiers/rates | `match_tiers`, `employer_match_graded_schedule`, `tenure_graded_bands`, `points_match_tiers` | Per design for the globally selected family | Numeric schedule variation is the central same-family use case. |
| Match cap and derived ceiling | `match_cap_percent`, `employer_match_max_deferral_rate` | Per design | Calculator and match-magnet behavior must agree. |
| Match family/label/enablement | `employer_match_status`, `match_template`, `employer_match_enabled` | Global | These select compile-time SQL shape or whole-model behavior. |
| Match/core eligibility policies | nested `employer_match`, `employer_core_contribution.eligibility` | Global | Not requested; includes status, hours, tenure, and exception policy rather than formula parameters. |
| Core flat rate | `employer_core_contribution_rate` | Per design | Numeric same-family parameter. |
| Core service-graded schedule | `employer_core_graded_schedule` | Per design | Requested repeated numeric schedule. |
| Core family/enablement | `employer_core_status`, `employer_core_enabled` | Global | Compile-time SQL shape or whole-model behavior. |
| Core points/age schedules | `employer_core_points_schedule`, `employer_core_age_schedule` | Deferred | Scope names the graded schedule; these need a separate product decision. |
| Core integration | `employer_core_integration_*` | Global | Integration changes formula structure and regulatory calculation, beyond Tier 1. |
| Auto-enrollment default rate | `auto_enrollment_default_deferral_rate` | Per design | Requested numeric parameter. |
| Auto-enrollment window | `auto_enrollment_window_days` | Per design | Requested timing parameter used in event dates. |
| Auto-enrollment scope | `auto_enrollment_scope` | Per design | Requested population parameter. |
| Auto-enrollment enable/cutoff/grace | `auto_enrollment_enabled`, `auto_enrollment_hire_date_cutoff`, `auto_enrollment_opt_out_grace_period` | Global | Enablement controls whole behavior; cutoff and grace were not requested. The assignment cutoff remains the grandfathering boundary. |
| Enrollment behavioral rates | voluntary, proactive, opt-out and demographic vars | Global | Workforce behavior assumptions, not plan design terms in this issue. |
| Escalation increment/cap | `deferral_escalation_increment`, `deferral_escalation_cap` | Per design | Requested numeric parameters; all event/state/validation consumers convert together. |
| Escalation enable/timing/eligibility | `deferral_escalation_enabled`, `deferral_escalation_effective_mmdd`, `deferral_escalation_hire_date_cutoff`, `deferral_escalation_require_enrollment`, `deferral_escalation_first_delay_years` | Global | Enablement and schedule shape remain common in Tier 1. |
| Plan eligibility wait | `eligibility_waiting_days`, `eligibility_waiting_period_days`, `plan_eligibility_waiting_period_days` | Per design through one canonical column | All aliases represent one concept and must not diverge. |
| Minimum age and eligibility overrides | related eligibility vars and census override flags | Global/per employee as today | Not part of requested waiting-day lever. |
| Vesting schedule | no effective simulation dbt var; request-level `VestingScheduleConfig` | Deferred follow-up | Current analytics applies one request schedule globally; proper per-design support needs service/API design, not an unused SQL relation. |
| IRS limits | IRS seed/config vars | Global | Regulatory limits are year-specific, not plan-design-specific. |
| Simulation, workforce, random, orchestration, reporting | remaining exported vars | Global | Run mechanics and population assumptions are not plan design terms. |
