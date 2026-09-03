# Validation Baselines

## Pre-change baseline (T003)

- Source commit: `9b13107efa065284885568f06e39b42882c3ba4f`
- Seed: `113435436`
- Horizon: 2025-2027
- Execution: isolated DuckDB files under `/tmp/run633/baseline/`, dbt threads `1`
- Ordered hash: SHA-256 of the ordered DuckDB row-hash sequence after excluding only the timestamp column listed below.

Canonical columns:

- `int_employee_match_calculations`: employee_id, simulation_year, eligible_compensation, deferral_rate, annual_deferrals, employer_match_amount, uncapped_match_amount, capped_match_amount, formula_type, match_cap_applied, irs_401a17_limit, irs_401a17_limit_applied, is_eligible_for_match, match_eligibility_reason, match_status, eligibility_config_applied, formula_id, formula_name, applied_years_of_service, applied_points, effective_match_rate, match_percentage_of_comp, scenario_id, parameter_scenario_id, plan_design_id. Excluded: `created_at`.
- `int_employer_core_contributions`: employee_id, simulation_year, eligible_compensation, employment_status, eligible_for_core, annual_hours_worked, employer_core_amount, core_contribution_rate, contribution_method, standard_core_rate, applied_years_of_service, irs_401a17_limit, irs_401a17_limit_applied, ss_wage_base, integration_level_applied, excess_compensation, base_core_amount, disparity_core_amount, scenario_id, parameter_scenario_id, plan_design_id. Excluded: `created_at`.
- `fct_employer_match_events`: event_id, employee_id, employee_ssn, event_type, simulation_year, effective_date, event_details, compensation_amount, previous_compensation, employee_deferral_rate, prev_employee_deferral_rate, employee_age, employee_tenure, level_id, age_band, tenure_band, event_probability, event_category, amount, event_payload, source_system, scenario_id, parameter_scenario_id. Excluded: `created_at`.
- `fct_workforce_snapshot`: employee_id, employee_ssn, employee_birth_date, employee_hire_date, current_compensation, prorated_annual_compensation, full_year_equivalent_compensation, current_age, current_tenure, level_id, age_band, tenure_band, employment_status, termination_date, termination_reason, detailed_status_code, simulation_year, employee_eligibility_date, waiting_period_days, current_eligibility_status, employee_enrollment_date, is_enrolled_flag, current_deferral_rate, participation_status, participation_status_detail, total_deferral_escalations, has_deferral_escalations, original_deferral_rate, prorated_annual_contributions, pre_tax_contributions, roth_contributions, ytd_contributions, irs_limit_reached, effective_annual_deferral_rate, total_contribution_base_compensation, first_contribution_date, last_contribution_date, contribution_quality_flag, compensation_quality_flag, employer_match_amount, employer_core_amount, total_employer_contributions, annual_hours_worked, scheduled_hours_per_week, scenario_id, plan_design_id, total_escalation_amount, last_escalation_date. Excluded: `snapshot_created_at`.

Hash columns below are match calculations, core contributions, match events, and workforce snapshot, respectively.

