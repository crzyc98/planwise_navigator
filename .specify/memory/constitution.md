<!--
SYNC IMPACT REPORT
==================
Version Change: 0.0.0 → 1.0.0 (MAJOR: Initial constitution)
Modified Principles: N/A (initial version)
Added Sections:
  - Core Principles (6 principles)
  - Development Workflow (testing, database, dbt patterns)
  - Governance (amendment procedures, compliance)
Removed Sections: N/A
Templates Requiring Updates:
  - .specify/templates/plan-template.md: ✅ Compatible (Constitution Check section exists)
  - .specify/templates/spec-template.md: ✅ Compatible (Requirements align with FR patterns)
  - .specify/templates/tasks-template.md: ✅ Compatible (Test-first phases align)
  - .specify/templates/checklist-template.md: ✅ Compatible
  - .specify/templates/agent-file-template.md: ✅ Compatible
Follow-up TODOs: None

--------------------------------------------------------------------------------

Version Change: 1.0.0 → 1.0.1 (PATCH: clarification/correction, no principle redefinition)
Modified Principles: III. Test-First Development (fast-suite target corrected from an
  unenforced, stale <10s claim to a measured, CI-enforced 360s budget)
Modified Sections: Development Workflow > Testing Requirements (same correction)
Rationale: #648 found the <10s target (set for an 87-test baseline) was never revised as
  the fast suite grew to ~2,780 tests (actual: ~288s) and was never enforced in CI, making
  it decorative. Fixed alongside `.github/workflows/ci.yml` (added a duration-assertion step)
  and `pyproject.toml` (corrected the `fast` marker's per-test description).
Templates Requiring Updates: None (no template references the specific numeric target)
Follow-up TODOs: Re-measure and update the 360s budget if the fast suite's test count or
  composition changes materially.
-->

# Fidelity PlanAlign Engine Constitution

## Core Principles

### I. Event Sourcing & Immutability

Every workforce event MUST be permanently recorded with a UUID and timestamp in the immutable event store (`fct_yearly_events`). Events are the single source of truth; state is derived by replaying events. No event may be modified or deleted after creation. All simulation outcomes MUST be reproducible given the same random seed and configuration.

**Rationale**: Enterprise audit compliance requires complete traceability. Immutable events enable point-in-time reconstruction, regulatory reporting, and scenario replay without data loss.

### II. Modular Architecture

Each component MUST have a single, well-defined responsibility. The codebase follows a modular package structure where no module exceeds ~600 lines and each module has 6-8 public methods maximum. Circular dependencies between layers are prohibited (staging → intermediate → marts; never reverse).

**Rationale**: Maintainability scales with module isolation. The E072 refactoring demonstrated that monolithic files (2,478 lines) create 2+ hour onboarding barriers; modular design reduces this to 20 minutes.

### III. Test-First Development

All significant features MUST include tests written before implementation (Red-Green-Refactor). The fast suite (`pytest -m fast`) MUST complete within a CI-enforced wall-clock budget (360s as of 2026-09-21, ~2,780 tests); the budget MUST be re-measured and updated as the suite grows rather than left to drift. Test coverage targets: 90%+ for core modules, 95% line coverage for Python code. Integration tests validate end-to-end workflows.

**Rationale**: The E075 testing infrastructure (256 tests, 87 fast tests in 4.7s) proves that comprehensive testing catches regressions early and enables confident refactoring. The original <10s target was calibrated for that 87-test baseline and was never revised as the suite grew ~32x; per #648, it had become a decorative, unenforced claim (actual: ~288s). A measured, CI-enforced budget is honest and catches regressions; a stale unenforced one does not.

### IV. Enterprise Transparency

All simulation decisions MUST be logged with sufficient context for audit reconstruction. Configuration changes are version-controlled. Every pipeline execution produces audit reports. Error messages MUST include correlation IDs, execution context, and resolution hints.

**Rationale**: Regulatory compliance and debugging efficiency require full visibility. The E074 error handling system targets <5 minute bug diagnosis through contextual diagnostics.

### V. Type-Safe Configuration

All configuration MUST use Pydantic v2 models with explicit validation constraints. SQL transformations use dbt with explicit `{{ ref() }}` references. No raw SQL string concatenation for table references. All event payloads have discriminated union types with exhaustive validation.

**Rationale**: Type safety prevents runtime errors that are costly in batch simulations. Pydantic validation catches configuration errors at load time rather than mid-simulation.

### VI. Performance & Scalability

Systems MUST handle 100K+ employee records without memory errors. Dashboard queries MUST respond in <2 seconds (95th percentile). Single-threaded execution MUST be the default for stability. Performance optimizations (Polars mode, parallel execution) are opt-in and documented.

**Rationale**: Work laptop deployments require conservative resource usage. The E068/E076 optimizations achieved 1000x+ improvements while maintaining stability as the default.

## Development Workflow

### Testing Requirements

- Fast tests (`pytest -m fast`): MUST complete within the CI-enforced budget defined in Principle III (360s baseline as of 2026-09-21; enforced by the `fast-tests` job in `.github/workflows/ci.yml`)
- Integration tests: MUST validate complete year simulations
- dbt tests: 90% coverage with schema and custom tests
- All tests MUST use fixtures from `tests/fixtures/` for consistency

### Database Access Patterns

- ALWAYS use `get_database_path()` from `planalign_orchestrator.config`
- ALWAYS close database connections explicitly or use context managers
- NEVER hold connections during long-running operations
- Standardized database location: `dbt/simulation.duckdb`

### dbt Development Patterns

- ALWAYS run dbt commands from the `/dbt` directory
- ALWAYS use `--threads 1` for work laptop stability
- ALWAYS filter by `{{ var('simulation_year') }}` in heavy models
- NEVER create circular dependencies between model layers

## Governance

This constitution supersedes all other development practices for Fidelity PlanAlign Engine. All pull requests and code reviews MUST verify compliance with these principles.

### Amendment Procedure

1. Proposed amendments MUST be documented with rationale
2. Breaking changes (principle removal/redefinition) require MAJOR version bump
3. New principles or expanded guidance require MINOR version bump
4. Clarifications and wording fixes require PATCH version bump
5. All amendments MUST update dependent templates if affected

### Compliance Review

- Code reviews MUST include Constitution Check verification
- Complexity violations MUST be justified in the Complexity Tracking table
- Performance regressions MUST be documented with mitigation plans

### Runtime Guidance

For day-to-day development guidance, refer to:
- `CLAUDE.md` - Code generation playbook
- `tests/TEST_INFRASTRUCTURE.md` - Testing guide
- `docs/guides/error_troubleshooting.md` - Error resolution

**Version**: 1.0.1 | **Ratified**: 2025-12-12 | **Last Amended**: 2026-09-21
