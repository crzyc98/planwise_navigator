# Feature 122 Phase-Gate Ledger

This ledger is the checked, PII-safe index for the ignored evidence produced under
`var/state_pipeline_validation/`. A gate is accepted only when its JSON evidence
uses the same frozen `baseline_id`, records isolated artifact identifiers (never
absolute census or database paths), passes every required check, and shows that the
shared development database and all pre-existing run artifacts were unchanged.

## Approval rules

1. Gates are completed in the order shown below; checkpoints within a gate are
   completed in their listed order.
2. `baseline_characterization` establishes the immutable `baseline_id`. Every later
   record must repeat it exactly.
3. A status may move from `pending` to `passed` only from reproducible ignored JSON
   evidence. `failed` evidence blocks later gates; reruns create a new attempt record
   without rewriting prior evidence.
4. Behavioral runs use newly allocated isolated databases. `dbt/simulation.duckdb`
   is signature-checked only and is never opened for writes or treated as truth.
5. Checked records contain aggregate schemas/counts/fingerprints only. Absolute input
   paths, census rows, employee samples, database files, and logs remain ignored.
6. Phase approval requires schema/content parity, relevant graph and invariant checks,
   invocation/node evidence, and file guards. The final RSS decision additionally
   requires three warm baseline and candidate repetitions for each workload.

## Evidence record fields

Each `gate.json` contains at least: schema version, gate/checkpoint, status,
`baseline_id`, candidate code/dirty fingerprint, normalized config/census/seed/
construction/database fingerprints, horizon, aggregate mart and transition results,
schedule and per-node execution summaries, isolated artifact labels, tool versions,
file guards, timestamps, failures, and approval decision. Paths are represented only
by stable labels relative to the ignored campaign root.

## Gate status

| Order | Gate / checkpoint | Status | Ignored evidence location | Approval requirement |
|---:|---|---|---|---|
| 1 | `baseline_characterization` | passed | `var/state_pipeline_validation/baseline_characterization/gate.json` | Clean A+B revision, 60,040 employees, 2025–2029, checked aggregate characterization, shared-DB guard |
| 2 | `run_database_isolation` | passed | `var/state_pipeline_validation/run_database_isolation/gate.json` | Fresh DB per attempt, atomic latest-success selection, failure/cancellation retention, API warning coverage, idle/active p95 ≤2s |
| 3 | `event_publication` | passed | `var/state_pipeline_validation/event_publication/gate.json` | Exact parity and one event/snapshot publication execution per effective year |
| 4a | `shadow_workforce/accumulator` | passed | `var/state_pipeline_validation/shadow_workforce/accumulator/gate.json` | All workforce columns and years match the frozen baseline behavior |
| 4b | `shadow_workforce/projection` | passed | `var/state_pipeline_validation/shadow_workforce/projection/gate.json` | Strict prior-year projection and exact parity |
| 5a | `consumers_migrated/employer_eligibility` | passed | `var/state_pipeline_validation/consumers_migrated/employer_eligibility/gate.json` | Full frozen-baseline gate |
| 5b | `consumers_migrated/employee_contributions` | passed | `var/state_pipeline_validation/consumers_migrated/employee_contributions/gate.json` | Full frozen-baseline gate |
| 5c | `consumers_migrated/employer_core` | passed | `var/state_pipeline_validation/consumers_migrated/employer_core/gate.json` | Full frozen-baseline gate |
| 5d | `consumers_migrated/employee_match` | passed | `var/state_pipeline_validation/consumers_migrated/employee_match/gate.json` | Full frozen-baseline gate |
| 5e | `consumers_migrated` | passed | `var/state_pipeline_validation/consumers_migrated/gate.json` | Aggregate consumer parity and invariants |
| 6a | `snapshot_composed_legacy_removed/composed` | passed | `var/state_pipeline_validation/snapshot_composed_legacy_removed/composed/gate.json` | Snapshot composition parity before deletion |
| 6b | `snapshot_composed_legacy_removed/graph_contract` | passed | `var/state_pipeline_validation/snapshot_composed_legacy_removed/graph_contract/gate.json` | Production SQL and calibration graph contracts |
| 6c | `snapshot_composed_legacy_removed` | passed | `var/state_pipeline_validation/snapshot_composed_legacy_removed/gate.json` | Legacy relations absent, Feature 107/112 and domain-boundary contracts pass |
| 7 | `state_stage_consolidated` | passed | `var/state_pipeline_validation/state_stage_consolidated/gate.json` | One state command/year, no state full refresh, exact parity, failure attribution, median RSS ≤110% |

## Final acceptance

Passed. The measured whole-run invocation total is reported as evidence only; it is
not compared with `20` or any other fixed pass/fail threshold. Feature gates, full
regression, static analysis, Studio/OpenAPI, and isolated quickstart acceptance are
all complete.

## Final acceptance matrix

| Area | Result | Evidence |
|---|---|---|
| Fast regression | passed | 1,782 passed, 690 deselected in 150.12s; under the 10-minute constitutional target |
| Feature 122/API focus | passed | 235 passed, 15 environment-gated full-scale cases skipped in 15.36s; the skipped cases were run separately against the supplied full-scale DBs |
| Non-default multi-year invariants | passed | 14 passed in 62.93s after removing a hard-coded deferral scenario scope found by acceptance |
| Final full-scale parity | passed | 10 passed against the frozen 60,040-employee, 2025–2029 A+B baseline |
| Targeted dbt contracts | passed | 58 schema/generic data tests passed with singular analytics tests excluded from the model-contract selection |
| Static analysis | passed | `ruff check .`; mypy clean across 224 source files |
| Module boundaries | passed | `year_executor.py` is 432 lines; extracted stage strategies are 140 lines; configured Ruff complexity/parameter checks are clean |
| Studio and API contract | passed | Vite production build (2,401 modules); OpenAPI snapshot and nine warning/lifecycle contract tests passed |
| File isolation | passed | Shared dev DB SHA-256 remained `46ef47d6…a5683`; all pre-existing run DB/archive/current-result signatures remained unchanged |
| Documentation | passed | Before/after DAG, schedule, warm resource matrix, compatibility, and SQL-only/Polars non-goal published |

