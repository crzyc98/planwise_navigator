# Evidence — Feature 132

Committed artifacts for every step attempted. Per `FR-013`, the parity gate runs
locally rather than in CI, so its full output lives here for review instead of
being asserted by a green check.

## Files

| File | What it records |
|---|---|
| `reference-workload.md` | The pinned 60,040-row census and its digest (invariant RW-1) |
| `step-00-baseline.md` | Pre-change baseline, three repetitions |
| `step-1a-*.md` | Redundant start-year build removed — parity and measurement |
| `step-1b-record.md` | Hazard-cache merge — attempted, stop condition hit, reverted |
| `decision-log.md` | Consolidated outcome for every step, including the ones not attempted |

## Step record format

Each `step-NN-record.md` reports, per the Step Record entity in
[`../data-model.md`](../data-model.md):

- **Measurement table** — one row per repetition plus a median: command count,
  wall time, and the startup / execution / orchestration split
- **Prior median** — the state this step is measured against, *not* the original
  baseline (invariant SR-2)
- **Delta** and the step's **bar**
- **Parity** — pass/fail with a link to the step's parity artifact
- **Decision** — `keep`, `revert`, or `stop`, with reasoning

A reverted step still gets a full record (invariant SR-3). A revert is a
successful outcome of the gate, not a missing one, and the reasoning is the part
worth keeping.

## Parity artifact format

Each `step-NN-parity.md` reports one row per mart with counts in both
directions, the candidate-vs-rerun determinism pair, and the audit columns
excluded for that mart. Marts not built by this workload are reported `absent`
rather than silently skipped, so the compared set can be checked against the
runtime-enumerated set (invariant PR-2).

## Reproducing

See [`../quickstart.md`](../quickstart.md). Every run uses an isolated database
under `var/perf_profile/`; the shared `dbt/simulation.duckdb` is never built
into.
