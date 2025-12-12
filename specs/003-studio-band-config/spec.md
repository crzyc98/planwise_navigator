# Feature Specification: Studio Band Configuration Management

**Feature Branch**: `003-studio-band-config`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Add band configuration management to PlanAlign Studio. Allow users to view and edit age/tenure band definitions (config_age_bands.csv, config_tenure_bands.csv) through the web UI. Include validation for [min, max) interval convention, no gaps, and no overlaps. Changes should trigger dbt seed reload. The current UI has a configuration page for each simulation on the new hire strategy that we can configure the new hire age and compensation min max with a magic button for each that looks at the census. we need this to work"

## Context

Feature 001-centralize-band-definitions created centralized dbt seeds for age and tenure band definitions:
- `dbt/seeds/config_age_bands.csv` - Age band definitions (6 bands)
- `dbt/seeds/config_tenure_bands.csv` - Tenure band definitions (5 bands)

These bands are used throughout the simulation for hazard rate calculations, workforce segmentation, and event generation. Currently, bands can only be modified by directly editing the CSV files. This feature adds UI support for viewing, editing, and validating band configurations through PlanAlign Studio, following the existing UI pattern for "Match Census" magic buttons.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Band Configurations (Priority: P1)

As a simulation analyst, I want to view the current age and tenure band definitions in the UI so that I can understand how employees are being segmented without needing to access CSV files.

**Why this priority**: Without visibility into band configurations, users cannot make informed decisions about modifying them. This is the foundational capability upon which editing features depend.

**Independent Test**: Can be fully tested by navigating to the configuration page and verifying that band data from CSV seeds is displayed correctly in a table format.

**Acceptance Scenarios**:

1. **Given** I am on the scenario configuration page, **When** I navigate to the "Workforce Segmentation" or similar section, **Then** I see a table displaying all age bands with columns: Band ID, Label, Min Value, Max Value, Display Order
2. **Given** I am on the scenario configuration page, **When** I navigate to the band configuration section, **Then** I see a separate table displaying all tenure bands with the same column structure
3. **Given** the seed files contain 6 age bands and 5 tenure bands, **When** I view the band configuration UI, **Then** all bands are displayed in display_order sequence

---

### User Story 2 - Edit Band Definitions (Priority: P2)

As a simulation analyst, I want to edit band boundaries (min/max values) and labels so that I can customize segmentation to match my organization's workforce analysis needs.

**Why this priority**: Editing capability enables customization, which is the primary reason for exposing bands in the UI. Depends on P1 (view) being complete.

**Independent Test**: Can be tested by modifying a band boundary value and verifying the change persists after save.

**Acceptance Scenarios**:

1. **Given** I am viewing the age band configuration, **When** I change the max_value of band "25-34" from 35 to 40, **Then** the UI shows the updated value and displays it as unsaved
2. **Given** I have modified one or more band values, **When** I click Save, **Then** the changes are persisted and a success message is shown
3. **Given** I have modified band values, **When** I click Save, **Then** the system validates that changes maintain [min, max) interval convention, no gaps, and no overlaps before saving

---

### User Story 3 - Real-time Validation (Priority: P2)

As a simulation analyst, I want the system to validate my band edits in real-time so that I can avoid configuration errors before saving.

**Why this priority**: Validation prevents invalid configurations that would cause simulation failures. This is bundled with P2 because validation is integral to the editing experience.

**Independent Test**: Can be tested by entering invalid values and verifying appropriate error messages appear before attempting to save.

**Acceptance Scenarios**:

1. **Given** I am editing band configurations, **When** I create a gap (e.g., band 1 max=25, band 2 min=26), **Then** I see an immediate validation error: "Gap detected between bands: 25 to 26"
2. **Given** I am editing band configurations, **When** I create an overlap (e.g., band 1 max=30, band 2 min=25), **Then** I see an immediate validation error: "Overlap detected between bands at value 25"
3. **Given** I have validation errors, **When** I attempt to save, **Then** the save is blocked and errors are highlighted

---

### User Story 4 - "Match Census" Magic Button for Age Bands (Priority: P3)

As a simulation analyst, I want to click a "Match Census" button that analyzes the current census data and suggests appropriate age band boundaries based on the actual employee age distribution.

**Why this priority**: This follows the existing UI pattern for age distribution and compensation analysis. It adds significant value but requires P1/P2 to be useful.

**Independent Test**: Can be tested by clicking the "Match Census" button and verifying that suggested band boundaries reflect the census age distribution.

**Acceptance Scenarios**:

1. **Given** I have a valid census file configured for the scenario, **When** I click "Match Census" for age bands, **Then** the system analyzes the census and suggests band boundaries based on employee age distribution
2. **Given** the census shows employees clustered at ages 25-35 and 45-55, **When** I click "Match Census", **Then** the suggested bands optimize breakpoints to align with distribution clusters
3. **Given** suggested bands are displayed, **When** I click "Apply Suggestions", **Then** the band configuration is updated with the suggested values (but not yet saved)

---

### User Story 5 - "Match Census" Magic Button for Tenure Bands (Priority: P3)