| Census | Axis | Family | Seconds | Match hash | Core hash | Match-event hash | Snapshot hash |
|---:|---|---|---:|---|---|---|---|
| 7,500 | match | deferral_based | 51.22 | `6c7264a75ec08a82970984b41b2ff6f75942046be04779fb979bc1f3b951bbf6` | `e5ea447058c688a00e53d0d1bdd2b826fe7bf6ac64155e8020d6b87d87f619e0` | `2d9921280d406c9be376c07aa22899cfa7b1b668a675937f5a628ace6d5c2287` | `422a36527dc1c8a2dbe35c431dc4e04d2a6b4617d12980e385ab56a6f40d1d57` |
| 7,500 | match | graded_by_service | 51.19 | `50efa6e0c2bed13fce5334bfa168fdb157d4897e3a7159e61ea67d0432cb1d8c` | `e5ea447058c688a00e53d0d1bdd2b826fe7bf6ac64155e8020d6b87d87f619e0` | `4abc6c1be43c222fbe212eb24251cd0db8af1af05455bf8be4dd72e40c7981a2` | `29f31b85046e915395ebdf13de79d8002a1062fb6a0c8ad4efb21e83cb08dbe4` |
| 7,500 | match | tenure_graded | 50.15 | `79e70d9a2dd6fb5735d16c0a74ff12f2fd56bf214edb305afad8be998296ee07` | `e5ea447058c688a00e53d0d1bdd2b826fe7bf6ac64155e8020d6b87d87f619e0` | `cddc90f3f55e3b11872a07ef19e2e2d2232ae6687ca76a5e4426afb30eac2a09` | `3b0dfef49aee0149defe63225ae8f10b550107699cc01f4434f389425cac03e3` |
| 7,500 | match | points_based | 51.19 | `7bc8c613606469c554f3f38e0093e75da5ea223b0f650e2cec5f27ba5d134058` | `e5ea447058c688a00e53d0d1bdd2b826fe7bf6ac64155e8020d6b87d87f619e0` | `9215db7f3db38bf4a6bde8ffdd83b168dd1b1198aecf3a5e04040c4c4fae8928` | `ab8ee6cf5149402affa33f098661981ffef1816b9dee93f5791df0847865ed0b` |
| 7,500 | core | flat | 51.18 | `6c7264a75ec08a82970984b41b2ff6f75942046be04779fb979bc1f3b951bbf6` | `e5ea447058c688a00e53d0d1bdd2b826fe7bf6ac64155e8020d6b87d87f619e0` | `2d9921280d406c9be376c07aa22899cfa7b1b668a675937f5a628ace6d5c2287` | `422a36527dc1c8a2dbe35c431dc4e04d2a6b4617d12980e385ab56a6f40d1d57` |
| 7,500 | core | graded_by_service | 51.19 | `6c7264a75ec08a82970984b41b2ff6f75942046be04779fb979bc1f3b951bbf6` | `efc5240c4cd10e371d6b154fbafa4eba8d91090b91d699168e22f1a97bd38631` | `2d9921280d406c9be376c07aa22899cfa7b1b668a675937f5a628ace6d5c2287` | `d3628941e6f07473f381a7057c0289cdc4f4a100efacd33c69c92d08969d0c2d` |
| 7,500 | core | points_based | 51.18 | `6c7264a75ec08a82970984b41b2ff6f75942046be04779fb979bc1f3b951bbf6` | `e12804e8aa84f4e8206beb82e4a007ac095988dbfc4671ea553b128cf6d01470` | `2d9921280d406c9be376c07aa22899cfa7b1b668a675937f5a628ace6d5c2287` | `2c947cf3a809c9a3a6f07b449dab92e4a63763428d7498c66be0c9f1842aa8e2` |
| 7,500 | core | age_banded | 50.17 | `6c7264a75ec08a82970984b41b2ff6f75942046be04779fb979bc1f3b951bbf6` | `8d0b6e2b9affe10913bfa6f47a86791f3c5a873da57495ce6d9e9edafdaad1ec` | `2d9921280d406c9be376c07aa22899cfa7b1b668a675937f5a628ace6d5c2287` | `dbe8e23cad064b733b0b105c57378e8fad08bb06fcc3142ee3018a34883fd1c0` |
| 60,000 | match | deferral_based | 60.25 | `846c240b01a15249925ced9d177c422dadfec63baa893da1bf662e8dd8b00340` | `2b01507cc07edbc7ce13ef393dada2ff54ed7c0cd655deb0da66479dffc94dd5` | `deda8afd4668abfed6eb87dac7dfcf53d0d5513dfa36e5298e0391a6b3c78231` | `b2cf7bc5991e803ca20734e89b439471a9b25acaba744d578d2dc88df0279907` |
| 60,000 | match | graded_by_service | 58.23 | `f597cf03db16dd31974999f2ad79858e6bf1cb5ffdc12baaab6ecae596ef7c6b` | `2b01507cc07edbc7ce13ef393dada2ff54ed7c0cd655deb0da66479dffc94dd5` | `f60a9bd3554366685711c4ac2ae9437d7d1e8ff8307e3d1ddfce9fa6a26dd478` | `d3eb1110e6ca361a34ac7639c55129b0f9fddfabd27e0f80b931c71c864e1253` |
| 60,000 | match | tenure_graded | 59.25 | `7f562a873e7feedf7113e0ed461acc7ee21d5c6f3c865cc95ee086602e95bed7` | `2b01507cc07edbc7ce13ef393dada2ff54ed7c0cd655deb0da66479dffc94dd5` | `19a5565f2144105b7c09341e63eb1c6a2b4fdb3bb96c643a512953f019b42bd1` | `0c4fb94df0c7982d142ebe9561bd6e3e4fb3addd94bb6e3983a7bedc7ca91cd8` |
| 60,000 | match | points_based | 58.22 | `825d85c07584349702036d599d0376cf1cbc730165bf07d8cb4a0745c8ded777` | `2b01507cc07edbc7ce13ef393dada2ff54ed7c0cd655deb0da66479dffc94dd5` | `0033246ff845a52de8ded10880903e7a1fb33d84fde9f9b0dcce9f967c17b6b3` | `1fca3caa4883cd04ccb35bfecb2c55916e4b48d46f5e475d536fe62a14cfe8f9` |
| 60,000 | core | flat | 58.23 | `846c240b01a15249925ced9d177c422dadfec63baa893da1bf662e8dd8b00340` | `2b01507cc07edbc7ce13ef393dada2ff54ed7c0cd655deb0da66479dffc94dd5` | `deda8afd4668abfed6eb87dac7dfcf53d0d5513dfa36e5298e0391a6b3c78231` | `b2cf7bc5991e803ca20734e89b439471a9b25acaba744d578d2dc88df0279907` |
| 60,000 | core | graded_by_service | 59.24 | `846c240b01a15249925ced9d177c422dadfec63baa893da1bf662e8dd8b00340` | `312632c581cb9b985ea8c817c2dacfe8797a3339a27b0dd403dbe4dd2adf2064` | `deda8afd4668abfed6eb87dac7dfcf53d0d5513dfa36e5298e0391a6b3c78231` | `84e6aeb15d4a7505beb759801d82d4b1b9fd35a3d000b19c562a289b3dab7351` |
| 60,000 | core | points_based | 58.24 | `846c240b01a15249925ced9d177c422dadfec63baa893da1bf662e8dd8b00340` | `51d32246c81991eb3d2c926b67d03630d5cc8947447c7f70c18b2bbb295540f9` | `deda8afd4668abfed6eb87dac7dfcf53d0d5513dfa36e5298e0391a6b3c78231` | `74fcd7aa31fb04f225ff75db6762f6cf70f1a787955551749ac52bfa08eefa1d` |
| 60,000 | core | age_banded | 58.23 | `846c240b01a15249925ced9d177c422dadfec63baa893da1bf662e8dd8b00340` | `34cd692fb4e2c24c44a66c5dd5cdb4c3423312b0c02939c67e8e40d3f6a263c5` | `deda8afd4668abfed6eb87dac7dfcf53d0d5513dfa36e5298e0391a6b3c78231` | `4143641ae1b14f206d46e525039efbdeb8df1554b1e166bf60c1a081dc035f43` |

