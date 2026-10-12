# Execution plan: faster ordinary simulations through deterministic SQL hashing

Status: implemented and acceptance gates passed on 2026-10-12.
See [execution evidence](deterministic-hash-optimization-results-2026-10-12.md),
including the unrelated pre-existing fast-suite worktree-scan failure.
Written 2026-10-12 for GPT-6.1-Sol.
Investigation base: `d594e084d57056272a90f2b10d515c86a9d797d7`.

## Objective and decision

Reduce ordinary single-scenario elapsed time while preserving every seeded
simulation decision and published result. Implement the focused SQL hash
optimization first; keep native-kernel issues #469 and #471–#475 paused pending a
separate decision after measurement. This plan does not authorize a native port.

The [investigation report](native-kernel-decision-2026-10-12.md) found one matched
CLI pair improved from 172.21s to 109.99s (36.1%) on 60,040 employees over five
years, with exact parity across all three built marts. A hash microbenchmark
improved 6.38x. These are exploratory observations, not release guarantees.
The primary success measure is ordinary CLI latency; ensemble throughput and
large-population scaling are secondary and do not expand this implementation.

## Scope and deliverables

| Area | Expected files | Deliverable |
|---|---|---|
| Production change | `dbt/macros/utils/stable_hash.sql` | Avoid repeated expensive macro expressions while retaining the frozen hash contract |
| Contract coverage | `tests/unit/test_stable_duckdb_semantics.py` | Independent-reference tests for scalar and vectorized SQL execution |
| Measurement reliability | `scripts/perf_profile/dbt_timing.py`, `tests/unit/test_state_pipeline_profile.py` | Correct artifact selection and rejection of stale node results |
| Reproducible A/B driver | Small module under `scripts/perf_profile/`, reusing existing helpers | Actual CLI invocation, isolated projects/databases, matched inputs, machine-readable samples |
| Evidence and documentation | New report under `docs/perf/`; `docs/guides/duckdb_upgrade.md` if needed | Commands, environment, parity, repeated timings, remaining bottlenecks |

Do not add a runtime dependency, alternate engine, Python UDF, new configuration
switch, public schema, or changes to business rules. Retain existing helper names
and the attribution in `docs/third_party/duckdb_hash_license.txt`. Do not change
decimal/date compatibility macros or upgrade dependencies as part of this work.

## Execution sequence

### 1. Freeze the baseline and verify the environment

- [x] Read current `AGENTS.md` and `CLAUDE.md`, inspect status and current revision,
  and preserve unrelated edits and `.worktrees/`. Do not create a branch, commit,
  push, or modify GitHub issues unless the user authorizes those actions.
- [x] Check whether the hash or profiler has changed since the investigation.
  Reconcile changes before applying the candidate below. Do not compare new code
  against the old reported times as though they were a matched baseline.
- [x] Activate `.venv`; record Python, architecture, CPU count, DuckDB, dbt-core,
  dbt-duckdb, and Pydantic versions and module locations. Verify the dbt subprocess
  imports the same DuckDB build as the parent process. Follow current repository
  dependency pins and installation permissions.
- [x] Resolve the known environment trap: investigation `.venv` contained DuckDB
  1.1.3, while the project pinned 1.5.6. Investigation used an existing cached
  1.5.6 package via `PYTHONPATH`; do not assume that cache still exists or silently
  benchmark 1.1.3. Record any overlay and propagate it to subprocesses.
- [x] Create a new ignored campaign directory under `var/perf_profile/`. Save
  baseline source, source revision/diff, config, seed-tree and census fingerprints,
  and the shared database fingerprint before changing the production macro.
  Keep census rows and employee-level outputs out of checked-in reports.

Reference workload: `config/simulation_config.yaml`, years 2025–2029, seed 42,
3% growth, with the existing 60,040-row census at
`workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet`.
Freeze the full effective configuration for both arms. If this input is absent,
continue unit/tooling work and report the performance gate as pending; do not
substitute the 7,505-row development census and claim equivalent evidence.

### 2. Make measurement trustworthy before timing the candidate

- [x] Fix `InvocationRecorder` artifact resolution. An explicit
  `dbt_artifacts_dir` takes precedence; otherwise resolve the effective dbt
  project's target directory. Account for supported command target overrides.
  `runner.target_path` currently falls back to `working_dir/target` even when
  `project_dir` differs, so blindly using that property is insufficient.
  Keep this scoped to profiling unless a shared correction is necessary.
