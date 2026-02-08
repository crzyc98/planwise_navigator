# Feature Specification: Events Module Modularization

**Feature Branch**: `035-events-modularization`
**Created**: 2026-02-06
**Status**: Draft
**Input**: User description: "Modularize config/events.py (~1,000 lines) into domain-specific submodules with shared validators and backwards-compatible imports"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Navigate to Domain-Specific Event Code (Priority: P1)

A developer working on DC Plan contribution logic wants to quickly locate and modify the ContributionPayload class without scrolling through 1,000+ lines of unrelated workforce and admin event code.

**Why this priority**: This is the core value proposition - reducing cognitive load and improving developer productivity when maintaining event-related code. A merge conflict hotspot becomes navigable domain modules.

**Independent Test**: Can be fully tested by verifying that domain-specific payloads exist in separate modules and that IDEs/editors can navigate directly to them.

**Acceptance Scenarios**:

1. **Given** a developer needs to modify ContributionPayload, **When** they navigate to `config/events/dc_plan.py`, **Then** they find ContributionPayload without scrolling through workforce events.
2. **Given** a developer needs to add a new workforce event type, **When** they open `config/events/workforce.py`, **Then** they see only workforce-related payloads and factories.
3. **Given** a developer wants to understand admin events, **When** they open `config/events/admin.py`, **Then** they find forfeiture, HCE, and compliance payloads grouped together.

---

### User Story 2 - Import Events Using Existing Paths (Priority: P1)

An existing codebase has 20+ files importing from `config.events`. After modularization, these imports must continue working without any code changes.

**Why this priority**: Breaking existing imports would cause widespread failures across the codebase. Backward compatibility is essential for a safe refactoring.

**Independent Test**: Can be fully tested by running the existing test suite and verifying all imports resolve correctly.

**Acceptance Scenarios**:

1. **Given** code imports `from config.events import SimulationEvent`, **When** the module is loaded, **Then** SimulationEvent is successfully imported.
2. **Given** code imports `from config.events import WorkforceEventFactory`, **When** the factory is called, **Then** it creates events identically to before.
3. **Given** code imports `from config.events import HirePayload, ContributionPayload`, **When** both are used, **Then** both work as expected.
4. **Given** code uses `config.events.__all__`, **When** iterating exports, **Then** all previously exported symbols remain available.

---

### User Story 3 - Use Shared Validators Without Duplication (Priority: P2)

A developer creating a new payload class needs to validate Decimal precision for compensation. Instead of copying the same validator from HirePayload, they import a shared helper.

**Why this priority**: Reducing code duplication improves maintainability. Currently, the same Decimal quantization logic is repeated 15+ times across different payloads.

**Independent Test**: Can be fully tested by creating a new payload that uses shared validators and verifying validation behavior.

**Acceptance Scenarios**:

1. **Given** a shared validator `validate_compensation_precision` exists, **When** HirePayload uses it, **Then** compensation is quantized to 6 decimal places.
2. **Given** a shared validator `validate_rate_precision` exists, **When** EnrollmentPayload uses it, **Then** contribution rates are quantized to 4 decimal places.
3. **Given** a developer creates a new payload, **When** they import `validate_compensation_precision`, **Then** they can reuse the standard validation logic.

---

### User Story 4 - Test Shared Validators Independently (Priority: P3)

A developer wants to ensure the shared validation helpers correctly handle edge cases (zero, negative, very large numbers) without testing through every payload that uses them.

**Why this priority**: Centralized validators need their own test coverage to ensure edge cases are handled consistently across all consumers.

**Independent Test**: Can be fully tested by running unit tests for the validators module in isolation.

**Acceptance Scenarios**:

1. **Given** a test for `validate_compensation_precision`, **When** given `Decimal("100000.123456789")`, **Then** it returns `Decimal("100000.123457")` (rounded to 6 places).
2. **Given** a test for `validate_rate_precision`, **When** given `Decimal("0.12345")`, **Then** it returns `Decimal("0.1235")` (rounded to 4 places).
3. **Given** a test for `validate_amount_precision`, **When** given `Decimal("-100")`, **Then** it still quantizes (validation for positivity is handled by Field constraints).

---

### Edge Cases

- What happens when importing a symbol that was never in `__all__`? (Should raise ImportError as before)
- How does circular import prevention work between submodules? (Each submodule should be self-contained)
- What happens if a validator receives a non-Decimal type? (Pydantic handles type coercion before validators run)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST organize event payloads into domain-specific submodules: `config/events/workforce.py` (HirePayload, PromotionPayload, TerminationPayload, MeritPayload, SabbaticalPayload), `config/events/dc_plan.py` (EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload, AutoEnrollmentWindowPayload, EnrollmentChangePayload), and `config/events/admin.py` (ForfeiturePayload, HCEStatusPayload, ComplianceEventPayload).
- **FR-002**: System MUST provide a shared validators module at `config/events/validators.py` containing reusable Decimal quantization functions for compensation (6 places), rates (4 places), and amounts (6 places).
- **FR-003**: System MUST maintain backward compatibility by re-exporting all existing public symbols from `config/events.py` (the compatibility layer).
- **FR-004**: System MUST keep SimulationEvent and factory classes (EventFactory, WorkforceEventFactory, DCPlanEventFactory, PlanAdministrationEventFactory) in a core module that imports payloads from submodules.
- **FR-005**: System MUST preserve the existing `__all__` export list in `config/events.py` with identical symbols.
- **FR-006**: System MUST ensure all existing tests pass without modification to their import statements.
- **FR-007**: Shared validators MUST have their own unit tests covering edge cases (zero values, maximum precision, rounding behavior).

### Key Entities

- **Payload Classes**: Domain-specific data models representing event details (e.g., HirePayload, ContributionPayload)
- **Factories**: Classes that create validated SimulationEvent instances (WorkforceEventFactory, DCPlanEventFactory, PlanAdministrationEventFactory)
- **Validators**: Reusable functions for Decimal precision standardization
- **SimulationEvent**: Core event model with discriminated union payload routing

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can locate any payload class within 3 files instead of searching 1,000+ line file
- **SC-002**: 100% of existing imports from `config.events` continue working without modification
- **SC-003**: Shared validator functions reduce duplicated quantization code by consolidating 15+ validators into 3 reusable helpers
- **SC-004**: All 256+ existing tests pass with no changes to import statements
- **SC-005**: Each domain submodule contains fewer than 300 lines of code
- **SC-006**: New payload additions require changes to only the relevant domain submodule (not the entire events.py)

## Assumptions

- The current module structure allows creating a `config/events/` directory alongside `config/events.py` (Python package mechanics)
- Pydantic v2 field validators can call standalone functions without issues
- The re-export pattern (`from .workforce import *`) is acceptable for the compatibility layer
- No runtime performance degradation is acceptable from the additional import indirection