The full machine-readable measurements are retained for the implementation session at `/tmp/run633/baseline/results_7500.json` and `/tmp/run633/baseline/results_60000.json`.

## Focused multi-family run (T029)

- Database: `/tmp/run633/us1/multi_family_retry4.duckdb`
- Seed/horizon/threads: `113435436`, 2025-2027, `1`
- Result: PASS in 49 seconds; all six yearly pipeline stages completed and summary artifacts were written.
- Formula map: `{"legacy":{"core_family":"flat","match_family":"deferral_based"},"new_hires":{"core_family":"age_banded","match_family":"tenure_graded"}}`.
- Final-year match calculations: legacy 30 rows / $196,210.62; new hires 148 rows / $650,218.39.
- Final-year core calculations: legacy 30 rows / $99,631.88; new hires 148 rows / $566,757.17.
- Full-horizon snapshots: legacy 35 distinct employees; new hires 180 distinct employees. Both exceed the ten-per-design acceptance floor.
- Downstream match fact: 455 rows. No employee changed `plan_design_id` in the assignment accumulator across the horizon.

## Formula-resolution guards (T039)

All four runs used the checked-in invariant census, seed `113435436`, requested
the full 2025-2027 horizon, and failed in 2025 state accumulation before a
workforce snapshot could be published.

