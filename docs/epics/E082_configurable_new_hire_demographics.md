# Epic E082: Configurable New Hire Demographics

## 🎯 Epic Overview

**Problem Statement**: New hire demographic profiles (age distribution and job level distribution) are currently hardcoded in dbt SQL models, preventing users from customizing hiring patterns for different workforce scenarios (e.g., tech startups hiring younger, senior-heavy workforces vs. healthcare hiring experienced professionals).

**Discovery Context**:
1. **Age Distribution**: Defined in `int_hiring_events.sql` lines 54-65 as a VALUES table but **NOT USED** - actual ages cycle deterministically (25, 28, 32, 35, 40) via modulo logic
2. **Job Level Distribution**: Currently **adaptive** (maintains workforce composition) in `int_workforce_needs_by_level.sql` - user wants option to override with fixed percentages

**Target State**:
- ✅ Age distribution configurable via seed file and UI
- ✅ Job level distribution: adaptive by default, optional fixed override via UI
- ✅ New Hire Strategy section in PlanAlign Studio exposes both configurations
- ✅ Per-scenario configuration support

**Business Impact**:
- **Flexibility**: Model different workforce profiles (tech startup vs. mature enterprise)
- **Accuracy**: Match hiring patterns to actual client workforce demographics
- **Scenario Planning**: Compare outcomes with different hiring strategies

---

## 📋 Current State Analysis

### Age Distribution (BROKEN - Dead Code)

**File**: `dbt/models/intermediate/events/int_hiring_events.sql`

**Lines 54-65** - Defined but unused:
```sql
age_distribution AS (
  SELECT * FROM (VALUES
    (22, 0.05), -- Recent college graduates
    (25, 0.15), -- Early career
    (28, 0.20), -- Established early career
    (32, 0.25), -- Mid-career switchers
    (35, 0.15), -- Experienced hires
    (40, 0.10), -- Senior experienced
    (45, 0.08), -- Mature professionals
    (50, 0.02)  -- Late career changes
  ) AS t(hire_age, age_weight)
),
```

**Lines 84-90** - Actual implementation (ignores above):
```sql
CASE
  WHEN hs.hire_sequence_num % 5 = 0 THEN 25
  WHEN hs.hire_sequence_num % 5 = 1 THEN 28
  WHEN hs.hire_sequence_num % 5 = 2 THEN 32
  WHEN hs.hire_sequence_num % 5 = 3 THEN 35
  ELSE 40
END AS employee_age,
```

### Job Level Distribution (Adaptive)

**File**: `dbt/models/intermediate/int_workforce_needs_by_level.sql`

**Lines 126-132**: Uses current workforce composition as weights:
```sql
WITH level_weights AS (
  SELECT
    level_id,
    current_headcount,
    current_headcount * 1.0 / SUM(current_headcount) OVER () AS raw_weight
  FROM workforce_by_level
  WHERE current_headcount > 0
),
```

**Behavior**: Hiring is distributed proportionally to maintain existing workforce level composition.

---

## 📋 Data Contract

### New Seed: `config_new_hire_age_distribution.csv`

```csv
scenario_id,hire_age,age_weight,description
default,22,0.05,Recent college graduates
default,25,0.15,Early career
default,28,0.20,Established early career
default,32,0.25,Mid-career switchers
default,35,0.15,Experienced hires
default,40,0.10,Senior experienced
default,45,0.08,Mature professionals
default,50,0.02,Late career changes
```

**Notes**:
- `scenario_id = 'default'` is used when no scenario-specific config exists
- `age_weight` values should sum to 1.0 within a scenario
- Scenario-specific overrides use the actual `scenario_id`

### New Seed: `config_new_hire_level_distribution.csv`

```csv
scenario_id,level_id,level_name,distribution_pct,use_fixed_distribution
default,1,Staff,0,false
default,2,Manager,0,false
default,3,SrMgr,0,false
default,4,Director,0,false
default,5,VP,0,false
```

**Notes**:
- `use_fixed_distribution = false` means use adaptive (current behavior)
- `use_fixed_distribution = true` + `distribution_pct` values enables fixed override
- `distribution_pct` values should sum to 1.0 when fixed distribution is enabled

---

## ✅ Acceptance Criteria

1. **Age Distribution Works**: New hires are assigned ages using weighted random sampling from seed configuration
2. **Level Distribution Toggle**: UI allows switching between "Adaptive" (default) and "Fixed Percentages"
3. **UI Integration**: New Hire Strategy section includes both configurations
4. **Per-Scenario Support**: Different scenarios can have different demographic profiles
5. **Backward Compatible**: Default seed values match current hardcoded behavior
6. **Validation**: Age weights and level distribution percentages validated to sum to 1.0

