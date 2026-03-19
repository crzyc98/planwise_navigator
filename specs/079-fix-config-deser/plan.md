# Implementation Plan: Fix SimulationConfig.from_dict() Failure in Result Handler

**Branch**: `079-fix-config-deser` | **Date**: 2026-03-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/079-fix-config-deser/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Fix a silent failure in the simulation result handler where deserialization of merged config dictionaries fails with a truncated error message. Implement three-step solution: (1) improve error logging to show actual exception details, (2) make from_dict() robust by filtering unknown keys, (3) ensure Decimal values are converted to floats via model_dump(mode='json') upstream. This enables operators to diagnose failures quickly and ensures result metadata is fully archived for all runs.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic v2, FastAPI, dbt-core 1.8.8, DuckDB 1.0.0
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: pytest with fixture library (256 tests, 87 fast tests)
**Target Platform**: Linux server (work laptop stable)
**Project Type**: Python backend (CLI + API + web service with React frontend)
**Performance Goals**: Sub-5-minute bug diagnosis via error logs; result handler completion without partial failures
**Constraints**: Single-threaded execution (default), work laptop stable, <2 second query responses
**Scale/Scope**: 100K+ employee records; multi-year simulations (2-5 years)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle Alignment

| Principle | Requirement | Status | Notes |
|-----------|-----------|--------|-------|
| **Enterprise Transparency (IV)** | Error messages must include context, correlation IDs, and resolution hints | ⚠️ VIOLATION | Current error at result_handlers.py:68 truncates to "from_dict" method name, hiding actual exception. Must improve logging to show exception type and message. |
| **Type-Safe Configuration (V)** | Pydantic v2 models with explicit validation | ✅ PASS | SimulationConfig already uses Pydantic v2 with Field validation and @validator decorators. from_dict() implementation must be robust to merged dicts. |
| **Test-First Development (III)** | All features include tests written before implementation | ✅ PASS (pending) | Must write tests for error handling, key filtering, and deserialization robustness before implementation. Target: fast test suite remains <10s. |
| **Modular Architecture (II)** | Single responsibility, max ~600 lines per module | ⏳ CHECK NEEDED | result_handlers.py needs line count verification; current export_results_to_excel function handles multiple concerns (DB connection, Excel export, config parsing). May need to extract config deserialization into separate utility. |

### Gate Evaluation

**PASS with noted improvements needed**:
- ✅ No circular dependencies introduced
- ✅ Type safety (Pydantic v2) maintained
- ⚠️ Transparency: Must improve error logging before Phase 1
- ⏳ Architecture: Evaluate module responsibilities post-design in Phase 1

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── config/
│   ├── loader.py              # SimulationConfig loading from files
│   ├── manager.py             # Config management and merging
│   └── [other config modules]
├── pipeline/
│   └── result_handlers.py      # ← PRIMARY: Error logging fix here
├── excel_exporter.py          # Excel export utilities
└── utils.py

config/
└── schema.py                  # ← SimulationConfig Pydantic model definition

planalign_api/
├── services/
│   └── simulation/
│       └── result_handlers.py  # ← AFFECTED: Contains from_dict() error (line 68)
└── main.py

tests/
├── fixtures/
│   ├── config.py              # Test configuration fixtures
│   └── [other fixtures]
├── integration/
│   └── test_result_handler.py  # ← NEW: Integration tests for result handler
└── unit/
    └── test_config_deser.py    # ← NEW: Unit tests for from_dict() robustness
```

**Structure Decision**: Bug fix is localized to result handler error logging (planalign_api/services/simulation/result_handlers.py) and SimulationConfig deserialization logic (config/schema.py). No new modules required. Tests will be added to existing test structure.

## Complexity Tracking

No violations to Constitution Check. Bug fix is localized and focused.

---

## Phase 0: Research Complete ✅

**Output**: `research.md`

**Resolved Unknowns**:
1. ✅ Root cause analysis: Type mismatch (Decimal), unknown keys, missing fields
2. ✅ Pydantic v2 best practices: Implement classmethod from_dict() with key filtering
3. ✅ Error handling: Capture `type(e).__name__` and `str(e)` for full context
4. ✅ Upstream serialization: Use `model_dump(mode='json')` to convert Decimals
5. ✅ Implementation strategy: Three-step approach confirmed

**Key Decisions**:
- Error logging: `{type(e).__name__}: {e}` pattern
- Key filtering: Classmethod with explicit dict filtering (transparent)
- Serialization: `model_dump(mode='json')` at archiver/logger boundaries

---

## Phase 1: Design Complete ✅

**Outputs**:
1. ✅ `data-model.md` - Entity definitions (SimulationConfig, ConfigMerge, RunMetadata)
2. ✅ `contracts/result_handler_api.md` - Internal API contract
3. ✅ `quickstart.md` - Developer guide with test cases

**Design Artifacts**:
- Data model: Config lifecycle from creation → serialization → deserialization
- Validation rules: Type constraints, field ranges, cross-field validators
- State transitions: 5-step flow from config creation to UI display
- Integration points: Identified all files needing changes

**Constitution Check (Re-evaluated)**:
- ✅ Enterprise Transparency: Error logging now includes full exception context
- ✅ Type Safety: Pydantic v2 validation maintained throughout
- ✅ Testing: Test cases provided for unit and integration coverage
- ✅ Architecture: No new modules; changes localized to existing components

---

## Phase 2: Ready for Implementation ⏳

**Next Phase** (`/speckit.tasks`): Generate actionable task list from this plan.

**Implementation Path**:
1. Step 1 (Error Logging): 30 minutes - Modify result_handlers.py exception handling
2. Step 2 (Key Filtering): 45 minutes - Add from_dict() classmethod to SimulationConfig
3. Step 3 (Serialization): 60 minutes - Identify and update model_dump() call sites
4. Testing: 90 minutes - Verify unit and integration tests pass
5. Review & Merge: 30 minutes - Code review and PR closure

**Total Estimated Effort**: 4-5 hours development + review

---

## Complexity Tracking

No violations to Constitution Check. Bug fix is localized and focused:
- Single feature branch (079-fix-config-deser)
- Minimal file modifications (3-4 files)
- No new dependencies
- Backward compatible