As a simulation analyst, I want to click a "Match Census" button that analyzes tenure distribution and suggests appropriate tenure band boundaries.

**Why this priority**: Mirrors the age band magic button for consistency. Same priority as User Story 4.

**Independent Test**: Can be tested independently from age bands by clicking the tenure "Match Census" button.

**Acceptance Scenarios**:

1. **Given** I have a valid census file configured for the scenario, **When** I click "Match Census" for tenure bands, **Then** the system suggests tenure band boundaries based on employee tenure distribution
2. **Given** the census shows most employees have 0-5 years tenure with a long tail, **When** I click "Match Census", **Then** the suggested bands have finer granularity in the 0-5 range

---

### User Story 6 - Trigger dbt Seed Reload (Priority: P4)

As a simulation analyst, when I save band configuration changes, I want the system to automatically reload the dbt seeds so that my next simulation run uses the updated band definitions.

**Why this priority**: This is an implementation detail that ensures changes take effect. Lower priority because simulations can still be run with a manual seed reload.

**Independent Test**: Can be tested by saving band changes and verifying that a subsequent `dbt seed` reload is triggered.

**Acceptance Scenarios**:

1. **Given** I have saved band configuration changes, **When** I run a new simulation, **Then** the simulation uses the updated band definitions
2. **Given** I save changes to age bands, **When** the save completes, **Then** the system shows a message indicating that seeds will be reloaded for the next simulation

---

### Edge Cases

- What happens when a user tries to delete a band that is referenced in hazard rate configuration?
- How does the system handle band edits while a simulation is running?
- What happens if the census file is missing or invalid when "Match Census" is clicked?
- How are changes handled if two users edit bands simultaneously?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display current age band configurations from `config_age_bands.csv` in a tabular format
- **FR-002**: System MUST display current tenure band configurations from `config_tenure_bands.csv` in a tabular format
- **FR-003**: Users MUST be able to edit band_label, min_value, and max_value for each band
- **FR-004**: System MUST validate that bands follow [min, max) interval convention (min is inclusive, max is exclusive)
- **FR-005**: System MUST validate that bands have no gaps (next band min equals previous band max)
- **FR-006**: System MUST validate that bands have no overlaps (ranges don't intersect)
- **FR-007**: System MUST display validation errors in real-time as users edit
- **FR-008**: System MUST block save operation when validation errors exist
- **FR-009**: System MUST persist valid band changes to the appropriate seed CSV files
- **FR-010**: System MUST provide a "Match Census" button for age bands that analyzes census data
- **FR-011**: System MUST provide a "Match Census" button for tenure bands that analyzes census data
- **FR-012**: System SHOULD trigger dbt seed reload after saving band changes

### Key Entities

- **Age Band**: Represents an age range segment (band_id, band_label, min_value, max_value, display_order). Currently 6 bands covering ages 0-999.
- **Tenure Band**: Represents a tenure range segment (same structure as age band). Currently 5 bands covering tenure 0-999 years.
- **Census Analysis Result**: Output from analyzing census data for band suggestions, containing recommended breakpoints and distribution statistics.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view all band configurations without accessing CSV files directly
- **SC-002**: All validation errors are detected and displayed before user attempts to save
- **SC-003**: 100% of saved band configurations pass the dbt tests for gaps and overlaps (test_age_band_no_gaps, test_age_band_no_overlaps, test_tenure_band_no_gaps, test_tenure_band_no_overlaps)
- **SC-004**: "Match Census" analysis completes within 5 seconds for census files up to 100,000 employees
- **SC-005**: Zero regression in existing simulation functionality - all 7 event types maintain identical counts before and after band editing feature

## Technical Notes

### Existing Patterns to Follow

The ConfigStudio.tsx component already implements similar functionality:

1. **New Hire Age Distribution** - Table with editable weights per age, "Match Census" button calls `analyzeAgeDistribution()` API
2. **Job Level Compensation** - Table with editable min/max compensation per level, "Match Census" button calls `analyzeCompensation()` API

The band configuration UI should follow these patterns:
- Editable table with inline input fields
- Real-time validation with error messages
- "Match Census" magic button with loading state
- Success/error status indicators
- Integration with scenario save flow

### API Endpoints Needed

Based on existing patterns in `planalign_api/routers/`:

1. `GET /api/workspaces/{workspace_id}/config/bands` - Retrieve current band configurations
2. `PUT /api/workspaces/{workspace_id}/config/bands` - Save band configurations (with validation)
3. `POST /api/workspaces/{workspace_id}/analyze-age-bands` - Analyze census for age band suggestions
4. `POST /api/workspaces/{workspace_id}/analyze-tenure-bands` - Analyze census for tenure band suggestions

### Files to Modify

**Frontend (planalign_studio/)**:
- `services/api.ts` - Add band config API types and functions
- `components/ConfigStudio.tsx` - Add band configuration section with tables

**Backend (planalign_api/)**:
- `routers/files.py` or new `routers/bands.py` - Add band config endpoints
- `services/` - Add band analysis service

**dbt (dbt/)**:
- Existing seed files are the source of truth, will be written by API