| Scenario/database | Observed diagnostic | Publication check |
|---|---|---|
| `match_gap_guarded.duckdb` | correlation ID plus invocation ID; `INV_EMP_0001`; design `invariant_tiered_401k`; year 2025; family `graded_by_service`; `arm_count=0`; value 1; remediation `match.graded_schedule` | No match calculation, match fact, or snapshot table. |
| `match_overlap.duckdb` | correlation ID plus invocation ID; `INV_EMP_0021`; design and year; family `graded_by_service`; `arm_count=2`; value 14; remediation `match.graded_schedule` | No match calculation, match fact, or snapshot table. |
| `core_gap.duckdb` | correlation ID plus invocation ID; `INV_EMP_0003`; design and year; family `age_banded`; `core_rate_source=default`; remediation `employer_core.age_schedule` | No core calculation or snapshot table. |
| `core_overlap.duckdb` | correlation ID plus invocation ID; `INV_EMP_0010`; design and year; family `age_banded`; `band_match_count=2`; remediation `employer_core.age_schedule` | No core calculation or snapshot table. |

Ineligible rows are excluded from both guards. A legitimate computed zero is a
resolved row and is not treated as a gap; only missing, duplicate, or fallback
resolution fails.

## Single-design branch parity and performance (T030-T032)

Every branch database used the same seed, census, horizon, thread count, and
canonical column lists as its baseline counterpart. Both-direction `EXCEPT ALL`
returned zero rows for all four tables in every case, so each ordered canonical
hash equals the corresponding pre-change hash recorded above.

| Census | Axis | Family | Branch seconds | Baseline delta | Canonical differences |
|---:|---|---|---:|---:|---:|
| 7,500 | match | deferral_based | 50.37 | - | 0 |
| 7,500 | match | graded_by_service | 49.39 | - | 0 |
| 7,500 | match | tenure_graded | 49.38 | - | 0 |
| 7,500 | match | points_based | 50.37 | - | 0 |
| 7,500 | core | flat | 50.35 | - | 0 |
| 7,500 | core | graded_by_service | 50.35 | - | 0 |
| 7,500 | core | points_based | 50.37 | - | 0 |
| 7,500 | core | age_banded | 50.37 | - | 0 |
| 60,000 | match | deferral_based | 59.51 | -1.23% | 0 |
| 60,000 | match | graded_by_service | 59.42 | +2.05% | 0 |
| 60,000 | match | tenure_graded | 60.27 | +1.72% | 0 |
| 60,000 | match | points_based | 59.25 | +1.77% | 0 |
| 60,000 | core | flat | 60.27 | +3.51% | 0 |
| 60,000 | core | graded_by_service | 59.24 | +0.01% | 0 |
| 60,000 | core | points_based | 60.26 | +3.46% | 0 |
| 60,000 | core | age_banded | 60.25 | +3.48% | 0 |

The maximum observed increase was 3.51%, below the 5% normal-path boundary.
Machine-readable 60k timings and difference counts are at
`/tmp/run633/branch/results_60000.json` for this implementation session.

## Unchanged pre-feature configuration (T033)

`tests/fixtures/invariant_config.yaml` was run unchanged for 2025-2027 against
the 7.5k census at `/tmp/run633/legacy/legacy_config.duckdb`. It completed in
51.23 seconds through the legacy no-`plan_design_parameters` compile path.
Both-direction `EXCEPT ALL` returned zero differences for all four canonical
tables relative to `baseline_7500_match_deferral_based.duckdb`.

## Integration-enabled core parity (T046 gap closure)

The T030-T032 matrix recorded above ran every core cell with
`integration_enabled: false`; `SUM(disparity_core_amount)` is `0` in all sixteen
baseline and branch databases. The quickstart's explicit requirement to "run the
core comparison twice, once with `integration_enabled: false` and once with it
true" was therefore never exercised. The cause was structural:
`apply_legacy_single_design_formula` hard-coded `integration.enabled = False`
with no override, so the baseline side could not produce an integrated run.

The builder now accepts `integration_enabled`, and the missing half of the
matrix was run at 7,500 against `main` (`9b13107e`) with the same seed, census,
horizon, and thread count, into `/tmp/run633/integration_on/`.

**A regression was found.** The pre-feature path passes the rate-gated
expression `CASE WHEN core_contribution_rate > 0 THEN recognized_compensation
ELSE 0 END` into `get_integrated_core_amounts`, so an ineligible employee's
excess compensation and disparity are both zero. The per-design
`integration_components` branch computed `excess_compensation` and
`disparity_core_amount` from `basis.recognized_compensation` directly and gated
only `base_core_amount`. Because `recognized_compensation` is capped
compensation for every employee and eligibility is expressed solely through a
zero `core_contribution_rate`, ineligible employees were paid permitted
disparity on top of a zero base.

