# Data Model: Match Census for Opt-Out Rate Configuration

**Branch**: `085-optout-match-census` | **Phase**: 1 Design

## Entities

### OptOutRateAnalysisRequest

Input to the census analysis endpoint.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `file_path` | `str` | required, non-empty | Path to census file (relative to workspace or absolute) |
| `lookback_years` | `int` | min=1, max=50, default=3 | Only include employees hired within this many years of the most recent hire date in the census |

---

### OptOutRateAnalysisResult

Response from the census analysis endpoint.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `suggested_rate` | `float` | yes | Suggested opt-out rate as decimal (0.0–1.0). Null if no eligible employees found in the lookback window. |
| `eligible_count` | `int` | no | Total eligible employees within the lookback tenure window |
| `non_participant_count` | `int` | no | Employees within the window with no active deferral (deferral_rate = 0 or NULL) |
| `total_eligible_in_census` | `int` | no | Total eligible employees in the entire census (pre-lookback filter) |
| `excluded_null_tenure` | `int` | no | Employees excluded because hire_date was missing/null |
| `lookback_years` | `int` | no | Echoed back from the request |
| `hire_date_column_used` | `str` | no | The census column name detected for hire date (e.g., "hire_date", "employee_hire_date") |
| `analysis_type` | `str` | no | Human-readable description of the analysis performed |
| `source_file` | `str` | no | Path to the source census file (for audit) |
| `message` | `str` | yes | Informational or warning message (e.g., "Only 5 employees found in lookback window") |

---

### Derived SQL Security Extension

Extend `CENSUS_DEFERRAL_COLUMNS` frozenset in `planalign_api/services/sql_security.py`:

| Column Name | Purpose |
|-------------|---------|
| `employee_deferral_rate` | Primary census field indicating active deferral (non-zero = enrolled) |
| `deferral_rate` | Alternate column name for same concept |

These are added to `ALL_CENSUS_COLUMNS` via the new frozenset.

---

## Enrollment Detection Logic

An employee in the census is classified as a **non-participant** (i.e., opted out) when:
- `employee_deferral_rate` = 0 OR `employee_deferral_rate` IS NULL

An employee is considered **eligible** when:
- `active` column indicates active employment (e.g., 'Active', 'Y', '1', true)

The analysis excludes:
- Terminated employees (where `active` = false/inactive)
- Employees with NULL or missing hire_date (excluded_null_tenure count)

---

## Calculation Formula

```
lookback_cutoff = MAX(hire_date) in census - (lookback_years × 365 days)
eligible_in_window = COUNT(*) WHERE active=true AND hire_date >= lookback_cutoff AND hire_date IS NOT NULL
non_participants_in_window = COUNT(*) WHERE active=true AND hire_date >= lookback_cutoff AND (deferral_rate = 0 OR deferral_rate IS NULL) AND hire_date IS NOT NULL
suggested_rate = non_participants_in_window / eligible_in_window  (NULL if eligible_in_window = 0)
```

---

## State Transitions (Frontend)

```
Idle
  │── [click "Match Census" with no census file] ──► Error: "Upload census first"
  │── [click "Match Census" with census file] ──► Analyzing (button spinner, disabled)
          │── [API error] ──► analysisError (error message shown)
          │── [API success] ──► PreviewShown (preview panel visible)
                  │── [change lookback_years] ──► Analyzing (re-fetch)
                  │── [click Apply] ──► Idle (dcOptOutRateTarget updated, preview dismissed)
                  │── [click Dismiss] ──► Idle (dcOptOutRateTarget unchanged, preview dismissed)
```

---

## Configuration Flow (No Schema Changes)

The feature uses the existing `dcOptOutRateTarget` form field. No new scenario config fields are needed — the census-derived value simply pre-fills the existing field. Scenario persistence is unchanged.
