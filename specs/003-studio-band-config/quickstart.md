# Quickstart: Studio Band Configuration Management

**Feature Branch**: `003-studio-band-config`
**Created**: 2025-12-12

## Prerequisites

1. PlanAlign Studio running (`planalign studio`)
2. A workspace with at least one scenario
3. Census file uploaded to the workspace (for "Match Census" features)

## Quick Test Scenarios

### Scenario 1: View Band Configurations (US1 - P1)

**Goal**: Verify bands are displayed correctly in the UI

**Steps**:
1. Launch PlanAlign Studio: `planalign studio`
2. Select a workspace from the dashboard
3. Click on any scenario to open configuration
4. Navigate to "Workforce Segmentation" section in the sidebar
5. Verify age bands table displays 6 rows with columns:
   - Band ID, Label, Min Value, Max Value, Display Order
6. Verify tenure bands table displays 5 rows

**Expected**:
- Age bands show: < 25, 25-34, 35-44, 45-54, 55-64, 65+
- Tenure bands show: < 2, 2-4, 5-9, 10-19, 20+
- All values match `dbt/seeds/config_age_bands.csv` and `config_tenure_bands.csv`

---

### Scenario 2: Edit Band Boundaries (US2 - P2)

**Goal**: Verify bands can be edited and saved

**Steps**:
1. View band configuration (per Scenario 1)
2. Change age band "25-34" max_value from 35 to 40
3. Observe the UI shows unsaved indicator
4. Click "Save"
5. Verify success message appears
6. Refresh the page
7. Verify the change persisted (max_value = 40)

**Expected**:
- Edit is reflected immediately in UI
- Save succeeds
- Change persists across page refresh
- CSV file `config_age_bands.csv` is updated

---

### Scenario 3: Validation - Gap Detection (US3 - P2)

**Goal**: Verify validation prevents gaps between bands

**Steps**:
1. View band configuration
2. Change age band "25-34" min_value from 25 to 26
3. Observe validation error appears immediately

**Expected**:
- Error message: "Gap detected between bands: 25 to 26"
- Save button is disabled
- Affected bands are highlighted

---

### Scenario 4: Validation - Overlap Detection (US3 - P2)

**Goal**: Verify validation prevents overlapping bands

**Steps**:
1. View band configuration
2. Change age band "< 25" max_value from 25 to 30
3. Observe validation error appears immediately

**Expected**:
- Error message: "Overlap detected between bands at value 25"
- Save button is disabled
- Affected bands are highlighted

---

### Scenario 5: Match Census - Age Bands (US4 - P3)

**Goal**: Verify Match Census analyzes data and suggests bands

**Prerequisites**: Census file with employee_birth_date column uploaded

**Steps**:
1. View band configuration
2. Click "Match Census" button in age bands section
3. Wait for analysis to complete (loading indicator)
4. Review suggested bands

**Expected**:
- Suggested bands appear based on census age distribution
- Statistics shown (total employees, min/max age, percentiles)
- "Apply" button to apply suggestions
- "Cancel" button to dismiss

---

### Scenario 6: Match Census - Tenure Bands (US5 - P3)

**Goal**: Verify Match Census works for tenure bands

**Prerequisites**: Census file with employee_hire_date column uploaded

**Steps**:
1. View band configuration
2. Click "Match Census" button in tenure bands section
3. Wait for analysis to complete
4. Review suggested bands

**Expected**:
- Suggested bands based on tenure distribution
- Appropriate statistics displayed

---

### Scenario 7: Simulation Regression Test (SC-005)

**Goal**: Verify band editing doesn't break simulations

**Steps**:
1. Run baseline simulation: `planalign simulate 2025-2027`
2. Record event counts (hire, termination, promotion, raise, etc.)
3. Edit a band boundary (non-breaking change, e.g., label only)
4. Save changes
5. Run simulation again: `planalign simulate 2025-2027`
6. Compare event counts

**Expected**:
- Event counts match within expected tolerance
- Simulation completes successfully

