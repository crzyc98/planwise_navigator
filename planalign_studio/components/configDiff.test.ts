import { describe, expect, it } from 'vitest';

import type { ConfigDelta } from '../services/api';
import { applyDeltaToOverrides } from './applyConfigDelta';
import { settingLabel } from './comparisonIntegrity';
import { configDiffRows, unsetLabel } from './configDiff';

describe('unset label', () => {
  it('names the side whose config lacks a one-sided setting', () => {
    const onlyA = { status: 'only_a' as const };
    expect(unsetLabel(onlyA, 'b')).toBe('Not set');
    expect(unsetLabel(onlyA, 'a')).toBeNull();
    expect(unsetLabel({ status: 'only_b' as const }, 'a')).toBe('Not set');
  });

  it('leaves an explicit null that both runs recorded alone', () => {
    expect(unsetLabel({ status: 'changed' as const }, 'a')).toBeNull();
    expect(unsetLabel({ status: 'changed' as const }, 'b')).toBeNull();
  });
});

describe('config diff rows (#1236)', () => {
  const changed = (path: string, a: unknown, b: unknown): ConfigDelta => ({ path, a, b, status: 'changed' });

  it('labels a generic key with its section, and form fields in the form\'s words', () => {
    const [integration, core, response] = configDiffRows([
      changed('employer_core_contribution.integration.enabled', false, true),
      changed('dc_plan.core_contribution_rate_percent', 2, 3),
      changed('deferral_match_response.downward_enabled', false, true),
    ]);
    expect(integration.label).toBe('Social Security integration');
    expect(core.label).toBe('Core rate');
    expect(response.label).toBe('Allow deferral decreases');
    expect(settingLabel('promotion_hazard.base_rate')).toBe('Promotion hazard base rate');
    expect(settingLabel('employer_match.eligibility.minimum_hours_annual')).toBe('Eligibility minimum hours annual');
  });

  it('shows rates and percents in percent, booleans as On/Off', () => {
    const [cola, cap, turnover, auto] = configDiffRows([
      changed('compensation.cola_rate', 0.02, 0.035),
      changed('dc_plan.match_cap_percent', 0.04, 0.06),
      changed('workforce.total_termination_rate', 0.12, 0.15),
      changed('dc_plan.auto_enroll', false, true),
    ]);
    expect([cola.a, cola.b]).toEqual(['2%', '3.5%']);
    expect([cap.a, cap.b]).toEqual(['4%', '6%']);
    expect([turnover.a, turnover.b]).toEqual(['12%', '15%']);
    expect([auto.a, auto.b]).toEqual(['Off', 'On']);
  });

  it('collapses a mirrored pair that agrees into one row', () => {
    const rows = configDiffRows([
      changed('compensation.cola_rate', 0.03, 0.07),
      changed('compensation.cola_rate_percent', 3, 7),
      changed('dc_plan.deferral_match_response.enabled', false, true),
      changed('deferral_match_response.enabled', false, true),
      changed('dc_plan.match_cap_percent', 0.04, 0.06),
    ]);
    expect(rows).toHaveLength(3);
    expect(rows.map(row => row.paths)).toEqual([
      ['compensation.cola_rate', 'compensation.cola_rate_percent'],
      ['dc_plan.deferral_match_response.enabled', 'deferral_match_response.enabled'],
      ['dc_plan.match_cap_percent'],
    ]);
    expect([rows[0].label, rows[0].a, rows[0].b]).toEqual(['Cost-of-living raise', '3%', '7%']);
  });

  it('collapses Studio core settings and the engine copies a run derives from them (#1321)', () => {
    const rows = configDiffRows([
      changed('dc_plan.core_contribution_rate_percent', 2, 3.5),
      changed('dc_plan.core_enabled', false, true),
      changed('dc_plan.core_min_tenure_years', 0, 1),
      changed('employer_core_contribution.contribution_rate', 0.02, 0.035),
      changed('employer_core_contribution.eligibility.minimum_tenure_years', 0, 1),
      changed('employer_core_contribution.enabled', false, true),
    ]);
    expect(rows.map(row => [row.label, row.a, row.b, row.paths])).toEqual([
      ['Core rate', '2%', '3.5%', ['dc_plan.core_contribution_rate_percent', 'employer_core_contribution.contribution_rate']],
      ['Employer core contribution', 'Off', 'On', ['dc_plan.core_enabled', 'employer_core_contribution.enabled']],
      ['Core service requirement', '0', '1', ['dc_plan.core_min_tenure_years', 'employer_core_contribution.eligibility.minimum_tenure_years']],
    ]);
  });

  it('keeps a Studio core setting and an engine copy that disagree', () => {
    const rows = configDiffRows([
      changed('dc_plan.core_contribution_rate_percent', 2, 3),
      changed('employer_core_contribution.contribution_rate', 0.02, 0.04),
    ]);
    expect(rows.map(row => [row.label, row.a, row.b])).toEqual([['Core rate', '2%', '3%'], ['Core rate', '2%', '4%']]);
  });

  it('keeps both copies of a mirrored pair that disagree', () => {
    const rows = configDiffRows([
      changed('compensation.cola_rate', 0.03, 0.04),
      changed('compensation.cola_rate_percent', 3, 5),
    ]);
    expect(rows.map(row => [row.delta.path, row.a, row.b])).toEqual([
      ['compensation.cola_rate', '3%', '4%'],
      ['compensation.cola_rate_percent', '3%', '5%'],
    ]);
  });

  it('does not collapse a mirror recorded on only one side with a changed copy', () => {
    const rows = configDiffRows([
      changed('compensation.cola_rate', 0.03, 0.04),
      { path: 'compensation.cola_rate_percent', a: null, b: 4, status: 'only_b' },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[1].a).toBe('Not set');
  });

  it('copies the raw path and value of the kept copy, as its own row did before', () => {
    const cola = changed('compensation.cola_rate', 0.03, 0.035);
    const [row] = configDiffRows([cola, changed('compensation.cola_rate_percent', 3, 3.5)]);
    expect(row.delta).toBe(cola);
    expect(applyDeltaToOverrides({}, row.delta.path, row.delta.b)).toEqual({
      compensation: { cola_rate: 0.035, cola_rate_percent: 3.5 },
    });
    const response = changed('dc_plan.deferral_match_response.upward_participation_rate', 0.4, 0.5);
    const [kept] = configDiffRows([changed('deferral_match_response.upward_participation_rate', 0.4, 0.5), response]);
    expect(kept.delta).toBe(response);
    expect(applyDeltaToOverrides({}, kept.delta.path, kept.delta.a)).toEqual({
      dc_plan: { deferral_match_response: { upward_participation_rate: 0.4 } },
    });
  });

  it('renders values it cannot show inline as JSON, and every unset side as "Not set"', () => {
    const tiers = [{ employee_min: 0, employee_max: 0.06, match_rate: 0.5 }];
    const [list, nested, missing, explicitNull] = configDiffRows([
      changed('dc_plan.match_tiers', [], tiers),
      changed('dc_plan.voluntary_deferral_base_rates', { young_low: 0.03 }, { young_low: 0.04 }),
      { path: 'dc_plan.core_enabled', a: null, b: true, status: 'only_b' },
      changed('new_hire.hire_pay_ratio', null, 0.9),
    ]);
    expect([list.a, list.b]).toEqual(['[]', JSON.stringify(tiers)]);
    expect(nested.b).toBe('{"young_low":0.04}');
    expect([missing.a, missing.b]).toEqual(['Not set', 'On']);
    expect(explicitNull.a).toBe('Not set');
  });

  it('shows recorded strings verbatim', () => {
    const [scope] = configDiffRows([changed('dc_plan.auto_enroll_scope', 'new_hires_only', 'all_eligible_employees')]);
    expect([scope.label, scope.a, scope.b]).toEqual(['Enrollment scope', 'new_hires_only', 'all_eligible_employees']);
  });

  it('adds decimals until two different values read differently', () => {
    const [spread, raise, small] = configDiffRows([
      changed('dc_plan.deferral_spread_max_lift', 0.021, 0.024),
      changed('compensation.raise_budget', 0.03121, 0.03124),
      changed('new_hire.hire_pay_ratio', 0.0001, 0.0002),
    ]);
    expect([spread.a, spread.b]).toEqual(['0.021', '0.024']);
    expect([raise.a, raise.b]).toEqual(['3.121%', '3.124%']);
    expect([small.a, small.b]).toEqual(['0.0001', '0.0002']);
  });

  it('never shows a nonzero value as 0', () => {
    const [row] = configDiffRows([changed('new_hire.hire_pay_ratio', 0, 0.0004)]);
    expect([row.a, row.b]).toEqual(['0', '0.0004']);
  });

  it('reads whole-percent rate keys as percents', () => {
    const [studio, engine] = configDiffRows([
      changed('dc_plan.core_points_pre_service_rate', 1, 2),
      changed('employer_core_contribution.points_pre_service_rate', 0.5, 3),
    ]);
    expect([studio.a, studio.b]).toEqual(['1%', '2%']);
    expect([engine.a, engine.b]).toEqual(['0.5%', '3%']);
  });

  it('uses one unit for both sides of a rate that crosses 1', () => {
    const [row] = configDiffRows([changed('promotion_hazard.base_rate', 0.5, 1.5)]);
    expect([row.a, row.b]).toEqual(['0.5', '1.5']);
  });

  it('reads no minimum wage or acquisitions as "None", like the banner', () => {
    const steps = [{ hourly_rate: 20, effective_date: '2026-07-01' }];
    const [wageMissing, wageNull, acquisitions] = configDiffRows([
      { path: 'compensation.minimum_wage', a: null, b: steps, status: 'only_b' },
      changed('compensation.minimum_wage', null, steps),
      { path: 'workforce.acquisitions', a: [{ name: 'Acme' }], b: null, status: 'only_a' },
    ]);
    expect([wageMissing.a, wageNull.a, acquisitions.b]).toEqual(['None', 'None', 'None']);
    expect(wageMissing.b).toBe('$20.00 an hour from Jul 1, 2026');
  });

  it('reads an empty string as "Not set"', () => {
    const [row] = configDiffRows([changed('dc_plan.escalation_hire_date_cutoff', '', '2020-01-01')]);
    expect([row.a, row.b]).toEqual(['Not set', '2020-01-01']);
  });
});