---

## 📋 Implementation Stories

### **Story E082-01: Create Seed Files**
**Priority**: P0 (Foundation)
**Effort**: 30 minutes

**Implementation**:
1. Create `dbt/seeds/config_new_hire_age_distribution.csv` with default values matching current hardcoded distribution
2. Create `dbt/seeds/config_new_hire_level_distribution.csv` with adaptive defaults
3. Add seed configuration to `dbt/dbt_project.yml`
4. Run `dbt seed` to load

**Files Created**:
- `dbt/seeds/config_new_hire_age_distribution.csv`
- `dbt/seeds/config_new_hire_level_distribution.csv`

**Files Modified**:
- `dbt/dbt_project.yml` (seed config)

---

### **Story E082-02: Update int_hiring_events.sql for Age Distribution**
**Priority**: P0 (Core)
**Effort**: 1 hour

**Implementation**:

Replace hardcoded age assignment with seed-based weighted selection:

```sql
-- Read from seed instead of hardcoded VALUES
age_distribution AS (
  SELECT
    hire_age,
    age_weight,
    SUM(age_weight) OVER (ORDER BY hire_age) AS cumulative_weight
  FROM {{ ref('config_new_hire_age_distribution') }}
  WHERE scenario_id = COALESCE(
    (SELECT scenario_id FROM {{ ref('stg_scenario_config') }} LIMIT 1),
    'default'
  )
),

-- In hire sequence generation, use weighted random selection
-- Replace modulo logic with:
SELECT
  hs.*,
  (SELECT ad.hire_age
   FROM age_distribution ad
   WHERE ad.cumulative_weight >= (hs.hire_sequence_num % 100) / 100.0
   ORDER BY ad.cumulative_weight
   LIMIT 1
  ) AS employee_age
FROM hire_sequence hs
```

**Acceptance Criteria**:
- ✅ Ages assigned from seed configuration
- ✅ Default seed produces similar distribution to current hardcoded values
- ✅ Scenario-specific overrides work

**Files Modified**:
- `dbt/models/intermediate/events/int_hiring_events.sql`

---

### **Story E082-03: Update int_workforce_needs_by_level.sql for Level Override**
**Priority**: P0 (Core)
**Effort**: 1.5 hours

**Implementation**:

Add conditional logic to use fixed distribution when enabled:

```sql
-- Check if fixed distribution is enabled for this scenario
fixed_distribution_config AS (
  SELECT
    level_id,
    distribution_pct,
    use_fixed_distribution
  FROM {{ ref('config_new_hire_level_distribution') }}
  WHERE scenario_id = COALESCE(
    (SELECT scenario_id FROM {{ ref('stg_scenario_config') }} LIMIT 1),
    'default'
  )
),

use_fixed AS (
  SELECT BOOL_OR(use_fixed_distribution) AS enabled
  FROM fixed_distribution_config
),

-- Modified level_weights CTE
level_weights AS (
  SELECT
    l.level_id,
    CASE
      WHEN (SELECT enabled FROM use_fixed) THEN fd.distribution_pct
      ELSE l.current_headcount * 1.0 / NULLIF(SUM(l.current_headcount) OVER (), 0)
    END AS raw_weight
  FROM workforce_by_level l
  LEFT JOIN fixed_distribution_config fd ON l.level_id = fd.level_id
  WHERE l.current_headcount > 0 OR (SELECT enabled FROM use_fixed)
),
```

**Acceptance Criteria**:
- ✅ `use_fixed_distribution = false` maintains current adaptive behavior
- ✅ `use_fixed_distribution = true` uses seed percentages
- ✅ Backward compatible (default = adaptive)

**Files Modified**:
- `dbt/models/intermediate/int_workforce_needs_by_level.sql`

---

### **Story E082-04: Add UI Controls to ConfigStudio**
**Priority**: P0 (UI)
**Effort**: 2 hours

**Implementation**:

Add to New Hire Strategy section (`planalign_studio/components/ConfigStudio.tsx`):

