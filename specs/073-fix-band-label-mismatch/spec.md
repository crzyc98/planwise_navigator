# Feature Specification: Fix Hardcoded Age/Tenure Band Label Mismatches

**Feature Branch**: `073-fix-band-label-mismatch`
**Created**: 2026-03-16
**Status**: Draft
**Input**: GitHub Issue #233 - Hardcoded band labels cause JOIN mismatches with hazard rate lookup tables

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Salary Growth Produces Correct Results (Priority: P1)

As a plan actuary running a multi-year workforce simulation, I need merit raise events to be generated correctly so that employee salary growth projections are accurate. Currently, 5 models produce band labels that never match the hazard rate lookup tables, causing zero raise/enrollment events to be generated silently.

**Why this priority**: This is the core bug — incorrect band labels cause JOIN mismatches with hazard rate tables, silently producing zero events for raises and enrollment. Without this fix, simulation outputs are materially wrong.

**Independent Test**: Run a single-year simulation and verify that merit raise events are generated for employees across all age and tenure bands by checking that `fct_yearly_events` contains RAISE events and that the count is non-zero for each band combination.

**Acceptance Scenarios**:

1. **Given** the 5 critically mismatched models are fixed, **When** a simulation is run for year 2025, **Then** merit raise events are generated for employees in every age/tenure band that has a non-zero hazard rate defined.
2. **Given** an employee aged 22 with 0.5 years tenure, **When** the simulation assigns bands, **Then** the employee receives age band `< 25` and tenure band `< 2` (matching the seed-defined labels exactly).
3. **Given** the `dim_enrollment_hazards` model uses corrected tenure boundaries, **When** enrollment events are generated, **Then** employees are matched to the correct enrollment hazard rates.

---

### User Story 2 - Band Labels Stay Consistent When Users Customize Bands (Priority: P2)

As a plan administrator customizing age/tenure bands via the Studio UI or CSV seed edits, I need all models to dynamically read band definitions from the centralized seed tables so that my customizations are reflected consistently throughout the simulation.

**Why this priority**: 14 models hardcode CASE statements that happen to match current defaults but will break silently when bands are customized. This undermines the Studio band configuration feature (E003).

**Independent Test**: Change the age band seed CSV to use different boundaries (e.g., merge `25-34` and `35-44` into `25-44`), rebuild the dbt models, and verify all models produce the new label consistently.

**Acceptance Scenarios**:

1. **Given** all 14 fragile-but-correct models are updated to use centralized macros, **When** a user changes band boundaries in `config_age_bands.csv`, **Then** all models produce the updated labels after a `dbt build`.
2. **Given** the tenure band seed is customized to use `< 3, 3-7, 8-14, 15+`, **When** a simulation runs, **Then** every model that assigns tenure bands uses the new labels (no hardcoded remnants).

---

### User Story 3 - Schema Validation Tests Match Seed-Defined Labels (Priority: P3)

As a developer running `dbt test`, I need the `accepted_values` tests in `schema.yml` to match the actual seed-defined band labels so that tests catch real data quality issues rather than failing on correct data or passing on incorrect data.

**Why this priority**: Mismatched schema tests give false confidence — tests pass even when band labels are wrong because the test expectations are also wrong.

**Independent Test**: Run `dbt test --select` on the affected schema tests and verify they pass with seed-defined labels and fail if a model produces a non-seed label.

**Acceptance Scenarios**:

1. **Given** `schema.yml` accepted_values are updated to match seed labels, **When** `dbt test` is run, **Then** all band label validation tests pass.
2. **Given** a model is intentionally broken to produce `Under 25` instead of `< 25`, **When** `dbt test` is run, **Then** the accepted_values test for that model fails.

---

### User Story 4 - Cross-Model Band Consistency Validation (Priority: P3)

As a developer or plan actuary, I need an automated test that validates all band labels appearing in final output tables exist in the seed configuration tables, so that future regressions are caught immediately.

**Why this priority**: Prevents the same class of bug from recurring. A consistency test acts as a guardrail for all future model changes.

**Independent Test**: Run the new consistency test and verify it passes when all models are correct, and fails when a model is intentionally modified to produce a non-seed label.

**Acceptance Scenarios**:

1. **Given** a new cross-model consistency test exists, **When** all models produce seed-defined labels, **Then** the test passes.
2. **Given** a developer introduces a hardcoded band label in a new model, **When** `dbt test` is run, **Then** the consistency test fails and identifies the non-matching label and its source model.

---

### Edge Cases

