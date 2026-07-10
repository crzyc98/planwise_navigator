# Research: Fail Dbt Stage

## Decision: Treat Any Non-Explicit Success Stage Outcome As Failure

**Rationale**: The feature exists because a stage can report `success: false` while the outer orchestration boundary ignores the result. The safest contract is fail-closed: only an explicit successful stage outcome allows orchestration to continue. Missing, malformed, or ambiguous outcomes are treated as failures because silently assuming success recreates the same data correctness risk.

**Alternatives considered**:

- Continue only on `success: true` but ignore missing success keys: rejected because malformed outcomes would still be swallowed.
- Trust exceptions only: rejected because the current stage executor intentionally catches exceptions and returns structured failure results.
- Add validation only to selected stages: rejected because the specification covers all required workflow stages and the risk applies to any stage handled by this boundary.

## Decision: Raise The Existing Orchestration Stage Error With Stage, Year, And Error Summary

**Rationale**: The repository already uses a stage-level orchestration error for adjacent fail-fast paths. Reusing that failure mode keeps the change local and makes failed runs follow existing exception handling. Including stage and year in the message satisfies audit and diagnosis requirements while preserving the original error summary when one is available.

**Alternatives considered**:

- Introduce a new exception type: rejected because it adds surface area without improving the current failure contract.
- Return a failed run object from the stage boundary: rejected because callers already rely on exceptions to abort orchestration.
- Log the error without raising: rejected because logging alone would still allow misleading successful run completion.

## Decision: Add Fast Unit Tests Around The Stage Boundary

**Rationale**: The defect is a narrow control-flow gap. A focused unit test can mock the stage executor result and prove the orchestrator raises immediately on `success: false`, preserving stage/year/error context. Additional tests should cover missing or malformed success indicators so the fail-closed behavior is protected.

**Alternatives considered**:

- Only run an end-to-end simulation smoke test: rejected because it is slower and less precise for the regression.
- Only test `YearExecutor`: rejected because `YearExecutor` already returns failure dictionaries; the bug is the caller ignoring them.
- Only inspect logs: rejected because the core requirement is aborting the run, not merely reporting the error.

## Decision: Keep Data And Interface Changes Out Of Scope

**Rationale**: The feature changes failure propagation semantics, not persisted event schemas, dbt model contracts, API payload schemas, or CLI arguments. Existing run status and diagnostics surfaces should reflect the failed run through the existing orchestration error handling path.

**Alternatives considered**:

- Add new run status fields: rejected as unnecessary for the issue and higher blast radius.
- Add new dbt validation models: rejected because the defect is in orchestration result handling, not validation coverage.
- Change event store behavior: rejected because failed partial outputs should not be promoted to valid event lineage.
