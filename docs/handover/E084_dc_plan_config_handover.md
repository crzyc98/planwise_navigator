# E084 Handover: Comprehensive DC Plan Configuration

## Context Resume Prompt

Copy this into a new Claude Code session:

---

**Resume E084: DC Plan Configuration Implementation**

I'm continuing work on Epic E084 - Comprehensive DC Plan Configuration. The planning is complete and committed.

**Branch**: `feature/E084-comprehensive-dc-plan-configuration`

**Epic Document**: `/docs/epics/E084_comprehensive_dc_plan_configuration.md`

## What Was Planned

**Phase A (Start Now - 1-2 weeks):**
Expose 16 existing YAML config fields in the UI that aren't currently accessible:

1. **Auto-Enrollment Section** (ConfigStudio.tsx):
   - `window_days` (45) - slider 30-90 days
   - `opt_out_grace_period` (30) - input
   - `scope` - dropdown (new_hires_only / all_eligible)
   - `hire_date_cutoff` - date picker

2. **Match Eligibility Section**:
   - `minimum_tenure_years` - input 0-5
   - `require_active_at_year_end` - toggle
   - `minimum_hours_annual` - input (default 1000)
   - `allow_terminated_new_hires` - toggle
   - `allow_experienced_terminations` - toggle

3. **Core Contribution Section (NEW)**:
   - `enabled` - toggle
   - `contribution_rate` - input 0-10%
   - Eligibility rules (reuse match pattern)

4. **Auto-Escalation Section**:
   - `effective_day` - month/day picker
   - `first_escalation_delay_years` - input 0-3
   - `hire_date_cutoff` - date picker

**Phase B (After Phase A, prioritized):**
1. **B3: Safe Harbor Formulas** (HIGH) - Add QACA, safe_harbor_basic to YAML + dbt
2. **B7: Graded Core by Service** (HIGH) - Core rate varies by tenure
3. B1-B5: Medium priority
4. B6, B8: Deferred

## Key Files

- **Primary UI**: `planalign_studio/components/ConfigStudio.tsx` (lines 2042-2115 for DC Plan section)
- **Config**: `config/simulation_config.yaml` (lines 151-394 for DC plan settings)
- **API**: `planalign_api/` for connecting UI to config
- **Epic**: `docs/epics/E084_comprehensive_dc_plan_configuration.md`

## Ready to Start

Start with Phase A1: Adding the UI fields to ConfigStudio.tsx. The YAML config already has all the settings - we just need to expose them.

---

## Session Summary

- Explored codebase: DC plan config (YAML), events (Pydantic), UI (React)
- Received ChatGPT schema reference for industry-standard DC plan designs
- Created pragmatic incremental plan (fix existing first, then expand)
- User confirmed which features to expose and prioritized Phase B features
- Created and committed epic document to feature branch

## Files Changed

- `docs/epics/E084_comprehensive_dc_plan_configuration.md` (NEW - 749 lines)