| Core family | Before fix (base_only/branch_only) | Ineligible disparity: main vs branch | After fix |
|---|---:|---:|---:|
| flat | 438 / 438 | $0.00 vs $235,784.87 | 0 / 0 |
| graded_by_service | 438 / 438 | $0.00 vs $235,784.87 | 0 / 0 |
| points_based | 438 / 438 | $0.00 vs $235,784.87 | 0 / 0 |
| age_banded | 438 / 438 | $0.00 vs $235,784.87 | 0 / 0 |

The fix applies the same rate gate to `excess_compensation` and
`disparity_core_amount`. After it, both-direction `EXCEPT ALL` returns zero for
`int_employer_core_contributions`, `fct_employer_match_events`, and
`fct_workforce_snapshot` in all four integrated cells, while eligible disparity
is unchanged at $1,584,834.59 -- integration still works, only the ineligible
leak is closed. The `integration_enabled: false` age-banded cell was re-run
post-fix and still matches its original baseline (0/0), confirming no
disturbance to the previously validated path.

Two durable nets were added: `test_core_rate_band_resolution.sql` now fails any
ineligible row carrying a non-zero `employer_core_amount` or
`disparity_core_amount`, and
`test_integration_amounts_are_gated_on_a_resolved_core_rate` pins the three
rate-gated components in the per-design block.

The two-design scenario was re-run post-fix at
`/tmp/run633/us1/postfix_two_design.duckdb`: match results are byte-identical to
the pre-fix run, ineligible core rows now total $0.00 for both designs, and
eligible results are unchanged (legacy 26 rows / $99,631.88 / one rate / zero
disparity; new hires 113 rows / $559,722.58 / three rates / $26,541.72
disparity). Sticky assignment, match grain, and core resolution all return `0`.

## Test and coverage gates (T042-T045)

- `pytest -m fast -q` (2026-09-03): 2,675 passed and 918 deselected in 265.91
  seconds (4:27.10 wall) after the regression fix; 246.41 seconds (4:07.55 wall)
  measured immediately before it. Functional result PASS in both runs; the
  constitution's stated under-10-second suite target is NOT MET by the
  repository's complete fast marker population, and the spread across runs is
  machine variance, not a change in the gate outcome. An earlier session
  recorded 277.91 seconds for the same suite.
- Post-fix re-runs: `pytest -m "fast and config" -q` 342 passed in 31.68s;
  `pytest -m integration -k plan_design -q` 37 passed in 435.88s; the three
  selected dbt data tests PASS=3 against the post-fix two-design database.
- `DATABASE_PATH=/tmp/run633/integration_suite.duckdb pytest -m integration -k plan_design -q`:
  37 passed and 3,556 deselected in 439.00 seconds.
- From `dbt/`, single-threaded against `multi_family_retry4.duckdb`, the relation,
  match-coverage, and core-resolution selection passed 3/3 in 0.37 seconds.
- Focused Python coverage used coverage.py's pure-Python tracer after importing
  DuckDB first (the normal coverage tracer conflicts with DuckDB 1.0.0): 52 tests
  passed; combined coverage for `config.plan_design`, `config.loader`,
  `config.export`, and `run_metadata` was 82.46%. Per-module results were 92.52%,
  60.44%, 86.83%, and 87.68%, respectively. The 95% module target is NOT MET;
  most uncovered lines are pre-existing general config/export branches outside
  this feature's focused paths.
- Schema documentation coverage for both changed contribution models is 48/48
  columns (100%). All three selected custom dbt tests passed, so the 90% dbt
  schema/custom-test target is met for the in-scope models and tests.

## 100k capacity gate (T047)

The default keyed `deferral_based`/`flat` configuration ran single-threaded for
2025-2029 at `/tmp/run633/capacity_100k.duckdb` in 103.81 seconds. The run status
is `success`, all 19 scheduled dbt invocations completed, and the final snapshot
contains 593,210 rows across all five years. Adaptive-memory monitoring recorded
365.0 MB peak RSS, zero fallbacks, zero memory warnings, and zero critical events.
No memory error occurred.