- [x] Test default project, separate project, and explicit artifact directory
  using distinct sentinel results. Include missing, malformed, unchanged/stale,
  and failed-invocation artifacts. Associate node timing only with the current
  invocation, using artifact identity/freshness; never reuse the last successful
  invocation's node timings. Preserve independently measured wall time and mark
  unavailable node attribution explicitly.
- [x] Add a small A/B driver that invokes the actual Typer `simulate` command
  through the same boundary for both arms, including health checks and validation.
  Reuse profiling/fingerprint helpers rather than introducing another framework.
  Allow explicit config, census, baseline/candidate project, and output paths;
  reject existing output databases. Document its exact runnable command.
- [x] Use identical isolated dbt project copies, excluding existing databases,
  targets, and logs. Their only production-code difference must be the hash macro.
  Bind each invocation to its own artifacts and database; propagate `DATABASE_PATH`
  to subprocesses. Run dbt with one thread. Verify the actual paths before the
  expensive campaign and verify the shared database remains unchanged afterward.
- [x] Record wall time with a monotonic clock, process-tree CPU and peak RSS,
  exit/validation status, invocation count, fresh node timings, and fingerprints.
  A wrapper-construction benchmark alone is not the primary ordinary-CLI metric.
  If timing Typer in-process, label interpreter startup and Studio HTTP/UI time
  as excluded. Never mix that boundary with external CLI timings.

The exploratory CLI node timings were invalid because they came from the wrong
target directory. Do not use them to claim per-model improvements. Its independent
wall/CPU/RSS measurements and output parity remain useful preliminary evidence.

### 3. Add contract tests, then implement the small SQL change

- [x] Retain all golden values, NULL behavior, UTF-8 property tests, and the
  independent Python arithmetic reference already in the unit test module.
- [x] Add explicit byte-boundary coverage (7/8/9 and 15/16/17 bytes), empty strings,
  embedded NUL, multibyte Unicode spanning blocks, and long multi-block inputs.
  Exercise a nullable SQL column with many rows as well as scalar parameters;
  compare each result against the independent reference. Cover supported
  non-string inputs through the existing `VARCHAR` conversion contract.
- [x] Exercise hash calls in representative SQL expressions/joins and nested
  lambda contexts used by callers, so the binding technique is not tested only
  on constants. Verify `UBIGINT` output and repeat installation in a connection.
- [x] Apply the candidate below to existing helpers, preserving multiplication,
  modulo arithmetic, byte order, seed, tail handling, and NULL constant. Add a
  short comment explaining why single-element list bindings are intentional.
  Do not retain exploratory `probe_*` aliases in production.
- [x] Run targeted tests on the pinned runtime. Use the existing 60,040-string
  microbenchmark shape as a diagnostic: `EMP_` + eight-digit ID +
  `|2025|TERMINATION|42`. Verify exact outputs before interpreting its timings.
  Built-in DuckDB `hash()` on 1.5.6 produces different values and is not a valid
  replacement.

### 4. Prove simulation equivalence

- [x] Run existing multi-year invariant and edge-configuration suites against
  their disposable databases. Inspect fixture behavior and report skipped or
  unavailable integration cases accurately. Missing dbt packages are an
  environment problem, not evidence of a product regression; follow installation
  permissions rather than fetching dependencies silently.
- [x] Complete baseline and candidate five-year reference runs with validation
  failures treated as failures. Compare every built public mart using
  `compare_marts_detailed` in `planalign_orchestrator/change_validation.py` and
  `specs/122-state-pipeline-redesign/contracts/parity-exclusions.yaml`.
- [x] Require matching schema, row counts, and zero differences in both
  `EXCEPT ALL` directions, including duplicates. Only named, applicable timestamp
  exclusions in that manifest are allowed. No new broad exclusions or numeric
  tolerances may hide changed seeded decisions, amounts, or event identifiers.
- [x] Repeat the candidate with identical inputs/seed in a fresh database and
  apply the same parity comparison to establish deterministic repeatability.
  Reuse a successful timed candidate repetition for this check.
- [x] Record absent-in-both marts as unbuilt, not validated. At the investigation
  base, built outputs were `fct_yearly_events`, `fct_workforce_snapshot`, and
  `fct_employer_match_events`; discover the current set rather than hardcoding it.

### 5. Run matched performance gates and report the decision

