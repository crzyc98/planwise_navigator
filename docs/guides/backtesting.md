# Backtesting fitted parameter packs

`planalign backtest` holds out the latest one or two annual census snapshots,
fits only on the earlier history, simulates the held-out period in isolated
databases, and writes a reviewable scorecard beside the fitted parameter pack.

```bash
source .venv/bin/activate
planalign backtest data/history \
  --output var/param_packs/client-backtest
```

With snapshots for 2021–2024, the default command fits 2021–2023 and scores
2024 over seeds 42, 43, and 44. Use `--holdout 2` for a two-year test,
`--seed-list 17,29,43` for an explicit seed set, and `--force` only when prior
scorecard evidence is intentionally being replaced.

## Reading the scorecard

Every metric reports the lower-median prediction across seeds, actual value,
signed absolute and percentage errors, applied threshold, and status. For an
even seed count, the lower of the two middle values is used so count metrics
stay integral. A positive error means over-prediction; a negative error means
under-prediction.

The default warn/fail bounds are:

| Family | Warn | Fail |
|---|---:|---:|
| Headcount | 2% | 4% |
| Compensation | 3% | 6% |
| Flows | 10% | 20% |
| Plan | 5% | 10% |

Values below the warn boundary pass, values from warn up to (but excluding)
fail warn, and values at or above fail fail. A zero actual has an undefined
percentage status but retains its signed absolute error. Missing source fields
are listed as not observable and do not affect the overall verdict.

Stock and rate metrics use the final held-out year for the cumulative row.
Flow metrics — hires, terminations, and promotions — sum the
held-out years. Seed min–max is descriptive simulation variation, not a
confidence interval.

Two definitions are worth knowing, because both sides must measure the same
thing or the error reports a definitional gap rather than a modelling one:

- **Employer-match cost is always reported as not observable.** A census records
  deferral rates, not match transactions, so any actual figure would come from
  assuming a match formula the plan may not use. Scored against the real match
  engine, a "50% of first 6%" proxy ran +24% — an artefact of the assumption.
  Reporting nothing beats reporting a number that looks like evidence.
- **By-level headcount is band-derived from compensation on both sides**, even
  when the census carries an authoritative `level_id`. `int_baseline_workforce`
  assigns the simulator's level by matching compensation ranges and never reads
  a census level column; scoring census levels against simulated ones agreed on
  only 76% of employees. The scorecard records
  `level_basis: compensation_band` so a reader knows what by-level means.

**Terminations count the experienced cohort on both sides** — employees already
on the books entering the year. The actual side reads this off the cohort-linked
transitions, whose exposure is the population active at the prior year end, so
an employee hired and terminated inside the same year never enters it. The
predicted side excludes same-year hires to match.

## Artifacts, schema, and provenance

The command writes:

- `<pack>/backtest/scorecard.md` for review;
- `<pack>/backtest/scorecard.json` for automation.

The machine contract is [scorecard.schema.json](../../specs/131-backtest-scorecard/contracts/scorecard.schema.json).
`schema_version` follows semantic versioning: incompatible field or meaning
changes increment the major version; backward-compatible additions increment
minor; documentation-only clarifications increment patch. Consumers should
reject unsupported major versions.

The JSON records source filenames and SHA-256 hashes, fit/holdout roles, seeds,
threshold overrides, pack identity, and a scorecard fingerprint. A later
`planalign simulate --params <pack>` records a compact score reference in
`run_metadata.backtest_score_ref` only when the scorecard still matches the
pack's current fitted fingerprint.

## Worked example

The [reference scorecard](../examples/backtest_reference/scorecard.md) backtests
a realistically anonymized 1,500-employee history (synthetic, generated
independently of the simulator, no client data). It is worth reading closely,
because it **fails** — and the shape of the failure is the point.

Totals and flows are healthy: headcount is off 0.24%, total compensation 0.08%,
promotions 2.0%, terminations 9.2%. What fails is the *composition*:

| Metric | Error | What it means |
|---|---:|---|
| `headcount.by_age_band.< 25` | +120% | The simulator hires far younger than this employer did |
| `headcount.by_age_band.25-34` | +27% | Same cause |
| `headcount.by_age_band.55-64` | -13% | Same cause, other end |
| `plan.participation_rate` | +24% | Auto-enrollment is on in config; this history shows voluntary enrollment only |

Neither is a modelling error in the fitted parameters. Both are **configuration
inputs the fitter does not fit** — `new_hire_age_distribution` and the
auto-enrollment policy — left at their defaults while the client's history says
something different. The fix is to configure them to match the client, then
re-run. Surfacing exactly this is what a backtest is for: the headline numbers
looked fine, and the model was still wrong about who those people are.

## Harness self-test

The self-test backtests history the **simulator itself produced**
(`tests/fixtures/backtest_history.py`), rather than analytically generated
history. That distinction is load-bearing: when the history comes from the
simulator under the same base config the backtest will run, every input the
fitter does not fit agrees on both sides by construction, so any residual error
is attributable to the harness. Scored against analytic history instead, a
harness bug, a fitter limitation, and plain configuration divergence all look
identical — as the worked example above shows.

Under that fixture, headcount, every age band, every tenure band, hires, and
terminations come out **exactly** equal, and compensation, participation, and
deferral land inside 0.5% (`SELF_TEST_TOLERANCE`). A mutation assertion proves
the check fails when the comparison logic is broken, rather than certifying
unconditionally.

Two documented carve-outs:

- **`headcount.by_level.*`** gets a 5% allowance (`SELF_TEST_BUCKET_TOLERANCE`).
  Level buckets compensation, and compensation itself carries the ~0.5% error
  above, so employees near a band boundary flip and a continuous error emerges
  as a discrete one. Age and tenure bands need no allowance because they bucket
  integers both sides compute identically.
- **`flows.promotions`** is excluded from the self-test only. The simulator's
  level is seeded by compensation banding, so in simulator-exported history an
  ordinary raise crossing a band boundary is indistinguishable from a promotion
  (measured: 221 inferred against 104 actual promotion events). A real census
  with persistent job levels has no such ambiguity — the reference example above
  scores promotions at -2.0% — so the metric remains scored; it simply cannot be
  certified by this fixture.

## Isolation and caveats

Each seed uses its own DuckDB file beneath `var/backtests/` and its own dbt
artifact directory. The shared `dbt/simulation.duckdb` is never opened. Seed
runs are serial to cap peak memory at one simulation. Databases are deleted
after extraction unless `--keep-databases` is supplied.

A good one- or two-year backtest is a sanity check, not a guarantee about a
long-range projection. The seed spread is not statistical inference, and the
scorecard intentionally does not auto-tune a weak model.

Common rejections are explicit: at least three consecutive snapshots are
required; a two-year holdout needs four; only one or two held-out years and one
to five unique seeds are supported; existing scorecards require `--force`.
