import { describe, expect, it } from 'vitest';

import { applyDeltaToOverrides, canApplyDelta, overrideWritesFor } from './applyConfigDelta';

describe('applyDeltaToOverrides', () => {
  it('writes a plain setting at its own path without touching siblings', () => {
    const overrides = { simulation: { start_year: 2025 }, workforce: { total_termination_rate: 0.12 } };
    const next = applyDeltaToOverrides(overrides, 'simulation.target_growth_rate', 0.03);
    expect(next).toEqual({
      simulation: { start_year: 2025, target_growth_rate: 0.03 },
      workforce: { total_termination_rate: 0.12 },
    });
    expect(overrides.simulation).toEqual({ start_year: 2025 });
  });

  it('creates missing parent sections', () => {
    expect(applyDeltaToOverrides({}, 'dc_plan.auto_enroll', true)).toEqual({ dc_plan: { auto_enroll: true } });
  });

  it('copies list values whole', () => {
    const tiers = [{ employee_min: 0, employee_max: 0.06, match_rate: 0.5 }];
    const next = applyDeltaToOverrides<Record<string, unknown>>({}, 'dc_plan.match_tiers', tiers);
    expect(next).toEqual({ dc_plan: { match_tiers: tiers } });
    expect((next?.dc_plan as { match_tiers: unknown }).match_tiers).not.toBe(tiers);
  });

  it('writes both pay keys in step when copying the engine decimal', () => {
    const overrides = { compensation: { cola_rate: 0.02, cola_rate_percent: 2, merit_budget_percent: 3 } };
    expect(applyDeltaToOverrides(overrides, 'compensation.cola_rate', 0.035)).toEqual({
      compensation: { cola_rate: 0.035, cola_rate_percent: 3.5, merit_budget_percent: 3 },
    });
  });

  it('writes both pay keys in step when copying the Studio percent', () => {
    expect(applyDeltaToOverrides({}, 'compensation.merit_budget_percent', 4)).toEqual({
      compensation: { merit_budget: 0.04, merit_budget_percent: 4 },
    });
  });

  it('leaves unrelated _percent pay settings as single keys', () => {
    expect(overrideWritesFor('compensation.target_compensation_growth_percent', 5)).toEqual([
      { path: 'compensation.target_compensation_growth_percent', value: 5 },
    ]);
  });

  it("writes the engine match-response section to Studio's DC plan copy", () => {
    expect(overrideWritesFor('deferral_match_response.enabled', false)).toEqual([
      { path: 'dc_plan.deferral_match_response.enabled', value: false },
    ]);
  });

  it.each([
    'setup.census_parquet_path',
    'param_pack.id',
    'employer_match.active_formula',
    'promotion_hazard.base_rate',
    'age_bands',
    'enrollment.auto_enrollment.voluntary_enrollment_rate',
    'employer_match.formulas.simple_match.match_rate',
    'employer_core_contribution.contribution_rate',
  ])('refuses %s', path => {
    expect(canApplyDelta(path)).toBe(false);
    expect(applyDeltaToOverrides({}, path, 1)).toBeNull();
  });
});