- [x] Run one unscored warmup per arm, then three scored pairs sequentially,
  alternating execution order A/B, B/A, A/B. Use fresh databases and identically
  prepared artifact directories for every sample. Avoid concurrent simulations
  and heavy unrelated work. Keep product parsing behavior identical across arms;
  a separate correctness run may use `--no-partial-parse` when needed.
- [x] Publish all sample times, both medians, ranges, CPU/RSS, invocation counts,
  environment/fingerprints, and parity results. Explain any failed sample and
  rerun the entire affected pair; do not discard slow successful samples.
- [x] Apply the proposed release gate: **at least 20% lower median ordinary CLI
  wall time** on the frozen 60,040-row/five-year workload, with all correctness
  gates passing. This is a planning threshold below the exploratory 36.1% result,
  not a user promise or a universal latency SLA. Investigate a material RSS
  increase or changed invocation/model set before declaring success.
- [x] If correctness fails, stop promotion and diagnose it. If the speed gate
  fails, retain the evidence and report the result; do not broaden into a native
  rewrite or relax the gate after seeing the numbers.
- [x] With valid node artifacts, identify remaining expensive work. Distinguish
  node execution from total dbt invocation time; their difference includes parse,
  compile, adapter, and startup work, not solely removable process overhead.
  Revisit native-kernel work only through a separate user decision grounded in
  remaining ordinary-run latency and the benefit/cost of the next alternative.

## Candidate SQL reference

Integrate these definitions into `install_stable_hash()` in dependency order.
Keep existing `pa_hash_mul`, `pa_hash_word`, `pa_hash_blocks`, and `planalign_hash`
definitions; `pa_hash_blocks` will call the updated `pa_hash_mix` by its existing
name. This reference is self-contained and does not require ignored probe files.

```sql
CREATE OR REPLACE MACRO pa_hash_mix(x) AS
  list_extract(list_transform([pa_hash_mul(x)],
    h -> pa_hash_mul(xor(h, h >> 47))), 1);

CREATE OR REPLACE MACRO pa_hash_finalize(x) AS
  list_extract(list_transform([x], h ->
    list_extract(list_transform([pa_hash_mul(xor(h, h >> 47))],
      k -> xor(k, k >> 47)), 1)), 1);

-- Define after pa_hash_blocks.
CREATE OR REPLACE MACRO pa_hash_hex(x) AS
  list_extract(list_transform([pa_hash_blocks(x)], h -> pa_hash_finalize(
    CASE WHEN length(x) % 16 = 0 THEN h
    ELSE pa_hash_mul(xor(h,
      pa_hash_word(substr(x, (length(x) // 16) * 16 + 1)))) END)), 1);
```

The list/lambda bindings express reuse of intermediate values instead of repeating
expensive expanded expressions. They preserve the frozen MurmurHash64A arithmetic;
tests and measured execution must establish that equivalence and benefit on the
supported runtime.

## Validation commands and handoff

Run from the repository root after resolving the environment in step 1:

```bash
source .venv/bin/activate
python -m pytest tests/unit/test_stable_duckdb_semantics.py tests/unit/test_state_pipeline_profile.py -q
python -m pytest tests/integration/test_multi_year_invariants.py tests/integration/test_edge_config_matrix.py -q
python -m pytest -m fast -q
ruff check scripts/perf_profile tests/unit/test_stable_duckdb_semantics.py tests/unit/test_state_pipeline_profile.py
mypy planalign_orchestrator/ planalign_cli/ planalign_core/ --ignore-missing-imports
git diff --check
```

Add the new driver's exact A/B command and any additional test file to the evidence
report. Integration fixtures must remain isolated; never point these checks at
`dbt/simulation.duckdb`. Preserve raw campaign JSON/logs under ignored `var/` and
check in only aggregate, privacy-safe evidence and reproduction instructions.
No performance test should enforce a machine-specific seconds threshold in CI.

Completion means: minimal reviewable production/tooling diff, passing contract and
integration gates, exact full-run parity and repeatability, a repeated matched
performance result, and an evidence report stating limitations. If a required
environment/input is unavailable, identify the incomplete gate rather than marking
the plan complete. Do not run new benchmarks merely to finish this planning task.

Original implementation handoff prompt:

> Implement `docs/perf/deterministic-hash-optimization-plan.md`. Read repository
> instructions, inspect the current checkout, and follow the plan through its
> correctness and repeated performance gates. Preserve unrelated changes and use
> isolated databases. Keep the native-kernel rewrite out of scope. Leave a
> reviewable diff and evidence report; do not commit, push, or modify GitHub issues.
