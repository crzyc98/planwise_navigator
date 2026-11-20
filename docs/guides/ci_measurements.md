# Coverage and shard measurements

## PR feedback and merge policy

Every PR keeps lint, Studio validation, dependency audits, the complete fast
suite, and dbt validation. Fast tests and model validation start independently
of lint. New PR runs cancel obsolete runs for the same PR; post-merge, scheduled,
and manually dispatched runs remain independent so their evidence is retained.

`scripts/ci_policy.py` keeps simulations off ordinary PRs. The simulation suites,
integration shards and coverage run on every push to `main`, nightly, on
dispatch, or with the `full-ci` label. A failed push or nightly run on `main`
opens one `CI failed on main` issue, and later failures comment on it, so a
regression that reaches `main` is reported within the hour.

Each simulation test file (marked `multi_year_invariants` or
`edge_config_matrix`) gets its own runner in the `simulation-suites` job, so the
job takes as long as its slowest file, about 11 minutes. `ci_policy.py` finds the
files by searching for the marker, and `tests/conftest.py` fails collection if
that search and pytest's own markers disagree. Run serially, the suites took
23 minutes on a good runner and timed out at 30 on a slow one, which left `main`
red through 2026-11-19. If one file approaches the 20-minute limit, split the
file. Don't raise the limit.

The eight integration shards and combined coverage still run on main/develop,
nightly, manual dispatch, and PRs carrying `full-ci`. Adding or removing a label
now triggers selection immediately. Use `full-ci` only for changes that need
integration-shard or coverage evidence before merge (integration tests, coverage
inventory, CI); otherwise rely on the post-merge `main` run. Adding the label,
even at creation, fires a `labeled` event that starts a second run and cancels
the first; ignore that cancelled run's `CI Gate` failure. No coverage threshold or test is removed.

