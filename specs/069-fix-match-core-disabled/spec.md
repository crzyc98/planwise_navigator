# Feature Specification: Fix DC Plan Match/Core Contributions Calculated When Disabled

**Feature Branch**: `069-fix-match-core-disabled`
**Created**: 2026-03-13
**Status**: Draft
**Input**: User description: "if i disable the match on the scenario on the dc plan page its still calculating and giving it. this is a bug. i'm not sure but this could be happening on the core too?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Disabling Employer Match Stops Match Calculations (Priority: P1)

As a plan analyst, when I disable the employer match toggle on the DC Plan configuration page for a scenario, the simulation should produce $0 employer match contributions for all employees in that scenario. Currently, disabling the match toggle has no effect — match amounts are still calculated and included in results.

**Why this priority**: This is the primary reported bug. Match contributions flowing through when disabled produces incorrect financial projections and misleading cost estimates.

**Independent Test**: Disable the match toggle in the DC Plan UI for a scenario, run the simulation, and verify that all employer match amounts are $0 in the workforce snapshot.

**Acceptance Scenarios**:

1. **Given** a scenario with match disabled (`match_enabled: false`) in DC Plan config, **When** the simulation runs, **Then** all employees receive $0 employer match contribution and the match status shows "disabled".
2. **Given** a scenario with match enabled (`match_enabled: true`) in DC Plan config, **When** the simulation runs, **Then** match contributions are calculated normally using the configured formula (no regression).
3. **Given** a scenario where match was previously enabled and is now toggled off, **When** the simulation re-runs, **Then** the new results reflect $0 match contributions.

---

### User Story 2 - Disabling Core Contribution Stops Core Calculations (Priority: P1)

As a plan analyst, when I disable the core contribution toggle on the DC Plan configuration page for a scenario, the simulation should produce $0 employer core contributions. The core contribution has an existing `employer_core_enabled` flag in the calculation model, but this flag may not be correctly wired from the UI toggle through the config export pipeline.

**Why this priority**: Same class of bug as match — if core contributions flow through when disabled, financial projections are wrong. Both need to be verified and fixed together.

**Independent Test**: Disable the core contribution toggle in the DC Plan UI for a scenario, run the simulation, and verify that all employer core amounts are $0.

**Acceptance Scenarios**:

1. **Given** a scenario with core contribution disabled (`core_enabled: false`) in DC Plan config, **When** the simulation runs, **Then** all employees receive $0 employer core contribution.
2. **Given** a scenario with core contribution enabled, **When** the simulation runs, **Then** core contributions are calculated normally (no regression).

---

### User Story 3 - Match/Core Disabled State Persists Across Sessions (Priority: P2)

As a plan analyst, when I save a scenario with match or core disabled, the disabled state should persist when I reload the scenario or run it later.

**Why this priority**: Configuration persistence is essential for the fix to be useful in real workflows, but is secondary to the calculation fix itself.

**Independent Test**: Disable match/core, save, reload the scenario config page, and confirm the toggles show the disabled state.

**Acceptance Scenarios**:

1. **Given** a scenario saved with match disabled, **When** the scenario config is reloaded, **Then** the match toggle shows disabled and the saved `match_enabled: false` value is present in the config.
2. **Given** a scenario saved with core disabled, **When** the scenario config is reloaded, **Then** the core toggle shows disabled.

---

### Edge Cases

- What happens when match is disabled but the match formula/tiers are still configured? The tiers should be preserved for re-enabling but not used in calculations.
- What happens when match is disabled mid-simulation (multi-year)? The disabled flag should apply consistently to all years in the run.
- What happens when the base config has match enabled but the scenario override disables it? The scenario override must take precedence.
- What happens to downstream models (workforce snapshot, contribution events) when match/core are disabled? All downstream employer match/core amounts should be $0.
- What happens when neither match nor core is explicitly set in config (legacy scenarios)? Both should default to enabled to preserve backward compatibility.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST honor the `match_enabled` flag from the DC Plan scenario configuration. When `match_enabled` is `false`, all employer match calculations MUST produce $0.
- **FR-002**: System MUST propagate the `match_enabled` flag from the UI through the API, orchestrator config export, and into simulation variables so the match calculation model can gate on it.
- **FR-003**: System MUST verify the existing `employer_core_enabled` flag is correctly wired end-to-end from UI toggle through API, config export, and into the calculation model.
- **FR-004**: System MUST include match/core enabled status in the simulation audit trail so analysts can verify which contributions were active for a given run.
- **FR-005**: System MUST default `match_enabled` to `true` and `core_enabled` to `true` when the flag is not explicitly set, preserving backward compatibility with existing scenarios.
- **FR-006**: System MUST preserve match formula/tier configuration when match is disabled, allowing analysts to re-enable without reconfiguring.

### Key Entities

- **Scenario Config Override**: Contains `dc_plan.match_enabled` and `dc_plan.core_enabled` boolean flags that control whether employer contributions are calculated.
- **Config Export Variables**: `employer_match_enabled` (new) and `employer_core_enabled` (existing) boolean variables passed to calculation models.
- **Match Calculation Model**: Gates all match amounts on the enabled flag — returns $0 when disabled.
- **Core Contribution Model**: Already gates on `employer_core_enabled` — requires end-to-end verification that the UI toggle correctly sets this variable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When match is disabled in the DC Plan UI, 100% of employees in the simulation output have $0 employer match contribution.
- **SC-002**: When core is disabled in the DC Plan UI, 100% of employees in the simulation output have $0 employer core contribution.
- **SC-003**: Enabling match/core produces identical results to the current behavior (zero regression in calculated amounts).
- **SC-004**: The enabled/disabled state round-trips correctly: set in UI, persisted via API, loaded on page reload, and applied in simulation.

## Assumptions

- The UI already sends `match_enabled` in the `dc_plan` payload (confirmed in `buildConfigPayload.ts`). The bug is that the backend ignores this field during config export.
- The `employer_core_enabled` variable exists in the calculation model and properly gates on it. The core fix likely only requires verifying the config export pipeline correctly maps the UI toggle to this variable.
- No database schema changes are needed — this is a config propagation and calculation gating fix.
- The fix applies to both CLI and Studio simulation paths since both use the same orchestrator config export.
