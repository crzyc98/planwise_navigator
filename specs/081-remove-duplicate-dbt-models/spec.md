# Feature Specification: Remove Duplicate/Versioned dbt Models (v2 Cleanup)

**Feature Branch**: `081-remove-duplicate-dbt-models`
**Created**: 2026-03-19
**Status**: Draft
**Input**: GitHub Issue #258 — Remove duplicate/versioned dbt models (v2 cleanup)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Remove Unused Model Variants (Priority: P1)

As a developer maintaining the dbt project, I want unused model variants (v2, optimized) removed so that I can confidently identify which model is authoritative without inspecting downstream references.

**Why this priority**: Unused models create confusion and maintenance burden. Developers may accidentally reference the wrong version, introducing bugs. This is the highest-value cleanup because it eliminates dead code with zero risk to production.

**Independent Test**: Run `dbt build --threads 1 --fail-fast` after removing unused models. All downstream models must compile and pass tests identically to before the change.

**Acceptance Scenarios**:

1. **Given** `int_enrollment_events_v2.sql` has zero downstream references, **When** it is removed, **Then** `dbt build` completes successfully with no errors or test failures.
2. **Given** `int_enrollment_events_optimized.sql` is only referenced by a debug model, **When** it is removed along with its debug reference, **Then** `dbt build` completes successfully.
3. **Given** `int_promotion_events_optimized.sql` has zero downstream references, **When** it is removed, **Then** `dbt build` completes successfully.
4. **Given** the base `int_deferral_rate_state_accumulator.sql` is superseded by the v2 version, **When** the unused base version is removed, **Then** `dbt build` completes successfully.
5. **Given** the base `int_workforce_previous_year.sql` is superseded by the v2 version, **When** the unused base version is removed, **Then** `dbt build` completes successfully.

---

### User Story 2 - Rename Active v2 Models to Drop Suffix (Priority: P2)

As a developer, I want active v2 models renamed to their canonical names (without the `_v2` suffix) so that model naming is consistent and follows the project's `tier_entity_purpose` convention.

**Why this priority**: After removing unused variants (P1), the remaining active models with `_v2` suffixes should be renamed to their canonical names. This depends on P1 being completed first, as both the old base and new v2 cannot coexist with the same name.

**Independent Test**: After renaming, run `dbt build --threads 1 --fail-fast` and verify all downstream `ref()` calls resolve correctly with the new names.

**Acceptance Scenarios**:

1. **Given** `int_deferral_rate_state_accumulator_v2` is the active version, **When** it is renamed to `int_deferral_rate_state_accumulator`, **Then** all 7 downstream models that reference it are updated and `dbt build` passes.
2. **Given** `int_workforce_previous_year_v2` is the active version, **When** it is renamed to `int_workforce_previous_year`, **Then** the downstream model `int_year_snapshot_preparation` is updated and `dbt build` passes.

---

### User Story 3 - Verify Simulation Output Consistency (Priority: P3)

As a simulation analyst, I want confirmation that the cleanup produces identical simulation results so that I can trust the refactoring did not alter any business logic.

**Why this priority**: This is a validation step that builds confidence in the cleanup. It is lower priority because the rename and removal operations are mechanically safe (only changing file names and `ref()` strings), but verifying output equivalence provides the final seal of correctness.

**Independent Test**: Run a baseline simulation before and after the cleanup. Compare `fct_yearly_events` and `fct_workforce_snapshot` row counts and checksums for a single-year simulation.

**Acceptance Scenarios**:

1. **Given** a simulation run before cleanup produces N rows in `fct_yearly_events`, **When** the same simulation is run after cleanup with the same seed, **Then** it produces exactly N rows with identical content.
2. **Given** a simulation run before cleanup produces a workforce snapshot, **When** the same simulation is run after cleanup, **Then** the snapshot is byte-identical.

---

### Edge Cases

- What happens if a removed model is referenced by a model outside the standard `dbt/models/` directory (e.g., in `dbt/models/analysis/` debug models)? Those references must also be updated or the debug model removed.
- What happens if the `dq_deferral_rate_state_audit_validation_v2` data quality model references the old base accumulator name? All data quality models must be checked for stale references.
- What happens if any Python orchestrator code references model names by string (e.g., in `dbt run --select` commands)? Those references must be updated to match new canonical names.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST remove all dbt model files that have zero downstream references and are superseded by an active variant.
- **FR-002**: Active models with `_v2` suffixes MUST be renamed to their canonical names (dropping the `_v2` suffix).
- **FR-003**: All downstream `ref()` calls MUST be updated to reference the renamed models.
- **FR-004**: Any Python orchestrator code that references model names by string MUST be updated to use the new canonical names.
- **FR-005**: The full dbt build (`dbt build --threads 1 --fail-fast`) MUST pass after all changes with zero errors and zero test failures.
- **FR-006**: Simulation output MUST be identical before and after the cleanup for the same input parameters and random seed.
- **FR-007**: Debug/analysis models that reference removed models MUST either be updated to reference the active model or be removed if they are no longer useful.

### Key Entities

- **Unused Models (to remove)**: `int_enrollment_events_v2`, `int_enrollment_events_optimized`, `int_promotion_events_optimized`, base `int_deferral_rate_state_accumulator`, base `int_workforce_previous_year`
- **Active v2 Models (to rename)**: `int_deferral_rate_state_accumulator_v2` (rename to `int_deferral_rate_state_accumulator`), `int_workforce_previous_year_v2` (rename to `int_workforce_previous_year`)
- **Downstream References**: All models using `ref('model_name')` for any affected model must be updated

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Total number of dbt model files is reduced by at least 5 (the unused variants removed).
- **SC-002**: Zero dbt models contain a `_v2` or `_optimized` suffix in their filename after cleanup.
- **SC-003**: `dbt build --threads 1 --fail-fast` completes with zero errors and zero test failures.
- **SC-004**: A single-year simulation produces identical `fct_yearly_events` and `fct_workforce_snapshot` output before and after cleanup (same row counts, same data).
- **SC-005**: No Python source files contain string references to removed or renamed model names.

## Assumptions

- The `dq_deferral_rate_state_audit_validation_v2` data quality model is a separate concern and will be evaluated independently — if both versions are actively used for different validation purposes, they are out of scope for this cleanup.
- The `int_workforce_snapshot_optimized` model is actively referenced by downstream models for match/contribution calculations and is NOT a duplicate — it is out of scope for removal.
- Debug/analysis models in `dbt/models/analysis/` that only reference removed models can be safely removed or updated without affecting production simulation output.