- What happens when an employee's age is exactly on a band boundary (e.g., age 25, 35, 45)? The `[min, max)` convention means age 25 falls into `25-34`, not `< 25`.
- What happens when an employee has exactly 0 years of tenure (new hire on day 1)? They should fall into the `< 2` tenure band.
- What happens when the `dim_enrollment_hazards` model needs tenure comparisons that don't map directly to band labels? The fix must use corrected boundary logic aligned with seed definitions.
- What happens when a model receives a NULL age or tenure value? The band assignment should produce a NULL or identifiable "Unknown" band rather than silently misclassifying.
- What happens when the enrollment events model (v2) computes tenure in months rather than years? The band assignment must convert to years before applying band logic.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All 5 critically mismatched models MUST produce band labels that exactly match the seed-defined values in `config_age_bands.csv` and `config_tenure_bands.csv`.
- **FR-002**: All 14 fragile-but-correct models MUST replace hardcoded CASE statements with centralized band assignment macros so that labels are dynamically derived from seed tables.
- **FR-003**: The `dim_enrollment_hazards` model MUST use tenure boundary comparisons that align with the seed-defined tenure bands (`< 2`, `2-4`, `5-9`, `10-19`, `20+`).
- **FR-004**: The `events_enrollment_sql` macro MUST NOT split the `10-19` tenure band into `10-14` and `15-19`; it MUST use the single `10-19` band from the seed.
- **FR-005**: The `int_enrollment_events_v2` model MUST use seed-defined age bands (not `< 30, 30-39, 40-49, 50+`) and seed-defined tenure bands (not month-based `< 2 years, 2-5 years` etc.).
- **FR-006**: Schema validation tests in `schema.yml` MUST use accepted_values that match the seed-defined labels (e.g., `< 25` not `Under 25`).
- **FR-007**: A cross-model band consistency test MUST exist that validates all band labels in `fct_workforce_snapshot` are present in the corresponding seed configuration table.
- **FR-008**: The `[min, max)` interval convention (lower bound inclusive, upper bound exclusive) MUST be preserved in all band assignments.
- **FR-009**: Band assignment for NULL age or tenure values MUST produce a deterministic, identifiable result (NULL propagation or explicit handling).

### Key Entities

- **Age Band Configuration**: Defines age range boundaries and labels. Source of truth is the `config_age_bands.csv` seed. Labels: `< 25`, `25-34`, `35-44`, `45-54`, `55-64`, `65+`.
- **Tenure Band Configuration**: Defines tenure range boundaries and labels. Source of truth is the `config_tenure_bands.csv` seed. Labels: `< 2`, `2-4`, `5-9`, `10-19`, `20+`.
- **Band Assignment Macros**: Centralized logic that reads seed tables and generates CASE expressions dynamically. Entry points: `assign_age_band()` and `assign_tenure_band()`.
- **Hazard Rate Lookup Tables**: Tables that define event probabilities by age/tenure band. JOINs on band labels must match exactly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the fix, a simulation for year 2025 produces non-zero merit raise events across all age/tenure band combinations that have defined hazard rates (currently produces zero due to JOIN mismatches).
- **SC-002**: After the fix, a simulation for year 2025 produces non-zero enrollment events for eligible employees (currently affected by `dim_enrollment_hazards` and `int_enrollment_events_v2` mismatches).
- **SC-003**: 100% of band labels appearing in `fct_workforce_snapshot` exist in the corresponding seed configuration table (validated by the new cross-model consistency test).
- **SC-004**: All 19 affected models (5 critical + 14 fragile) produce band labels derived from the centralized seed configuration, with zero hardcoded CASE statements for band assignment remaining.
- **SC-005**: All existing dbt tests pass after the changes, including the updated `accepted_values` tests in `schema.yml`.
- **SC-006**: When a user customizes band boundaries via seed CSV changes, a full `dbt build` produces consistent labels across all models without any manual model edits.

## Assumptions

- The existing `assign_age_band()` and `assign_tenure_band()` macros correctly read from the seed tables and produce labels matching the seed CSV values. These macros are the trusted source of band assignment logic.
- The `[min, max)` interval convention documented in CLAUDE.md Section 9.1 is the correct behavior and should be preserved.
- The `dim_enrollment_hazards` model may need direct boundary corrections rather than macro calls if it uses tenure comparisons in a context where the macro doesn't directly apply (e.g., hazard rate definitions rather than employee band assignment).
- NULL handling for age/tenure follows existing macro behavior (NULL input produces NULL output).
- No changes to the seed CSV values themselves are required — the seeds are correct; the models are wrong.

## Scope

### In Scope

- Fixing 5 critically mismatched models to produce correct band labels
- Replacing hardcoded CASE statements in 14 fragile models with centralized macro calls
- Updating `schema.yml` accepted_values tests to match seed-defined labels
- Adding a cross-model band consistency dbt test
- Verifying the fix by running simulations and checking event generation

### Out of Scope

- Changing the seed CSV band definitions themselves
- Modifying the `assign_age_band()` or `assign_tenure_band()` macros
- Adding new band types or changing the band configuration UI
- Performance optimization of band assignment queries
- Changes to non-dbt Python code (orchestrator, CLI, API)
