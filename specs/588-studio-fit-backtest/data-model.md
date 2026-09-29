# Data Model: Studio Fit & Backtest (#588)

All records are JSON on disk under the workspace. The API exposes them as Pydantic v2 models (`planalign_api/models/param_fit.py`).

## HistorySet — `workspaces/<ws>/fit_history/<history_id>/`

| Field | Type | Notes |
|---|---|---|
| history_id | str | `hist_<12 hex>` |
| created_at | datetime | |
| snapshots | list[SnapshotInfo] | Sorted by year |
| source_digest | str | Same algorithm as `SnapshotSet.source_digest` |
| splits | dict["1"\|"2", SplitPreview \| SplitError] | Backtest split for each holdout choice |

The set is immutable once created. Files live in `files/`; `history.json` records the original names.

**SnapshotInfo**: `year`, `filename`, `row_count`, `sha256`, `as_of_date` (the snapshot year's Dec 31), and `columns_present` (`level_id` and deferral columns, relevant to the diagnostics).

**SplitPreview**: `fit_years`, `holdout_years`, `boundary_year`, and `simulation_effective_date` (the first holdout year's Dec 31, matching `planalign_backtest.simulate.configure_seed`).

**SplitError**: `message`, from `plan_split`'s `BacktestError`.

## ParamFitJob — `workspaces/<ws>/param_fits/<job_id>/job.json`

| Field | Type | Notes |
|---|---|---|
| job_id | str | `fit_<12 hex>` |
| workspace_id | str | |
| mode | `"fit"` \| `"backtest"` | |
| status | `queued` \| `running` \| `completed` \| `failed` \| `cancelled` | |
| created_at / started_at / completed_at | datetime? | |
| request | ParamFitRequest | Echo of the validated launch request |
| inputs | JobInputs | Recorded at launch |
| progress | JobProgress? | Latest structured progress event |
| error | JobError? | Set on `failed` |

**JobInputs**: `history_id`, `source_digest`, `snapshots` (list of SnapshotInfo), `split` (SplitPreview, backtest only), `base_scenario_id`, `base_scenario_name`, `base_scenario_fingerprint`, and `moved_settings` (dict of settings that differ from their defaults).

**JobProgress**: `stage` (`queued`, `loading_history`, `fitting`, `simulating`, `scoring` or `writing_pack`), `seed?`, `index?`, `total?`, `message?`, `updated_at`.

**JobError**: `kind` (`invalid_input`, `invalid_history`, `output_conflict`, `simulation_failure`, `interrupted` or `unexpected`), `message`, `status` (422, 409 or 500), `failed_seed?`, `failed_year?`.

### State transitions

```
queued ──▶ running ──▶ completed
   │          ├──────▶ failed      (non-zero exit, or found non-terminal and unowned on read → interrupted)
   └──────────┴──────▶ cancelled   (cancel request; the pack/ and work/ directories are removed)
```

Terminal states are final. `completed` implies `pack/manifest.json` exists. For `backtest` it also implies `pack/backtest/scorecard.json` exists.

## ParamFitRequest (launch body)

| Field | Type | Validation |
|---|---|---|
| history_id | str | Must exist in the workspace |
| base_scenario_id | str | Must exist in the workspace |
| mode | `"fit"` \| `"backtest"` | |
| holdout_years | int | 1 or 2; backtest only; must produce a valid split |
| seeds | list[int] | 1–5 distinct values; backtest only; default `[42, 43, 44]` |
| thresholds | {headcount, compensation, flows, plan}: {warn, fail} | 0 < warn < fail; defaults match the CLI |
| fit_options | {credibility_k ≥ 0, min_exposure ≥ 0, level_coverage_threshold ∈ (0,1], separation_exposure_gate ∈ (0,1]} | Defaults match the CLI |
| notes | str | ≤ 500 characters |

## ParamFitResult (on a completed job)

- **summary**: `snapshot_years`, `linked_employees`, `fitted_count`, `thin_count`, `promotion_basis` + `promotion_basis_label`, `unfittable` (list of {name, reason, default_used}), `warnings`
- **diagnostics**: groups → list of FittedValue dicts, each with `thin: bool` derived from `basis ∈ {pooled, prior}`
- **provenance**: `pack_id`, `fingerprint`, `fit_date`, `source_digest`, `sources`, `base_config`, `base_seeds`, `planalign_version`, `thresholds_moved`, `fingerprint_verified`
- **scorecard** (backtest only): the parsed `scorecard.json` (`comparisons`, `verdict`, `verdict_summary`, `seeds`, `seed_runs`, `thresholds`, `overridden_thresholds`, `split`, `provenance`), plus `current: bool` (its `pack_fingerprint` matches the pack)
- **stale**: list of `{reason: history_changed | pack_modified | base_scenario_changed, message}`

## Apply

**ApplyPreview**, returned by `GET …/apply-preview?source_scenario_id=`:
- `source_scenario_id`
- `source_config_fingerprint`
- `pack_fingerprint`
- `required_acknowledgements` (subset of `thin_cells`, `unfittable`, `no_backtest`, `backtest_warn`, `backtest_fail`)
- `diff` (a list of `{path, before, after}` between the source's merged config and the resulting merged config)
- `seed_files` (the pack's seed file names that will ride with the scenario)
- `suggested_name`

**ApplyRequest**: `source_scenario_id`, `name`, `description?`, `pack_fingerprint`, `source_config_fingerprint`, `acknowledgements` (list).

**Pack-derived Scenario**: a new `Scenario` with these parts:
- `config_overrides` = the source overrides ⊕ the pack fragment ⊕ `promotion_hazard` (from the pack seeds) ⊕ the `param_pack` block
- `provenance` = `{source: "param_pack", param_fit_job_id, pack_id, pack_fingerprint, source_digest, source_scenario_id, source_config_fingerprint, backtest_verdict, acknowledgements, applied_at}`
- a directory `scenarios/<id>/param_pack/`, a full copy of the pack, whose `seeds/` are layered into every run

## Settings

`APISettings.param_fit_max_jobs_per_workspace: int = 20` (gt 0). Finished jobs beyond this limit are pruned after each job finishes.
