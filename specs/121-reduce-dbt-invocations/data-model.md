# Phase 1 Data Model: Reduce Production-Path dbt Invocations

**Feature**: 121-reduce-dbt-invocations | **Date**: 2026-07-21

This feature introduces **no new persisted product tables** and **no change to any `fct_*`/`int_*`/`dim_*` schema**. The "entities" below are the conceptual objects the work produces and reasons about (measurement artifacts, schedule records, gate outcomes). Where an entity maps to an existing DuckDB table, that table is named; none are added or altered by this feature.

---

## Entity 1 — Invocation Schedule

The ordered sequence of dbt commands one five-year production run issues. Already recorded, per run, in the append-only `run_execution_metadata` table (produced by feature 120); this feature only *shortens* the schedule.

| Field | Type | Notes |
|---|---|---|
| `sequence` | int (1-based) | Position in the run |
| `selector` | string | Exact dbt selection (e.g. `run --select int_baseline_workforce`) |
| `stage` | enum | `INITIALIZATION` / `FOUNDATION` / `EVENT_GENERATION` / `STATE_ACCUMULATION` / setup |
| `simulation_year` | int \| null | Null for run-once setup steps (seed, staging, hazard rebuild) |
| `runner_kind` | string | `dbt` for every step in scope |
| `invocation_count` | int | Total steps in the run (baseline = 38) |

**Baseline instance (HEAD, authoritative — feature 120)**: 38 steps = 8 first-year prep + 6 × 5 years.
**Validation rules**: order is byte-equivalent across identical configs (modulo run-specific paths); the accumulator → events → snapshot relative order is invariant across any consolidation; `invocation_count` after consolidation ≤ 32 (target ~20–26).
**State transitions**: `HEAD baseline (38)` → `after Tier A (~33–34)` → `after Tier B (~28–29)` → `after Tier C (~19–24)`.

---

## Entity 2 — Consolidation Tier

One applied batch of related, independently-measurable consolidations.

| Field | Type | Notes |
|---|---|---|
| `id` | enum | `A` (hazard-cache batch) / `B` (INIT+FOUNDATION merge) / `C` (STATE_ACCUMULATION split collapse) |
| `touched_seam` | string | `HazardCacheManager.rebuild_hazard_caches` / `year_executor._run_parallel_or_single` / `year_executor._group_models_by_full_refresh` |
| `delta_invocations` | int | Commands removed (A: −4/−5, B: −5, C: −5/−10) |
| `risk` | enum | `low` (A) / `medium` (B) / `high` (C) |
| `output_neutral` | bool | Gate: must be proven true (all-mart parity) before the tier is kept |
| `ships` | bool | Set by the ship gate / maintainer decision |

**Validation rules**: a tier is retained only if `output_neutral == true` AND peak-RSS delta ≤ +10% AND it does not reorder accumulator→events→snapshot or cross a transaction boundary. Tiers are applied and measured in order A → B → C.

---

## Entity 3 — Before/After Run-Cost Artifact

The recorded measurement set for one config × one schedule state, produced by `scripts.perf_profile`.

| Field | Type | Notes |
|---|---|---|
| `config_label` | enum | `reference` / `studio` (both required — FR-013) |
| `schedule_state` | enum | `baseline` / `after_A` / `after_B` / `after_C` |
| `invocation_count` | int | From `run_execution_metadata` |
| `wall_time_warm_median` | float (s) | Median of ≥3 warm reps (`--skip-cold`) |
| `dbt_command_wall` | float (s) | Sum of dbt command durations |
| `model_execution` | float (s) | From `run_results.json` per-model timings |
| `subprocess_launch` | float (s) | Fixed per-invocation cost × count |
| `residue` | float (s) | Wall − (launch + command wall) ; must be small |
| `cpu_time` | float (s) | |
| `peak_rss` | float (MiB) | Ceiling: ≤ baseline × 1.10 |
| `config_fingerprint` | hash | From `to_dbt_vars` / product loader |
| `census_fingerprint` | hash | 60,040-employee Studio census |
| `construction_signature` | hash | Must match the product signature for the config |

**Validation rules**: baseline and every candidate share census + construction signature for the same config; the four-way time split plus residue accounts for total wall within measurement tolerance; every headline claim (count, wall, RSS) traces to an artifact (SC-009).

---

## Entity 4 — Correctness Parity Result

The bidirectional multiset comparison between a baseline run and a candidate run.

| Field | Type | Notes |
|---|---|---|
| `mart` | string | Each `fct_*` / `dim_*` mart table (enumerated from dbt `ls`) |
| `diff_baseline_minus_candidate` | int rows | `EXCEPT ALL` count; must be 0 |
| `diff_candidate_minus_baseline` | int rows | `EXCEPT ALL` count; must be 0 |
| `excluded_fields` | list | `created_at`, `snapshot_created_at`, run-metadata rows |

**Validation rules**: for **every** mart, both diff counts are 0 (FR-009). A single non-zero on any mart fails the tier. Determinism corollary: two candidate runs with identical seed+config also produce 0/0 (FR-010).

---

## Entity 5 — Ship Decision Record

The recorded outcome of the ship gate for the cumulative consolidation.

| Field | Type | Notes |
|---|---|---|
| `warm_improvement_pct` | float | Cumulative vs HEAD baseline |
| `gate_met` | bool | `warm_improvement_pct >= 20` |
| `decision` | enum | `auto_ship` (gate met) / `maintainer_ship` / `maintainer_no_ship` |
| `maintainer_note` | string | Present when `gate_met == false` — the human rationale |
| `evidence_ref` | link | The before/after artifacts the decision rests on |

**Validation rules**: when `gate_met == false`, `decision` MUST be one of the two `maintainer_*` values (never auto) — the human escalation the spec requires (Clarifications Q1). Any tiers shipped under a `maintainer_ship` still independently satisfy Entities 4 (parity) and the RSS ceiling.

---

## Relationships

```
Invocation Schedule ──(shortened by)── Consolidation Tier ──(measured into)── Before/After Run-Cost Artifact
                                              │
                                              ├──(gated by)── Correctness Parity Result   (per mart, must be 0/0)
                                              │
                                              └──(rolled up into)── Ship Decision Record  (≥20% → auto; else maintainer)
```
