# Quickstart: Running the Gate and the Measurement

**Feature**: 132-collapse-dbt-invocations

Everything below runs against **isolated databases under `var/`**. The shared `dbt/simulation.duckdb` is never built into by this work.

## 1. Generate the reference census (once per gate)

The 60,040-row census is not in the repository — it is scaled 8× from the 7,505-row source. Generate it **once** and reuse the same file for every run in a gate (research Finding 6):

```bash
source .venv/bin/activate
python -m scripts.perf_profile.make_large_census \
  --factor 8 \
  --out var/perf_profile/census_60k.parquet
```

Confirm it reports 60,040 rows with unique ids before proceeding.

## 2. Capture the baseline

Before touching any orchestration code, on the unmodified revision:

```bash
DATABASE_PATH=var/perf_profile/baseline.duckdb \
  planalign simulate 2025-2029 \
    --config var/perf_profile/studio_shape.yaml \
    --database var/perf_profile/baseline.duckdb
```

Read the finalized command schedule back out — this is the count `SC-006` is measured against, and it comes from the recorded metadata rather than from log scraping:

```bash
duckdb var/perf_profile/baseline.duckdb \
  "SELECT simulation_year, stage, COUNT(*) AS commands
     FROM run_execution_metadata
    GROUP BY 1,2 ORDER BY 1,2"
```

## 3. Run the fast schedule tests

These are the cheap half of the gate and **do** run in CI. They assert the shape in `contracts/command-schedule.md` without executing a simulation:

```bash
pytest -m fast tests/test_workflow_schedule.py -v
```

They must fail before a step is implemented and pass after — that is the step's red/green signal.

## 4. Run the parity gate (local, per step)

```bash
python scripts/parity_gate.py \
  --baseline var/perf_profile/baseline.duckdb \
  --candidate var/perf_profile/candidate.duckdb \
  --determinism var/perf_profile/candidate2.duckdb \
  --out specs/132-collapse-dbt-invocations/evidence/step-1a-parity.md
```

The driver enumerates marts via `dbt ls` rather than a hardcoded list, so a newly added mart is covered automatically. Any non-zero count in either direction fails the step.

**A failing gate means revert, not iterate.** Do not narrow the mart set or drop to 7.5k to get a pass — 7.5k parity is explicitly not evidence.

## 5. Measure (median of three)

```bash
python -m scripts.perf_profile.run_matrix \
  --census var/perf_profile/census_60k.parquet \
  --years 2025-2029 --repeat 3 \
  --out var/perf_profile/step-1a-timing.json
```

Record the median wall time and the startup / execution / orchestration split into the step record. Story 2's delta is measured **against the post-Story-1 state** (`SC-002`, invariant SR-2). Treat startup as a diagnostic residual, not as wholly removable cost; historical command-count cohorts are the authoritative basis for the bars.

## 6. Decide

| Condition | Action |
|---|---|
| Parity clean **and** delta ≥ the step's bar | `keep` — commit, including the evidence artifact |
| Parity clean, delta below bar | `revert` — the gain does not pay for the residual risk |
| Parity dirty | `revert` — no exceptions |

Write the outcome into the step record either way. A reverted step still needs its record — `SC-004` treats a documented revert as a successful outcome, not a missing one.

## Step order

1. **1a** — drop the redundant year-1 `int_baseline_workforce` build. Lowest risk; a deletion, not a regrouping.
2. **1b** — merge the hazard-cache pair. Watch `hazard_params_hash` and the newly-executing schema tests.
3. **2** — fold later-year setup into event generation. **Highest risk in the feature.** Do not start before 1a/1b are measured and merged.

Optional **1c** (union the seed load with staging, → 13 commands) is evaluated only if 1a and 1b together miss `SC-001`'s 3s bar.
