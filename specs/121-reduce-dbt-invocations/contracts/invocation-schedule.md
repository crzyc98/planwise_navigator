# Contract: Invocation Schedule & Safe Floor

**Feature**: 121-reduce-dbt-invocations

This feature's externally-observable "interface" is the **ordered dbt command schedule** the orchestrator issues, recorded at the single seam `DbtRunner.execute_command` and persisted (per run) to the append-only `run_execution_metadata` table. This contract fixes what the schedule must satisfy before and after consolidation.

## Recorded schedule shape (unchanged by this feature)

Each step already records: `sequence` (1-based), `selector` (exact dbt command), `stage`, `simulation_year`, `runner_kind=dbt`. The run's terminal record carries `invocation_count` and the full ordered `schedule_steps`.

Query:

```sql
SELECT run_id, invocation_count, schedule_steps
FROM run_execution_metadata
ORDER BY recorded_at DESC LIMIT 1;
```

## Baseline (authoritative, HEAD)

- **`invocation_count == 38`** for a five-year (2025–2029), 60,040-employee run on both the reference and Studio configs (feature 120).
- Structure: 8 first-year prep + 6 × 5 years.

## Post-consolidation invariants (MUST hold)

1. **Count ceiling**: `invocation_count <= 32` after consolidation; target floor ~20–26. If a tier cannot be shipped output-neutral, the floor is recorded at the last safe tier — never lowered by shipping an unsafe tier.
2. **Ordering invariant**: within any single run, the *relative* order `… → int_*_state_accumulator → fct_yearly_events → fct_workforce_snapshot` is preserved. A consolidated multi-model selection relies on dbt's ref() DAG to order intra-selection; any selection that would place a consumer before its producer is rejected.
3. **Transaction-boundary invariant**: no consolidation merges across a point where events must be committed before a later reader (e.g., EVENT_GENERATION output must be persisted before STATE_ACCUMULATION reads it) — these remain separate invocations.
4. **Determinism invariant**: the schedule is a pure function of (config, horizon); identical inputs yield a byte-equivalent schedule (modulo run-specific paths) and identical `construction_signature`.
5. **Failure-attribution invariant**: a failure inside any consolidated selection still surfaces the failing **model**, **stage**, and **year** (the existing `PipelineStageError` messages name the model group + stage; `extract_dbt_failure_detail` pulls the failing node from `run_results.json`). A batched selection must not degrade this.

## Safe-floor publication (FR-003)

Planning publishes the floor as the cumulative `invocation_count` of the tiers proven output-neutral:

| Schedule state | invocation_count (expected) |
|---|---:|
| HEAD baseline | 38 |
| after Tier A | 33–34 |
| after Tier B | 28–29 |
| after Tier C | 19–24 |

The floor is **evidence-based**, not aspirational: each row is confirmed by an actual `run_execution_metadata` reading on an isolated run, not asserted.