**1. Form State** (add to formData):
```typescript
// New Hire Demographics
newHireAgeDistribution: [
  { age: 22, weight: 0.05, description: 'Recent college graduates' },
  { age: 25, weight: 0.15, description: 'Early career' },
  { age: 28, weight: 0.20, description: 'Established early career' },
  { age: 32, weight: 0.25, description: 'Mid-career switchers' },
  { age: 35, weight: 0.15, description: 'Experienced hires' },
  { age: 40, weight: 0.10, description: 'Senior experienced' },
  { age: 45, weight: 0.08, description: 'Mature professionals' },
  { age: 50, weight: 0.02, description: 'Late career changes' },
],
levelDistributionMode: 'adaptive', // 'adaptive' | 'fixed'
newHireLevelDistribution: [
  { level: 1, name: 'Staff', percentage: 40 },
  { level: 2, name: 'Manager', percentage: 30 },
  { level: 3, name: 'Sr Manager', percentage: 20 },
  { level: 4, name: 'Director', percentage: 8 },
  { level: 5, name: 'VP', percentage: 2 },
],
```

**2. UI Components**:

```tsx
{/* Age Distribution Section */}
<div className="bg-gray-50 p-6 rounded-lg border border-gray-200">
  <h3 className="text-sm font-semibold text-gray-900 mb-4">New Hire Age Profile</h3>
  <p className="text-xs text-gray-500 mb-4">
    Define the age distribution for new hires. Weights should sum to 100%.
  </p>
  <table className="min-w-full">
    <thead>
      <tr>
        <th>Age</th>
        <th>Weight (%)</th>
        <th>Description</th>
      </tr>
    </thead>
    <tbody>
      {formData.newHireAgeDistribution.map((row, idx) => (
        <tr key={row.age}>
          <td>{row.age}</td>
          <td>
            <input
              type="number"
              value={row.weight * 100}
              onChange={(e) => handleAgeWeightChange(idx, e.target.value)}
            />
          </td>
          <td>{row.description}</td>
        </tr>
      ))}
    </tbody>
  </table>
  <p className="text-xs text-gray-500 mt-2">
    Total: {(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) * 100).toFixed(0)}%
  </p>
</div>

{/* Level Distribution Section */}
<div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
  <h3 className="text-sm font-semibold text-gray-900 mb-4">New Hire Level Distribution</h3>

  <div className="flex items-center space-x-4 mb-4">
    <label className={`flex items-center p-3 border rounded-lg cursor-pointer ${formData.levelDistributionMode === 'adaptive' ? 'bg-green-50 border-fidelity-green' : ''}`}>
      <input type="radio" name="levelDistributionMode" value="adaptive" ... />
      <div className="ml-2">
        <span className="font-medium">Adaptive</span>
        <span className="text-xs text-gray-500 block">Maintain current workforce composition</span>
      </div>
    </label>
    <label className={`flex items-center p-3 border rounded-lg cursor-pointer ${formData.levelDistributionMode === 'fixed' ? 'bg-green-50 border-fidelity-green' : ''}`}>
      <input type="radio" name="levelDistributionMode" value="fixed" ... />
      <div className="ml-2">
        <span className="font-medium">Fixed Percentages</span>
        <span className="text-xs text-gray-500 block">Specify exact distribution</span>
      </div>
    </label>
  </div>

  {formData.levelDistributionMode === 'fixed' && (
    <table className="min-w-full">
      {/* Level distribution table similar to age distribution */}
    </table>
  )}
</div>
```

**3. Save Handler** - Map to API payload structure

**Files Modified**:
- `planalign_studio/components/ConfigStudio.tsx`
- `planalign_studio/types.ts` (add types)

---

### **Story E082-05: Add API Support**
**Priority**: P0 (API)
**Effort**: 1 hour

**Implementation**:

1. Update workspace/scenario config handling to include new hire demographics
2. Add validation for weight sums (should equal 1.0)
3. Ensure config flows through to seed generation

**Config Structure**:
```python
# In config payload
"new_hire": {
    "strategy": "percentile",
    "target_percentile": 50,
    "compensation_variance_percent": 5.0,
    # NEW FIELDS:
    "age_distribution": [
        {"age": 22, "weight": 0.05},
        {"age": 25, "weight": 0.15},
        # ...
    ],
    "level_distribution_mode": "adaptive",  # or "fixed"
    "level_distribution": [
        {"level": 1, "percentage": 0.40},
        {"level": 2, "percentage": 0.30},
        # ...
    ]
}
```

**Files Modified**:
- `planalign_api/services/template_service.py` (add defaults to templates)
- `planalign_api/models/scenario.py` (if typed models exist)

---

### **Story E082-06: Testing and Validation**
**Priority**: P1 (Validation)
**Effort**: 1 hour

**Implementation**:

