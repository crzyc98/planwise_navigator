# Quickstart — Promotion Fit Bias

**Feature**: 130-promotion-fit-bias | **Branch**: `130-promotion-fit-bias`

How to reproduce the defect, grade the fix, and verify the whole feature.

---

## Reproduce the bug first

Everything in this feature is judged against one number. Get it on the board before changing anything.

```bash
source .venv/bin/activate
pytest tests/test_parameter_fitting.py::TestRoundTrip::test_promotion_rate_recovered -v
```

That passes today, because the fixture supplies `level_id`. The defect only appears when the column is absent. A scratch script that strips it:

```python
# /private/tmp/claude-501/.../scratchpad/repro_511.py
import csv, pathlib
from planalign_fit import FitOptions, fit_parameter_pack
from tests.fixtures.synthetic_census import generate_history

work = pathlib.Path("/tmp/fit511"); work.mkdir(exist_ok=True)
history = generate_history(work / "snapshots", headcount=9_000, years=3)

for path in history.paths:                     # drop level_id, keep everything else
    rows = list(csv.DictReader(path.open()))
    fields = [f for f in rows[0] if f != "level_id"]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows({k: r[k] for k in fields} for r in rows)

run = fit_parameter_pack(history.directory, FitOptions(credibility_k=25.0))
print("truth   ", history.truth.promotion)                        # 0.06
print("observed", run.result.promotion.observed_overall_rate)     # ~0.168 before the fix
```

**Record the number you actually get.** The 16.8% in the issue is the reference; confirm it on this machine before trusting any improvement.

---

## The prerequisite nobody expects

`tests/fixtures/synthetic_census.py:144` gives every non-promoted survivor exactly `merit + cola` and every promoted one exactly `promotion_raise`. Zero variance — two point masses.

A mixture estimator would separate those perfectly and tell you nothing, and `sigma → 0` is a division by zero in the separation statistic. **Add raise dispersion to the fixture before writing the estimator** (research.md R-7). Until that lands, no test in this feature grades anything.

Sanity check that dispersion is real:

```python
import statistics
growth = [...]  # per-employee YoY growth from two snapshots
print(statistics.stdev(growth))   # must be > 0
```

---

## Grade the fix

```bash
# The two P1 outcomes
pytest tests/test_parameter_fitting.py::TestRoundTrip -v

# The estimator in isolation — fast, no census, no DuckDB
pytest tests/test_promotion_mixture.py -v

# Full fitter suite
pytest tests/test_parameter_fitting.py -v

# Fast suite must stay under 10s (Constitution III)
time pytest -m fast
```

Targets, from the spec's success criteria:

| Check | Target | SC |
|---|---|---|
| Promotion rate, no `level_id` | within 1.5pp of 0.06 | SC-001 |
| Merit per level, no `level_id` | within 1pp of truth | SC-002 |
| Inseparable population | reports `not_fitted`, never a rate | SC-003 |
| Partial separation | per-level verdicts match truth | SC-003a |
| With `level_id` | unchanged from `main` | SC-005 |

---

## Verify determinism

The pack fingerprint is a content hash, so a nondeterministic estimator silently destroys provenance. This is the check most likely to be skipped and most expensive to miss.

```bash
planalign fit /tmp/fit511/snapshots -o /tmp/pack-a
planalign fit /tmp/fit511/snapshots -o /tmp/pack-b
diff -r /tmp/pack-a /tmp/pack-b     # expect: only fit_date differs in manifest.json
```

Fingerprints must match exactly. If they drift, EM picked up an ordering or floating-point dependence — find it rather than widening a tolerance.

---

## Verify the clean path did not move

SC-005 is a regression guarantee, and the easiest thing to break.

```bash
git stash                                    # or check out main in a worktree
planalign fit /tmp/fit-with-levels -o /tmp/pack-main
git stash pop
planalign fit /tmp/fit-with-levels -o /tmp/pack-feature

diff /tmp/pack-main/seeds/config_promotion_hazard_base.csv \
     /tmp/pack-feature/seeds/config_promotion_hazard_base.csv
```

Expect **no difference**. With 0/1 weights the weighted paths reduce to the unweighted ones exactly (data-model.md, "Clean-path parity") — this is arithmetic identity, not a tolerance, so any diff at all is a bug.

---

## Verify a defaulted pack still runs

FR-009: a pack whose promotion hazard could not be fitted must still be a usable pack.

```bash
planalign fit /tmp/inseparable-census -o /tmp/pack-nofit
grep promotion_basis /tmp/pack-nofit/manifest.json          # "not_fitted"
ls /tmp/pack-nofit/seeds/config_promotion_hazard_*.csv      # all three present

planalign simulate 2025-2027 --params /tmp/pack-nofit --database /tmp/iso.duckdb
duckdb /tmp/iso.duckdb "SELECT param_pack_id FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1"
```

Note the isolated `--database` path. Per `CLAUDE.md` §8, never build into `dbt/simulation.duckdb` to check a change. The fitter itself never opens a simulation database at all (`runner.py:66` uses in-memory DuckDB) — only this last verification step runs a simulation, and it uses its own file.

---

## Read the report

Half the requirements are about what the analyst is told. Read it, don't just assert on it.

```bash
cat /tmp/pack-nofit/fit_report.md
```

Confirm by eye:

- A "Promotion basis" row in the summary, on every path.
- The string `upper bound` appears **nowhere** (FR-012).
- The merit section no longer claims promotions were excluded (FR-008).
- On `estimated`, a per-level verdict table with exposure, separation distance, and BIC gain.
- On `not_fitted`, promotion in "Not fitted — defaults retained" with a reason naming the exposure gate.

---

## Scope reminder

This feature touches no dbt model, no SQL under `dbt/`, and no simulation database. If a change starts reaching into `dbt/`, it has left the plan.
