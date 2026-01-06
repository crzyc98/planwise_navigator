# Tech Debt Spec Priorities for PlanAlign Engine

Based on comprehensive codebase exploration, here are **spec-worthy tech debt items** organized by the SDD principle: _preserved behavior + improved guarantees_.

---

## Tier 1: Critical Specs (High Impact, Blocks Features)

### ✅ SPEC-TD-001: Centralized Band Definitions — COMPLETED

**Status**: Merged in PR #100 (E001 + E003)

**What was delivered**:

- `config_age_bands.csv` and `config_tenure_bands.csv` seed files
- `assign_age_band()` and `assign_tenure_band()` dbt macros
- Studio UI for viewing/editing bands with "Match Census" feature
- Data quality tests (no gaps, no overlaps)

---

### ✅ SPEC-TD-002: Event Type Abstraction Layer — COMPLETED

**Status**: Implemented as E004 in `planalign_orchestrator/generators/`

**What was delivered**:

- `base.py` - `EventGenerator` ABC with `HazardBasedEventGeneratorMixin`
- `registry.py` - `EventRegistry` singleton with decorator registration
- Event wrappers: `termination.py`, `hire.py`, `promotion.py`, `merit.py`, `enrollment.py`
- `sabbatical.py` - Example new event type implementation

---

### ✅ SPEC-TD-003: Database Path Resolution Unification — COMPLETED

**Status**: Implemented in `planalign_api/services/database_path_resolver.py`

**What was delivered**:

- `DatabasePathResolver` service class with fallback chain logic
- All API services (analytics, comparison, simulation) inject the resolver
- Path resolution testable in isolation

---

## Tier 2: High Priority Specs (Maintainability + Compliance)

### ✅ SPEC-TD-004: Temporal State Accumulator Contract — COMPLETED

**Status**: Merged in PR #107 (E007)

**What was delivered**:

- `StateAccumulatorContract` base class with Pydantic v2 validation
- `StateAccumulatorRegistry` for centralized accumulator management
- `YearDependencyValidator` to detect circular dependencies and ensure proper build order
- `YearDependencyError` exception with actionable resolution hints
- Comprehensive test coverage (unit + integration tests)

---

### ✅ SPEC-TD-005: IRS Limit Enforcement Hardening — COMPLETED

**Status**: Merged in PR #108 (E008)

**What was delivered**:

- `config_irs_limits.csv` seed file with IRS 402(g) limits by year
- Property-based tests using Hypothesis for edge case coverage
- Catch-up age threshold (50) now configurable via seed
- Future IRS limits (2025, 2026+) addable without code changes
- Comprehensive unit tests in `tests/unit/test_irs_402g_limits.py`
- sqlparse 0.5.5 token limit fix for large SQL models

---

### SPEC-TD-006: SQL/Polars Mode Parity

**The Problem**: Event generation exists in TWO implementations (SQL + Polars) that could diverge.

**Preserved Behavior (BG-009)**:

- Same seed produces identical events in both modes
- Hire/termination/promotion counts match exactly

**Improved Guarantees**:

- Automated parity test: run both modes, compare outputs
- Single source of truth for business rules (not duplicated)
- Mode switch is transparent to downstream consumers

**Files Affected**: `event_generation_executor.py`, `polars_event_factory.py`, `int_*_events.sql`

**Blocks**: GPU acceleration, real-time streaming, A/B testing strategies

**📋 Specify Prompt**:

```
Ensure SQL and Polars event generation modes produce identical outputs and cannot
diverge. Currently event generation exists in two implementations (dbt SQL models
and polars_event_factory.py) that could produce different results. Preserved behavior:
same random seed produces identical events in both modes, hire/termination/promotion
counts match exactly between modes. Improved constraints: automated parity test that
runs both modes and compares outputs (row counts, event types, employee IDs), single
source of truth for business rules extracted to shared config (not duplicated in
SQL and Python), mode switch is transparent to downstream consumers (fct_yearly_events
schema identical). This enables GPU acceleration, real-time streaming, and A/B testing.
```

---

## Tier 3: Medium Priority Specs (Performance + Developer Experience)

### SPEC-TD-007: Pandas → Polars Migration Completion

**The Problem**: 4 files still use Pandas, blocking full Polars adoption.

**Preserved Behavior**:

- Excel exports produce identical files
- Monitoring reports unchanged
- Hazard cache behavior identical

**Improved Guarantees**:

- Zero Pandas imports outside explicit bridge modules
- 10-50ms latency reduction per database operation
- Single DataFrame library to learn/maintain

**Files Affected**: `excel_exporter.py`, `monitoring.py`, `hazard_cache_manager.py`, `debug_utils.py`

**Blocks**: Polars-native optimizations, reduced dependencies

**📋 Specify Prompt**:

```
Complete the Pandas to Polars migration by converting the remaining 4 files that
still use Pandas (excel_exporter.py, monitoring.py, hazard_cache_manager.py,
debug_utils.py). Preserved behavior: Excel exports produce byte-identical files,
monitoring reports unchanged, hazard cache read/write behavior identical.
Improved constraints: zero Pandas imports outside explicit bridge modules (if any),
all DataFrame operations use Polars API, 10-50ms latency reduction per database
operation. This enables Polars-native optimizations and reduces the dependency
footprint (remove pandas from requirements).
```

---

### SPEC-TD-008: Hazard Calculation Consolidation

**The Problem**: 5 SQL files duplicate the base_rate × age_multiplier × tenure_multiplier pattern.

**Preserved Behavior**:

- Termination hazards unchanged
- Promotion hazards unchanged
- Merit hazards unchanged

**Improved Guarantees**:

- Single `calculate_hazard_rate` macro
- Adding location-based multipliers requires 1 macro change
- Hazard calculation tested in isolation

