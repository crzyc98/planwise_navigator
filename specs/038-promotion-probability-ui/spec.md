# Feature Specification: Promotion Hazard Configuration UI

**Feature Branch**: `038-promotion-probability-ui`
**Created**: 2026-02-09
**Status**: Draft
**Input**: User description: "can we add the promotion probability to the ui? its a part of the config_job_levels.csv"

## Clarifications

### Session 2026-02-09

- Q: Which promotion hazard parameters should be exposed in the UI? → A: All three seeds: base rate + level dampener (`config_promotion_hazard_base.csv`), age multipliers (`config_promotion_hazard_age_multipliers.csv`), and tenure multipliers (`config_promotion_hazard_tenure_multipliers.csv`) — 13 values from 3 CSV files.
- Q: Where should the Promotion Hazard section be placed on the Configuration page? → A: As a new standalone "Promotion Hazard" section placed after the Job Level Compensation section.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Promotion Hazard Parameters (Priority: P1)

A plan administrator opens the Configuration page in PlanAlign Studio and scrolls to the new "Promotion Hazard" section (placed after the Job Level Compensation section). It displays the three components that drive promotion probability in the simulation:
- **Base parameters**: base rate (2%) and level dampener factor (15%)
- **Age multipliers**: a table of 6 multipliers by age band (e.g., < 25 → 1.6, 25-34 → 1.4, etc.)
- **Tenure multipliers**: a table of 5 multipliers by tenure band (e.g., < 2 → 0.5, 2-4 → 1.5, etc.)

This gives them immediate visibility into the actual parameters that drive promotions in the simulation.

**Why this priority**: Visibility is the foundation — users need to see the current values before they can decide whether to change them. This is also the lowest-risk change and delivers value on its own.

**Independent Test**: Can be fully tested by loading the Configuration page and verifying the promotion hazard section appears with correct values from the three seed CSVs.

**Acceptance Scenarios**:

1. **Given** the Configuration page is loaded with a workspace, **When** the user views the Promotion Hazard section, **Then** the base rate (2%), level dampener (15%), and all age/tenure multiplier values are displayed matching the seed CSV data.
2. **Given** a seed CSV has been updated externally, **When** the user reloads the Configuration page, **Then** the displayed values reflect the updated seed data.

---

### User Story 2 - Edit Promotion Hazard Parameters (Priority: P2)

A plan administrator wants to model a scenario with more aggressive promotions. They increase the base rate from 2% to 4% and adjust the age multiplier for the 25-34 band from 1.4 to 1.8. They save the changes, and the updated values persist and are used in the next simulation run.

**Why this priority**: Editing enables "what-if" scenario modeling, which is the core value of PlanAlign Studio. This builds on the P1 visibility story.

**Independent Test**: Can be fully tested by changing hazard parameter values in the UI, saving, reloading the page, and verifying the values persist.

**Acceptance Scenarios**:

1. **Given** the user is viewing the Promotion Hazard section, **When** they change the base rate, level dampener, or any multiplier, **Then** the input accepts the new value and the save button becomes active.
2. **Given** the user has edited hazard parameters, **When** they save the configuration, **Then** the system validates the values and persists them.
3. **Given** the user enters an invalid value (e.g., negative multiplier or base rate > 100%), **When** they attempt to save, **Then** the system displays a clear validation error and prevents the save.
4. **Given** the user saves valid changes, **When** they reload the page, **Then** the saved values are displayed correctly.

---

### Edge Cases

- What happens when the base rate is set to 0? The system should accept it — a 0% base rate means no promotions occur.
- What happens when a multiplier is set to 0? The system should accept it — a 0 multiplier means that age/tenure band contributes no promotion probability.
- What happens when the level dampener is set to 0? The system should accept it — all levels would have the same base promotion rate (no dampening by seniority).
- What happens if a seed CSV is missing or malformed? The system should display hardcoded defaults and show an informational message.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Configuration page MUST display a "Promotion Hazard" section showing the base rate, level dampener factor, age multipliers, and tenure multipliers that drive the simulation's promotion model.
- **FR-002**: The base rate MUST be displayed as a percentage (e.g., "2" for 2%, not "0.02"). The level dampener MUST also be displayed as a percentage (e.g., "15" for 0.15).
- **FR-003**: Age and tenure multipliers MUST be displayed as decimal values (e.g., 1.6, 0.5) with their corresponding band labels.
- **FR-004**: Users MUST be able to edit all promotion hazard parameters via inline input fields.
- **FR-005**: The system MUST validate that the base rate is between 0 and 100 (inclusive), the level dampener is between 0 and 100 (inclusive), and multipliers are non-negative.
- **FR-006**: The system MUST persist edited values so they are used by subsequent simulation runs.
- **FR-007**: The system MUST load promotion hazard values from the seed CSVs (or workspace/scenario config) when the configuration page is loaded.

### Key Entities

- **Promotion Hazard Base**: Global parameters controlling promotion rates. Attributes: base_rate (0.00–1.00), level_dampener_factor (0.00–1.00). Source: `config_promotion_hazard_base.csv`.
- **Promotion Age Multiplier**: Per-age-band multiplier applied to the base promotion rate. Attributes: age_band (label), multiplier (non-negative decimal). Source: `config_promotion_hazard_age_multipliers.csv`. 6 bands.
- **Promotion Tenure Multiplier**: Per-tenure-band multiplier applied to the base promotion rate. Attributes: tenure_band (label), multiplier (non-negative decimal). Source: `config_promotion_hazard_tenure_multipliers.csv`. 5 bands.
- **Promotion Probability Formula**: `base_rate * tenure_multiplier * age_multiplier * max(0, 1 - level_dampener * (level - 1))`, capped at 1.0.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view all promotion hazard parameters within the existing Configuration page without navigating to a separate screen.
- **SC-002**: Users can edit and save promotion hazard parameter changes in under 60 seconds.
- **SC-003**: Saved values are used by subsequent simulation runs (the promotion hazard model consumes these parameters).
- **SC-004**: Invalid inputs (negative multipliers, base rate > 100%, non-numeric) are rejected with a clear error message before saving.

## Assumptions

- The three promotion hazard seed CSVs already exist and are consumed by `dim_promotion_hazards.sql` in the simulation.
- Values are stored as decimals (base_rate=0.02, multipliers=1.6) in the seeds. The UI converts base rate and level dampener to percentages for display but shows multipliers as-is.
- The existing Configuration page in PlanAlign Studio is the correct location for this section.
- The save workflow will follow the existing pattern (workspace YAML config or band-config-style direct CSV write — to be determined in planning).
- The band labels (e.g., "< 25", "25-34", "2-4") are read-only — only the multiplier values are editable.
