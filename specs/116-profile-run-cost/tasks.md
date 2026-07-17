# Tasks: Run-Cost Profile — Orchestration Overhead vs Computation (Go/No-Go for Compiled Execution)

**Input**: Design documents from `/specs/116-profile-run-cost/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/timing-data.md, quickstart.md

**Tests**: No dedicated test tasks — per plan.md Constitution Check (Principle III, justified): this feature ships no product code. Harness validity is enforced by built-in cross-checks that ARE tasks below (schema validation, decomposition identity, FR-004 cross-check, probe equivalence, SC-006 regeneration).

**Organization**: Tasks grouped by user story. Note the execution nuance for this feature: US1 (the P1 decision/report) *consumes* data produced by US2/US3, so US1 is implemented and independently tested against smoke-run samples, then finalized in the Polish phase once campaign data exists.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Package scaffold and output locations

- [X] T001 Create `scripts/perf_profile/__init__.py` (empty package marker) and output directories `var/perf_profile/samples/` + `var/perf_profile/db/`; verify `var/` is covered by `.gitignore` (it should be per repo convention — if not, add `var/perf_profile/`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The sample pipeline every story depends on — schema models, dbt timing capture, and the single-run driver, proven by a smoke run

**⚠️ CRITICAL**: No user story work can begin until this phase is complete (US1 renders samples, US2 produces them at scale, US3 writes to the same contract)

- [X] T002 Implement Pydantic v2 models `ProfileConfig`, `TimingSample`, `Invocation`, `ModelTiming`, `EnvNote`, `ProbeResult` in `scripts/perf_profile/profile_config.py` exactly per `data-model.md` (field names/types are the normative contract; include the validation rules: residue ≥ 0, decomposition identity within 10%, warm-rep minimums)
- [X] T003 Implement `scripts/perf_profile/dbt_timing.py`: a runtime wrapper around a `DbtRunner` instance's `execute_command` (composition — wrap the bound method on the orchestrator's runner object, never edit `planalign_orchestrator/dbt_runner.py`) recording per-invocation seq/year/stage/command/wall_s, and snapshotting `dbt/target/run_results.json` immediately after each invocation into the in-memory sample (dbt overwrites it per invocation — research.md R2)
- [X] T004 Implement single-run driver in `scripts/perf_profile/run_matrix.py`: fresh isolated DuckDB under `var/perf_profile/db/`, set `DATABASE_PATH` (set/restore pattern from `tests/fixtures/invariant_simulation.py:85-93`), set `config.setup["census_parquet_path"]`, `create_orchestrator(config, db_path=…, threads=1)`, wrap its runner via T003, time `execute_multi_year_simulation(2025, 2027)`, capture `EnvNote` (machine/os/versions/git SHA), and write a schema-valid `TimingSample` JSON to `var/perf_profile/samples/{size}-{rep}.json`
- [X] T005 Add campaign guardrails to `scripts/perf_profile/run_matrix.py`: refuse to start if the resolved DB path is `dbt/simulation.duckdb` (assert per run), SHA-256 `dbt/simulation.duckdb` before the campaign and re-verify after (SC-007), record the before-hash in each sample's `EnvNote` and both hashes in campaign-level `campaign.json`, nonzero exit on any violation
- [X] T006 Smoke-run the pipeline: convert `tests/fixtures/invariant_census.csv` → parquet (same as `tests/fixtures/invariant_simulation.py:134-137`), run `python -m scripts.perf_profile.run_matrix --sizes tiny --reps 1`, and verify the emitted sample validates against T002 models with decomposition identity holding (computation + overhead + residue ≈ total within 10%)

**Checkpoint**: One valid `tiny-1.json` sample exists — all three stories can now proceed

---

## Phase 3: User Story 1 — Evidence-backed go/no-go decision (Priority: P1) 🎯 MVP

**Goal**: The report builder that turns samples into `docs/perf/run_cost_profile.md` with criteria stated before results and exactly one mechanical recommendation

**Independent Test**: Render the report from smoke samples only (tiny size); verify the 10 contract sections appear in order, FR-007 criteria appear verbatim before any results, and re-running regenerates byte-identical tables (SC-006)

- [X] T007 [US1] Implement sample loading/aggregation in `scripts/perf_profile/build_report.py`: read `var/perf_profile/samples/*.json`, validate against T002 models (fail loudly on mismatch — contract §1), exclude `warm=false` and `completed=false` from stats (but list them in the footer), compute min/median/max per size and the computation/overhead/residue split
- [X] T008 [US1] Implement report rendering in `scripts/perf_profile/build_report.py`: emit the 10 sections in contract §2 order (1 criteria verbatim from spec FR-007 → 10 reproduction commands + consumed-sample list) to `docs/perf/run_cost_profile.md`; tolerate missing sizes/probe by rendering an explicit "NOT YET MEASURED" placeholder (never silently omit a section)
- [X] T009 [US1] Implement decision evaluation in `scripts/perf_profile/build_report.py`: overhead share evaluated at the `large` row (fallback: largest measured size, labeled as such), GO/NO-GO/judgment-band logic per FR-007, per-scale divergence note when verdicts differ by size, exactly one recommendation emitted
- [X] T010 [US1] Verify US1 independently: run `build_report` twice against the smoke sample set; confirm section order, criteria-before-results, deterministic regeneration (byte-identical tables), and that the decision section correctly reports "insufficient data — large size not yet measured" rather than fabricating a verdict

**Checkpoint**: Report machinery complete and independently tested — awaiting campaign data

---

## Phase 4: User Story 2 — Wall-time attribution across census sizes (Priority: P2)

**Goal**: The three-size measurement campaign producing the overhead-share-vs-size curve plus the independent fixed-cost cross-check

**Independent Test**: Samples exist for all three sizes with required warm repetitions; decomposition identity holds at every size; cross-check ratio lands within 0.3×–3× of the M2 overhead figure

- [X] T011 [P] [US2] Implement `scripts/perf_profile/make_large_census.py`: scale `data/census_preprocessed.parquet` (7,505 rows — NOTE: the `_5k`/`_7k` variants are stale identical copies, do not use; research.md R3) ~8× to `var/perf_profile/census_large.parquet` with globally unique perturbed `employee_id`s, jittered ages/comp within valid ranges, preserved level/status mix; print row count + demographic sanity summary vs source
- [X] T012 [US2] Extend `scripts/perf_profile/run_matrix.py` to full matrix mode: `--sizes tiny,dev,large --reps N --horizon 2025-2027` where `--reps N` = N **warm** repetitions and the harness always prepends one extra cold run per size saved as `{size}-0.json` (`repetition: 0, warm: false`), failed runs captured as `completed=false` samples with `error` (never dropped), per-size census resolution (tiny→fixture parquet, dev→`data/census_preprocessed.parquet`, large→T011 output)
- [X] T013 [US2] Implement the M3 fixed-cost cross-check in `scripts/perf_profile/run_matrix.py` (flag `--measure-floor`): count invocations per simulated year from sample data, time a genuinely trivial `dbt run --select stg_config_age_bands` (config-seed staging model — NOT `stg_census_data`, whose parquet scan would contaminate the fixed floor) against an already-built isolated DB ≥5 times, subtract its dbt-reported execute time from each measurement, store floor stats + invocation count in `campaign.json` for the report's section 6
- [X] T014 [US2] Execute the campaign for tiny + dev: `run_matrix --sizes tiny,dev --reps 3` (plus automatic cold run each) and `--measure-floor`; spot-validate samples against the T002 schema
- [X] T015 [US2] Execute the campaign for large: `run_matrix --sizes large --reps 3` (long-running — accept 2 warm reps if the time budget bites, per spec edge case; the label must say so); confirm SC-007 hash check passed at campaign end
- [X] T016 [US2] Validate FR-003/FR-004 across all samples: decomposition residue ≤ 10% at every size and cross-check ratio in 0.3×–3×; if either fails, diagnose (e.g., missed invocation site, unattributed orchestrator time), fix the harness (not the product), and re-run the affected size

**Checkpoint**: Decision-grade data exists — the overhead-share-vs-size curve is renderable

---

## Phase 5: User Story 3 — Direct-execution headroom probe (Priority: P3)

**Goal**: Observed (not projected) evidence: EVENT_GENERATION year-2025 via compiled SQL directly vs the standard path, with equivalence verified

**Independent Test**: `probe.json` exists with both wall times and an equivalence verdict from row-count + checksum comparison on the same starting DB copy

- [X] T017 [US3] Implement probe setup in `scripts/perf_profile/probe_direct_execution.py`: run a dev-census year-2025 simulation in an isolated DB, stopping after FOUNDATION (drive stages via the orchestrator's workflow up to `WorkflowStage.FOUNDATION`; see `planalign_orchestrator/pipeline/workflow.py:169`), then snapshot-copy the `.duckdb` file so both paths start identically
- [X] T018 [US3] Implement direct execution path in `scripts/perf_profile/probe_direct_execution.py`: `dbt compile` once with the year's vars, read `dbt/target/manifest.json` for the EVENT_GENERATION model set (`dbt/models/intermediate/events/`, 12 models) in topological order, execute each compiled SQL from `dbt/target/compiled/` via the `duckdb` client replaying the incremental delete+insert contract (pre-hook `DELETE … WHERE simulation_year = 2025` where the model config declares it), timing the whole stage
- [X] T019 [US3] Implement equivalence diff + timing in `scripts/perf_profile/probe_direct_execution.py`: run the standard path on the other DB copy (timed), compare per-model target tables (row counts per event type + ordered-checksum), emit `var/perf_profile/samples/probe.json` (`ProbeResult`) with `equivalent`, `diffs`, both wall times, speedup
- [X] T020 [US3] Execute the probe and review: if `equivalent=false`, investigate each diff enough to name its cause in `probe.json`'s `diffs` entries — this is the critical-finding path that FR-007's judgment text must address; do NOT paper over divergence

**Checkpoint**: All measurement data complete

---

## Phase 6: Polish & Close the Loop

**Purpose**: The final report, the decision, and roadmap bookkeeping

- [X] T021 Generate the final report: `python -m scripts.perf_profile.build_report --out docs/perf/run_cost_profile.md`; walk the quickstart.md sanity checklist (SC-007 line, warm-rep counts, residue ≤ 10%, cross-check ratio, probe verdict); author the projection-assumptions prose (GO path) or top-3 hotspot list (NO-GO path) in the report where tables alone don't speak
- [X] T022 Read the report cold against spec SC-001…SC-007 and User Story 1 acceptance scenarios; fix any gap by regenerating (never hand-editing tables)
- [X] T023 Commit `scripts/perf_profile/`, `docs/perf/run_cost_profile.md`, and spec artifacts on branch `116-profile-run-cost` and open a PR (repo convention; never commit `var/perf_profile/`)
- [X] T024 Close the loop on GitHub: comment the recommendation + report link on issue #455, check off the #455 item in tracking issue #463, and if GO, paste the projection baseline into issue #456 (per contract §4); if NO-GO, open the redirect issue naming the top-3 hotspots

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2**: strict (package must exist)
- **Phase 2 blocks everything**: T002 (schema) → T003/T004 → T005 → T006 (smoke)
- **US1 (Phase 3)**: needs only the smoke sample from T006; fully implementable/testable before any campaign data
- **US2 (Phase 4)**: T011 is independent [P]; T012–T013 build on T004; T014–T015 need T012 (+T011 for large); T016 needs T014–T015
- **US3 (Phase 5)**: needs only Phase 2 (writes to the same sample contract); independent of US1/US2 — can run in parallel with either
- **Phase 6**: T021 needs T009 + T015 + T020 (all data + report machinery); T022 → T023 → T024 sequential

### Story Dependency Note

US1 is P1 by *value* (the decision is the deliverable) but consumes US2/US3 *data*. The task flow resolves this: US1 is built and independently verified against smoke samples (T010), then the Polish phase produces the real report once US2/US3 land. The spec's extreme case (decision justifiable from Stories 1–2 alone) maps to: T021 may proceed without T020 if the probe is descoped, with the report's section 7 marked NOT MEASURED and FR-007's judgment text addressing the gap.

### Parallel Opportunities

- After T006: **US1 (T007–T010), T011, and US3 (T017–T019) can all proceed in parallel** — different files, shared read-only contract
- T014 (tiny+dev campaign, ~30+ min of runs) can execute while T017–T019 are being written
- T015 (large campaign, the long pole) should be started as early as its prerequisites (T011, T012) allow — ideally overnight

### Suggested MVP Scope

Phases 1–4 (Setup + Foundational + US1 + US2): this yields a decision-grade report in the spec's extreme case. US3 (probe) converts the projection from arithmetic to observed evidence and should only be skipped if US2's result is overwhelming (overhead ≥ 90%).

---

## Task Summary

| Phase | Tasks | Story |
|---|---|---|
| 1 Setup | T001 | — |
| 2 Foundational | T002–T006 | — |
| 3 Report & decision | T007–T010 | US1 (4 tasks) |
| 4 Measurement campaign | T011–T016 | US2 (6 tasks) |
| 5 Direct-execution probe | T017–T020 | US3 (4 tasks) |
| 6 Polish & close | T021–T024 | — |

**Total**: 24 tasks. Longest pole: T015 (large-census runs). Human-judgment tasks: T021 (projection prose), T022 (cold read), T024 (roadmap bookkeeping).
