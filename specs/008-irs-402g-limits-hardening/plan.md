# Implementation Plan: IRS 402(g) Limits Hardening

**Branch**: `008-irs-402g-limits-hardening` | **Date**: 2025-12-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-irs-402g-limits-hardening/spec.md`

## Summary

Harden IRS 402(g) contribution limit enforcement by ensuring 100% compliance across all simulations. The implementation will: (1) rename the seed file to `config_irs_limits.csv` for naming consistency, (2) remove any remaining hardcoded catch-up age thresholds in favor of seed-based configuration, (3) add comprehensive property-based tests using Hypothesis to mathematically guarantee that `max(contribution) <= applicable_limit` for all employees in all scenarios, and (4) validate existing dbt tests correctly enforce limits without violations.

## Technical Context

**Language/Version**: Python 3.11, SQL (DuckDB 1.0.0)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Hypothesis (property-based testing), pytest
**Storage**: DuckDB (`dbt/simulation.duckdb`)
**Testing**: pytest with Hypothesis for property-based tests, dbt tests for SQL validation
**Target Platform**: Linux server / macOS (work laptops)
**Project Type**: Data pipeline (dbt + Python orchestration)
**Performance Goals**: Property tests complete in <60 seconds for 10,000 random employees
**Constraints**: Single-threaded dbt execution for stability
**Scale/Scope**: 100K+ employees across multi-year simulations (2025-2035)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | ✅ PASS | No changes to event structure; contribution calculations preserve immutable audit fields |
| II. Modular Architecture | ✅ PASS | Changes isolated to seed file, one dbt model, and new test module |
| III. Test-First Development | ✅ PASS | Property-based tests are the core deliverable; tests written before model changes |
| IV. Enterprise Transparency | ✅ PASS | Preserves existing transparency fields: `requested_contribution_amount`, `applicable_irs_limit`, `limit_type` |
| V. Type-Safe Configuration | ✅ PASS | Seed file schema explicitly defined; no raw string concatenation |
| VI. Performance & Scalability | ✅ PASS | No performance regression; property tests designed for 10K+ scale |

**Gate Status**: ✅ PASSED - All principles satisfied, no violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/008-irs-402g-limits-hardening/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # N/A (no API contracts needed)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
dbt/
├── seeds/
│   ├── config_irs_limits.csv           # RENAMED from irs_contribution_limits.csv (FR-005)
│   └── ...existing seeds...
├── models/
│   ├── intermediate/
│   │   └── events/
│   │       └── int_employee_contributions.sql  # Update ref to renamed seed
│   └── marts/
│       └── fct_workforce_snapshot.sql          # Remove hardcoded >= 50, use seed
├── tests/
│   └── data_quality/
│       ├── test_employee_contributions.sql     # Existing - verify passes
│       └── test_employee_contributions_validation.sql  # Existing - verify passes

tests/
├── unit/
│   └── test_irs_402g_limits.py        # NEW: Property-based tests with Hypothesis
└── fixtures/
    └── irs_limits.py                  # NEW: Test fixtures for IRS limits
```

**Structure Decision**: Minimal changes to existing structure. New property-based test module added under `tests/unit/`. Seed file renamed for consistency with other `config_*` seeds.

## Complexity Tracking

No violations requiring justification. Implementation is straightforward:
- Rename one seed file
- Update two dbt model references
- Add one new test module

## Phase 0: Research Summary

### Unknowns Identified

1. **Hardcoded age threshold locations**: Where exactly is `>= 50` hardcoded vs. using seed?
2. **Hypothesis best practices**: Strategies for property-based testing of contribution limits
3. **Seed file reference updates**: Which models reference `irs_contribution_limits`?

### Research Tasks

These will be documented in `research.md`:

1. Audit all hardcoded `>= 50` age comparisons in production SQL models
2. Document Hypothesis strategies for contribution limit invariants
3. Identify all dbt model references to `irs_contribution_limits` seed

## Phase 1: Design Summary

### Data Model Changes

Documented in `data-model.md`:

**Entity: IRS Limit Configuration** (seed table)
- `limit_year` (INTEGER, PK): Plan year
- `base_limit` (INTEGER): IRS 402(g) base limit in dollars
- `catch_up_limit` (INTEGER): Total limit including catch-up (base + catch-up amount)
- `catch_up_age_threshold` (INTEGER): Age at which catch-up eligibility begins (currently 50)

Note: Column names remain as-is (`catch_up_limit` not `catchup_limit` per spec) since existing seed already uses underscores.

### Contracts

N/A - This feature involves dbt models and Python tests, no API contracts needed.

### Quickstart

Documented in `quickstart.md`:

```bash
# 1. Rename seed file
git mv dbt/seeds/irs_contribution_limits.csv dbt/seeds/config_irs_limits.csv

# 2. Update dbt to use renamed seed
cd dbt && dbt seed --threads 1

# 3. Run property-based tests
pytest tests/unit/test_irs_402g_limits.py -v

# 4. Run dbt data quality tests
cd dbt && dbt test --select tag:irs_compliance --threads 1
```
