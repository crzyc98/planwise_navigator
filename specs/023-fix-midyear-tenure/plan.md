# Implementation Plan: Fix Mid-Year Termination Tenure Calculation

**Branch**: `023-fix-midyear-tenure` | **Date**: 2026-01-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/023-fix-midyear-tenure/spec.md`

## Summary

Fix incorrect `current_tenure` values for mid-year terminated employees in the workforce snapshot. The bug manifests in two places: (1) tenure band is calculated from the pre-recalculated tenure value, and (2) new hires who are terminated have tenure hardcoded to 0 instead of calculated to their termination date. Both the SQL (dbt) pipeline and Polars state pipeline must be fixed to ensure parity.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator), SQL/Jinja (dbt models)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Polars 1.0+
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`)
**Testing**: pytest (Python), dbt tests (SQL)
**Target Platform**: Linux/macOS server (work laptop deployment)
**Project Type**: Single project (monorepo with dbt + Python orchestrator)
**Performance Goals**: Maintain current performance (<5 minutes for 2-year simulation)
**Constraints**: Single-threaded execution default, 100K+ employee support
**Scale/Scope**: Bug fix affecting ~3-5 files, no new schema changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No changes to event structure; fix is in derived state calculation |
| II. Modular Architecture | PASS | Changes confined to existing modules; no new modules needed |
| III. Test-First Development | PASS | Will add regression tests before/with implementation |
| IV. Enterprise Transparency | PASS | Bug fix improves data accuracy for audit purposes |
| V. Type-Safe Configuration | PASS | Using existing `calculate_tenure` macro; no new config |
| VI. Performance & Scalability | PASS | No performance impact; reusing existing calculation patterns |

**Development Workflow Compliance:**
- Testing: Will add dbt tests and pytest cases for tenure edge cases
- Database Access: No changes to database access patterns
- dbt Patterns: Will run from `/dbt` directory with `--threads 1`

## Project Structure

### Documentation (this feature)

```text
specs/023-fix-midyear-tenure/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output - root cause analysis
├── data-model.md        # Phase 1 output - affected entities
├── quickstart.md        # Phase 1 output - testing guide
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (affected files)

```text
# SQL Pipeline (dbt models)
dbt/models/marts/
└── fct_workforce_snapshot.sql          # Main fix: tenure recalculation + tenure_band fix

dbt/macros/
├── calculate_tenure.sql                # Existing macro (reuse, verify correctness)
└── bands/assign_tenure_band.sql        # Tenure band macro (verify consistency)

# Polars Pipeline
planalign_orchestrator/
└── polars_state_pipeline.py            # SnapshotBuilder.build() tenure calculation

# Tests
tests/
├── test_tenure_calculation.py          # New: unit tests for tenure edge cases
└── fixtures/workforce_data.py          # Test data fixtures

dbt/tests/
└── test_tenure_band_consistency.sql    # New: dbt test for tenure/band consistency
```

**Structure Decision**: Existing monorepo structure with dbt models and Python orchestrator. No structural changes needed - this is a bug fix within existing modules.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations - all Constitution principles pass.
