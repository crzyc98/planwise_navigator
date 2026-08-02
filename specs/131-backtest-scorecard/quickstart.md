# Quickstart: Backtest Scorecard

How an analyst uses `planalign backtest`, and what the output means.

## Prerequisites

- At least **3** consecutive annual census snapshots in one directory (`.parquet` or `.csv`), named so the year is unambiguous (`census_2021.parquet`) or carrying a `snapshot_year` column.
- The same columns `planalign fit` requires: `employee_id`, `employee_birth_date`, `employee_hire_date`, `employee_gross_compensation`. Optional columns (`employee_termination_date`, `active`, `level_id`, `employee_deferral_rate`, `employee_enrollment_date`) each unlock additional scored metrics.

## Run a backtest

```bash
source .venv/bin/activate

planalign backtest data/history/ --output var/param_packs/acme-backtest
```

With 4 snapshots (2021–2024) and the default 1-year holdout, this:

1. fits a parameter pack on **2021–2023 only**,
2. starts a simulation from the 2023 census,
3. simulates 2024 three times (seeds 42, 43, 44) in three isolated databases,
4. scores the predictions against the actual 2024 census,
5. writes `var/param_packs/acme-backtest/backtest/scorecard.md` and `scorecard.json`.

Expect roughly three single-year simulations' worth of runtime. Progress is reported per seed and year.

### Common variations

```bash
# Hold out two years — a harder test, needs at least 4 snapshots
planalign backtest data/history/ --holdout 2

# Five seeds for a wider spread; one seed for a fast smoke check
planalign backtest data/history/ --seeds 5
planalign backtest data/history/ --seeds 1

# Tighten the compensation threshold to 2% warn / 4% fail
planalign backtest data/history/ --threshold-compensation 0.02,0.04

# Keep the per-seed databases to inspect predictions yourself
planalign backtest data/history/ --keep-databases
```

## Read the scorecard

```text
Backtest scorecard — pack acme-backtest
Fitted 2021-2023 · held out 2024 · seeds 42,43,44

Year 2024
  metric                        predicted     actual     abs err    % err   status
  headcount.total                   4,812      4,790         +22    +0.5%   pass
  headcount.by_level.1              1,905      1,868         +37    +2.0%   warn
  compensation.average            118,430    121,006      -2,576    -2.1%   pass
  flows.terminations                  412        447         -35    -7.8%   pass
  flows.hires                         434        421         +13    +3.1%   pass
  flows.promotions                    188        231         -43   -18.6%   warn
  plan.participation_rate           0.681      0.702      -0.021    -3.0%   pass

Not observable
  plan.employer_match_cost   — snapshots carry no employee_deferral_rate column

Seed spread (3 seeds)
  headcount.total          4,798 – 4,829   actual inside
  flows.promotions            181 – 195    actual outside by +36

Verdict: WARN — 5 pass, 2 warn, 0 fail, 1 not observable
Thresholds: headcount 2%/4% · compensation 3%/6% · flows 10%/20% · plan 5%/10%
```

### What the columns mean

- **predicted** — the median across seeds for that metric, not a single run.
- **abs err / % err** — signed, `predicted − actual`. Direction matters: consistently negative compensation error means the model under-pays.
- **status** — against the threshold printed in the footer. `warn` is a near-miss, `fail` a real one.
- **not observable** — the census lacks the column that metric needs. It is listed rather than dropped, so you can see what the data could not tell you.
- **seed spread** — where the actual sits relative to the range across seeds. "Actual outside" means the miss is larger than random variation explains, which is the interesting signal.

In the example above, promotions are the finding: the model is off by 19% *and* the actual falls outside the seed spread. Headcount and compensation are within tolerance, so the projection's headline numbers are defensible; the promotion mix is not.

### Verdict and exit code

The verdict summarizes the worst observable status. **A `fail` verdict still exits 0** — a failing score is a result, not a command error. The scorecard is evidence for you, not a gate.

## Use the pack, carrying the score

```bash
planalign simulate 2025-2029 \
  --params var/param_packs/acme-backtest \
  --database var/runs/acme.duckdb
```

The run records the pack **and** its backtest score. To audit later:

```bash
duckdb var/runs/acme.duckdb "
  SELECT run_timestamp, param_pack_id, backtest_score_ref
  FROM run_metadata ORDER BY run_timestamp DESC LIMIT 5"
```

That gives the full chain: run → pack → scorecard → source census content hashes.

## Isolation

Backtests never touch `dbt/simulation.duckdb`. Per-seed databases live under `var/backtests/<timestamp>-<pack_id>/` and are deleted after scoring unless you pass `--keep-databases`. Your snapshot directory is read-only input.

## Troubleshooting

| Message | What to do |
|---|---|
| `Backtest needs at least 3 snapshots…` | Supply another year, or use `planalign fit` alone (which needs only 2) without a backtest. |
| `A 2-year holdout of 3 snapshots leaves 1 year to fit…` | Use `--holdout 1`, or add a 4th snapshot. |
| `Snapshot years must be consecutive; found a gap…` | The cohort-linked diff assumes a one-year step. Fill the gap or backtest the consecutive run only. |
| `…already exists, scored on <date>. Pass --force to replace it.` | Prior evidence is not discarded silently. Pass `--force` if you mean to replace it. |
| `Backtest simulation failed for seed 43, year 2024.` | A constituent simulation failed; the underlying error follows. No scorecard is written from a partial run. |
| Everything scores as `not observable` | The census carries only the four required columns. Add optional columns to unlock plan and flow metrics. |

## Caveats worth stating to a client

- **A good backtest is not a guarantee.** Reproducing 2024 says the fitted parameters describe the recent past. It does not certify a 2029 projection.
- **One or two held-out years is a small sample.** Treat the scorecard as a sanity check that would have caught a badly wrong model, not as a precision estimate.
- **The seed spread is not a confidence interval.** It shows simulation variability at a handful of seeds, nothing more. Statistical inference is deliberately out of scope.
