# Data Model: Run-Cost Profile

Three entities from the spec, made concrete. All persisted as JSON under `var/perf_profile/samples/` (per-repetition) except the decision record, which lives inside the committed report. Field-level schema is normative in [contracts/timing-data.md](contracts/timing-data.md).

## TimingSample (one per repetition)

One completed simulation run of one configuration.

| Field | Type | Notes |
|---|---|---|
| `sample_id` | str | `{size}-{rep}` e.g. `dev-2` |
| `census_size` | enum | `tiny` (150) / `dev` (7505) / `large` (~60000) |
| `census_rows` | int | actual row count of the parquet used |
| `census_parquet` | str | path used for `census_parquet_path` |
| `horizon` | [int, int] | `[2025, 2027]` |
| `repetition` | int | 1-based |
| `warm` | bool | `false` for the first run per size — excluded from headline stats |
| `db_path` | str | isolated DuckDB path (under `var/perf_profile/db/`) |
| `total_wall_s` | float | wall time around `execute_multi_year_simulation` |
| `invocations` | list[Invocation] | see below |
| `env` | EnvNote | see below |
| `completed` | bool | failed runs kept with `completed=false` + `error` field, never silently dropped |

### Invocation (nested)

One `DbtRunner.execute_command` subprocess call.

| Field | Type | Notes |
|---|---|---|
| `seq` | int | order within the run |
| `year` | int \| null | simulation year if applicable |
| `stage` | str \| null | workflow stage name (`event_generation`, …) |
| `command` | str | dbt command + selector |
| `wall_s` | float | measured around the call |
| `models` | list[ModelTiming] | from the post-invocation `run_results.json` snapshot |

### ModelTiming (nested)

| Field | Type | Notes |
|---|---|---|
| `unique_id` | str | dbt node id |
| `execute_s` | float | dbt-reported execute-phase time (the "computation" component) |
| `compile_s` | float | dbt-reported compile-phase time (counted as overhead) |
| `status` | str | success/error/skipped |

### EnvNote (nested)

| Field | Type | Notes |
|---|---|---|
| `machine` | str | model identifier + CPU + RAM |
| `os` | str | platform string |
| `python`, `dbt_core`, `dbt_duckdb`, `duckdb` | str | versions |
| `git_sha` | str | repo state measured |
| `shared_db_sha256_before` | str | SC-007 evidence; the matching `_after` hash lives in campaign-level `campaign.json` (it cannot exist until the campaign ends — samples stay append-only) |

**Validation rules** (enforced by the harness before a sample is used in the report):

- `total_wall_s ≥ Σ invocations.wall_s` (residue is the difference; must be ≥ 0)
- decomposition identity: `computation + overhead + residue` within 10% of `total_wall_s` (FR-003)
- headline stats require ≥ 3 samples with `warm=true`… (`large`: ≥ 2, and the report labels it)

## ProbeResult (exactly one)

| Field | Type | Notes |
|---|---|---|
| `stage` | str | `event_generation` |
| `year` | int | 2025 |
| `census_size` | enum | `dev` |
| `standard_wall_s` / `direct_wall_s` | float | both paths, same starting DB copy |
| `speedup` | float | standard / direct |
| `equivalent` | bool | row-count + checksum comparison verdict |
| `diffs` | list[str] | non-empty iff `equivalent=false` — each entry names table + discrepancy (critical finding path) |

**State transition**: a ProbeResult with `equivalent=false` does not block the report — it converts the probe section into a risk finding and forces FR-007's judgment text to address it.

## DecisionRecord (inside `docs/perf/run_cost_profile.md`)

| Field | Notes |
|---|---|
| criteria | FR-007 verbatim, stated **before** results |
| overhead_share_by_size | the size curve; decision evaluates the `large` row |
| crosscheck_ratio | M2 overhead vs M3 (invocations × fixed floor) — same order required |
| projection | speedup range + enumerated assumptions (GO path) or top-3 compute hotspots (NO-GO path) |
| recommendation | exactly one of GO / NO-GO (+ per-scale note if the verdict differs by size) |
| references | issue #455 (source), #456 (gated), tracking #463 |

## Relationships

```
TimingSample 1..n ──aggregated by──▶ build_report.py ──▶ DecisionRecord (in report)
ProbeResult  1    ──────────────────────────────┘
```
