# Requirements Checklist: Studio Band Configuration Management

**Feature Branch**: `003-studio-band-config`
**Spec Version**: Draft 2025-12-12

## Functional Requirements

### View Capabilities (P1)
- [ ] **FR-001**: Display age band configurations in tabular format
  - [ ] Columns: Band ID, Label, Min Value, Max Value, Display Order
  - [ ] Data loaded from `config_age_bands.csv`
  - [ ] Bands displayed in display_order sequence
- [ ] **FR-002**: Display tenure band configurations in tabular format
  - [ ] Same column structure as age bands
  - [ ] Data loaded from `config_tenure_bands.csv`

### Edit Capabilities (P2)
- [ ] **FR-003**: Allow editing of band_label, min_value, max_value
  - [ ] Inline editing in table cells
  - [ ] Visual indicator for unsaved changes
  - [ ] band_id and display_order are read-only

### Validation (P2)
- [ ] **FR-004**: Validate [min, max) interval convention
  - [ ] min_value is inclusive
  - [ ] max_value is exclusive
  - [ ] First band min_value must be 0
  - [ ] Last band max_value must cover upper bound (999)
- [ ] **FR-005**: Validate no gaps between bands
  - [ ] next_band.min_value == previous_band.max_value
  - [ ] Error message format: "Gap detected between bands: X to Y"
- [ ] **FR-006**: Validate no overlaps between bands
  - [ ] Ranges must not intersect
  - [ ] Error message format: "Overlap detected between bands at value X"
- [ ] **FR-007**: Display validation errors in real-time
  - [ ] Errors shown immediately as user types
  - [ ] Error highlighting on affected rows
- [ ] **FR-008**: Block save when validation errors exist
  - [ ] Save button disabled
  - [ ] Clear error summary

### Persistence (P2)
- [ ] **FR-009**: Persist valid band changes to CSV files
  - [ ] Write to `dbt/seeds/config_age_bands.csv`
  - [ ] Write to `dbt/seeds/config_tenure_bands.csv`
  - [ ] Preserve CSV header row
  - [ ] Success message on save

### Census Analysis (P3)
- [ ] **FR-010**: "Match Census" for age bands
  - [ ] API endpoint to analyze census age distribution
  - [ ] Algorithm to suggest optimal band boundaries
  - [ ] Loading state while analyzing
  - [ ] Apply/Cancel suggested values
- [ ] **FR-011**: "Match Census" for tenure bands
  - [ ] API endpoint to analyze census tenure distribution
  - [ ] Same UX pattern as age bands

### Integration (P4)
- [ ] **FR-012**: Trigger dbt seed reload
  - [ ] After saving band changes
  - [ ] Display reload status message
  - [ ] Ensure next simulation uses updated bands

## Success Criteria

- [ ] **SC-001**: View bands without CSV file access
- [ ] **SC-002**: All validation errors detected before save attempt
- [ ] **SC-003**: 100% pass rate on dbt band validation tests
- [ ] **SC-004**: "Match Census" completes in <5 seconds for 100K employees
- [ ] **SC-005**: Zero regression in simulation event counts

## API Endpoints

- [ ] `GET /api/workspaces/{workspace_id}/config/bands`
- [ ] `PUT /api/workspaces/{workspace_id}/config/bands`
- [ ] `POST /api/workspaces/{workspace_id}/analyze-age-bands`
- [ ] `POST /api/workspaces/{workspace_id}/analyze-tenure-bands`

## Files Modified

### Frontend
- [ ] `planalign_studio/services/api.ts`
- [ ] `planalign_studio/components/ConfigStudio.tsx`

### Backend
- [ ] `planalign_api/routers/` (new or existing)
- [ ] `planalign_api/services/` (band analysis service)

### dbt (existing, read/write by API)
- [ ] `dbt/seeds/config_age_bands.csv`
- [ ] `dbt/seeds/config_tenure_bands.csv`

## Testing

- [ ] Unit tests for band validation logic
- [ ] Unit tests for census analysis algorithm
- [ ] Integration tests for API endpoints
- [ ] Frontend component tests
- [ ] E2E test for complete edit/save flow
- [ ] Regression test: run simulation before/after to verify identical event counts
