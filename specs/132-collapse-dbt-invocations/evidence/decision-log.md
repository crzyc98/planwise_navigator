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

### The baseline was a phantom

Issue #519 stated 91.5s. Across **43 recorded 60k runs** in `var/perf_profile/`,
none is close:

| Invocations | n | Median | Range |
|---|---:|---:|---|
| 38 (pre-#478) | 6 | 131.9s | 129.9–134.1 |
| 30 (post-#478) | 17 | 120.2s | 116.3–127.9 |
| **20 (current)** | **18** | **102.7s** | **97.1–183.7** |

The fresh baseline of 103.576s sits mid-band. The issue's own components also
fail to reconcile: 27.7 + 43.2 + 16.1 = **87.0s**, not the 91.5s stated.

This is the same defect pattern as #478's "62 invocations", which turned out to
be 38.

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
   drained; the recoverable marginal cost is ~1.5–1.75s per command. The
   remaining invocation-collapse ceiling is **~9s, not ~30s**.
2. **A phantom baseline is retired**, and the real one (102.7s across 18 runs)
   is recorded for whoever measures next.
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
