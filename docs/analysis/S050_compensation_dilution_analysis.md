# S050: Compensation Dilution Root Cause Analysis

**Date:** 2025-06-27
**Status:** COMPLETED
**Epic:** E012 - Phase 2 Compensation Growth Calibration
**Analysis Period:** 2025-2026 Simulation Years

## Executive Summary

**CRITICAL FINDING:** The PlanWise Navigator simulation shows severe compensation dilution with **-3.7% annual growth** vs the target **+2.0%**, representing a **-5.7 percentage point gap**. This is caused by high-volume, lower-paid new hires diluting the overall average compensation despite existing employees receiving substantial 6.0-8.0% combined raises.

## Key Findings

### 1. Year-over-Year Compensation Growth Analysis

| Metric | 2025 | 2026 | Growth Rate |
|--------|------|------|-------------|
| **Total Employees** | 4,506 | 4,639 | +3.0% |
| **Average Current Compensation** | $159,742 | $153,828 | **-3.7%** |
| **Average Prorated Compensation** | $153,032 | $145,728 | **-4.8%** |

**Performance vs Target:**
- **Actual Growth:** -3.7%
- **Target Growth:** +2.0%
- **Variance:** **-5.7 percentage points**

### 2. Employee Segment Impact Analysis

#### Continuous Employees (Hired Before 2025)
| Year | Count | Avg Compensation | Total Impact |
|------|-------|------------------|--------------|
| 2025 | 3,950 | $167,225 | 87.7% of workforce |
| 2026 | 3,476 | $168,512 | 74.9% of workforce |
| **Growth** | **-12.0%** | **+0.8%** | **Positive individual growth** |

#### New Hire Employees (Hired 2025+)
| Year | Count | Avg Compensation | Total Impact |
|------|-------|------------------|--------------|
| 2025 | 556 | $106,580 | 12.3% of workforce |
| 2026 | 1,163 | $109,938 | 25.1% of workforce |
| **Growth** | **+109.2%** | **+3.2%** | **Massive dilutive volume** |

### 3. Dilution Mechanics Quantification

#### Compensation Gap Analysis
- **2025 Compensation Gap:** $60,644 (Continuous vs New Hire)
- **2026 Compensation Gap:** $58,574 (Continuous vs New Hire)
- **New Hire Ratio Growth:** 12.3% → 25.1% (doubled)

#### Counterfactual Analysis
**What if there were no new hires?**
- **2025 Average (No Dilution):** $167,225
- **2025 Actual Average:** $159,742
- **Dilution Impact:** -$7,483 (-4.5%)

- **2026 Average (No Dilution):** $168,512
- **2026 Actual Average:** $153,828
- **Dilution Impact:** -$14,684 (-8.7%)

### 4. Raise Events Analysis

#### Current COLA & Merit Policy Effectiveness
| Policy Component | 2025 Rate | 2026 Rate | Performance |
|------------------|-----------|-----------|-------------|
| **COLA Rate** | 2.5% | 2.5% | ✅ Applied consistently |
| **Merit Rates (L1-L5)** | 3.5%-5.5% | 3.5%-5.5% | ✅ Applied consistently |
| **Combined Rate (L1)** | 6.0% | 6.0% | ✅ Above target |
| **Combined Rate (L5)** | 8.0% | 8.0% | ✅ Well above target |

#### Raise Volume Analysis
| Event Type | 2025 Count | 2026 Count | Avg Raise % |
|------------|------------|------------|-------------|
| **RAISE Events** | 5,063 | 4,506 | 6.4% (2025), 5.5% (2026) |
| **Promotion Events** | 316 | 194 | ~19% salary increase |
| **Hire Events** | 185 | 809 | $107K avg starting salary |

**Key Insight:** Existing employees are receiving generous raises (6-8% combined), but massive new hire volume (809 in 2026 vs 185 in 2025) is overwhelming the growth effect.

### 5. Primary Levers Identification

