# Contract: `planalign backtest`

Command implemented in `planalign_cli/commands/backtest.py`, registered in `planalign_cli/main.py`. Mirrors the shape of `planalign fit`.

## Synopsis

```bash
planalign backtest <SNAPSHOTS_DIR> [OPTIONS]
```

Holds out the most recent snapshot year(s), fits a parameter pack on the rest, simulates the held-out span in isolated databases across a seed set, and writes a scorecard into the pack.

## Arguments

| Argument | Type | Required | Description |
|---|---|---|---|
| `SNAPSHOTS_DIR` | path | yes | Directory of consecutive annual census snapshots (`.parquet` or `.csv`). At least 3 required. |

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--holdout N` | int | `1` | Snapshot years to hold out. 1 or 2. |
| `--seeds N` | int | `3` | Number of random seeds to run. 1–5. Seeds are `42, 43, …` unless `--seed-list` is given. |
| `--seed-list A,B,C` | csv ints | — | Explicit seed values. Mutually exclusive with `--seeds`. |
| `--output PATH` | path | fitter default | Parameter pack destination. |
| `--config PATH` | path | `config/simulation_config.yaml` | Base simulation config. |
| `--seeds-dir PATH` | path | `dbt/seeds` | Seed CSVs for band definitions and priors. Passed to the fitter. |
| `--threshold-headcount W,F` | csv floats | `0.02,0.04` | Warn and fail percentage-error bounds. |
| `--threshold-compensation W,F` | csv floats | `0.03,0.06` | |
| `--threshold-flows W,F` | csv floats | `0.10,0.20` | |
| `--threshold-plan W,F` | csv floats | `0.05,0.10` | |
| `--workdir PATH` | path | `var/backtests/<ts>-<pack_id>` | Isolated run databases and effective configs. |
| `--notes TEXT` | str | `""` | Recorded on the scorecard. |
| `--keep-databases` | flag | `False` | Retain per-seed databases after scoring. Off by default; they are large. |
| `--force` | flag | `False` | Overwrite an existing scorecard for this pack. |
| `--verbose` / `-v` | flag | `False` | Detailed simulation output. |

Fitter passthrough options (`--credibility-k`, `--min-exposure`, `--level-coverage-threshold`, `--separation-exposure-gate`) carry the same defaults and meanings as `planalign fit`.

`--holdout`, `--seeds`, and every threshold are recorded on the scorecard, with overrides flagged (FR-017).

## Behavior

1. Discover, validate, and hash snapshots. Reject on gaps, unreadable files, or fewer than 3.
2. Compute the split (`SnapshotSplit`). Reject an infeasible split before doing any work.
3. Fit a pack on `fit_years` **only**, via `FitOptions.only_years`.
4. Write the pack to `--output`.
5. Convert the boundary-year census to parquet in the workdir if needed.
6. For each seed, serially: write an effective config, run the simulation over `holdout_years` in an isolated database, extract predicted metrics.
7. Extract actual metrics from the held-out snapshots.
8. Score, render, and write `<pack>/backtest/scorecard.json` and `scorecard.md`.
9. Print a summary table and the artifact paths.

Progress is reported per seed and per simulated year (FR-033).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Scorecard produced. **Including a `fail` verdict** — a failing score is a result, not an error (Assumption 9). |
| `1` | Unexpected internal error. |
| `2` | Invalid invocation: bad option values, `--seeds` with `--seed-list`, unreadable directory. |
| `3` | Input rejected: too few snapshots, year gap, infeasible holdout, existing scorecard without `--force`. |
| `4` | A constituent simulation failed. No scorecard written. |

Exit code `3` is the "your data cannot support this" class, distinct from `2` ("you typed it wrong") — the same split `planalign calibrate` uses for its prerequisite guard.

## Required rejection messages (SC-010)

Each names the specific cause and the values involved. Wording may be refined; the named quantities are the contract.

| Condition | Message shape |
|---|---|
| Fewer than 3 snapshots | `Backtest needs at least 3 snapshots (2 to fit, 1 to hold out); found 2 in <dir>: 2022, 2023.` |
| Infeasible holdout | `A 2-year holdout of 3 snapshots leaves 1 year to fit, but fitting needs at least 2. Use --holdout 1 or supply a 4th snapshot.` |
| Holdout out of range | `--holdout must be 1 or 2; got 3. A longer holdout is not supported.` |
| Year gap | `Snapshot years must be consecutive; found a gap between 2021 and 2023.` (from the fitter) |
| Existing scorecard | `<pack>/backtest/scorecard.json already exists, scored on 2026-07-14. Pass --force to replace it.` |
| Simulation failure | `Backtest simulation failed for seed 43, year 2024. No scorecard was written. <underlying error>` |
| Seed count | `--seeds must be between 1 and 5; got 8.` |
| Duplicate seeds | `--seed-list contains duplicate seed 42; duplicate runs would narrow the reported spread without adding information.` |

## Console output

On success, a Rich table: one row per metric per held-out year, columns predicted / actual / abs error / % error / status, with the cumulative block separated. Not-observable metrics are listed after the scored ones with their reason. Footer: verdict summary, thresholds in effect, seed set, and artifact paths.

Single-seed runs print `no seed spread computed (1 seed)` rather than a zero-width range (FR-022).

## Guarantees

- Never opens `dbt/simulation.duckdb` (FR-006). Enforced by an integration test asserting the file's mtime and size are unchanged.
- Never mutates `SNAPSHOTS_DIR`.
- Never changes the pack's fingerprint (FR-028).
- Identical invocation on identical inputs produces a byte-identical `scorecard.json` (FR-008, SC-005).