---

## API Testing (curl)

### Get Band Configurations

```bash
curl -X GET "http://localhost:8000/api/workspaces/{workspace_id}/config/bands" \
  -H "Content-Type: application/json"
```

### Save Band Configurations

```bash
curl -X PUT "http://localhost:8000/api/workspaces/{workspace_id}/config/bands" \
  -H "Content-Type: application/json" \
  -d '{
    "age_bands": [
      {"band_id": 1, "band_label": "< 25", "min_value": 0, "max_value": 25, "display_order": 1},
      {"band_id": 2, "band_label": "25-34", "min_value": 25, "max_value": 35, "display_order": 2},
      {"band_id": 3, "band_label": "35-44", "min_value": 35, "max_value": 45, "display_order": 3},
      {"band_id": 4, "band_label": "45-54", "min_value": 45, "max_value": 55, "display_order": 4},
      {"band_id": 5, "band_label": "55-64", "min_value": 55, "max_value": 65, "display_order": 5},
      {"band_id": 6, "band_label": "65+", "min_value": 65, "max_value": 999, "display_order": 6}
    ],
    "tenure_bands": [
      {"band_id": 1, "band_label": "< 2", "min_value": 0, "max_value": 2, "display_order": 1},
      {"band_id": 2, "band_label": "2-4", "min_value": 2, "max_value": 5, "display_order": 2},
      {"band_id": 3, "band_label": "5-9", "min_value": 5, "max_value": 10, "display_order": 3},
      {"band_id": 4, "band_label": "10-19", "min_value": 10, "max_value": 20, "display_order": 4},
      {"band_id": 5, "band_label": "20+", "min_value": 20, "max_value": 999, "display_order": 5}
    ]
  }'
```

### Analyze Age Bands from Census

```bash
curl -X POST "http://localhost:8000/api/workspaces/{workspace_id}/analyze-age-bands" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/census_preprocessed.parquet"}'
```

### Analyze Tenure Bands from Census

```bash
curl -X POST "http://localhost:8000/api/workspaces/{workspace_id}/analyze-tenure-bands" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/census_preprocessed.parquet"}'
```

---

## Validation Test Cases

### Test 1: Valid Configuration

```json
{
  "age_bands": [
    {"band_id": 1, "band_label": "< 30", "min_value": 0, "max_value": 30, "display_order": 1},
    {"band_id": 2, "band_label": "30-50", "min_value": 30, "max_value": 50, "display_order": 2},
    {"band_id": 3, "band_label": "50+", "min_value": 50, "max_value": 999, "display_order": 3}
  ]
}
```
**Expected**: Save succeeds

### Test 2: Gap Error

```json
{
  "age_bands": [
    {"band_id": 1, "min_value": 0, "max_value": 25, ...},
    {"band_id": 2, "min_value": 26, "max_value": 35, ...}
  ]
}
```
**Expected**: Error "Gap detected between bands: 25 to 26"

### Test 3: Overlap Error

```json
{
  "age_bands": [
    {"band_id": 1, "min_value": 0, "max_value": 30, ...},
    {"band_id": 2, "min_value": 25, "max_value": 45, ...}
  ]
}
```
**Expected**: Error "Overlap detected between bands at value 25"

### Test 4: Coverage Error

```json
{
  "age_bands": [
    {"band_id": 1, "min_value": 10, "max_value": 50, ...}
  ]
}
```
**Expected**: Error "First band must start at 0"

---

## Troubleshooting

### Band changes not reflected in simulation

**Cause**: dbt seeds not reloaded
**Solution**: Run `dbt seed --select config_age_bands config_tenure_bands` or restart simulation

### "Match Census" button fails

**Cause**: Census file missing required columns
**Solution**: Ensure census has `employee_birth_date` (for age) or `employee_hire_date` (for tenure)

### Validation errors not showing

**Cause**: Frontend validation disabled or bypassed
**Solution**: Check browser console for errors, verify ConfigStudio.tsx loaded correctly
