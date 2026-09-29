# Research: Studio Workflows for Parameter Fit and Backtest (#588)

Every decision below was made against the code as it stands on `main` @ e8a0df6c.

## R1. Execution model: CLI subprocess, not an in-process thread

- **Decision**: Each job runs `python -m planalign_cli.main fit|backtest …` as a child process, in its own process group. A daemon thread owns the process, streams its stdout, and records progress and outcome on disk.
- **Rationale**:
  - A backtest runs full orchestrator simulations in-process (`planalign_backtest/simulate.py::run_seed`). A thread cannot be cancelled mid-simulation.
  - Killing the process group reclaims every child, including dbt.
  - The CLI is already the tested engine; Studio becomes one more caller of it, which satisfies FR-033 by construction.
  - Studio simulations already use this pattern (`services/simulation/run_execution.py`).
- **Alternatives rejected**:
  - An in-process thread, as in `calibration.py` and `optimizer.py`. It cannot be cancelled.
  - `multiprocessing`. It pickles config and fixtures and gains nothing over the CLI.
  - The async `create_subprocess` in `subprocess_utils`. Its async machinery isn't needed, because the job thread is synchronous and a plain `subprocess.Popen` is simpler.

## R2. Structured progress

- **Decision**: A new helper, `planalign_fit/progress.py::emit(event, **fields)`, prints `PLANALIGN_FIT_PROGRESS|{json}` lines to stdout, but only when `PLANALIGN_FIT_PROGRESS=1`.
  - The fit runner emits stages `loading_history`, `fitting` and `writing_pack`.
  - The backtest runner adds `simulating` (with `seed`, `index` and `total`), `scoring`, and a terminal `simulation_failed` event carrying `seed` and `year`.
- **Rationale**:
  - It mirrors the existing `PLANALIGN_TELEMETRY|` convention (`pipeline/telemetry_emitter.py`), so progress never has to be regex-parsed from log text (FR-013).
  - It is gated by an environment variable, so plain CLI output is unchanged.
- **Alternatives rejected**:
  - Reusing `PLANALIGN_STRUCTURED_TELEMETRY`. That protocol is shaped around simulation years and stages. Turning it on inside backtest seeds would also stream per-year simulation noise.
  - A progress file. Stdout is already streamed, so a file adds nothing.

## R3. Job persistence and retention

- **Decision**: Each job lives at `workspaces/<ws>/param_fits/<job_id>/` and contains:
  - `job.json` (written atomically: temp file, then rename)
  - `inputs/` (base config and seeds)
  - `pack/`
  - `work/` (backtest scratch)
  - `job.log` (tail of the output)

  On the first read of a record whose status is non-terminal and which is not owned by the current process, the job is marked `failed`, reason `interrupted`. Once a job finishes, finished jobs beyond `APISettings.param_fit_max_jobs_per_workspace` (default 20) are deleted, oldest first. `planalign gc` gains a sweep for `workspaces/*/param_fits/*/work` trees older than the artifact age cutoff.
- **Rationale**: Packs are evidence reviewed over days (FR-016). Lazy reconciliation needs no startup hook and handles crashes the same way it handles clean restarts.
- **Alternatives rejected**:
  - The in-memory registry used by calibration and optimizer. Jobs would be lost on restart.
  - A DuckDB job table. It adds locking and schema for about 20 small records.

## R4. History storage

- **Decision**: A multipart upload of 2–5 files creates an immutable history set at `workspaces/<ws>/fit_history/<history_id>/`. Files are stored byte-for-byte, with sanitized names. Uploads are validated immediately with `planalign_fit.snapshots.load_snapshots`, which already rejects the following:
  - gaps and duplicate years
  - fewer than 2 or more than 5 snapshots
  - missing columns
  - undated or empty files

  Invalid sets return 422 with that message and nothing is kept. Preview re-hashes the files on every read.
- **Rationale**:
  - The fitter defines what a valid snapshot is, so validating with the fitter is the only honest preview (FR-004).
  - Keeping the bytes unchanged makes the recorded sha256 identical to what the CLI hashes.
  - Uploads only (FR-002) avoid path-traversal and remote-policy concerns.
- **Alternatives rejected**:
  - `FileService.save_uploaded_file`. It normalizes census files, which changes the bytes and the columns.
  - Pointing at arbitrary server directories. This is a security surface we don't need.

## R5. Priors come from the base scenario

- **Decision**: At launch, the job snapshots the base scenario:
  - writes `storage.get_merged_config(ws, scenario)` to `inputs/base_config.yaml`
  - materializes that scenario's seeds into `inputs/seeds/` with the same function Studio runs use (`write_seeds`, including any pack overlay the scenario carries)
  - passes both as `--config` and `--seeds-dir`

  `apply_pack` gains an optional `seeds_root` argument (default `dbt_root/seeds`, so there is no behavior change), and `run_backtest` passes `fit_options.seeds_dir` into it. The held-out simulations then use the same bands and priors the fit used.
- **Rationale**: The fit should be measured against the scenario the pack will be applied to. Before this change, `backtest --seeds-dir` fitted on one seed set and simulated on `dbt/seeds`, a latent mismatch that the Studio path would hit on every workspace with custom bands.
- **Alternatives rejected**: Fitting on the global `config/simulation_config.yaml`. The resulting pack would not match the scenario it is applied to.

