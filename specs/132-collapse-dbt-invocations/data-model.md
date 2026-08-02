# Phase 1 Data Model: Collapse Remaining Per-Year Transformation Invocations

**Feature**: 132-collapse-dbt-invocations
**Date**: 2026-08-02

This feature introduces **no database schema change**. No `fct_*`, `int_*`, `dim_*`, seed, or macro is modified. The entities below are the in-process and on-disk artifacts the work produces and asserts against.

---

## 1. Command Schedule

The ordered set of dbt commands a run issues. Already recorded per run in `run_execution_metadata` (Feature 120/121), so `FR-016` needs no new persistence — only a stable read path for the tests.

| Field | Type | Notes |
|---|---|---|
| `simulation_year` | int | Year the command belongs to |
| `stage` | str | `INITIALIZATION`, `FOUNDATION`, `EVENT_GENERATION`, `STATE_ACCUMULATION`, `VALIDATION`, or a setup pseudo-stage |
| `sequence` | int | Position within the run |
| `verb` | str | `seed`, `run`, or `build` |
| `selection` | list[str] | Model names and/or tag selectors |
| `full_refresh` | bool | Whether the command carries a rebuild flag |
| `extra_vars` | dict | Vars beyond the run's base vars (notably `hazard_params_hash`) |

**Invariants**

- **CS-1** (`FR-002`): no model name appears in more than one command's resolved selection within a year.
- **CS-2** (`FR-005`): the set of models built with `full_refresh=true` is identical before and after any step.
- **CS-3** (`FR-003`): after Step 2, every year past the start year contributes exactly two commands.
- **CS-4** (`FR-001`): after Step 1, the start year contributes fewer than eight.
- **CS-5**: `extra_vars` present on a pre-merge command is present on the command that absorbs it (Finding 4, risk 1).

**State transitions** — the schedule is built once per year by `WorkflowBuilder.build_year_workflow`, then finalized as commands are issued. Only the finalized form is asserted against.

---

## 2. Reference Workload

The fixed measurement subject. Held constant so successive measurements compare.

| Field | Value |
|---|---|
| `census_rows` | 60,040 (7,505 × 8, via `scripts/perf_profile/make_large_census.py`) |
| `census_path` | a single generated file, reused across all four runs of a gate |
| `years` | 5 |
| `config_shape` | Studio-realistic DC-plan configuration |
| `threads` | 1 |
| `database` | isolated per-run file under `var/`; never `dbt/simulation.duckdb` |

**Invariants**

- **RW-1** (Finding 6): all runs within one gate share the *same generated census file*, not merely the same generation parameters.
- **RW-2**: every run uses a fresh isolated database.

---

## 3. Parity Result

Outcome of the all-marts comparison between a baseline run and a candidate run. Produced by `scripts/parity_gate.py`, committed under `specs/132-collapse-dbt-invocations/evidence/`.

| Field | Type | Notes |
|---|---|---|
| `mart` | str | One row per mart table |
| `baseline_minus_candidate` | int | Must be 0 |
| `candidate_minus_baseline` | int | Must be 0 |
| `excluded_columns` | list[str] | Audit timestamps actually excluded for this mart |
| `mart_set_source` | str | How the mart list was enumerated |
| `determinism_clean` | bool | Two same-seed candidate runs also compared 0/0 |
| `scale` | int | Must be 60,040 |
| `horizon_years` | int | Must be 5 |

**Invariants**

- **PR-1** (`FR-006`, `FR-008`): every mart is 0/0, at 60k, over five years.
- **PR-2** (`FR-007`): the compared mart set equals the full enumerated mart set — a missing mart fails the gate rather than passing silently.
- **PR-3** (`FR-011`): `determinism_clean` is true.
- **PR-4** (`FR-009`): only audit-timestamp and per-run provenance fields are excluded; the exclusion list is reported, not assumed.

---

## 4. Step Record

One per step, recording the measurement and the keep/revert decision (`SC-003`, `SC-004`, `FR-017`–`FR-020`).

| Field | Type | Notes |
|---|---|---|
| `step_id` | str | `1a`, `1b`, `2` (and `1c` if attempted) |
| `command_count` | int | From the Command Schedule |
| `wall_time_median_s` | float | Median of ≥3 runs |
| `startup_s` / `execution_s` / `orchestration_s` | float | The three-way split |
| `delta_vs_prior_s` | float | Against the immediately preceding step, not the original baseline |
| `bar_s` | float | The step's target from `SC-001` / `SC-002` |
| `parity` | ref | The Parity Result for this step |
| `decision` | enum | `keep`, `revert`, `stop` |

**Invariants**

- **SR-1** (`SC-003`): `decision = keep` requires `delta_vs_prior_s >= bar_s` **and** a clean Parity Result.
- **SR-2** (`SC-002`): Story 2's delta is measured against the post-Story-1 state, not a historical headline baseline.
- **SR-3** (`SC-004`): every step has a record, including reverted ones — a reverted step is a successful outcome, not an absent one.
