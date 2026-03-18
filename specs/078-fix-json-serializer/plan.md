# Implementation Plan: Fix JSON Serialization of Decimal Values in Logger

**Branch**: `078-fix-json-serializer` | **Date**: 2026-03-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/078-fix-json-serializer/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

**Problem**: PipelineOrchestrator crashes during initialization with `TypeError: Object of type Decimal is not JSON serializable` when attempting to log configuration containing Decimal fields from Pydantic models.

**Root Cause**: `json.dumps()` does not natively handle `decimal.Decimal` types. When Pydantic's `model_dump()` is called on config models containing Decimal fields, the resulting dict retains Decimal objects which then fail JSON serialization.

**Technical Approach**: Apply serialization at the source using Pydantic's `model_dump(mode='json')` parameter at serialization boundaries (run_summary.py line 129). This converts Decimals to floats at the model level before the logger attempts JSON encoding. This is preferred over adding a custom JSON encoder because it fixes the root cause at the boundary rather than patching the symptom in the logger.

**Scope**: Fix 3 affected code paths: `logger.py:57`, `run_summary.py:129`, and `pipeline_orchestrator.py:118`.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic v2 (model serialization), DuckDB 1.0.0 (database), dbt-core 1.8.8 + dbt-duckdb 1.8.1, Rich (CLI)
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: pytest with fixture-based tests, 256 test suite, fast tests <10s
**Target Platform**: Linux server (work laptop deployment)
**Project Type**: CLI-based workforce simulation orchestration engine
**Performance Goals**: Single simulations complete in <5 minutes, batch processing stable
**Constraints**: <500MB memory on work laptops (single-threaded by default), deterministic reproducibility with same random seed
**Scale/Scope**: 100K+ employee records per simulation, multi-year scenarios (2-5 years typical)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle Alignment

| Principle | Status | Details |
|-----------|--------|---------|
| **I. Event Sourcing & Immutability** | N/A | Not applicable to logger fix |
| **II. Modular Architecture** | ✅ PASS | Fix is localized to 3 files (logger.py, run_summary.py, pipeline_orchestrator.py), no circular dependencies introduced |
| **III. Test-First Development** | ⚠️ GATE | Must include unit tests for Decimal serialization before implementation code. Target: fast tests <10s, 90%+ coverage for affected code paths |
| **IV. Enterprise Transparency** | ✅ PASS | Logger enhancement maintains audit trail and diagnostic transparency |
| **V. Type-Safe Configuration** | ✅ PASS | Fix leverages Pydantic v2's `model_dump(mode='json')` for type-safe serialization at boundaries |
| **VI. Performance & Scalability** | ✅ PASS | Minimal overhead; no memory or performance impact |

### Gate Resolution

**Gate III (Test-First)**: Phase 1 design will include unit test specifications covering:
- Decimal serialization with `model_dump(mode='json')`
- JSON output parsing validation
- Nested Decimal handling
- Edge cases (very large Decimals, precision preservation)

## Project Structure

### Documentation (this feature)

```text
specs/078-fix-json-serializer/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification
├── research.md          # Phase 0 output (TBD)
├── data-model.md        # Phase 1 output (TBD)
├── quickstart.md        # Phase 1 output (TBD)
├── contracts/           # Phase 1 output (TBD)
├── checklists/
│   └── requirements.md  # Spec quality validation (completed)
└── tasks.md             # Phase 2 output (/speckit.tasks command - TBD)
```

### Source Code (repository root)

```text
# Modified files for this bug fix (no new modules created)
planalign_orchestrator/
├── logger.py            # Line 57: JSON serialization (fix)
├── run_summary.py       # Line 129: Configuration serialization (fix)
└── pipeline_orchestrator.py  # Line 118: Configuration logging (affected)

tests/
├── test_logger.py       # Unit tests for JSON serialization
└── fixtures/
    ├── config.py        # Config fixtures with Decimal fields
    └── mock_pydantic.py # Mock models with Decimal types
```

**Structure Decision**: This is a targeted bug fix affecting 3 existing files in the `planalign_orchestrator` package. No new modules or directories are created. Tests are added to the existing test suite using the established fixture library pattern (Constitution III). The fix is minimal and localized to serialization boundaries.

## Complexity Tracking

No Constitution Check violations identified. This bug fix maintains all architectural principles and introduces no additional complexity.
