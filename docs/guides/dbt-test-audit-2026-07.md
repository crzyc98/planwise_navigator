# dbt test audit — 2026-07

## Scope and evidence

This ledger covers every project-owned singular test under `dbt/tests/` and all
schema data tests parsed from project `schema.yml` files (not dependency-package
integration tests).  Evidence was gathered with `dbt parse`, `dbt ls
--resource-type test`, manifest dependency resolution, and source inspection.
The audit found 83 singular SQL files before changes and 848 manifest data-test
nodes; after removing five obsolete singular tests and four stale schema
patches there are 78 singular SQL files and 838 manifest data-test nodes.

All retained singular tests use `ref()` targets that resolve in the manifest.
Behavioral execution must be performed by the orchestrator against an explicit
`DATABASE_PATH`, never `dbt/simulation.duckdb`.

## Singular tests

| Group / files | Classification | Evidence and action |
| --- | --- | --- |
| Root enrollment assertions: `assert_enrollment_after_hire_date`, `assert_ineligible_no_enrollment`, `assert_new_hire_hire_year_snapshot_participating`, `assert_new_hire_single_enrollment_event`, `assert_new_hire_voluntary_enroll_effective_date`, `assert_new_hire_voluntary_enrollment_hire_year`, `assert_no_multi_cycle_enrollment`, `assert_optout_no_deferral_escalation`, `assert_participation_deferral_consistency`, `assert_same_year_enroll_optout_window`, `assert_voluntary_enrollee_match_nonzero`, `assert_voluntary_enrollment_persists`, `assert_voluntary_enrollment_snapshot` | retain | Active event/state/snapshot refs; preserves enrollment continuity and output contracts. |
| Root contribution tests: `test_audit_trail_core_contributions`, `test_enrollment_deferral_ceiling`, `test_enrollment_match_magnet_proactive`, `test_enrollment_match_magnet_voluntary`, `test_flat_rate_core_contributions`, `test_magnet_upward_only`, `test_magnet_upward_only_proactive`, `test_multi_tier_core_contributions`, `test_service_match_boundaries`, `test_service_tier_core_contributions`, `test_tiered_match_rate`, `test_yoy_respects_voluntary_rate` | retain | Active contribution/event refs and runtime variables; retain configuration-sensitive coverage. |
| Root state/isolation tests: `test_auto_enrollment_disabled_no_events`, `test_auto_enrollment_enabled_generates_events`, `test_auto_enrollment_new_hires_only_scope`, `test_census_participants_not_reenrolled`, `test_enrollment_population_split`, `test_helper_model_year_continuity`, `test_multi_year_state_history_retained`, `test_participation_label_lineage` | retain | Active variables and accumulator/fact refs; preserves scenario/plan isolation and multi-year behavior. |
| `analysis/test_e058_business_logic`, `test_enrollment_continuity`, `test_escalation_bug_fix`, `test_multi_year_compensation_inflation`, `test_opt_out_rates` | retain | Current intermediate/fact refs resolve; no shared database dependency. |
| `analysis/test_deferral_rate_source_of_truth` | remove | Retired: fixed employee ID/rate assertion (`NH_2025_000007 = 6%`) is not a current configuration contract. General deferral-source coverage remains in the accumulator tests. |
| `intermediate/test_enrollment_deferral_consistency` | retain | Active accumulator/event/baseline lineage coverage. |
| `intermediate/test_s042_source_of_truth` | remove | Retired: queried ambient `main.enrollment_registry` and a fixed historic employee. It is incompatible with disposable isolated databases. |
| `marts/test_event_sequence_chronological_order` | retain | Directly validates the active fact-event ordering contract. |
| `marts/test_deferral_state_continuity`, `test_deferral_orphaned_states` | remove | Superseded: both join state and fact rows without scenario/plan keys and produce cross-context false failures. `test_multi_year_state_history_retained` retains multi-year accumulator coverage. |
| `data_quality/test_401a17_compliance`, `test_age_band_no_gaps`, `test_age_band_no_overlaps`, `test_annualization_logic`, `test_band_label_consistency`, `test_compensation_bounds`, `test_deferral_escalation`, `test_deferral_match_response`, `test_deferral_rate_validation`, `test_deferral_state_audit_v2`, `test_duplicate_events`, `test_e058_match_eligibility_consistency`, `test_eligibility_vs_vesting_independence`, `test_employee_contributions`, `test_employee_contributions_validation`, `test_employee_id_format`, `test_enrollment_after_optout`, `test_enrollment_requires_prior_eligibility`, `test_future_event_dates`, `test_hours_threshold`, `test_iecp_computation`, `test_integrity_violations`, `test_missing_enrollment_dates`, `test_negative_compensation`, `test_new_hire_core_proration`, `test_new_hire_match_validation`, `test_new_hire_status_accuracy`, `test_new_hire_termination`, `test_new_hire_termination_completeness`, `test_new_hire_termination_match`, `test_tenure_at_termination`, `test_tenure_band_no_gaps`, `test_tenure_band_no_overlaps`, `test_tenure_graded_match_amount_nonnegative`, `test_tenure_graded_tier_no_gaps_overlaps`, `test_termination_after_hire`, `test_termination_date_distribution`, `test_violation_details` | retain | Every `ref()` resolves in the current manifest. These tests cover active seed bands, contribution/eligibility behavior, immutable events, and workforce output quality. |
| `data_quality/test_enrollment_architecture` | remove | Superseded: it compares event dates to every subsequent accumulator year and omits scenario/plan keys, generating false failures. Root enrollment assertions preserve event-to-state, continuity, and snapshot coverage. |

