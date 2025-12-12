# Research: Studio Band Configuration Management

**Feature Branch**: `003-studio-band-config`
**Created**: 2025-12-12
**Status**: Complete

## Research Summary

This document captures decisions made during Phase 0 research for the band configuration management feature.

---

## Decision 1: Existing Census Analysis Patterns

**Question**: How do existing "Match Census" features work?

**Finding**: The codebase has established patterns in `planalign_api/services/file_service.py`:

1. **`analyze_age_distribution()`** (lines 278-439):
   - Takes `workspace_id` and `file_path` parameters
   - Uses Polars to read Parquet/CSV census files
   - Filters to recent hires (most recent calendar year with >=10 hires)
   - Calculates age at hire or current age
   - Returns distribution buckets with weights, counts, and descriptions
   - Normalizes weights to sum to 1.0

2. **`analyze_compensation_by_level()`** (lines 441-499+):
   - Similar pattern: workspace_id, file_path, lookback_years
   - Uses Polars for data processing
   - Handles both level-based and overall analysis
   - Returns percentile-based statistics

**Decision**: Follow these patterns exactly for band analysis endpoints:
- Use Polars for data loading and analysis
- Support both Parquet and CSV files
- Filter to recent hires when possible
- Return structured result with statistics

**Rationale**: Consistency with existing code reduces implementation risk and maintenance burden.

**Alternatives Considered**:
- Pandas: Rejected - Polars already used throughout, better performance
- DuckDB direct queries: Rejected - census files are external, Polars pattern established

---

## Decision 2: Band Boundary Optimization Algorithm

**Question**: How should "Match Census" suggest band boundaries?

**Finding**: Band boundaries need to:
1. Cover the full range (0 to upper bound)
2. Follow [min, max) convention
3. Avoid gaps and overlaps
4. Create meaningful groupings based on data distribution

**Decision**: Use percentile-based boundary detection:

```python
# For age bands (6 bands), use approximate percentiles:
# 0%, 10%, 25%, 50%, 75%, 90%, 100%
# This creates bands that roughly follow: bottom 10%, next 15%, middle 25%, next 25%, next 15%, top 10%

# For tenure bands (5 bands), use:
# 0%, 20%, 40%, 60%, 80%, 100%
# Even distribution since tenure is more uniform
```

**Rationale**:
- Percentile-based approach adapts to actual data distribution
- Simple to implement and explain to users
- Creates more employees per band in dense regions (useful for simulation accuracy)

**Alternatives Considered**:
- K-means clustering: Rejected - adds complexity, may create unintuitive boundaries
- Fixed bucket sizes: Rejected - doesn't adapt to data distribution
- Jenks natural breaks: Rejected - complex to implement, marginal benefit

---

## Decision 3: Validation Logic Placement

**Question**: Where should band validation logic live?

**Finding**: Validation needs to run in two places:
1. **Client-side (React)**: Real-time feedback as user types
2. **Server-side (FastAPI)**: Final validation before save

**Decision**: Implement validation in both places:

```typescript
// Frontend: planalign_studio/components/ConfigStudio.tsx
function validateBands(bands: Band[]): ValidationError[] {
  const errors: ValidationError[] = [];
  // Check [min, max) convention
  // Check no gaps
  // Check no overlaps
  // Check coverage (0 to upper bound)
  return errors;
}
```

```python
# Backend: planalign_api/services/band_service.py
def validate_bands(bands: list[Band]) -> list[ValidationError]:
    """Server-side validation - authoritative."""
    errors = []
    # Same checks as frontend
    return errors
```

**Rationale**:
- Frontend validation provides instant feedback (better UX)
- Backend validation is authoritative (security, data integrity)
- Duplicating logic is acceptable for small, stable validation rules

**Alternatives Considered**:
- Backend-only validation: Rejected - poor UX, requires round-trip for every edit
- Shared validation library: Rejected - overkill for simple rules, adds build complexity

---

## Decision 4: CSV File Read/Write Location

**Question**: Where should the API read/write band CSV files?

**Finding**: Band seed files are at:
- `/workspace/dbt/seeds/config_age_bands.csv`
- `/workspace/dbt/seeds/config_tenure_bands.csv`

**Decision**: Use absolute paths to dbt seeds directory:

```python
DBT_SEEDS_DIR = Path("/workspace/dbt/seeds")  # Or configurable via env var

def get_band_config_path(band_type: str) -> Path:
    filename = f"config_{band_type}_bands.csv"
    return DBT_SEEDS_DIR / filename
```

**Rationale**:
- Bands are global configuration, not workspace-specific
- dbt seeds directory is the single source of truth
- Keeps band data separate from workspace data

**Alternatives Considered**:
- Workspace-specific bands: Rejected - bands should be consistent across scenarios
- Database storage: Rejected - dbt seeds are the established pattern, enables version control

---

## Decision 5: dbt Seed Reload Strategy

**Question**: How should band changes trigger dbt seed reload?

**Finding**: dbt seed reload can be done via:
1. `dbt seed --select config_age_bands config_tenure_bands`
2. Full `dbt seed` (reloads all seeds)

**Decision**: Don't auto-reload in the save endpoint. Instead:
- Display message: "Band configurations saved. Seeds will be reloaded at simulation start."
- The orchestrator already runs `dbt seed` at the start of each simulation
- Optionally provide a "Reload Seeds Now" button that calls `dbt seed --select config_*_bands`

**Rationale**:
- Automatic reload on every save is slow and unnecessary
- Simulations already reload seeds
- Optional manual reload gives user control when needed

**Alternatives Considered**:
- Auto-reload on save: Rejected - slow, unnecessary for most workflows
- Background reload: Rejected - complexity without clear benefit

---

## Decision 6: API Endpoint Structure

**Question**: How should the band API endpoints be organized?

**Finding**: Existing patterns in `planalign_api/routers/`:
- Files router: `/api/workspaces/{workspace_id}/upload`, `/analyze-age-distribution`, etc.
- Separate routers for distinct domains (files, scenarios, simulations)

**Decision**: Create a new `bands.py` router with workspace-scoped endpoints:

```
GET  /api/workspaces/{workspace_id}/config/bands
PUT  /api/workspaces/{workspace_id}/config/bands
POST /api/workspaces/{workspace_id}/analyze-age-bands
POST /api/workspaces/{workspace_id}/analyze-tenure-bands
```

**Rationale**:
- Follows existing URL patterns
- Workspace scoping is consistent even though bands are global (simplifies frontend code)
- Separate router keeps code modular

**Alternatives Considered**:
- Global endpoints without workspace: Rejected - breaks URL consistency
- Add to files router: Rejected - conceptually different, would bloat files.py

---

## Decision 7: Frontend UI Section

**Question**: Where should band configuration appear in ConfigStudio.tsx?

**Finding**: ConfigStudio.tsx has multiple sections:
- Simulation settings
- Compensation settings
- New Hire settings (contains age distribution and job level compensation)
- DC Plan settings
- Advanced settings

**Decision**: Add a new "Workforce Segmentation" section after "New Hire" settings:

```typescript
// New section in sidebar navigation
const sections = [
  { id: 'simulation', label: 'Simulation', icon: Settings },
  { id: 'compensation', label: 'Compensation', icon: DollarSign },
  { id: 'newHire', label: 'New Hire', icon: Users },
  { id: 'segmentation', label: 'Workforce Segmentation', icon: PieChart }, // NEW
  { id: 'dcPlan', label: 'DC Plan', icon: Shield },
  { id: 'advanced', label: 'Advanced', icon: Server },
];
```

**Rationale**:
- Bands are related to workforce analysis, not strictly new hires or compensation
- Separate section makes it easy to find
- Follows existing section pattern

**Alternatives Considered**:
- Add to New Hire section: Rejected - bands apply to all employees, not just new hires
- Add to Advanced section: Rejected - bands are commonly configured, shouldn't be hidden

---

## Summary

| Topic | Decision |
|-------|----------|
| Census analysis | Follow existing Polars-based patterns in file_service.py |
| Band boundary algorithm | Percentile-based boundary detection |
| Validation | Duplicate in frontend (UX) and backend (authority) |
| CSV location | Global dbt seeds directory, not workspace-specific |
| dbt seed reload | Message user, don't auto-reload (orchestrator handles it) |
| API structure | New bands.py router with workspace-scoped endpoints |
| UI location | New "Workforce Segmentation" section in ConfigStudio |