## R6. Machine-readable diagnostics

- **Decision**: A new module, `planalign_fit/diagnostics.py::build_diagnostics(run) -> dict`, holds:
  - every `FittedValue.to_dict()`, grouped as termination, promotion, merit, deferral and config
  - `unfittable`
  - `warnings`
  - `promotion_classification`
  - `diagnostics` counts
  - `thin_cell_count`

  `write_pack(..., diagnostics=None)` writes it as `diagnostics.json` when given. The fit CLI always passes it. The backtest CLI now also writes `fit_report.md` and `diagnostics.json`. `load_pack` and the fingerprint ignore the file.
- **Rationale**: FR-019. The fingerprint (`_fingerprint`) only covers the fragment, the seeds and the source digest, so the file is additive by construction.
- **Alternatives rejected**: Parsing `fit_report.md`, which is brittle.

## R7. Applying a pack to Studio

- **Finding**: `WorkspaceStorage._inject_seed_config_defaults` always injects `promotion_hazard`, `age_bands` and `tenure_bands` into merged config. `write_all_seed_csvs` then always rewrites the promotion hazard seed CSVs from config. A pack's promotion seeds dropped into a run's `seeds/` would be silently overwritten.
- **Decision**:
  - Build the new scenario's `config_overrides` from these parts:
    - the source scenario's overrides
    - deep-merged with the pack's `parameters.yaml` fragment
    - `promotion_hazard` replaced with the pack's promotion seeds, translated into the config section's exact schema
    - a `param_pack` block from `planalign_fit.apply.provenance_block`
  - Copy the whole pack to `scenarios/<new>/param_pack/`.
  - `write_seeds(config, run_dir, pack_seeds_dir=None)` layers seeds in this order: default seeds, then pack seeds, then config-generated seeds. `SimulationService._prepare_simulation` passes the scenario's `param_pack/seeds` when it exists.
- **Rationale**:
  - The fitted promotion hazard becomes visible and editable in Studio's existing promotion-hazard editor, and edits win naturally (FR-029).
  - Termination, `comp_levers` and deferral seeds have no Studio editor, so there is no conflict to resolve for them.
  - The `param_pack` block reaches `run_metadata` through the existing extraction (FR-028).
- **Alternatives rejected**:
  - Pack seeds winning over config. The Studio editor would show values the run ignores.
  - Mutating the source scenario. Forbidden by FR-023.

## R8. Staleness and the review handshake

- **Decision**:
  - **Recorded at launch**: `source_digest` (from the preview), `base_scenario_fingerprint` (`config_fingerprint(merged)`), and the job's settings.
  - **Stale reasons computed on read**:
    - `history_changed`: the current digest ≠ the recorded one, or files are missing
    - `pack_modified`: `verify_pack` is false
    - `base_scenario_changed`: informational only
  - **Apply preview** (`GET …/apply-preview?source_scenario_id=`) returns:
    - the source fingerprint
    - the pack fingerprint
    - the required acknowledgements
    - the config diff (reusing `config_diff_service`)
  - **Apply** (`POST …/apply`) re-computes everything and returns:
    - 409 with a `stale` reason if a fingerprint or the history changed
    - 422 if required acknowledgements are missing
    - 409 with `suggested_name` if the name collides
  - The required acknowledgements are:
    - `thin_cells` (when `thin_cell_count > 0`)
    - `unfittable` (when the pack has unfittable groups)
    - `no_backtest`
    - `backtest_warn`
    - `backtest_fail`

    A backtest verdict counts only if it is current: its `pack_fingerprint` matches the pack.
- **Rationale**: The same handshake shape as calibration's `_verify_apply_context` and the optimizer's promote-name 409 (FR-024–FR-030).

## R9. Error mapping

| Job | Exit code | Classification | HTTP-equivalent `error_status` |
|-----|-----------|----------------|--------------------------------|
| fit | 2 | `invalid_input` | 422 |
| fit | 3 | `invalid_history` | 422 |
| fit | 4 | `output_conflict` | 409 |
| backtest | 2 | `invalid_input` | 422 |
| backtest | 3 | `invalid_history` | 422 (rejected history, pack or split) |
| backtest | 4 | `simulation_failure` | 500 (plus `failed_seed` and `failed_year` from the `simulation_failed` progress event) |
| any | other non-zero | `unexpected` | 500 (sanitized message; details only in `job.log`) |
| any | killed by cancel | status `cancelled` | — |

For classified failures, the job error message is the CLI's last `stderr`/`stdout` line (these are user-facing messages printed by the CLI). Unexpected failures get a generic message.

## R10. Studio UI

- **Decision**:
  - A new route `/w/:workspaceId/fit`, listed in the "Run" nav group as "Fit & Backtest".
  - Components live under `components/paramFit/`, with a thin `ParamFitPage.tsx` shell and pure helpers in `paramFitHelpers.ts` (tested with vitest).
  - The API client functions are added to `services/api.ts` with `Schemas[...]` aliases generated from the refreshed OpenAPI snapshot.
  - Polling runs every 1.5 s while any job is non-terminal.
- **Rationale**: This matches `OptimizerPanel` and `EnsemblesPage` and the #661 generated-types migration.
