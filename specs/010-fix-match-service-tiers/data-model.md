# Data Model: Service-Based Match Contribution Tiers

**Feature**: 010-fix-match-service-tiers
**Date**: 2026-01-05

## Entities

### 1. ServiceMatchTier

Represents a years-of-service band with associated match rate and deferral cap.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| min_years | integer | >= 0, required | Inclusive lower bound of service years |
| max_years | integer | > min_years or null | Exclusive upper bound (null = infinity) |
| rate | decimal | 0-100, required | Match rate as percentage (e.g., 100 for 100%) |
| max_deferral_pct | decimal | 0-100, required | Maximum deferral % to match (e.g., 6 for 6%) |

**Validation Rules**:
- min_years must be >= 0
- max_years must be > min_years (or null for no upper bound)
- Tiers must not have gaps (next min_years = previous max_years)
- Tiers must not overlap
- rate must be between 0 and 100 (percentage)
- max_deferral_pct must be between 0 and 100 (percentage)

**Example**:
```json
[
  {"min_years": 0, "max_years": 5, "rate": 50, "max_deferral_pct": 6},
  {"min_years": 5, "max_years": null, "rate": 100, "max_deferral_pct": 6}
]
```

### 2. MatchConfiguration (Extended)

Extended from existing match configuration to support service-based mode.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| employer_match_status | enum | 'none', 'flat', 'deferral_based', 'graded_by_service' | Match calculation mode |
| employer_match_graded_schedule | ServiceMatchTier[] | Required when status='graded_by_service' | Service tier definitions |
| match_tiers | MatchTier[] | Required when status='deferral_based' | Existing deferral tier definitions |
| match_template | string | Optional | Template name for deferral-based mode |
| match_cap_percent | decimal | Optional | Cap for deferral-based mode only |

**State Transitions**:
- Default: `employer_match_status = 'deferral_based'` (backward compatible)
- User selects service-based → status = 'graded_by_service', graded_schedule populated
- User selects deferral-based → status = 'deferral_based', match_tiers populated

### 3. MatchCalculationOutput (Extended)

Extended output from `int_employee_match_calculations.sql`.

| Field | Type | Description |
|-------|------|-------------|
| employee_id | string | Employee identifier |
| simulation_year | integer | Simulation year |
| employer_match_amount | decimal | Calculated match amount |
| applied_years_of_service | integer | **NEW**: Years of service used for tier lookup (null if deferral-based) |
| formula_type | string | 'graded_by_service' or existing template name |
| is_eligible_for_match | boolean | Eligibility status |
| ... | ... | (existing fields preserved) |

## Relationships

```
MatchConfiguration
    │
    ├── has many → ServiceMatchTier[]    (when status = 'graded_by_service')
    │
    └── has many → MatchTier[]           (when status = 'deferral_based')

MatchCalculationOutput
    │
    ├── references → Employee            (via employee_id)
    │
    └── references → WorkforceSnapshot   (for years_of_service lookup)
```

## dbt Variable Schema

### New Variables

```yaml
# employer_match_status: Match calculation mode
# Type: string enum
# Values: 'none' | 'flat' | 'deferral_based' | 'graded_by_service'
# Default: 'deferral_based'
employer_match_status: 'graded_by_service'

# employer_match_graded_schedule: Service tier definitions
# Type: list of tier objects
# Required when: employer_match_status = 'graded_by_service'
employer_match_graded_schedule:
  - min_years: 0
    max_years: 5
    rate: 50        # 50% match rate
    max_deferral_pct: 6  # Match up to 6% of deferrals
  - min_years: 5
    max_years: null
    rate: 100       # 100% match rate
    max_deferral_pct: 6  # Match up to 6% of deferrals
```

### Existing Variables (Unchanged)

```yaml
# These remain for deferral-based mode
match_tiers:
  - employee_min: 0.00
    employee_max: 0.03
    match_rate: 1.00
  - employee_min: 0.03
    employee_max: 0.05
    match_rate: 0.50

match_template: 'tiered'
match_cap_percent: 0.04
```

## UI Data Model (TypeScript)

### New Types

```typescript
// Service-based match tier (UI representation)
interface ServiceMatchTier {
  serviceYearsMin: number;  // UI field name
  serviceYearsMax: number | null;
  matchRate: number;        // Percentage (0-100)
  maxDeferralPct: number;   // Percentage (0-100)
}

// Extended match configuration
interface MatchConfig {
  status: 'deferral_based' | 'graded_by_service';

  // For deferral-based mode
  template?: 'simple' | 'tiered' | 'stretch' | 'safe_harbor' | 'qaca';
  tiers?: DeferralMatchTier[];

  // For service-based mode
  gradedSchedule?: ServiceMatchTier[];
}
```

### Field Name Mapping (UI → dbt)

| UI Field | dbt Variable Field |
|----------|-------------------|
| serviceYearsMin | min_years |
| serviceYearsMax | max_years |
| matchRate | rate (converted: UI decimal × 100) |
| maxDeferralPct | max_deferral_pct (converted: UI decimal × 100) |

## Calculation Formula

When `employer_match_status = 'graded_by_service'`:

```
match_amount = tier_rate × min(deferral_pct, tier_max_deferral_pct) × compensation

Where:
- tier_rate: From service tier matching employee's years_of_service
- deferral_pct: Employee's effective annual deferral rate
- tier_max_deferral_pct: Maximum deferral % to match from service tier
- compensation: Employee's eligible compensation
```

**Example**:
- Employee: 7 years service, $100,000 salary, 8% deferral
- Tier: 5+ years → 100% rate, 6% max deferral
- Calculation: 1.00 × min(0.08, 0.06) × $100,000 = 1.00 × 0.06 × $100,000 = $6,000
