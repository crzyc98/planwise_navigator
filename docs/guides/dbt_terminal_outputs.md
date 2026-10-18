# Scheduled dbt terminal outputs

The production graph guard checks both reachability and scheduled terminal
outputs. Scheduling a model does not establish that its output is useful.
A terminal model must have a documented non-SQL consumer or an intentional
inspection purpose. First-year and later-year manifests are checked together
because conditional `ref()` calls can hide prior-year consumers in the first year.
Self references and consumers in opt-in diagnostic directories do not qualify.

The explicit purposes in
`tests/unit/orchestrator/test_dbt_model_reachability.py` cover these outputs:

- `fct_compensation_growth`: compensation calibration reads this mart in
  `CalibrationRunner._read_year`.
- `fct_employer_match_events`: the timeline API reads employer contribution
  history in `planalign_api/services/timeline_service.py`.
- `hazard_cache_metadata`: `HazardCacheManager` queries the materialization
  fingerprint to decide whether hazard caches are current.
- `dim_hazard_table`: supported combined hazard lookup for ad-hoc inspection,
  retained by the existing standalone-root contract.
- `stg_config_age_bands` and `stg_config_tenure_bands`: Python event generators
  query these relations in `generators/base.py`.
- `stg_census_duplicates_audit`: inspect census deduplication decisions.
- `stg_comp_targets` and `stg_scenario_meta`: inspect staged compensation targets
  and scenario metadata. These are retained inspection outputs, not inputs to
  the simulation SQL graph.
- `stg_config_raise_timing_distribution`, `stg_config_raises_hazard`, and
  `stg_config_timing_validation_rules`: inspect staged configuration independently
  of simulation results. Their inclusion here preserves existing staging outputs;
  it does not assert that production SQL reads them.

The prior-year workforce helpers have downstream SQL consumers in later years;
they do not need terminal-output exceptions. The `analysis`, `data_quality`,
`debug`, `monitoring`, and `reporting` directories remain opt-in diagnostics.

## Issue #875 cleanup

Removed `int_workforce_pre_enrollment`, `int_eligibility_determination`, and
`int_deferral_escalation_state_accumulator`. A repository audit found no SQL
consumers, dynamic relation reads, Python data consumers, or supported standalone
use. Their non-SQL references were scheduling/declaration metadata, cleanup
compatibility, tests, or historical documentation. Eligibility events use
`int_plan_eligibility_determination`; contributions use
`int_deferral_rate_state_accumulator`. Historical specs and performance reports
describe earlier implementations and are retained.

The API year-range cleanup no longer references the retired escalation relation.

Removing these models also exposed `int_workforce_active_for_events` as an input
only to `test_compensation_compounding_validation`. It is preserved under
`dbt/models/analysis/` with analysis tags and removed from the production schedule.
Its schema contract and diagnostic consumer remain intact. Build it explicitly
with `--select +test_compensation_compounding_validation`; no diagnostic models
are deleted.

## Reproduce parity

The baseline comparison was run before the model removal and cannot be rerun
against the current tree. Its original evidence is retained below. Current
graph checks can be run from the repository root:

```bash
pytest tests/unit/orchestrator/test_dbt_model_reachability.py tests/unit/orchestrator/test_pipeline_graph_contract.py tests/test_workflow_schedule.py tests/test_calibration_workflow.py tests/unit/orchestrator/test_post_termination_workflow.py -q
```

The original comparison used checked-in synthetic census fixtures, fresh databases, isolated
dbt artifacts, one dbt thread, and complete 2025–2027 runs for standard enrollment,
broad auto-enrollment with an early hire cutoff, new-hire eligibility suppression,
an escalation cap, and grandfathered hire-date designs with different enrollment,
eligibility, escalation, match, and core terms. It requires exact schema and
duplicate-preserving bidirectional row parity for yearly and employer-match events, workforce snapshots,
enrollment, deferral rates, employee contributions, match/core calculations, and
design assignments. Only audit timestamps `created_at`, `snapshot_created_at`,
and `int_employee_contributions.calculated_at` are excluded. The latter is
populated by `CURRENT_TIMESTAMP`, not a simulated contribution date.
No runtime speedup is claimed; this is a correctness validation, not a benchmark.

Validation on 2026-10-16, based on commit
`8aa25044c33105c272667a797e479f007d6f5eca`: all ten synthetic three-year runs
completed. All 45 relation comparisons (five configurations, nine relations)
had zero differences in both directions after the audit timestamp exclusions.
The harness also verified identical effective inputs, all three snapshot years,
both grandfathered designs, absence of the four unscheduled materializations in
candidate databases, and an unchanged shared-database signature. The 53 graph,
workflow, and cleanup tests, 33 generator/execution tests, and isolated dbt schema
evolution test passed (87 total). Ruff, Black formatting, and whitespace checks
passed. Local evidence is in `var/validation/875-isolated/parity.json`; runtime
logs and databases are ignored artifacts, not committed inputs.
