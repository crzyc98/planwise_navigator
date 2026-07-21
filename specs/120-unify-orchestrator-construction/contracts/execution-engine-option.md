# Contract: Execution-Engine Option

Ensures no execution-selection option is silently ignored (FR-008, SC-004).

## Current reality

`optimization.execution_engine` is a typed config field introduced by this feature. It defaults to `dbt`; the paused compiled-engine value is deliberately unsupported.

## Rules (MUST)

1. The canonical seam recognizes exactly one supported engine (the standard dbt runner).
2. If a configuration carries an `execution_engine` selection (now or in future) whose value is not the supported engine, **config/CLI validation rejects it** with a clear message naming the option and the supported value(s). It is never accepted-and-ignored, and never silently defaulted to standard.
3. A supported engine value resolves to identical behavior from every entry point.
4. The canonical seam is the **single attach point** if a future engine (e.g., a revived native kernel) is supported end-to-end — at which point this contract flips from "reject" to "resolve".

## Out of scope

- Wiring the paused compiled engine (#476) — it stays paused/NO-GO and is not advertised.

## Acceptance checks

1. Config with an unsupported `execution_engine` value → run rejected at validation with a clear message; no run starts.
2. Config with the supported engine (or unset) → identical behavior across entry points.