## Schema data tests

| Test group | Classification | Evidence and action |
| --- | --- | --- |
| `models/staging/schema.yml`, `models/intermediate/events/schema.yml`, `models/intermediate/hazards/schema.yml`, `models/intermediate/schema.yml` | retain / update |  Manifest resolves the active staging and intermediate contracts. Legacy `tests:` keys converted to `data_tests:`. |
| `models/marts/schema.yml`, `models/marts/data_quality/schema.yml`, `models/data_quality/schema.yml`, `models/monitoring/schema.yml` | retain / investigate | Active fact, quality, and monitoring contracts parse. Two stale model patches in `models/marts/data_quality/schema.yml` are explicitly identified below. |
| `models/analysis/schema.yml` | update | Removed stale validation-model patches; remaining debug model tests are active and legacy `tests:` syntax is converted. |
| `seeds/schema.yml` | retain | Seed data tests target the current configuration seeds. Removed three unused seed configuration paths from `dbt_project.yml`. |
| `tests/schema.yml` | update | Global singular-test configuration converted from deprecated `tests:` syntax to `data_tests:`. |

## Remediated findings

`dbt parse` initially reported missing schema patches for
`validate_enrollment_architecture`, `dq_employee_id_validation`, and
`dq_new_hire_termination_match_validation` (plus the legacy
`validate_enrollment_continuity` patch). Those obsolete validation-model patches
are removed. All legacy `tests:` configuration keys in project schema files
are now `data_tests:`. The three unused seed configuration paths in
`dbt_project.yml` (`census_data`, `baseline_workforce`, `plan_designs` — no
matching seed CSVs exist) are also removed.

An earlier draft of this change deleted four entire schema files
(`models/intermediate/schema.yml`, `models/analysis/schema.yml`,
`models/marts/data_quality/schema.yml`, `models/monitoring/schema.yml`) and
ten retained singular tests to force a green isolated `dbt test` run. That
over-deletion (848 → 251 manifest tests) was reverted; only the surgical
changes in this ledger remain. A red `dbt test` against a fresh isolated
database is a test-selection problem (some models are not materialized in
that context), not license to delete active contracts.

## Isolated validation command

```bash
source .venv/bin/activate
DATABASE_PATH=/tmp/planalign-dbt-audit/isolated.duckdb \
  planalign simulate 2025-2027 --database /tmp/planalign-dbt-audit/isolated.duckdb
cd dbt
DATABASE_PATH=/tmp/planalign-dbt-audit/isolated.duckdb \
  dbt test --threads 1 --select test_multi_year_state_history_retained test_enrollment_population_split
```
