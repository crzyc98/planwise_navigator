# State Pipeline Redesign (Feature 122)

## Outcome

Feature 122 makes each managed simulation attempt immutable and isolated, publishes
the current-year event fact once, and replaces duplicate workforce replay with one
authoritative workforce accumulator. The public marts remain schema- and
content-identical to the frozen 60,040-employee, 2025–2029 A+B baseline.

The active pipeline is SQL/dbt only. This work does not restore the retired Polars
pipeline and does not broadly remove its inactive compatibility remnants.

## Run storage and read contract

Each API or Studio attempt receives a new directory and database under
`runs/<run_id>/`. A successful, readable attempt is atomically promoted through the
scenario's current-result pointer. Failed and cancelled attempt databases remain
associated with their terminal status for diagnosis and never replace the latest
success.

Scenario reads continue using the latest successful result while another attempt is
queued or running. The API exposes the split through `X-PlanAlign-Run-Warning`,
`X-PlanAlign-Result-Run-Id`, and `X-PlanAlign-Active-Run-Id`; Studio aggregates those
headers into one global in-progress banner. Corrupt pointers fail closed instead of
silently selecting another database. Legacy lookup is retained only for scenarios
that have never published a current-result pointer.

Measured read latency remained well inside the two-second requirement: idle p95 was
0.00361 seconds and active-run p95 was 0.00364 seconds.

## Before and after DAG

Before:

```text
event candidates
  -> fct_yearly_events (built in EVENT_GENERATION)
  -> legacy employee state + scratch workforce snapshot
  -> separate enrollment/deferral accumulators
  -> contributions/core/match replaying portions of workforce state
  -> fct_yearly_events rebuilt in STATE_ACCUMULATION
  -> fct_workforce_snapshot replaying workforce events again
```

After:

```text
EVENT_CANDIDATE nodes
  -> int_current_year_events
  -> fct_yearly_events                 [EVENT_PUBLICATION, once/year]
  -> int_workforce_state_accumulator   [DOMAIN_STATE]
  -> enrollment + deferral state       [separate DOMAIN_STATE owners]
  -> eligibility/contribution/core/match calculations
  -> fct_employer_match_events
  -> fct_workforce_snapshot            [SNAPSHOT_PUBLICATION, composition]
```

The compiled manifest enforces mutually exclusive ownership, complete event-candidate
coverage, dependency closure, declared audit sinks, strict prior-year projection
boundaries, and no current-year event-fact feedback. Normal and calibration workflows
share those contracts.

## Schedule

STATE_ACCUMULATION now runs as one dependency-closed dbt command per simulation year,
with no state-stage `--full-refresh`. The five-year reference run changed from three
state commands per year to one. The complete observed schedule changed from 30 to 20
dbt invocations and from 214 to 204 node executions.

The 20-invocation total is descriptive evidence, not a test target. Contracts assert
the architectural properties—one state command per year, no state full refresh, and
exactly-once publication—so future legitimate changes to other stages do not create
count-forcing failures.

## Warm performance matrix

All values are medians of three warm runs for the frozen baseline and candidate. Peak
RSS covers the orchestrator process tree. The resource gate required candidate median
RSS to remain at or below 110% of the matching baseline.

| Workload | Revision | Wall | CPU | dbt wall | Model execute | Residue | Peak RSS | Invocations / nodes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Reference | baseline | 119.59s | 140.28s | 105.13s | 20.81s | 14.60s | 1214.81 MiB | 30 / 214 |
| Reference | candidate | 100.52s | 112.15s | 81.67s | 16.98s | 18.72s | 1046.62 MiB | 20 / 204 |
| Studio | baseline | 119.58s | 137.59s | 104.58s | 20.00s | 14.71s | 1260.12 MiB | 30 / 214 |
| Studio | candidate | 100.10s | 111.17s | 82.43s | 16.67s | 17.44s | 1026.17 MiB | 20 / 204 |

Candidate peak RSS was 86.2% of baseline for the reference workload and 81.4% for
Studio. Median wall time was 15.9% and 16.3% lower, respectively. Wall-time improvement
is useful evidence but was not a correctness gate.

## Compatibility and proof

- Every built mart matched the frozen baseline in column name/order/type/nullability,
  duplicate-preserving content, grouped event counts, deterministic IDs/sequences,
  and duplicate multiplicity.
- Feature 107 enrollment reconstruction, Feature 112 post-termination integrity,
  stale-rerun cleanup, determinism, calibration, injected failure attribution,
  cancellation, and partial failed-output retention remained green.
- The removed `int_employee_state_by_year` and
  `int_workforce_snapshot_optimized` relations have no production manifest or workflow
  consumers.
- Behavioral validation used newly allocated isolated databases. The shared development
  database and pre-existing run/archive signatures remained unchanged.

Reproducible, PII-safe gate summaries are indexed in
`specs/122-state-pipeline-redesign/phase-gates.md`; detailed databases and profiler
samples remain ignored runtime artifacts.
