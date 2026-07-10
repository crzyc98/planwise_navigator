# Contract: Stage Outcome Handling

## Purpose

Defines the internal contract between workflow stage execution and the outer simulation orchestrator. This contract prevents failed stage results from being treated as completed work.

## Producer

`YearExecutor.execute_workflow_stage(stage, year)` produces a stage outcome for required workflow stages.

## Consumer

`PipelineOrchestrator._execute_stage_core(stage, year)` consumes the stage outcome and decides whether orchestration may continue.

## Successful Outcome

A stage outcome is successful only when:

- The outcome is a mapping-like result.
- The outcome includes `success` with the exact value `true`.

When this contract is met, orchestration may continue to later required stages.

## Failed Outcome

A stage outcome is failed when:

- The outcome includes `success` with the value `false`.
- The outcome is missing.
- The outcome is not mapping-like.
- The outcome does not include `success`.
- The outcome includes an ambiguous or non-boolean `success` value.

When this contract is met, orchestration must stop the run by raising the existing stage failure path.

## Required Failure Context

Every stopped run must include:

- Stage name from the orchestration call.
- Simulation year from the orchestration call.
- Error summary from the outcome when available.

When the outcome does not include an error summary, the consumer must provide a generic error summary that identifies the stage outcome as unsuccessful or invalid.

## Compatibility

This contract does not change public CLI arguments, API routes, database schemas, dbt model contracts, or event payload schemas.
