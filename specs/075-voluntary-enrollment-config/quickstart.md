# Quick Start: Voluntary Enrollment Rate Configuration

**Feature**: 075-voluntary-enrollment-config

## What This Feature Does

Adds a configurable voluntary enrollment rate to the DC plan configuration page. Users can set a percentage (0–100%) that scales the demographic-based enrollment probabilities used in simulation. This allows modeling different voluntary participation levels without modifying the underlying demographic assumptions.

## Key Files to Modify

### Layer 1: Python Config (Pydantic)
- `planalign_orchestrator/config/workforce.py` — Add `voluntary_enrollment_rate` field to `AutoEnrollmentSettings`
- `planalign_orchestrator/config/export.py` — Export the new field in `_export_auto_enrollment_fields()`

### Layer 2: dbt Models (SQL)
- `dbt/dbt_project.yml` — Add default variable `voluntary_enrollment_rate: null`
- `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` — Apply multiplier to `final_enrollment_probability`
- `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` — Apply same multiplier

### Layer 3: Frontend (React)
- `planalign_studio/components/config/DCPlanSection.tsx` — Add form field (slider + numeric input)
- `planalign_studio/components/config/ConfigContext.tsx` — Add `dcVoluntaryEnrollmentRate` to FormData and mapping
- `planalign_studio/components/config/buildConfigPayload.ts` — Transform form value to API payload

## Development Workflow

```bash
# 1. Make Python config changes
# Edit workforce.py and export.py

# 2. Run fast tests
pytest -m fast

# 3. Make dbt changes
cd dbt
dbt run --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment --vars '{"simulation_year": 2025, "voluntary_enrollment_rate": 0.40}' --threads 1

# 4. Run dbt tests
dbt test --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment --threads 1

# 5. Make frontend changes
cd planalign_studio
npm run dev  # Start dev server

# 6. End-to-end test
planalign simulate 2025 --verbose
```

## Testing Strategy

1. **Unit tests**: Verify `AutoEnrollmentSettings` accepts and validates the new field
2. **Export tests**: Verify `_export_auto_enrollment_fields()` exports the variable to dbt vars
3. **dbt tests**: Verify enrollment counts scale with the multiplier (rate=0 → 0 enrollments, rate=1 → baseline enrollments)
4. **Integration tests**: End-to-end config → simulation → results verification