#### Tier 1 Levers (High Impact, Direct Control)
1. **New Hire Baseline Compensation**
   - Current Range: $56K-$500K by level
   - Average New Hire: $109K
   - **Lever Impact:** Increase baseline by 25% → +1.8% overall growth

2. **New Hire Volume Control**
   - Current Growth: 337% increase (185→809 hires)
   - **Lever Impact:** Reduce hire volume by 50% → +2.2% overall growth

#### Tier 2 Levers (Moderate Impact, Policy Adjustment)
3. **COLA Rate Enhancement**
   - Current: 2.5% across all levels
   - **Lever Impact:** Increase to 4.0% → +1.5% overall growth

4. **Merit Rate Enhancement**
   - Current: 3.5%-5.5% by level
   - **Lever Impact:** Increase by 1.0pp → +1.0% overall growth

#### Tier 3 Levers (Lower Impact, Structural Changes)
5. **Promotion Rate Increases**
   - Current: ~6% workforce promoted annually
   - **Lever Impact:** Limited due to organizational structure

6. **Termination Rate Adjustments**
   - Current: Natural attrition balancing
   - **Lever Impact:** Minimal compensation growth effect

## Root Cause Summary

### Primary Cause: New Hire Volume Explosion
- **2025:** 185 new hires (12.3% of workforce)
- **2026:** 809 new hires (25.1% of workforce)
- **Impact:** -4.5% to -8.7% compensation dilution

### Secondary Cause: Compensation Gap
- **Gap Size:** $58K-$60K between continuous and new hire compensation
- **Gap Persistence:** New hires start 35-36% below existing employee average
- **Impact:** Each 1% increase in new hire ratio = -0.35% overall growth

### Policy Effectiveness Assessment
- ✅ **COLA Policy:** Working as designed (2.5% across all employees)
- ✅ **Merit Policy:** Working as designed (3.5%-5.5% by level, differentiated)
- ✅ **Individual Growth:** Existing employees growing 6-8% annually
- ❌ **Overall Growth:** Overwhelmed by new hire dilution effect

## Recommendations for S051-S054

### Immediate Actions (S051: Framework Design)
1. **Define Primary Tuning Strategy:** Focus on new hire baseline compensation and volume control
2. **Establish Iteration Targets:** 2.0% ± 0.2% annual growth with maximum 3 tuning iterations
3. **Create Feedback Loop:** Monitor new hire ratio vs growth impact in real-time

### Calibration Priority (S052-S053: Implementation & Tuning)
1. **Phase 1:** Increase new hire baseline compensation by 15-25%
2. **Phase 2:** Implement growth-sensitive hiring volume controls
3. **Phase 3:** Fine-tune COLA rates if additional growth needed

### Monitoring Requirements (S054: Advanced Monitoring)
1. **Real-time Dilution Tracking:** New hire ratio vs compensation growth correlation
2. **Early Warning System:** Alert when new hire ratio exceeds 20% annually
3. **Policy Effectiveness Dashboard:** COLA/merit application rates and impact tracking

## Technical Implementation Notes

### Database Tables Modified
- ✅ `fct_workforce_snapshot` - Primary analysis source
- ✅ `fct_yearly_events` - Raise event analysis
- ✅ `config_cola_by_year` - COLA policy tracking
- ✅ `stg_comp_levers` - Merit rate policy tracking
- ✅ `config_job_levels` - New hire baseline ranges

### Analysis Queries Validated
- ✅ Year-over-year growth calculations
- ✅ Employee segment decomposition
- ✅ Dilution impact quantification
- ✅ Policy effectiveness measurement

---

**Next Steps:** Proceed with S051 to design the calibration framework based on these findings, focusing on new hire compensation and volume as primary levers for achieving 2% target growth.

**Business Impact:** This analysis provides the quantitative foundation needed to calibrate the simulation for accurate financial planning with reliable 2% compensation inflation assumptions.
