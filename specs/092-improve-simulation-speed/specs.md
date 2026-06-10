Performance Improvement Plan + Code Issues Log

 Context

 Multi-year simulations run ~3× slower on the work Ubuntu server than on M4 Macs. Investigation shows the dominant
 cost is not single-threaded query time but per-model dbt subprocess overhead, which is heavily
 single-thread-CPU-bound (Python interpreter startup + dbt project parsing per invocation) — exactly the dimension
 where the Ubuntu server is weakest vs. an M4.

 Key findings

 - ~17–19 dbt subprocess spawns per simulated year. The worst offender is _run_sequential_event_models() in
 planalign_orchestrator/pipeline/year_executor.py:501-527, which runs the STATE_ACCUMULATION stage as 14 separate
 dbt run --select <one model> invocations. Each spawn re-starts Python and re-parses the dbt project (~2–8s each on
 slow cores). That's potentially 1–2 minutes of pure overhead per year on the server.
 - This per-model loop is unnecessary: with --threads 1, a single dbt run --select m1 m2 m3 ... already executes
 models sequentially in DAG order within one process. The only per-model special case is the pre-clear of
 fct_workforce_snapshot rows, which can be done once before the combined invocation.
 - dbt_threads: 1 everywhere in config/simulation_config.yaml (lines 501, 539, 548). dbt threads matter little here
 since most invocations select few models — subprocess count is the real cost.
 - DuckDB query parallelism is independent of dbt threads and defaults to CPU count — fine as-is. memory_limit: 4GB
 in dbt/profiles.yml may be unnecessarily conservative on the server.

 Plan

 1. Consolidate STATE_ACCUMULATION into one dbt invocation (the big win)

 In planalign_orchestrator/pipeline/year_executor.py, change _run_sequential_event_models() to:
 - Run _clear_snapshot_rows_if_needed() up front for fct_workforce_snapshot (it's in the stage model list).
 - Issue a single dbt run --select <model1> <model2> ... for all stage models (preserving any --full-refresh logic
 — if only some models need full refresh, split into at most two invocations: full-refresh group + normal group,
 still ordered correctly because dbt resolves DAG order within each invocation; if ordering between the groups
 matters, keep the full-refresh models' current behavior).
 - Same treatment applies to EVENT_GENERATION when it goes through this path.

 Expected gain: removes ~13 subprocess spawns/year → roughly 30–90s/year on the slow server, likely the bulk of the
 3× gap.

 2. Reduce dbt parse overhead per remaining invocation

 - Verify partial parsing is active (dbt caches target/partial_parse.msgpack); ensure nothing deletes target/
 between invocations and that --no-partial-parse isn't being passed.
 - Optionally add DBT_NO_VERSION_CHECK=1 / --no-print style flags in dbt_runner.py to shave startup.

 3. Server-side quick checks (no code change)

 - Confirm the venv on Ubuntu uses the same Python 3.11 and that the repo/database live on local SSD, not NFS (NFS
 would devastate DuckDB I/O and dbt parse times).
 - Consider raising memory_limit in dbt/profiles.yml if the server has RAM to spare.

 4. Benchmark before/after

 Time planalign simulate 2025-2027 on the Mac and (when available) the server; also time a bare dbt run --select
 int_baseline_workforce --threads 1 to quantify per-invocation startup cost on each machine.

 5. Log code issues found during review

 Create docs/code_issues_2026-06.md documenting issues found (no behavior changes in this plan beyond #1):

 - HIGH — planalign_api/models/suggestion.py:61: bare except: in a Pydantic field validator swallows everything
 incl. KeyboardInterrupt; should be except (ValueError, TypeError, decimal.InvalidOperation):. (Also violates the
 project's own SonarQube rules.) Fix this one inline since it's a one-liner.
 - MEDIUM — planalign_orchestrator/debug_utils.py:62: DatabaseInspector opens a DuckDB connection in __init__; safe
 only if used as a context manager — leaks fd otherwise.
 - MEDIUM (design) — 20+ int_* models (e.g., int_enrollment_state_accumulator.sql:77,
 int_deferral_rate_state_accumulator.sql:59) read from fct_yearly_events, violating the CLAUDE.md rule "Don't read
 from fct_* tables in int_* models." Works because of stage ordering, but it's an undocumented hard coupling —
 document as intentional or rename the event table to an int/snapshot tier.
 - LOW — Dead Polars cruft post-E024: config/loader.py:104-118 (is_polars_mode_enabled etc. always return False),
 - LOW — Dead Polars cruft post-E024: config/loader.py:104-118 (is_polars_mode_enabled etc. always return False),
 config/performance.py:170-201 (PolarsEventSettings), and polars.max_threads in simulation_config.yaml:512.
 - LOW — excel_exporter.py:676 uses iterrows() (reporting only, minor).

 Verification

 1. pytest -m fast (orchestrator tests cover year executor paths).
 2. Run planalign simulate 2025-2026 --verbose locally; confirm STATE_ACCUMULATION now logs one dbt invocation, results identical (row
 tables in int_* models." Works because of stage ordering, but it's           an                                                               undocumented                       hard                                                             coupling                                   document                                                         as                                               intentional                                                      or
 rename the event table to an int/snapshot tier.
 - LOW — Dead Polars cruft post-E024: config/loader.py:104-118 (is_polars_mode_enabled           etc.                                                             always                       return                                                           False),
 config/performance.py:170-201 (PolarsEventSettings), and polars.max_threads           in                                                               simulation_config.yaml:512.
 - LOW — excel_exporter.py:676 uses iterrows() (reporting only, minor).

 Verification

 1. pytest -m fast (orchestrator tests cover year executor paths).
 2. Run planalign simulate 2025-2026 --verbose locally; confirm STATE_ACCUMULATION           now                                                              logs                       one                                                              dbt                                   invocation,                                                      results
 identical (row counts in fct_yearly_events / fct_workforce_snapshot           match                                                            pre-change                       run                                                              with                                   the                                                              same                                               s
 through this path.

 Expected gain: removes ~13 subprocess spawns/year → roughly
 30–90s/year on the slow server, likely the bulk of the 3× gap.

 2. Reduce dbt parse overhead per remaining invocation

 - Verify partial parsing is active (dbt caches
 target/partial_parse.msgpack); ensure nothing deletes target/
 between invocations and that --no-partial-parse isn't being
 passed.
 - Optionally add DBT_NO_VERSION_CHECK=1 / --no-print style
 flags in dbt_runner.py to shave startup.

 3. Server-side quick checks (no code change)

 - Confirm the venv on Ubuntu uses the same Python 3.11 and that
 the repo/database live on local SSD, not NFS (NFS would
 devastate DuckDB I/O and dbt parse times).
 - Consider raising memory_limit in dbt/profiles.yml if the
 server has RAM to spare.

 4. Benchmark before/after

 Time planalign simulate 2025-2027 on the Mac and (when
 available) the server; also time a bare dbt run --select
 int_baseline_workforce --threads 1 to quantify per-invocation
 startup cost on each machine.

 5. Log code issues found during review

 Create docs/code_issues_2026-06.md documenting issues found (no
 behavior changes in this plan beyond #1):

 - HIGH — planalign_api/models/suggestion.py:61: bare except: in
 a Pydantic field validator swallows everything incl.
 KeyboardInterrupt; should be except (ValueError, TypeError,
 decimal.InvalidOperation):. (Also violates the project's own
 SonarQube rules.) Fix this one inline since it's a one-liner.
 - MEDIUM — planalign_orchestrator/debug_utils.py:62:
 DatabaseInspector opens a DuckDB connection in __init__; safe
 only if used as a context manager — leaks fd otherwise.
 - MEDIUM (design) — 20+ int_* models (e.g.,
 int_enrollment_state_accumulator.sql:77,
 int_deferral_rate_state_accumulator.sql:59) read from
 fct_yearly_events, violating the CLAUDE.md rule "Don't read
 from fct_* tables in int_* models." Works because of stage
 ordering, but it's an undocumented hard coupling — document as
 intentional or rename the event table to an int/snapshot tier.
 - LOW — Dead Polars cruft post-E024: config/loader.py:104-118
 (is_polars_mode_enabled etc. always return False),
 config/performance.py:170-201 (PolarsEventSettings), and
 polars.max_threads in simulation_config.yaml:512.
 - LOW — excel_exporter.py:676 uses iterrows() (reporting only,
 minor).

 Verification

 1. pytest -m fast (orchestrator tests cover year executor
 config/performance.py:170-201 (PolarsEventSettings), and polars.max_threads in simulation_config.yaml:512.
 - LOW — excel_exporter.py:676 uses iterrows() (reporting only, minor).

 Verification

 1. pytest -m fast (orchestrator tests cover year executor paths).
 2. Run planalign simulate 2025-2026 --verbose locally; confirm STATE_ACCUMULATION now logs one dbt invocation,
 results identical (row counts in fct_yearly_events / fct_workforce_snapshot match a pre-change run with the same
 seed).
 3. Compare wall-clock per year before/after; then re-test on the Ubuntu server.
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