`CI Gate` rejects failed/cancelled jobs, missing baseline checks, skipped selected
suites, and invalid selection outputs. Since 2026-10-18 (#891) **CI Gate** is a
required check in the "required CI checks" ruleset, alongside the five baseline
checks, so a PR cannot merge until its selected simulation suites pass. "Require
branches to be up to date" stays off: many parallel PRs would each need a rebase
and rerun, and the post-merge `main` run catches cross-PR interactions. Admins
keep bypass for emergencies; don't use it on PRs that change CI workflows.

The inspected PR run 38967045844 took about 7m48s, including 59s of lint before
the fast job could start and 6m24s in its pytest step. Removing that dependency
can save roughly a minute absent runner queueing; this is an estimate, not a
measured result of the new workflow. Measure the next hosted runs before further
splitting or pruning tests. The fast suite warns above 540s and never fails on
time, because runner speed swings it widely; see #928 and #1083.

Local policy validation (no simulation database is touched):

```bash
source .venv/bin/activate
DATABASE_PATH=/tmp/planalign-ci-policy-sentinel.duckdb pytest tests/unit/test_ci_policy.py -q
ruff check scripts/ci_policy.py tests/unit/test_ci_policy.py
black --check scripts/ci_policy.py tests/unit/test_ci_policy.py
```

## Coverage inventory

`pyproject.toml`'s `[tool.coverage.run].source` is the authoritative coverage
package list. Use bare `pytest --cov` locally and in CI; `--cov=package` overrides
that inventory. The combined CI report checks every shipped `.py` file, including
unexecuted modules, and prints covered/total statements for each package. Both
JSON and XML reports are retained even if the gate fails.

Complete four-shard run
[39954102337](https://github.com/crzyc98/planwise_navigator/actions/runs/39954102337)
measured **77.88%** combined coverage (35,288 statements, 7,804 missed) across all
nine packages:

| Package | Covered / statements | Modules |
| --- | ---: | ---: |
| planalign_api | 12,888 / 15,217 | 145 |
| planalign_backtest | 544 / 606 | 10 |
| planalign_cli | 1,165 / 2,997 | 26 |
| planalign_core | 610 / 731 | 10 |
| planalign_ensemble | 891 / 950 | 11 |
| planalign_evidence | 898 / 946 | 11 |
| planalign_fit | 1,659 / 1,778 | 19 |
| planalign_optimizer | 562 / 606 | 12 |
| planalign_orchestrator | 8,267 / 11,457 | 103 |

The gate is **75%**, ratcheted up after this run and the earlier complete run
39034496592 (2026-10-18, 77.54%). The July 2026 estimate of 63% used an incomplete
denominator and is not the expanded baseline. Investigate regressions rather than
lower the gate.

The validation job installs `-e .` directly, then prints and checks the effective
dbt-core/dbt-duckdb versions against `project.dependencies` in `pyproject.toml`.
It does not preinstall a separate engine version.

## Refresh timings using GitHub-hosted runners

The suite runs on eight shards, split by test file (`tests/file_shards.py`). To
change the count, edit the `shard` list and `--file-shard` in `ci.yml` together;
`tests/unit/test_ci_policy.py` checks they agree.

Whole files are assigned because the heavy files each share one simulation
fixture that takes about ten minutes to build. Until 2026-11-20 `pytest-split`
assigned single tests, which spread `test_backtest_harness.py` over six shards
and `test_employer_eligibility_tenure.py` over five, and each shard rebuilt the
fixture. In run 44653147239 the shards spent 294 minutes on work estimated at
about 137 when each file runs once. `pytest-split` also dropped any setup
longer than ten minutes from its timings, so rebalancing could not see the cost.

`.test_durations` holds seconds per test file, fixtures included. Each shard
reads the committed file to pick its files, then overwrites it with its own
measurements and uploads it as `test-durations-N/.test_durations`. The merge
script rejects missing or failed shards, empty artifacts, a file measured in
more than one shard, and invalid timings.

If one shard stays slow after a refresh, a single file is the floor. Split that
file, or move its simulation to a `multi_year_invariants` suite so it gets its
own runner. It records the source SHA, run URL, test count, and
actual test-step elapsed seconds separately from pytest's per-test durations.

After committing this workflow on an authorized branch:

```bash
gh workflow run ci.yml --ref <branch>
# Wait for every test shard to succeed; record that run ID as BEFORE.
gh run download "$BEFORE" --pattern 'test-durations-*' --dir var/ci-timings/before
source .venv/bin/activate
python scripts/refresh_test_durations.py --run "$BEFORE" --artifacts var/ci-timings/before
```

Review and commit `.test_durations` and `.test_durations.provenance.json`, then run
the full workflow again on that commit. Use the same runner class, Python and
dependency versions, test selection, shard count, and splitting algorithm; avoid
unrelated code changes between measurements.

```bash
gh workflow run ci.yml --ref <branch>
# Record the second complete run ID as AFTER.
python scripts/refresh_test_durations.py --run "$BEFORE" \
  --artifacts var/ci-timings/before --compare-run "$AFTER"
```

This retains the BEFORE observations as the assignment input and adds the actual
AFTER elapsed times to provenance. Review the total and the maximum shard
time (the suite's critical path); do not claim improvement based only on summed
per-test estimates. A single pair has runner noise; repeat if the result is close.
Do not use timings from failed, interrupted, or partial shards as a baseline.

## Eight-shard baseline (2026-11-20)

Run [44645859007](https://github.com/crzyc98/planwise_navigator/actions/runs/44645859007)
(PR #1259) was the first on eight shards, still assigned by the four-shard
timings. Test steps took 29 to 52 minutes (shard 4 was the critical path), down
from 60-70 on four shards. Rebalancing on that run's timings (run 44653147239)
left seven shards at 32-38 minutes and one at 50, which led to the switch to
file shards described above.

Run [44744381092](https://github.com/crzyc98/planwise_navigator/actions/runs/44744381092)
was the first split by file, on weights estimated from logs. Test steps took 11
to 29 minutes and the whole pipeline 30, against 70-85 before. The shards spent
153 minutes in total, down from 294. `.test_durations` now holds that run's
measured values (388 files); they predict seven shards near 19 minutes and one
at 23, which is `test_integrated_core_contributions.py` on its own.

## Issue #874 measurement status

The BEFORE baseline is nightly main run
[39954102337](https://github.com/crzyc98/planwise_navigator/actions/runs/39954102337)
at `04bff1eb`; all four test shards succeeded. Their "Run Python tests" steps
elapsed 71.8, 48.8, 63.9, and 42.5 minutes for shards 1–4 respectively. Shard 1
was the critical path (4,308 seconds). `.test_durations` was refreshed from this
run's four timing artifacts; `.test_durations.provenance.json` records the source
SHA, run URL, test count, and step elapsed seconds.

The AFTER run
[40013973725](https://github.com/crzyc98/planwise_navigator/actions/runs/40013973725)
used the refreshed timings (PR #981 head `c21324da`), and all four shards succeeded:

| Shard | BEFORE (min) | AFTER (min) | Delta |
| --- | ---: | ---: | ---: |
| 1 | 71.8 | 68.0 | -3.8 |
| 2 | 48.8 | 46.2 | -2.6 |
| 3 | 63.9 | 28.4 | -35.5 |
| 4 | 42.5 | 59.5 | +17.0 |

The critical path dropped by 3.8 minutes, from 71.8 to 68.0 (about 5%). Total shard
time fell from 227 to 202 minutes. The shards are still unbalanced: the slowest takes
2.4x as long as the fastest. Per-test durations sum to only about 153 minutes, so
roughly 50 minutes of shard time is fixture and setup cost that `least_duration`
cannot see. Better balancing would need to account for that cost, not just refresh
timings again. #874 closes on this measurement.
