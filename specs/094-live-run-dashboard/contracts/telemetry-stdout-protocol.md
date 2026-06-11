# Contract: Orchestrator → API Structured Telemetry (stdout line protocol)

**Producer**: `planalign_orchestrator/pipeline/telemetry_emitter.py` (hook callbacks registered by `PipelineOrchestrator`)
**Consumer**: `planalign_api/services/simulation/output_parser.py` (within the existing stdout streaming loop)
**Transport**: subprocess stdout, one record per line

## Format

```
PLANALIGN_TELEMETRY|{single-line JSON object}
```

- Sentinel prefix is exact and case-sensitive; everything after the first `|` is `json.loads`-able.
- Records MUST be single-line (no embedded newlines) and ≤ 8 KB.
- Lines without the sentinel are treated as ordinary log output (existing regex heuristics apply as fallback only).
- Unknown `record` values MUST be ignored by the consumer (forward compatibility).
- Emission is enabled when env var `PLANALIGN_STRUCTURED_TELEMETRY=1` is set (the Studio API sets it in `_build_env`; plain CLI usage is unaffected by default).

## Record types

Common fields: `v` (protocol version, int, =1), `record` (discriminator), `ts` (ISO-8601 UTC).

### run_started
```json
{"v":1,"record":"run_started","ts":"...","start_year":2025,"end_year":2027,"total_years":3}
```

### stage_started / stage_completed
```json
{"v":1,"record":"stage_started","ts":"...","year":2025,"stage":"EVENT_GENERATION"}
{"v":1,"record":"stage_completed","ts":"...","year":2025,"stage":"EVENT_GENERATION","duration_seconds":12.4}
```
`stage` ∈ {INITIALIZATION, FOUNDATION, EVENT_GENERATION, STATE_ACCUMULATION, VALIDATION, REPORTING}.

### year_completed
Emitted after a year's final stage; carries exact counts from `fct_yearly_events` (queried on the orchestrator's own connection).
```json
{"v":1,"record":"year_completed","ts":"...","year":2025,"duration_seconds":48.2,
 "event_counts":{"HIRE":142,"TERMINATION":98,"PROMOTION":31,"RAISE":876,"ENROLLMENT":57},
 "cumulative_counts":{"HIRE":142,"TERMINATION":98,"PROMOTION":31,"RAISE":876,"ENROLLMENT":57}}
```

### run_completed
```json
{"v":1,"record":"run_completed","ts":"...","years_completed":[2025,2026,2027],"duration_seconds":151.0}
```

## Consumer obligations

- Parse failures of a sentinel line MUST NOT crash the stream loop; log a warning and continue (line still goes to `simulation.log`).
- Stage/year from structured records take precedence over regex-derived guesses for the remainder of the run.
- `year_completed.cumulative_counts` replaces (not merges into) the cumulative `EventTypeCounts.by_type`.
