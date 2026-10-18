# Coverage and shard measurements

## PR feedback and merge policy

Every PR keeps lint, Studio validation, dependency audits, the complete fast
suite, and dbt validation. Fast tests and model validation start independently
of lint. New PR runs cancel obsolete runs for the same PR; post-merge, scheduled,
and manually dispatched runs remain independent so their evidence is retained.

`scripts/ci_policy.py` compares the PR base/head merge-base diff (including
deletions and both sides of renames). Only frontend files and an explicit set of
Markdown documentation paths may omit simulation checks. Backend, SQL, config,
dependency, test, CI, and unknown paths require multi-year invariants and the
edge-config matrix before `CI Gate` passes. Empty diffs select simulations;
missing Git history fails selection. This deliberately makes engine changes
slower than presentation changes while preserving the full fast suite for both.

The four integration shards and combined coverage still run on main/develop,
nightly, manual dispatch, and PRs carrying `full-ci`. Adding or removing a label
now triggers selection immediately. Use `full-ci` only for changes that need
integration-shard or coverage evidence before merge (integration tests, coverage
inventory, CI); otherwise rely on the post-merge `main` run. Apply it when
creating the PR: labeling later cancels the first run and reports a spurious
`CI Gate` failure. No coverage threshold or test is removed.

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
splitting or pruning tests. The fast suite warns above 450s and fails above its
540s wall-clock budget; see #928 for the runner-variance re-baseline.

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

The gate remains **60%**. The July 2026 estimate of 63% used an incomplete
denominator and is not the expanded baseline. Record the first complete run's
per-package counts and combined percentage before proposing any threshold change.
A synthetic smoke run proves inventory inclusion, not suite coverage. A fresh
four-shard CI run is required to establish the expanded suite baseline.

The validation job installs `-e .` directly, then prints and checks the effective
dbt-core/dbt-duckdb versions against `project.dependencies` in `pyproject.toml`.
It does not preinstall a separate engine version.

## Refresh timings using GitHub-hosted runners

Each successful test shard uploads `test-durations-N/.test_durations`.
`--store-durations --clean-durations` first reads the committed durations to
assign tests, then writes only that shard's observations. Without cleaning,
inherited observations would create duplicate tests and preserve stale entries.
The merge script rejects missing/failed shards, empty artifacts, duplicate test
IDs, and invalid timings. It records the source SHA, run URL, test count, and
actual test-step elapsed seconds separately from pytest's per-test durations.

After committing this workflow on an authorized branch:

```bash
gh workflow run ci.yml --ref <branch>
# Wait for all four test shards to succeed; record that run ID as BEFORE.
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
AFTER elapsed times to provenance. Review all four deltas and the maximum shard
time (the suite's critical path); do not claim improvement based only on summed
per-test estimates. A single pair has runner noise; repeat if the result is close.
Do not use timings from failed, interrupted, or partial shards as a baseline.

## Issue #874 measurement status

The checked-in timings remain unchanged until a representative complete run can
produce artifacts under the new workflow. The October 15 run
[38803893150](https://github.com/crzyc98/planwise_navigator/actions/runs/38803893150)
at `e20a92836c2d08827369b63cb39dc18536da1999` failed shard 1 and has no timing
artifacts; it cannot supply that baseline. The 49/65/49/63-minute figures in the
workflow header are historical August measurements, not evidence of a current
regression. Expanded suite coverage and actual before/after shard measurements
remain pending the two complete runs above.