1. Run simulation with default seeds (should match current behavior)
2. Create test scenario with modified demographics
3. Verify age distribution in `fct_yearly_events` matches seed config
4. Verify level distribution respects adaptive/fixed toggle

**Validation Queries**:
```sql
-- Check age distribution of new hires
SELECT
  employee_age,
  COUNT(*) as count,
  COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () as actual_pct
FROM fct_yearly_events
WHERE event_type = 'hire'
  AND simulation_year = 2025
GROUP BY employee_age
ORDER BY employee_age;

-- Check level distribution of new hires
SELECT
  job_level,
  COUNT(*) as count,
  COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () as actual_pct
FROM fct_yearly_events
WHERE event_type = 'hire'
  AND simulation_year = 2025
GROUP BY job_level
ORDER BY job_level;
```

---

## 🎯 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Age distribution configurable | ✅ | Seed values reflected in hire events |
| Level distribution toggle works | ✅ | Adaptive vs fixed produces different distributions |
| UI exposes both configs | ✅ | New Hire Strategy section complete |
| Backward compatible | ✅ | Default seeds match current hardcoded behavior |
| Validation works | ✅ | Weights summing ≠ 1.0 shows error |

---

## 🚨 Risks & Mitigation

### **Risk 1: Weighted Random Selection Performance**
**Likelihood**: Low | **Impact**: Low

**Mitigation**: DuckDB handles this efficiently. If needed, pre-compute cumulative weights in seed.

### **Risk 2: UI Complexity**
**Likelihood**: Medium | **Impact**: Low

**Mitigation**: Use collapsible sections. Show summary (e.g., "Default Profile") with expand for details.

---

## 📋 Implementation Timeline

| Story | Effort | Dependencies |
|-------|--------|--------------|
| E082-01: Create Seed Files | 30 min | None |
| E082-02: Update int_hiring_events.sql | 1 hour | E082-01 |
| E082-03: Update int_workforce_needs_by_level.sql | 1.5 hours | E082-01 |
| E082-04: Add UI Controls | 2 hours | E082-01 |
| E082-05: Add API Support | 1 hour | E082-04 |
| E082-06: Testing and Validation | 1 hour | E082-02, E082-03 |

**Total Effort**: ~7 hours (1 day)

---

## 📚 Files Summary

### Created
- `dbt/seeds/config_new_hire_age_distribution.csv`
- `dbt/seeds/config_new_hire_level_distribution.csv`

### Modified
- `dbt/dbt_project.yml`
- `dbt/models/intermediate/events/int_hiring_events.sql`
- `dbt/models/intermediate/int_workforce_needs_by_level.sql`
- `planalign_studio/components/ConfigStudio.tsx`
- `planalign_studio/types.ts`
- `planalign_api/services/template_service.py`

---

---

## ✅ Implemented Features (2025-12-01)

### Feature 1: Promotion Rate Multiplier

**Problem**: Users couldn't configure the rate at which employees get promoted. Promotion rates were fixed in seed files (`config_job_levels.csv`) with no way to scale them up or down for different scenarios.

**Solution**: Added a configurable promotion rate multiplier that scales the base promotion probability.

**UI Changes** (`planalign_studio/components/ConfigStudio.tsx`):
- Added "Promotion Rate Multiplier" input field in Compensation section
- Default: 1.0× (use seed defaults)
- Range: 0× to 5×
- Helper text explains: "1.0 = use defaults, 1.5 = 50% more promotions"

**Backend Changes**:

1. **`planalign_orchestrator/config.py`**:
   - Added `promotion_rate_multiplier` field to `CompensationSettings` class
   - Added to `dbt_vars` in `build_dbt_vars()` function

2. **`planalign_orchestrator/polars_event_factory.py`**:
   - Added `promotion_rate_multiplier` to `EventFactoryConfig` dataclass
   - Applied multiplier in `generate_promotion_events()`:
     ```python
     effective_promotion_rate = base_promotion_rate * self.config.promotion_rate_multiplier
     ```

3. **`planalign_orchestrator/pipeline/event_generation_executor.py`**:
   - Passes `promotion_rate_multiplier` from config to `EventFactoryConfig`

4. **`dbt/models/intermediate/events/int_promotion_events.sql`**:
   - Added variable: `{% set promotion_rate_multiplier = var('promotion_rate_multiplier', 1.0) %}`
   - Applied multiplier to hazard rate lookup:
     ```sql
     LEAST(h.promotion_rate * {{ promotion_rate_multiplier }}, 1.0) AS promotion_rate
     ```
   - Capped at 1.0 to prevent impossible probabilities

