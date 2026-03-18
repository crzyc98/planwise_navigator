# Research & Design Decisions: Fix JSON Serialization of Decimal Values

**Phase**: 0 - Research & Clarification
**Date**: 2026-03-18
**Status**: Complete

## Research Questions & Decisions

### Decision 1: Serialization Strategy for Decimal Types

**Question**: How should Decimal values from Pydantic models be serialized to JSON?

**Alternatives Considered**:

| Option | Approach | Pros | Cons | Decision |
|--------|----------|------|------|----------|
| A | Custom JSON Encoder | Centralized, reusable encoder class | Fixes symptom, not root cause; adds encoder complexity | REJECTED |
| B | `model_dump(mode='json')` at boundaries | Fixes at source; Pydantic's native support; future-proof | Requires changes at each serialization site | ✅ SELECTED |
| C | Pre-conversion in model fields | Type system enforces conversion | Breaks Decimal precision guarantees; not practical for financial data | REJECTED |

**Decision**: **Option B** - Use Pydantic v2's `model_dump(mode='json')` parameter at serialization boundaries.

**Rationale**:
- Pydantic v2 introduced the `mode='json'` parameter specifically to handle non-JSON-serializable types (like Decimal, datetime, UUID)
- This follows the principle of handling serialization at boundaries rather than patching downstream code
- Converts Decimals to floats only in the JSON output, preserving Decimal arithmetic throughout the application
- More maintainable: if new Pydantic types need JSON serialization, they work automatically with `mode='json'`
- Aligns with Constitution V (Type-Safe Configuration): leveraging Pydantic's type system for safety

**Implementation Sites**:
- `run_summary.py:129` - Configuration model dump (primary fix)
- `logger.py:57` - JSON serialization (will work once upstream is fixed)
- `pipeline_orchestrator.py:118` - Configuration logging (will work once upstream is fixed)

**Precision Handling**:
- Decimal to float conversion acceptable for logging/display purposes
- Audit trail preserves original Decimal values in configuration objects
- No precision loss for simulation calculations (Decimals remain in-memory)

---

### Decision 2: Test Coverage Strategy

**Question**: What test coverage is needed for Decimal serialization?

**Approach**:
- Unit tests for `model_dump(mode='json')` with Decimal fields
- Integration test: full PipelineOrchestrator initialization without errors
- Edge case tests for nested Decimals and special values

**Test Framework**:
- pytest with existing fixture library (Constitution III)
- Use `tests/fixtures/config.py` for Decimal-containing test configs
- Fast tests only (target <10s for entire test suite)

**Coverage Target**: 90%+ line coverage for affected code paths (logger.py, run_summary.py, pipeline_orchestrator.py initialization)

---

### Decision 3: Backward Compatibility

**Question**: Will this change break existing code or simulations?

**Analysis**:
- No breaking changes: `model_dump(mode='json')` is only used at serialization boundaries
- Existing in-memory calculations use Decimal types (no change)
- JSON output format unchanged (Decimals still represented as numbers)
- Simulations remain reproducible with same random seed

**Conclusion**: Safe to implement as a patch-level bug fix. No migration needed.

---

## Technical Context Clarifications

All questions from Technical Context section are resolved:

| Item | Status | Resolution |
|------|--------|-----------|
| Language/Version | ✅ Clear | Python 3.11 |
| Primary Dependencies | ✅ Clear | Pydantic v2, DuckDB, dbt-core |
| Storage | ✅ Clear | DuckDB (`dbt/simulation.duckdb`) |
| Testing | ✅ Clear | pytest with fixtures, 256-test suite |
| Target Platform | ✅ Clear | Linux server (work laptop) |
| Project Type | ✅ Clear | CLI orchestration engine |
| Performance Goals | ✅ Clear | <5 min simulations, batch stable |
| Constraints | ✅ Clear | <500MB memory, deterministic |
| Scale/Scope | ✅ Clear | 100K+ employees, multi-year scenarios |

---

## Design Decisions Summary

**Primary Fix**: Use `model_dump(mode='json')` in `run_summary.py` line 129 when converting Pydantic config to dict for logging

**Secondary Changes**:
- Add unit tests for Decimal serialization
- Verify all three affected files (logger.py, run_summary.py, pipeline_orchestrator.py) work correctly with the fix
- No structural changes to existing modules

**Validation**: All Constitution principles satisfied, no violations or exceptions needed

---

## Next Steps (Phase 1)

1. Create `data-model.md` documenting the affected Pydantic models
2. Create `quickstart.md` with testing instructions
3. Create contracts (if needed) for logger interface
4. Run agent context update
5. Proceed to Phase 2: Task generation with `/speckit.tasks`
