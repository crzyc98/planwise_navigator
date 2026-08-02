# Decision Log — Feature 132

Consolidated outcome for every step, including the ones deliberately not
attempted. Satisfies `SC-004`: every kept step cleared its bar, and every
reverted or abandoned step has a recorded measurement and an explicit decision.

## Outcome

| Step | Change | Commands | Delta | Bar | Parity | Decision |
|---|---|---:|---:|---:|---|---|
| 00 | Baseline capture | 20 | — | — | — | baseline = **103.576s** |
| 1a | Remove redundant start-year `int_baseline_workforce` build | 20 → 19 | **−3.787s** | 3.0s | PASS | **KEEP** |
| 1b | Merge hazard-cache `run` + `build` | 19 → 18 | not measured | 3.0s | not reached | **REVERT** — stop condition |
| 1c | Union seed load with staging | — | — | — | — | **NOT ATTEMPTED** |
| 2 | Fold later-year setup into event generation | 18 → 14 | — | 6.0s | — | **STOP** |

**Shipped**: 20 → 19 commands, 103.576s → **99.789s** (−3.7%, median of three),
all-marts parity clean at 60k over five years.

## Step 1a — KEEP

Deleted a build whose output was provably discarded: INITIALIZATION built
`int_baseline_workforce` incrementally, then FOUNDATION `--full-refresh`ed the
same model moments later. `StageValidator` dispatches no INITIALIZATION
validation, so nothing was lost by emptying the stage.

Cleared its bar on timing alone (3.787s vs 3.0s), and would have been worth
keeping regardless — removing discarded work simplifies the path independent of
the clock.

## Step 1b — REVERT

Hit its predeclared stop condition (T024) on the first 60k run: switching
`int_effective_parameters` from `run` to `build` activates a schema test that
errors with `VARCHAR >= INTEGER`.

The test was already broken and had **never executed**, because the orchestrator
only ever `run`s that model. Step 1b surfaced a dormant coverage gap rather than
causing a regression. Filed as **#533**; not fixed here, because deciding what
`job_level` should assert is a correctness investigation on a critical
foundation model, and folding it into an invocation-count change would destroy
this diff's reviewability as behavior-preserving.

Full detail: [step-1b-record.md](step-1b-record.md).

## Steps 1c and 2 — STOP

Stopped on economics, established during T011 reconciliation.

### Correction: the baseline gap was a census mismatch, not a bad number

**This was an error in this feature's own method, recorded here rather than
quietly fixed.**

T011 flagged the fresh 103.576s baseline as a 13.2% disagreement with #519's
91.5s and stopped the work. The stop was correct; the diagnosis was not.

`quickstart.md` specified generating the reference census with
`scripts/perf_profile/make_large_census.py --factor 8`. But **every prior 60k
measurement used the workspace census**
(`workspaces/1497b19c-.../data/census.parquet`) — 49 recorded runs, versus 9
using the scaled file, all 9 from this feature:

| Census | Runs |
|---|---:|
| workspace | 49 |
| synthetic 8× scaled | 9 (all feature 132) |
| `census_large.parquet` | 13 |

The scaled census is eight copies of the same 7,505 people. Same row count,
different distributions, therefore different event volumes and different SQL
time. **103.576s and 91.5s were never measuring the same workload**, so the
"material disagreement" T011 detected was manufactured by this feature's own
census choice.

#519's 91.5s traces to the #516 fix session (2026-07-30, workspace census), which
recorded 117.7s → 91.5s at 28 → 20 invocations. It is a real measurement, not a
fabrication. It remains below the workspace-census 20-invocation cohort
(~97.1–106.8s across ~15 runs), so it is optimistic relative to later runs — but
that is a separate question from the one T011 raised.

**What survives**: every conclusion below. Marginal cost is derived entirely
within the workspace-census cohort, and step 1a's −3.787s is self-baselined —
the same scaled census on both sides of the A/B, per `FR-010`. The census
mismatch invalidates the *comparison to 91.5s*, nothing else.

**What to fix before the next measurement**: use the workspace census, so
results join the existing cohort instead of starting a new one.

### Marginal cost is ~1.5–1.75s per command, not 2–4s

Two natural experiments already on disk:

- 38 → 30 (8 commands removed): 131.9 → 120.2 = **1.46s/command**
- 30 → 20 (10 commands removed): 120.2 → 102.7 = **1.75s/command**

The "43.2s of startup across 20 commands" framing implies 2.16s/command, and
dividing this run's measured 66.8s startup by 20 implies 3.34s — but neither
figure is recoverable by removing a command. Both metrics compute startup as dbt
wall minus summed model execution, which sweeps in parse, adapter init, and
catalog work that does not vanish when commands merge. The cohort deltas are the
trustworthy number because they measure actual invocation-count changes.

Step 1a's 3.787s beat that estimate, which is consistent with it removing an
above-average command (a full model build, not just process overhead).

### Consequence

Step 2 removes four commands: **~6–7s**, for the highest-risk change in the
feature, on the exact stage where Feature 121's Tier C broke. Tier C also
passed at 7.5k and failed at 60k, so the risk is not theoretical and cannot be
cheaply de-risked.

Six seconds does not justify that exposure plus three more 60k gate runs. The
spec's stop condition — *"stop the sequence entirely once the remaining ceiling
no longer justifies the correctness risk"* — is met.

Step 1c (~1.5s, and it newly runs seed and staging tests, inviting the same
class of surprise 1b hit) is not worth attempting for the same reason.

## What this feature actually delivered

The seconds are the smaller half.

1. **#519's premise is corrected.** Startup is not a 43.2s pool waiting to be
   drained; the recoverable marginal cost is ~1.5–1.75s per command, measured
   across the 38 → 30 → 20 cohorts. The remaining invocation-collapse ceiling is
   **~9s, not ~30s**.
2. **A measurement-method trap is documented**: the reference census must be
   the workspace census, not a synthetic scale-up, or results cannot be compared
   to any prior run. This feature tripped it and nearly drew the wrong
   conclusion from it.
3. **A dormant test on a critical foundation model** is filed as #533.
4. **A genuinely redundant build is gone**, worth 3.787s with clean parity.
5. **A reusable all-marts parity driver** (`scripts/parity_gate.py`) now exists,
   enumerating marts at runtime rather than hardcoding them.

## Recommended next target

Not further invocation collapse. The orchestrator Python — 16.1s in #519's
split, 17.2s measured here, and untouched by this feature — is now the larger
addressable block. That is **#521**.

## Test-suite note

The full fast suite passes: **2107 passed, 0 failed**.

One existing test needed updating. `tests/unit/test_tier_b_stage_merge.py::test_start_year_is_left_split` asserted
`init.models == [MODEL_INT_BASELINE_WORKFORCE]` — Feature 121 pinning its own
*scope boundary* ("Tier B left year 1 alone"), which step 1a deliberately moves.
The substantive assertions were kept and one was added: FOUNDATION must still
contain `int_baseline_workforce` **exactly once**. The invariant is stronger
after the change than before, because the model is now built once rather than
twice.

Note for future work: `tests/unit/orchestrator/test_*_graph_contract.py` and
`test_pipeline_stage_ownership.py` shell out to the `dbt` executable and fail
with `dbt executable is required for graph-contract tests` if pytest is invoked
without `.venv/bin` on `PATH`. Run them as `source .venv/bin/activate && pytest`
(or with `PATH="$PWD/.venv/bin:$PATH"`), not as a bare `.venv/bin/python -m
pytest`. Eleven spurious failures in this feature's first full-suite run traced
to exactly that, and they are easy to mistake for a broken `main`.
