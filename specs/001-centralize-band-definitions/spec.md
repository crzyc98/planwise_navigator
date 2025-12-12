# Feature Specification: Centralize Age/Tenure Band Definitions

**Feature Branch**: `001-centralize-band-definitions`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Centralize hardcoded age/tenure band definitions from 25+ SQL files into configurable seeds and dbt macros. Preserved behavior: same band boundaries, identical hazard calculations and event counts."

## Clarifications

### Session 2025-12-12

- Q: How should boundary edge cases be handled (e.g., age exactly 35)? → A: Lower bound inclusive - standard [min, max) interval convention. Age 35 falls into "35-44" band, not "<35" band.
- Q: What happens when band configuration validation fails? → A: Fail fast - abort pipeline execution immediately with descriptive error message.
- Q: What happens if a model references a non-existent band? → A: Fail fast - treat as validation error, abort with error identifying the missing band.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Data Administrator Updates Band Boundaries (Priority: P1)

A data administrator needs to modify age or tenure band boundaries to reflect new actuarial assumptions or regulatory requirements. Currently, this requires editing 25+ SQL files, risking inconsistencies. With centralized definitions, the administrator updates a single configuration source and all downstream calculations automatically use the new boundaries.

**Why this priority**: This is the core value proposition. Without single-source-of-truth band definitions, every band boundary change risks calculation inconsistencies and requires error-prone multi-file edits.

**Independent Test**: Can be fully tested by modifying the centralized band configuration, running the simulation pipeline, and verifying that all models reference the updated boundaries correctly.

**Acceptance Scenarios**:

1. **Given** a centralized age band configuration exists, **When** an administrator modifies an age band boundary (e.g., changes 35-44 to 35-49), **Then** all 25+ dependent models use the updated boundary without manual edits.
2. **Given** the current hardcoded band definitions, **When** the centralization is complete with identical boundaries, **Then** hazard calculations produce exactly the same results as before (zero regression).
3. **Given** a centralized tenure band configuration, **When** a tenure band is added or removed, **Then** the simulation pipeline completes successfully with the new band structure.

---

### User Story 2 - Developer Maintains Band Logic (Priority: P2)

A developer maintaining the simulation codebase needs to understand and modify band-related logic. Currently, band definitions are scattered across 25+ files with potential inconsistencies. With centralized definitions, the developer finds all band logic in one location with reusable helpers, reducing debugging time and change risk.

**Why this priority**: Developer productivity directly affects feature velocity and code quality. Centralized definitions reduce maintenance burden and cognitive load.

**Independent Test**: Can be tested by asking a developer to locate and modify band logic, measuring time-to-change and number of files touched.

**Acceptance Scenarios**:

1. **Given** band definitions are centralized, **When** a developer searches for age band logic, **Then** they find a single authoritative source rather than 25+ scattered definitions.
2. **Given** reusable band assignment helpers exist, **When** a developer creates a new model requiring band assignments, **Then** they call the centralized helper instead of copying/pasting band logic.
3. **Given** the centralized band system is documented, **When** a new team member onboards, **Then** they understand the band architecture within one documentation page.

---

### User Story 3 - Auditor Validates Band Consistency (Priority: P3)

An auditor or compliance officer needs to verify that band definitions are consistent across all calculations for regulatory reporting. With centralized definitions, the auditor can inspect a single source of truth and have confidence that all downstream calculations use identical boundaries.

**Why this priority**: Audit and compliance validation is critical but less frequent than daily development or configuration changes.

**Independent Test**: Can be tested by producing an audit report showing band definition source and all dependent models.

**Acceptance Scenarios**:

1. **Given** centralized band definitions, **When** an auditor requests proof of consistent band usage, **Then** a single configuration file demonstrates the authoritative boundaries.
2. **Given** the migration is complete, **When** comparing pre-migration and post-migration event counts, **Then** counts are identical for all band-related calculations.

---

### Edge Cases

- Invalid band configurations (negative age, overlapping ranges, gaps) cause immediate pipeline abort with descriptive error.
- Zero tenure (new hires) falls into the first tenure band per [min, max) convention (e.g., [0, 1) years).
- References to non-existent bands cause immediate pipeline abort with error identifying the missing band.
- Band boundaries use [min, max) convention: exactly age 35 falls into "35-44" band (lower bound inclusive).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a single authoritative source for all age band definitions used across the simulation.
- **FR-002**: System MUST provide a single authoritative source for all tenure band definitions used across the simulation.
- **FR-003**: System MUST expose reusable helpers that assign entities to the correct band based on their age or tenure value.
- **FR-004**: All 25+ existing models with hardcoded band definitions MUST be updated to reference the centralized source.
- **FR-005**: System MUST maintain exact backward compatibility: running with centralized bands MUST produce identical hazard calculations and event counts as the current hardcoded approach.
- **FR-006**: Band boundaries MUST be validated on load; invalid configurations (overlapping ranges, gaps, negative values) MUST cause immediate pipeline abort with descriptive error message.
- **FR-007**: System MUST use [min, max) interval convention: lower bound inclusive, upper bound exclusive. An employee aged exactly 35 is assigned to the "35-44" band, not "<35".
- **FR-008**: System MUST document the band configuration schema and usage patterns for maintainers.

### Key Entities

- **Age Band**: A range defining an age group for actuarial calculations. Attributes: band identifier, lower bound (inclusive), upper bound (exclusive), display label.
- **Tenure Band**: A range defining a tenure group for turnover and vesting calculations. Attributes: band identifier, lower bound (inclusive), upper bound (exclusive), display label.
- **Band Assignment**: The mapping of an individual entity (employee) to their appropriate age and tenure bands based on current values.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of previously hardcoded band definitions (25+ files) are replaced with centralized references.
- **SC-002**: Band boundary changes require editing exactly 1 configuration source instead of 25+ files.
- **SC-003**: Regression test passes: event counts before and after centralization differ by 0% for all simulation scenarios.
- **SC-004**: Hazard calculation outputs before and after centralization are byte-identical for identical inputs.
- **SC-005**: New models requiring band assignments can be implemented using a reusable helper, reducing band-related code duplication by at least 90%.
- **SC-006**: Band configuration validation catches 100% of invalid configurations (overlapping ranges, gaps) at load time before simulation execution.

## Assumptions

- The existing 25+ SQL files all use conceptually identical band boundaries (same age ranges, same tenure ranges), even if implemented with slight syntax variations.
- Band boundaries use inclusive lower bounds and exclusive upper bounds as the standard convention.
- The centralized configuration format will be human-readable and version-controllable.
- No changes to band boundaries are required as part of this feature; this is purely a refactoring for maintainability.
- Performance impact of centralized band lookups is negligible compared to current inline definitions.

## Out of Scope

- Adding new band types beyond age and tenure.
- Modifying actual band boundary values (this feature preserves existing boundaries).
- User interface for band configuration editing (this is a backend/configuration change only).
- Historical versioning of band definitions (bands are point-in-time configurations).
