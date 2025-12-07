# E084: Comprehensive DC Plan Configuration

**Status**: ✅ COMPLETE
**Priority**: High
**Approach**: Incremental - Fix existing, then expand
**Dependencies**: E023 (Enrollment Engine), E058 (Match Eligibility), E035 (Auto-Escalation)

## Completion Summary (2025-12-07)

### Phase A: Expose Existing Config in UI ✅ COMPLETE
All 16 YAML config fields now exposed in ConfigStudio UI:
- Auto-enrollment: window_days, opt_out_grace_period, scope, hire_date_cutoff
- Match eligibility: min_tenure_years, require_year_end_active, min_hours_annual, allow_terminated toggles
- Core contribution: enabled, contribution_rate, eligibility rules
- Auto-escalation: effective_day, first_escalation_delay_years, hire_date_cutoff

### Phase B: Configurable Match Tiers ✅ COMPLETE (B3)
- Replaced hardcoded formula selection with editable tier system
- 5 template presets: Simple, Tiered, Stretch, Safe Harbor, QACA
- Users can customize individual tiers after selecting template
- Auto-calculate max employer match from tier definitions
- Add/remove tiers dynamically in UI
- dbt model updated (`int_employee_match_calculations.sql`)
- Copy from Scenario feature added

### Phase B: Graded Core by Service ✅ COMPLETE (B7)
- Core contribution status: none / flat / graded_by_service
- Editable graded schedule with tiers (min_years, max_years, rate)
- Add/remove tiers dynamically
- Full eligibility settings (tenure, hours, year-end active, termination toggles)

### Deferred Items (Not Required for MVP)
- B1: Vesting Events - Schema exists, dbt model deferred
- B2: Forfeiture Events - Schema exists, dbt model deferred
- B4: Entry Date Rules - Not implemented
- B5: True-Up Calculations - Not implemented
- B6: Tenure-Based Match - Deferred
- B8: HCE Status Events - Schema exists, dbt model deferred

---

---

## Executive Summary

This epic takes an **incremental approach** to implementing real-world DC plan configuration:

