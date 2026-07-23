# Contract: Normalized State Pipeline DAG

## Target dependency graph

```text
prior canonical workforce rows
          |
          v
workforce_state_projection (strictly prior-year, disposable)
          |
          v
foundation + active SQL event candidates
          |
          v
int_current_year_events
          |
          v
fct_yearly_events (one publication/year)
          |
          +----------------------+----------------------+
          v                      v                      v
workforce accumulator    enrollment accumulator   deferral accumulator
          |                      |                      |
          +----------------------+----------------------+
                                 v
                      eligibility / contributions
                                 |
                                 v
                      employer core / match
                         |               |
                         v               v
             fct_employer_match_events  fct_workforce_snapshot
                                         (one publication/year)
```

## Ownership classes

Every production dbt model selected by the yearly pipeline has exactly one logical ownership class:

| Ownership | Definition |
|---|---|
| `EVENT_CANDIDATE` | Produces current-year proposed events; cannot depend on current-year published events or current-year accumulators. |
| `EVENT_PUBLICATION` | Assembles/publishes the immutable yearly event set. |
| `DOMAIN_STATE` | Accumulates workforce, enrollment, or deferral state from prior state plus published events. |
| `BENEFIT_CALCULATION` | Computes eligibility, contributions, core, or match from authoritative domain state. |
| `SNAPSHOT_PUBLICATION` | Publishes composed point-in-time/audit facts. |

Folder inheritance and model configuration must not leave contribution or match nodes tagged as event candidates. The event executor uses the ownership selection without a manual exclusion list.

## Temporal rules

- Current-year ordering is expressed through `ref`/`source` edges.
- An accumulator may read `{{ this }}` only for a strictly earlier year.
- An orchestrator-built projection must document its source, be reconstructible, and expose only strictly earlier years.
- Current-year event candidates cannot read `fct_yearly_events`, `fct_workforce_snapshot`, or current-year domain state.
- Dynamic relation lookup cannot be used solely to hide a manifest cycle.

## Publication rules

- `int_current_year_events` covers the exact complete candidate ancestry for the active SQL pipeline.
- `fct_yearly_events` executes once per scenario/plan/year and is absent from STATE_ACCUMULATION.
- `fct_workforce_snapshot` executes once per scenario/plan/year and does not replay workforce events.
- `fct_employer_match_events` is an explicitly documented audit/publication sink if it remains terminal.
- Public schemas, IDs, sequence, order semantics, and duplicate multiplicities are unchanged.

## STATE_ACCUMULATION selection

After all migration gates pass, the state stage has one dbt command per year, no command-level `--full-refresh`, and a dependency-closed selection containing domain state, benefit calculations, and snapshot publications. Event publication completes before that command. Failure metadata must still identify the failing model, stage, and year from dbt results.

## Required graph-contract assertions

The compiled production-SQL manifest plus effective workflow must prove:

1. No event candidate has a current-year event/snapshot fact in its transitive ancestors.
2. The candidate set upstream of `int_current_year_events` is exactly the checked expected set.
3. Ownership tags are mutually exclusive and require no executor manual excludes.
4. `fct_yearly_events` is absent from state selection and each publication node executes exactly once per effective year, using `run_results.json` evidence.
5. Every state-stage dependency is already published or inside the same selection.
6. STATE_ACCUMULATION records one command and no full-refresh flag.
7. Temporal reads use only accumulator self-reference or checked orchestrator projection sources.
8. The workforce accumulator has the four-column key, no benefit fields, no hard-coded scope, correct first-year behavior, and an N-1-only self-read.
9. Every staged node has a downstream model consumer or an explicit checked-in audit-sink exemption.
10. Calibration and normal simulation workflows contain no removed model, satisfy their own dependency closure, and preserve their accepted output/failure contracts; calibration does not inherit the managed-simulation current-result lifecycle.
11. `enrollment_decision_projection` reads only earlier years and remains disposable/non-authoritative, while enrollment and deferral remain separate authoritative state domains.

Legacy inactive Polars compatibility branches are not raw-text failures; the graph is compiled with active production SQL variables.
