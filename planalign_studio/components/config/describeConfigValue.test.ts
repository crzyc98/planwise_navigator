import { describe, expect, it } from 'vitest';
import { describeConfigValue } from './describeConfigValue';
import { formatDraftValue } from './EffectiveConfigReview';

describe('describeConfigValue', () => {
  it.each([
    ['dc_plan.core_age_schedule', [{ min_age: 0, max_age: 30, contribution_rate: 0.03 }, { min_age: 60, max_age: null, contribution_rate: 0.06 }], 'Age 0–30: 3%; Age 60+: 6%'],
    ['employer_core_age_schedule', [{ min_age: 30, max_age: 40, rate: 4.0 }], 'Age 30–40: 4%'],
    ['employer_core_contribution.graded_schedule', [{ service_years_min: 3, service_years_max: 5, contribution_rate: 0.02 }], '3–5 yrs service: 2%'],
    ['employer_core_points_schedule', [{ min_points: 75, max_points: null, rate: 3 }], '75+ points: 3%'],
    ['opt_out_multipliers_income', [{ min: 0, multiplier: 1.3 }, { min: 50000, multiplier: 1 }], '$0+ pay: ×1.3; $50,000+ pay: ×1'],
    ['deferral_rate_changes_multipliers_decrease_rate', [{ min: 0.04, multiplier: 0.8 }], '4%+ contribution: ×0.8'],
    ['new_hire_age_distribution', [{ age: 22, weight: 0.05 }], 'Age 22: 5%'],
    ['job_level_compensation', [{ level: 1, name: 'Staff', min_compensation: 56000, max_compensation: 80000 }], 'Staff (level 1): $56,000–$80,000'],
    ['employer_core_contribution.integration', { enabled: true, level_mode: 'ss_wage_base', level_value: null, disparity_rate: 0.05 }, 'Enabled: Yes, Level mode: ss_wage_base, Level value: None, Disparity rate: 5%'],
  ])('%s', (key, value, expected) => {
    expect(describeConfigValue(key, value)).toBe(expected);
  });

  it('never falls back to JSON for unknown nested settings', () => {
    const text = describeConfigValue('mystery', { eligibility: { minimum_tenure_years: 1 }, tiers: [{ a: 1 }] });
    expect(text).toBe('Eligibility (Minimum tenure years: 1), Tiers: A: 1');
    expect(text).not.toMatch(/[{}[\]"]/);
  });

  it('is used by the review and comparison formatter for structured values', () => {
    expect(formatDraftValue('dc_plan.deferral_match_response', { enabled: true, upward_participation_rate: 0.4 }))
      .toBe('Enabled: Yes, Upward participation rate: 40%');
  });
});