1. **Phase A**: Fix and expose existing YAML configuration in the UI (what's already built)
2. **Phase B**: Add missing features one-by-one based on priority

**Current State**: The system has solid foundations in YAML configuration (auto-enrollment, match formulas, eligibility, core contributions, auto-escalation, IRS limits) but the UI only exposes 10 of 40+ available fields.

**Immediate Goal**: Expose existing configuration capabilities in the UI before adding new features.

---

## Part 1: Target Configuration Schema (Reference)

Adopt this industry-standard schema as the canonical `plan_design` structure:

```json
{
  "plan_design_id": "string",
  "plan_name": "string",
  "plan_type": "401k | 403b | profit_sharing | safe_harbor_401k",

  "eligibility": {
    "age_min": 21,
    "service_requirement_months": 0,
    "hours_requirement": null,
    "eligibility_measure": "elapsed_service | hours | immediate",
    "entry_frequency": "immediate | monthly | quarterly | semiannual | annual",
    "different_for_match": false,
    "match_eligibility_lag_months": 0
  },

  "auto_enrollment": {
    "status": "none | initial | re_enroll_existing | sweep_non_participants",
    "default_deferral_type": "pre_tax | roth | split",
    "default_deferral_rate_pct": 3.0,
    "eligibility_trigger": "first_eligible | first_of_month_after_eligible | annual_window",
    "opt_out_method": "paper | online | call_center",
    "eaca": {
      "is_eaca": false,
      "withdrawal_window_days": null
    },
    "qaca": {
      "is_qaca": false
    }
  },

  "auto_escalation": {
    "status": "none | opt_out | opt_in",
    "increment_pct": 1.0,
    "max_deferral_pct": 10.0,
    "frequency": "annual | payroll_periodic",
    "start_timing": "first_anniversary | calendar_year_start | plan_year_start",
    "applies_to": "auto_enrolled_only | all_participants",
    "escalate_if_above_cap": false
  },

  "match": {
    "status": "none | fixed | discretionary | safe_harbor_basic | safe_harbor_enhanced | qaca_safe_harbor",
    "structure": "single_tier | tiered | stretch | flat_dollar",
    "tiers": [
      { "match_pct": 100, "on_deferrals_up_to_pct": 3 },
      { "match_pct": 50, "on_deferrals_up_to_pct": 2 }
    ],
    "max_matchable_deferral_pct": 6,
    "true_up": true,
    "pay_defn": "eligible_comp | section_415 | w2",
    "match_on_bonus": true,
    "match_pay_period_vs_annual": "per_pay | annual"
  },

  "core_non_elective": {
    "status": "none | flat | graded_by_service | age_plus_service | integrated_with_social_security | performance_based | profit_sharing",
    "base_pct_of_pay": 3.0,
    "graded_schedule": [
      { "service_years_min": 0, "service_years_max": 2, "pct_of_pay": 3.0 },
      { "service_years_min": 3, "service_years_max": null, "pct_of_pay": 5.0 }
    ],
    "allocation_formula": "pro_rata | new_comparability | integrated",
    "safe_harbor_3pct": false,
    "eligibility_same_as_deferrals": true
  },

  "vesting": {
    "applies_to": "match_core | match_only | core_only",
    "schedule_type": "immediate | cliff | graded",
    "cliff_years": null,
    "graded_schedule": [
      { "year_of_service": 1, "vested_pct": 0 },
      { "year_of_service": 2, "vested_pct": 20 },
      { "year_of_service": 3, "vested_pct": 40 },
      { "year_of_service": 4, "vested_pct": 60 },
      { "year_of_service": 5, "vested_pct": 80 },
      { "year_of_service": 6, "vested_pct": 100 }
    ],
    "year_of_service_definition": "1000_hours | elapsed"
  }
}
```

---

## Part 2: Pragmatic Implementation Plan

### PHASE A: Fix and Expose Existing Configuration (Priority 1)

The YAML config already has most of what we need. The immediate work is exposing it in the UI.

#### A1. Expose Existing YAML Fields in UI

**CONFIRMED by user - ALL of these should be exposed:**

**Auto-Enrollment Section:**
| YAML Config | Action |
|-------------|--------|
| `enrollment.auto_enrollment.window_days` (45) | Add slider (30-90 days) |
| `enrollment.auto_enrollment.opt_out_grace_period` (30) | Add input |
| `enrollment.auto_enrollment.scope` | Add dropdown (new_hires_only / all_eligible) |
| `enrollment.auto_enrollment.hire_date_cutoff` | Add date picker |

**Match Eligibility Section:**
| YAML Config | Action |
|-------------|--------|
| `employer_match.eligibility.minimum_tenure_years` | Add input (0-5 years) |
| `employer_match.eligibility.require_active_at_year_end` | Add toggle |
| `employer_match.eligibility.minimum_hours_annual` | Add input (default 1000) |
| `employer_match.eligibility.allow_terminated_new_hires` | Add toggle |
| `employer_match.eligibility.allow_experienced_terminations` | Add toggle |

**Core Contribution Section (NEW in UI):**
| YAML Config | Action |
|-------------|--------|
| `employer_core_contribution.enabled` | Add toggle |
| `employer_core_contribution.contribution_rate` (1%) | Add input (0-10%) |
| `employer_core_contribution.eligibility.*` | Reuse match eligibility pattern |

**Auto-Escalation Section:**
| YAML Config | Action |
|-------------|--------|
| `deferral_auto_escalation.effective_day` (01-01) | Add month/day picker |
| `deferral_auto_escalation.first_escalation_delay_years` | Add input (0-3 years) |
| `deferral_auto_escalation.hire_date_cutoff` | Add date picker |

**Files to Modify**:
- `planalign_studio/components/ConfigStudio.tsx` (lines 2042-2115)

**Estimated Effort**: 3-5 days

#### A2. Connect UI to Actual Config Variables

Currently the UI has fields but they may not map correctly to dbt variables. Verify and fix:

1. `dcMatchFormula` → `var('employer_match.active_formula')`
2. `dcMatchPercent` → Match formula tier configuration
3. `dcMatchLimit` → `var('employer_match.formulas.*.max_match_percentage')`
4. `dcAutoEscalation` → `var('deferral_auto_escalation.enabled')`
5. `dcEscalationRate` → `var('deferral_auto_escalation.increment_amount')`
6. `dcEscalationCap` → `var('deferral_auto_escalation.maximum_rate')`

**Files to Modify**:
- `planalign_api/services/` - Config serialization
- `planalign_studio/services/api.ts` - API calls

**Estimated Effort**: 2-3 days

---

### PHASE B: Add Features Incrementally (Priority 2+)

After Phase A is complete, add features one at a time. **User-confirmed priorities:**

| Priority | Feature | What Already Exists | What to Add |
|----------|---------|---------------------|-------------|
| **HIGH** | **B3: Safe Harbor Formulas** | 4 match formulas exist | Add safe_harbor_basic, qaca_safe_harbor |
| **HIGH** | **B7: Graded Core by Service** | flat rate exists | Add graded_schedule config |
| MEDIUM | B1: Vesting Events | Schema in events.py | dbt model + seed file |
| MEDIUM | B2: Forfeiture Events | Schema in events.py | dbt model |
| MEDIUM | B4: Entry Date Rules | Not implemented | Add to eligibility config |
| MEDIUM | B5: True-Up Calculations | Not implemented | New dbt model |
| LOW | B6: Tenure-Based Match | eligibility exists | Extend to formula selection |
| LOW | B8: HCE Status Events | Schema exists | dbt model |

**Recommended order**: B3 → B7 → B1 → B2 → B4 → B5 (defer B6, B8)

---

## Part 3: Current State Analysis

### 3.1 What Exists Today

**YAML Configuration** (`config/simulation_config.yaml`):
| Feature | Status | Lines |
|---------|--------|-------|
| Auto-enrollment (basic) | Implemented | 152-307 |
| Match formulas (4 types) | Implemented | 315-380 |
| Match eligibility | Implemented | 326-333 |
| Core contribution (flat) | Implemented | 381-394 |
| Auto-escalation | Implemented | 591-600 |
| IRS limits | Via seed file | N/A |

**Event Schemas** (`config/events.py`):
| Event Type | Schema Defined | dbt Model | Production Ready |
|------------|----------------|-----------|------------------|
| ELIGIBILITY | Yes | Yes | Yes |
| ENROLLMENT | Yes | Yes | Yes |
| CONTRIBUTION | Yes | Yes | Yes |
| EMPLOYER_MATCH | Yes | Yes | Yes |
| EMPLOYER_CORE | Yes | Yes | Yes |
| DEFERRAL_ESCALATION | Yes | Yes | Yes |
| VESTING | Yes | **NO** | **NO** |
| FORFEITURE | Yes | **NO** | **NO** |
| HCE_STATUS | Yes | **NO** | **NO** |
| COMPLIANCE | Yes | **NO** | **NO** |

**UI** (`planalign_studio/components/ConfigStudio.tsx`):
- Only 10 fields exposed (lines 2042-2115)
- Missing 40+ configuration options available in YAML

### 3.2 Critical Gaps

1. **Safe Harbor Plans**: No QACA, QNEC, QMAC support
2. **Entry Date Rules**: No entry frequency configuration (immediate/monthly/quarterly/annual)
3. **Vesting Events**: Schema exists but no generation
4. **Forfeiture Processing**: Schema exists but no generation
5. **True-Up Calculations**: Not implemented
6. **Tenure-Based Progression**: Match/core formulas can't change by tenure
7. **EACA Withdrawal Window**: Not modeled
8. **Service Computation**: Only elapsed time, not hours-based
9. **Different Eligibility for Match**: Not supported (same eligibility for all)

---

## Part 4: Reference Implementation Details

Use these detailed specs when implementing each Phase B feature.

### B1: Vesting Events

**What Exists**: `VestingPayload` schema in `config/events.py` (lines 197-228)

**What to Add**:
1. Create seed file: `dbt/seeds/vesting_schedules.csv`
2. Create dbt model: `dbt/models/intermediate/events/int_vesting_events.sql`

**Seed File**:
```csv
schedule_id,schedule_type,year_of_service,vested_pct
immediate,immediate,0,100
cliff_2,cliff,2,100
cliff_3,cliff,3,100
graded_5,graded,1,20
graded_5,graded,2,40
graded_5,graded,3,60
graded_5,graded,4,80
graded_5,graded,5,100
graded_6,graded,2,20
graded_6,graded,3,40
graded_6,graded,4,60
graded_6,graded,5,80
graded_6,graded,6,100
qaca_2_year,cliff,2,100
```

---

### B2: Forfeiture Events

**What Exists**: `ForfeiturePayload` schema in `config/events.py` (lines 286-309)

**What to Add**:
1. Create dbt model: `dbt/models/intermediate/events/int_forfeiture_events.sql`
2. Link to termination events and vesting status

---

### B3: Safe Harbor Formulas

**What Exists**: 4 match formulas in `simulation_config.yaml` (simple, tiered, stretch, enhanced_tiered)

**What to Add**:
```yaml
# Add to employer_match.formulas in simulation_config.yaml
safe_harbor_basic:
  name: 'Safe Harbor Basic Match'
  type: 'safe_harbor'
  tiers:
    - tier: 1
      employee_min: 0.00
      employee_max: 0.03
      match_rate: 1.00
    - tier: 2
      employee_min: 0.03
      employee_max: 0.05
      match_rate: 0.50
  max_match_percentage: 0.04
  immediate_vesting: true

qaca_safe_harbor:
  name: 'QACA Safe Harbor Match'
  type: 'qaca'
  tiers:
    - tier: 1
      employee_min: 0.00
      employee_max: 0.01
      match_rate: 1.00
    - tier: 2
      employee_min: 0.01
      employee_max: 0.06
      match_rate: 0.50
  max_match_percentage: 0.035
  vesting_schedule: 'qaca_2_year'
```

---

### B4: Entry Date Rules

**What Exists**: Eligibility waiting period only (days)

**What to Add**:
```yaml
# Add to eligibility section in simulation_config.yaml
eligibility:
  entry_frequency: "monthly"  # immediate, monthly, quarterly, semiannual, annual
  next_entry_date_rule: "first_of_month_following"
```

---

### B5: True-Up Calculations

**What Exists**: Per-pay match calculations only

**What to Add**:
```yaml
# Add to employer_match in simulation_config.yaml
employer_match:
  true_up:
    enabled: true
    frequency: 'annual'
    threshold: 5.00
```
Create: `dbt/models/intermediate/events/int_match_true_up_calculations.sql`

---

### B6: Tenure-Based Match Progression

**What Exists**: Match eligibility by tenure, single formula for all

**What to Add**:
```yaml
employer_match:
  tenure_progression:
    enabled: true
    milestones:
      - years_of_service: 0
        match_formula: 'simple_match'
      - years_of_service: 1
        match_formula: 'tiered_match'
```

---

### B7: Graded Core by Service

**What Exists**: Flat core contribution rate (1%)

**What to Add**:
```yaml
employer_core_contribution:
  status: "graded_by_service"
  graded_schedule:
    - service_years_min: 0
      service_years_max: 2
      contribution_rate: 0.03
    - service_years_min: 3
      service_years_max: null
      contribution_rate: 0.05
```

---

### B8: HCE Status Events

**What Exists**: `HCEStatusPayload` schema in `config/events.py` (lines 311-329)

**What to Add**:
Create: `dbt/models/intermediate/events/int_hce_status_events.sql`

---

## Part 5: Plan Design Templates (Reference)

Include these ready-to-use templates as starting points:

### Template 1: Basic Auto-Enrollment (Baseline)

```json
{
  "plan_design_id": "basic_ae_low_default",
  "plan_name": "Basic 401(k) with Auto-Enrollment",
  "plan_type": "401k",
  "eligibility": {
    "age_min": 21,
    "service_requirement_months": 3,
    "eligibility_measure": "elapsed_service",
    "entry_frequency": "monthly"
  },
  "auto_enrollment": {
    "status": "initial",
    "default_deferral_type": "pre_tax",
    "default_deferral_rate_pct": 3.0,
    "eligibility_trigger": "first_of_month_after_eligible",
    "eaca": { "is_eaca": false },
    "qaca": { "is_qaca": false }
  },
  "auto_escalation": {
    "status": "opt_out",
    "increment_pct": 1.0,
    "max_deferral_pct": 6.0,
    "frequency": "annual",
    "start_timing": "first_anniversary",
    "applies_to": "auto_enrolled_only"
  },
  "match": {
    "status": "fixed",
    "structure": "single_tier",
    "tiers": [{ "match_pct": 50, "on_deferrals_up_to_pct": 6 }],
    "true_up": false,
    "match_pay_period_vs_annual": "per_pay",
    "max_matchable_deferral_pct": 6
  },
  "core_non_elective": { "status": "none" },
  "vesting": {
    "applies_to": "match_core",
    "schedule_type": "graded",
    "graded_schedule": [
      { "year_of_service": 1, "vested_pct": 0 },
      { "year_of_service": 2, "vested_pct": 20 },
      { "year_of_service": 3, "vested_pct": 40 },
      { "year_of_service": 4, "vested_pct": 60 },
      { "year_of_service": 5, "vested_pct": 80 },
      { "year_of_service": 6, "vested_pct": 100 }
    ],
    "year_of_service_definition": "1000_hours"
  }
}
```

### Template 2: Safe Harbor QACA

```json
{
  "plan_design_id": "safe_harbor_qaca",
  "plan_name": "Safe Harbor QACA Plan",
  "plan_type": "safe_harbor_401k",
  "eligibility": {
    "age_min": 18,
    "service_requirement_months": 0,
    "eligibility_measure": "immediate",
    "entry_frequency": "immediate"
  },
  "auto_enrollment": {
    "status": "initial",
    "default_deferral_type": "pre_tax",
    "default_deferral_rate_pct": 3.0,
    "eligibility_trigger": "first_eligible",
    "eaca": { "is_eaca": false },
    "qaca": { "is_qaca": true }
  },
  "auto_escalation": {
    "status": "opt_out",
    "increment_pct": 1.0,
    "max_deferral_pct": 6.0,
    "frequency": "annual",
    "start_timing": "first_anniversary",
    "applies_to": "auto_enrolled_only"
  },
  "match": {
    "status": "qaca_safe_harbor",
    "structure": "tiered",
    "tiers": [
      { "match_pct": 100, "on_deferrals_up_to_pct": 1 },
      { "match_pct": 50, "on_deferrals_up_to_pct": 5 }
    ],
    "true_up": true,
    "match_pay_period_vs_annual": "per_pay",
    "max_matchable_deferral_pct": 6
  },
  "core_non_elective": { "status": "none" },
  "vesting": {
    "applies_to": "match_core",
    "schedule_type": "cliff",
    "cliff_years": 2,
    "year_of_service_definition": "elapsed"
  }
}
```

### Template 3: Healthcare/Higher-Ed Graded Core

```json
{
  "plan_design_id": "healthcare_graded_core",
  "plan_name": "Healthcare Core + Match Plan",
  "plan_type": "401k",
  "eligibility": {
    "age_min": 21,
    "service_requirement_months": 12,
    "hours_requirement": 1000,
    "eligibility_measure": "hours",
    "entry_frequency": "semiannual",
    "different_for_match": true,
    "match_eligibility_lag_months": 12
  },
  "auto_enrollment": {
    "status": "initial",
    "default_deferral_type": "pre_tax",
    "default_deferral_rate_pct": 6.0,
    "eligibility_trigger": "first_of_month_after_eligible",
    "eaca": { "is_eaca": true, "withdrawal_window_days": 90 },
    "qaca": { "is_qaca": false }
  },
  "auto_escalation": {
    "status": "opt_out",
    "increment_pct": 1.0,
    "max_deferral_pct": 10.0,
    "frequency": "annual",
    "start_timing": "first_anniversary",
    "applies_to": "auto_enrolled_only"
  },
  "match": {
    "status": "fixed",
    "structure": "tiered",
    "tiers": [
      { "match_pct": 100, "on_deferrals_up_to_pct": 3 },
      { "match_pct": 50, "on_deferrals_up_to_pct": 2 }
    ],
    "true_up": true,
    "match_pay_period_vs_annual": "annual",
    "max_matchable_deferral_pct": 5
  },
  "core_non_elective": {
    "status": "graded_by_service",
    "graded_schedule": [
      { "service_years_min": 0, "service_years_max": 2, "pct_of_pay": 3.0 },
      { "service_years_min": 3, "service_years_max": 5, "pct_of_pay": 5.0 },
      { "service_years_min": 6, "service_years_max": null, "pct_of_pay": 7.0 }
    ],
    "allocation_formula": "pro_rata",
    "eligibility_same_as_deferrals": false
  },
  "vesting": {
    "applies_to": "match_core",
    "schedule_type": "graded",
    "graded_schedule": [
      { "year_of_service": 1, "vested_pct": 0 },
      { "year_of_service": 2, "vested_pct": 20 },
      { "year_of_service": 3, "vested_pct": 40 },
      { "year_of_service": 4, "vested_pct": 60 },
      { "year_of_service": 5, "vested_pct": 80 },
      { "year_of_service": 6, "vested_pct": 100 }
    ],
    "year_of_service_definition": "1000_hours"
  }
}
```

---

## Part 6: Migration and Backward Compatibility

### 6.1 YAML Configuration Migration

The existing `simulation_config.yaml` structure must remain valid. New `plan_designs` section is additive:

```yaml
# Existing structure preserved (backward compatible)
enrollment:
  auto_enrollment:
    enabled: true
    # ... existing fields

employer_match:
  active_formula: 'simple_match'
  # ... existing fields

# NEW: Optional plan_designs section
plan_designs:
  default:
    # Uses new PlanDesign schema
    eligibility:
      entry_frequency: "monthly"
    # ...
```

### 6.2 Database Schema

No schema changes required - use existing `event_type` column with new enum values:
- `VESTING`
- `FORFEITURE`
- `HCE_STATUS`
- `COMPLIANCE`

### 6.3 Multi-Year State

Vesting requires tracking across years. Follow existing accumulator pattern:
- `int_vesting_state_accumulator.sql` (new)
- Similar to `int_enrollment_state_accumulator.sql`

---

## Part 7: Success Criteria

1. **Feature Coverage**: Support 95% of Fortune 500 401(k) plan designs
2. **Performance**: <5% overhead from new event types (leverage Polars mode)
3. **UI Usability**: 80% of plans configurable in "simple" mode
4. **Backward Compatibility**: Zero breaking changes to existing simulations
5. **Test Coverage**: 90%+ coverage for new configuration code
6. **Validation**: Golden dataset validation for Safe Harbor formula accuracy

---

## Part 8: Risk Assessment

### Migration Risks
- **Backward Compatibility**: Mitigated by additive changes only
- **Database Schema**: No changes needed - uses existing event_type column

### Technical Risks
- **Performance**: Mitigated by Polars mode (1000x+ improvement already achieved)
- **Complexity**: Mitigated by progressive disclosure UI

### Compliance Risks
- **Safe Harbor Calculations**: Require formula review by compliance team
- **IRS Limit Accuracy**: Use authoritative IRS publication sources

---

## Part 9: Critical Files Reference

### Configuration
- `/Users/nicholasamaral/planwise_navigator/config/simulation_config.yaml` (693 lines)
- `/Users/nicholasamaral/planwise_navigator/config/events.py` (971 lines)

### dbt Models (to modify)
- `/Users/nicholasamaral/planwise_navigator/dbt/models/intermediate/events/int_employee_match_calculations.sql`
- `/Users/nicholasamaral/planwise_navigator/dbt/models/intermediate/events/int_employer_core_contributions.sql`
- `/Users/nicholasamaral/planwise_navigator/dbt/models/intermediate/events/int_employee_contributions.sql`

### dbt Models (to create)
- `dbt/models/intermediate/events/int_vesting_events.sql`
- `dbt/models/intermediate/events/int_forfeiture_events.sql`
- `dbt/models/intermediate/events/int_match_true_up_calculations.sql`
- `dbt/models/intermediate/events/int_hce_status_events.sql`

### Seeds (to create/update)
- `dbt/seeds/vesting_schedules.csv`
- `dbt/seeds/irs_contribution_limits.csv` (update with SECURE 2.0 limits)
- `dbt/seeds/plan_design_templates.csv`

### UI Components
- `/Users/nicholasamaral/planwise_navigator/planalign_studio/components/ConfigStudio.tsx` (2,308 lines)
- New: `planalign_studio/components/dc_plan/*.tsx`

### API
- New: `planalign_api/routers/plan_designs.py`
- New: `planalign_api/models/plan_design.py`

### Orchestrator
- `/Users/nicholasamaral/planwise_navigator/planalign_orchestrator/pipeline/event_generation_executor.py`
- `/Users/nicholasamaral/planwise_navigator/planalign_orchestrator/pipeline/workflow.py`

---

## Part 10: Implementation Order

**Pragmatic Approach - Fix existing first, then expand:**

```
PHASE A: Fix & Expose Existing (1-2 weeks)
├── A1: Expose YAML config in UI (3-5 days)
│   ├── Auto-enrollment: window_days, grace_period, scope, cutoff
│   ├── Match eligibility: tenure, hours, year-end, terminations
│   ├── Core contribution: enabled, rate, eligibility
│   └── Auto-escalation: effective_day, delay, cutoff
└── A2: Connect UI to dbt variables (2-3 days)
    └── Verify config flows through simulation

PHASE B: Add Features (user-prioritized order)
├── B3: Safe Harbor Formulas (HIGH) ─── YAML + dbt match model
├── B7: Graded Core by Service (HIGH) ── config + dbt core model
├── B1: Vesting Events (MEDIUM) ──────── seed + dbt model
├── B2: Forfeiture Events (MEDIUM) ───── dbt model
├── B4: Entry Date Rules (MEDIUM) ────── config only
├── B5: True-Up Calculations (MEDIUM) ── dbt model
├── B6: Tenure-Based Match (LOW) ─────── defer
└── B8: HCE Status Events (LOW) ──────── defer
```

**Start Tomorrow**: Phase A - exposes what already exists

---

## Appendix A: Mapping Current Config to Target Schema

| Current YAML Path | Target Schema Path | Status |
|-------------------|-------------------|--------|
| `enrollment.auto_enrollment.enabled` | `auto_enrollment.status` | Transform |
| `enrollment.auto_enrollment.default_deferral_rate` | `auto_enrollment.default_deferral_rate_pct` | Rename |
| `enrollment.auto_enrollment.window_days` | N/A (implicit in eligibility_trigger) | Remove |
| `employer_match.active_formula` | `match.status` + `match.structure` | Split |
| `employer_match.formulas.*.tiers` | `match.tiers` | Restructure |
| `employer_match.eligibility.*` | `eligibility.different_for_match` | Consolidate |
| `employer_core_contribution.contribution_rate` | `core_non_elective.base_pct_of_pay` | Rename |
| `deferral_auto_escalation.*` | `auto_escalation.*` | Rename |
| N/A | `eligibility.entry_frequency` | **NEW** |
| N/A | `auto_enrollment.eaca` | **NEW** |
| N/A | `auto_enrollment.qaca` | **NEW** |
| N/A | `match.true_up` | **NEW** |
| N/A | `core_non_elective.graded_schedule` | **NEW** |
| N/A | `vesting.*` | **NEW** (schema exists, config doesn't) |

---

## Appendix B: ChatGPT Reference Schema

The complete schema provided by ChatGPT is incorporated into Part 1 of this epic. Key additions from ChatGPT's design:

1. **EACA/QACA flags** - Critical for Safe Harbor compliance
2. **Entry date frequency** - Important for eligibility timing
3. **Match on bonus** - Common plan design option
4. **Pay definition** - Eligible comp vs W2 vs 415
5. **Year of service definition** - Hours vs elapsed time
6. **Allocation formula** - Pro-rata vs new comparability
7. **Age plus service** - Points-based formulas for core

These are all incorporated into the target schema and implementation plan.