The focused collection's 15 skips require full-scale DB environment variables rather
than representing unexecuted acceptance behavior. T075–T077 and the final parity run
supplied those databases and passed the determinism, domain, calibration, resource,
and exact-content gates separately.

## Recorded decisions

- `baseline_characterization`: passed against clean revision `c6ad648` with baseline
  ID `f122-ab-c6ad648`. The five-year run completed for 60,040 synthetic/profile
  records, all nine marts were accounted for, and the shared development database
  retained the same SHA-256 signature. The ignored reference DB remains local.
- `run_database_isolation`: passed with 189 focused Python tests, the Studio
  production build, distinct managed run directories, atomic latest-success
  promotion, failure/cancellation retention, and unchanged shared-DB signature.
  Across 100 representative requests per condition, idle p95 was 0.00361 seconds
  and active-run p95 was 0.00364 seconds.
- `event_publication`: passed against the full 60,040-employee, 2025–2029 frozen
  baseline. All built mart schemas, content, grouped counts, deterministic event
  identifiers/sequences, and duplicate multiplicities matched exactly. Profiler
  artifacts measured one successful event fact and snapshot publication per year;
  the observed 30-command total is evidence, not a pass/fail assertion.
- `shadow_workforce/accumulator`: passed for all 351,243 employee-year rows. Every
  declared workforce column matched the accepted snapshot per year, including
  representative hire and termination transitions; graph contracts confirm strict
  N-1 self-state and separation from enrollment, deferral, and benefit state.
- `shadow_workforce/projection`: passed the full frozen-baseline comparison. All
  mart schemas and duplicate-preserving content matched exactly, prior-state helpers
  use declared disposable projections with no dynamic snapshot lookup, and localized
  eligibility, contribution, core, match, proration, and composition checks passed.
- `consumers_migrated/employer_eligibility`: passed after moving eligibility behind
  canonical workforce accumulation. The 60,040-employee candidate preserved the
  accepted later-year tenure and new-hire-termination hours conventions; the
  eligibility relation and every published mart matched exactly.
- `consumers_migrated/employee_contributions`: passed after replacing independent
  workforce population/status replay with canonical workforce, enrollment, and
  deferral state. Published compensation facts preserve the accepted contribution
  base, and the contribution relation plus every mart matched exactly.
- `consumers_migrated/employer_core`: passed after replacing its duplicated
  population, status, tenure, age, and termination replay with canonical workforce
  plus employer eligibility. The accepted core compensation/service conventions,
  localized core relation, and all published marts matched exactly.
- `consumers_migrated/employee_match`: passed after replacing the scratch-workforce
  service join with canonical current/prior workforce state. Contributions and
  eligibility remain the authoritative financial inputs; the localized match
  relation and every published mart matched exactly.
- `consumers_migrated`: passed the combined 32-test suite against the final
  full-scale consumer candidate. Exact frozen parity and localized relation checks
  passed alongside contribution-limit, eligibility-hours, and zero-ineligible-core/
  match financial invariants.
- `snapshot_composed_legacy_removed/composed`: passed after replacing snapshot
  workforce-event replay with direct domain composition. Exact schema and content,
  all published marts, localized snapshot fields, consumer invariants, and workforce
  shadow parity passed before any legacy relation was removed.
- `snapshot_composed_legacy_removed` post-deletion evidence: the fresh full-scale
  candidate passed exact parity plus 37 domain-separation, Feature 107 enrollment,
  and Feature 112 termination tests after both legacy models were removed.
- `snapshot_composed_legacy_removed/graph_contract`: passed after a freshly compiled
  production manifest proved exact event-candidate coverage, no current-year fact
  feedback or dynamic snapshot lookup, mutually exclusive ownership, declared audit
  sinks, and normal/calibration dependency closure. Calibration output and failure
  contracts remained green.
- `snapshot_composed_legacy_removed`: passed on the post-ownership 60,040-employee,
  2025–2029 candidate. Every mart matched the frozen A+B baseline exactly, Feature
  107/112 and domain contracts passed, and the shared development database signature
  remained unchanged. The observed 20 invocations were recorded only as evidence.
- `state_stage_consolidated`: passed after exact full-scale parity, 154 targeted
  regressions, determinism, Feature 107/112, calibration, injected-failure, and
  partial-output checks. Both three-run warm performance matrices passed: reference
  median peak RSS fell from 1214.8 MiB to 1046.6 MiB (86.2% of baseline), and Studio
  median peak RSS fell from 1260.1 MiB to 1026.2 MiB (81.4%). The candidate used one
  state command per year with no state full refresh. Its observed 20-command total
  remains descriptive evidence only.
- Final acceptance found and fixed one non-default-scenario composition defect that
  default-scenario frozen parity could not expose: the deferral accumulator persisted
  a literal `default` scope. It now persists the configured scenario ID, is guarded by
  a graph contract, passes all 14 multi-year invariants, and preserves exact full-scale
  default-scenario parity. A newly built final Studio candidate passed all 10 parity
  checks, and 58 targeted dbt contracts passed on that database.