**Files Affected**: `dim_promotion_hazards.sql`, `dim_termination_hazards.sql`, `int_hazard_*.sql`

**Blocks**: Location-based hazards, performance-tier adjustments

**📋 Specify Prompt**:

```
Consolidate hazard rate calculations that are duplicated across 5 SQL files
(dim_promotion_hazards.sql, dim_termination_hazards.sql, int_hazard_termination.sql,
int_hazard_promotion.sql, int_hazard_merit.sql). All use the pattern:
base_rate × age_multiplier × tenure_multiplier. Preserved behavior: termination,
promotion, and merit hazard rates produce identical values to current implementation.
Improved constraints: single calculate_hazard_rate(base_rate, age_band, tenure_band, hazard_type)
macro that all models call, adding new multipliers (e.g., location-based, performance-tier)
requires only macro change, hazard calculation unit-testable in isolation with
dbt test. This enables location-based hazards and performance-tier adjustments.
```

---

### SPEC-TD-009: Test Fixture Decoupling

**The Problem**: Tests verify exact data structures, not behaviors; breaks on any schema change.

**Preserved Behavior**:

- All 256 tests continue passing
- Coverage targets maintained (90%+)

**Improved Guarantees**:

- Fixtures test BEHAVIOR (enrollment happens, rate changes)
- Schema changes don't break unrelated tests
- Abstract interfaces enable implementation swaps

**Files Affected**: `tests/fixtures/`, `test_enrollment_state_builder.py`, `test_deferral_rate_builder.py`

**Blocks**: State accumulator refactoring, DuckDB-native implementations

**📋 Specify Prompt**:

```
Decouple test fixtures from exact data structures so they test behavior instead
of implementation details. Currently tests break on any schema change because
they assert exact column names and data shapes. Preserved behavior: all 256 tests
continue passing, coverage targets maintained (90%+). Improved constraints: fixtures
assert BEHAVIOR (employee enrolled, deferral rate changed, contribution calculated)
not exact data structures, schema changes to internal columns don't break unrelated
tests, abstract interfaces (e.g., StateAccumulator protocol) enable implementation
swaps without test rewrites. Files: tests/fixtures/, test_enrollment_state_builder.py,
test_deferral_rate_builder.py. This enables state accumulator refactoring and
DuckDB-native implementations.
```

---

## NOT Spec-Worthy (Task-Level Work)

These are cleanup items, NOT specs:

| Item                                | Why Not a Spec                           |
| ----------------------------------- | ---------------------------------------- |
| Remove `.apply()` in excel_exporter | Pure optimization, no behavior change    |
| Consolidate DELETE patterns         | Internal cleanup, no external contract   |
| Connection pool consistency         | Performance tuning, not feature-blocking |
| Percent field normalization         | Config layer detail, not business rule   |
| `pl.from_pandas()` → `.pl()`        | API preference, identical results        |

---

## Spec Queue Status

| Priority | Spec                                 | Status                | Effort  |
| -------- | ------------------------------------ | --------------------- | ------- |
| 1st      | TD-001: Centralized Band Definitions | ✅ **DONE** (PR #100) | ~8-12h  |
| 2nd      | TD-002: Event Type Abstraction       | ✅ **DONE** (E004)    | ~12-16h |
| 3rd      | TD-003: Database Path Resolution     | ✅ **DONE**           | ~4-6h   |
| 4th      | TD-004: Temporal State Contract      | ✅ **DONE** (PR #107) | ~8-12h  |
| 5th      | TD-005: IRS Limit Hardening          | ✅ **DONE** (PR #108) | ~6-8h   |
| 6th      | TD-006: SQL/Polars Parity            | 🔲 Ready              | ~8-12h  |
| 7th      | TD-008: Hazard Consolidation         | 🔲 Ready              | ~6-8h   |
| 8th      | TD-007: Pandas Migration             | 🔲 Ready              | ~8-12h  |
| 9th      | TD-009: Test Fixture Decoupling      | 🔲 Ready              | ~12-16h |

---

## Key Behavioral Guarantees to Preserve

Any tech debt spec MUST include tests for these invariants:

| ID     | Guarantee                   | Test Assertion                       |
| ------ | --------------------------- | ------------------------------------ |
| BG-001 | Event ordering determinism  | Same seed → identical event sequence |
| BG-003 | Temporal state accumulation | Year N reads Year N-1; no skip       |
| BG-004 | Latest event wins           | Multiple events → last by date wins  |
| BG-008 | IRS limits zero tolerance   | `max(contribution) <= limit` always  |
| BG-009 | SQL/Polars parity           | Both modes → identical outputs       |
| BG-011 | Delete+insert idempotency   | Re-run → same row count              |

---

## How to Run a Spec

### Step 1: Create the Spec

Copy the **📋 Specify Prompt** from the spec section above, then run:

```
/speckit.specify
```

Paste the prompt when asked for the feature description.

### Step 2: Clarify the Spec

Run `/speckit.clarify` to identify any underspecified areas

### Step 3: Plan Implementation

Run `/speckit.plan` to design the implementation approach

### Step 4: Generate Tasks

Run `/speckit.tasks` to create the implementation task list

### Step 5: Execute

Run `/speckit.implement` to execute the tasks

---

## Summary

**Completed** (5 of 9):
- TD-001 (Centralized Band Definitions) — PR #100
- TD-002 (Event Type Abstraction Layer) — E004
- TD-003 (Database Path Resolution) — `database_path_resolver.py`
- TD-004 (Temporal State Accumulator Contract) — PR #107
- TD-005 (IRS Limit Enforcement Hardening) — PR #108

**Next Up**: TD-006 (SQL/Polars Mode Parity)
**Remaining**: 4 specs
**Priorities**: Performance, Developer velocity