**Formula**: `effective_rate = MIN(base_hazard_rate × multiplier, 1.0)`

---

### Feature 2: Promotion + Merit Compensation Compounding Fix

**Problem**: When an employee received both a promotion (Feb 1) and a merit raise (Jul 15) in the same year, the merit raise was incorrectly calculated from the pre-promotion baseline salary instead of the post-promotion salary. This caused:
- Promoted employees to have lower-than-expected year-end compensation
- Average workforce compensation to remain flat despite promotions
- Compensation not carrying forward correctly to subsequent years

**Root Cause Analysis**:
1. Event generation models (`int_promotion_events`, `int_merit_events`) both read from `int_employee_compensation_by_year` which contains start-of-year baseline compensation
2. Events are generated in parallel from the same baseline, not sequentially
3. `fct_workforce_snapshot` applied merit salary directly without checking if employee was also promoted

**Example of Bug**:
- Employee baseline: $66,000
- Promotion (Feb 1): $66k → $81,424 (+23%)
- Merit raise (Jul 15): Incorrectly used $66k → $69,300 (+5%)
- Snapshot showed: $69,300 (WRONG - should be ~$85,495)

**Solution** (`dbt/models/marts/fct_workforce_snapshot.sql`):

1. **Capture merit raise rate from events**:
   ```sql
   -- In employee_events_consolidated CTE
   MAX(CASE WHEN event_type = 'raise' AND previous_compensation > 0
       THEN (compensation_amount / previous_compensation) - 1.0
       ELSE NULL END) AS merit_raise_rate,
   ```

2. **Apply merit rate to promoted salary when both events occur**:
   ```sql
   -- In workforce_after_merit CTE
   CASE
       -- E082 FIX: Employee promoted AND got merit - apply raise rate to promoted salary
       WHEN ec.has_promotion AND ec.has_merit AND ec.merit_raise_rate IS NOT NULL THEN
           ROUND(w.employee_gross_compensation * (1 + COALESCE(ec.merit_raise_rate, 0)), 2)
       -- Only merit (no promotion) - use pre-calculated merit salary
       WHEN ec.has_merit THEN ec.merit_salary
       -- No merit - keep current compensation
       ELSE w.employee_gross_compensation
   END AS employee_gross_compensation,
   ```

3. **Fix full_year_equivalent_compensation to use corrected current_compensation**:
   ```sql
   -- Simplified to use the already-corrected current_compensation
   current_compensation AS full_year_equivalent_compensation,
   ```

**Result After Fix**:
- Employee baseline: $66,000
- Promotion (Feb 1): $66k → $81,424 (+23%)
- Merit raise (Jul 15): Applied to $81,424 → $85,495 (+5%)
- Year 2 starts with: $85,495 (CORRECT)
- Year 2 ends with: $90,198 (+5.5%)
- Year 3 ends with: $95,159 (+5.5%)

**Impact on Average Compensation**:
- Before fix: Flat ~$95k across all years
- After fix: Growing $96k → $97k → $98k (proper compounding)

---

## 📋 Files Modified (2025-12-01 Session)

### UI Layer
- `planalign_studio/components/ConfigStudio.tsx`
  - Added `promoRateMultiplier` to form state
  - Added input field in Compensation section
  - Added to config save/load functions

### Backend Configuration
- `planalign_orchestrator/config.py`
  - Added `promotion_rate_multiplier` to `CompensationSettings`
  - Added to `dbt_vars` in `build_dbt_vars()`

### Polars Event Factory
- `planalign_orchestrator/polars_event_factory.py`
  - Added `promotion_rate_multiplier` to `EventFactoryConfig`
  - Applied multiplier in `generate_promotion_events()`

- `planalign_orchestrator/pipeline/event_generation_executor.py`
  - Passes multiplier from config to event factory

### dbt Models
- `dbt/models/intermediate/events/int_promotion_events.sql`
  - Added `promotion_rate_multiplier` variable
  - Applied multiplier to hazard rate with cap at 1.0

- `dbt/models/marts/fct_workforce_snapshot.sql`
  - Added `merit_raise_rate` calculation in consolidated events
  - Fixed `workforce_after_merit` to compound promotion + merit
  - Simplified `full_year_equivalent_compensation` to use corrected value

---

**Epic Owner**: Workforce Simulation Team
**Created**: 2025-12-01
**Updated**: 2025-12-01
**Target Completion**: 1 day
**Priority**: Medium - Enables demographic customization
**Status**: Partially Implemented (Promotion Rate Multiplier + Compounding Fix Complete)
