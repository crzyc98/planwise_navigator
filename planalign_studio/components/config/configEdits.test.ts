import { describe, expect, it } from 'vitest';
import { applyConfigEdits, preserveDisplayedMatchEligibility, synchronizeCompensationAliases } from './configEdits';
import { buildConfigPayload } from './buildConfigPayload';
import { DEFAULT_FORM_DATA } from './constants';
import { applyResolvedFormData } from './resolvedFormData';

describe('lossless configuration edits', () => {
  it.each([false, true])('saves the complete visible legacy policy for scenario=%s', scenario => {
    const variables = { employer_match: { apply_eligibility: false, eligibility: {
      minimum_tenure_years: 3, minimum_hours_annual: 500, require_active_at_year_end: false,
      allow_terminated_new_hires: true, allow_experienced_terminations: true, allow_new_hires: false,
    } } };
    const original = scenario ? { custom: 'retain' } : { ...variables, custom: 'retain' };
    const loaded = applyResolvedFormData(variables, DEFAULT_FORM_DATA);
    const before = buildConfigPayload(loaded, null, null);
    const after = buildConfigPayload({ ...loaded, dcMatchMinHoursAnnual: 750 }, null, null);
    const edited = applyConfigEdits(original, before, after) as Record<string, unknown>;
    expect(preserveDisplayedMatchEligibility(edited, before, after, variables)).toEqual({
      ...original, dc_plan: { match_min_tenure_years: 0, match_min_hours_annual: 750,
        match_require_year_end_active: true, match_allow_terminated_new_hires: false,
        match_allow_experienced_terminations: false },
    });
    expect(preserveDisplayedMatchEligibility(original, before, before, variables)).toEqual(original);
    expect(preserveDisplayedMatchEligibility(edited, before, after,
      { employer_match: { apply_eligibility: true } })).toEqual(edited);
  });

  it('leaves the new-hire waiver to service after a legacy edit, reload and service edit', () => {
    const save = (config: Record<string, unknown>, variables: Record<string, unknown>,
      edit: Partial<typeof DEFAULT_FORM_DATA>) => {
      const loaded = applyResolvedFormData(variables, DEFAULT_FORM_DATA);
      const before = buildConfigPayload(loaded, null, null);
      const after = buildConfigPayload({ ...loaded, ...edit }, null, null);
      const edited = applyConfigEdits(config, before, after) as Record<string, unknown>;
      return preserveDisplayedMatchEligibility(edited, before, after, variables);
    };
    const legacy = save({}, { employer_match: { apply_eligibility: false } }, { dcMatchMinHoursAnnual: 500 });
    expect(legacy.dc_plan).not.toHaveProperty('match_allow_new_hires');
    // The export activates the saved policy; its waiver follows the 0-year service.
    const reloaded = { employer_match: { apply_eligibility: true, eligibility: {
      minimum_tenure_years: 0, minimum_hours_annual: 500, require_active_at_year_end: true,
      allow_terminated_new_hires: false, allow_experienced_terminations: false, allow_new_hires: true,
    } } };
    // Python export of this dc_plan: tests/unit/orchestrator/test_config_export.py
    // (test_service_edit_after_legacy_studio_edit_requires_new_hire_service).
    expect(save(legacy, reloaded, { dcMatchMinTenureYears: 1 }).dc_plan).toEqual({
      match_min_tenure_years: 1, match_min_hours_annual: 500, match_require_year_end_active: true,
      match_allow_terminated_new_hires: false, match_allow_experienced_terminations: false,
    });
  });
  const policies = [false, true].flatMap(require_active_at_year_end =>
    [false, true].flatMap(allow_terminated_new_hires =>
      [false, true].map(allow_experienced_terminations => ({
        require_active_at_year_end, allow_terminated_new_hires, allow_experienced_terminations,
      })),
    ),
  );

  it.each(policies.flatMap(match => policies.map(core => ({ match, core }))))(
    'round trips independent match/core policies without materializing inherited overrides %j',
    ({ match, core }) => {
      const inherited = {
        employer_match: { apply_eligibility: true, eligibility: { ...match, minimum_tenure_years: 2, allow_new_hires: true } },
        employer_core_contribution: { eligibility: { ...core, minimum_tenure_years: 3, allow_new_hires: false } },
      };
      const original = { custom: { retain: true }, plan_design_parameters: { design_a: { eligibility: { waiting_period_days: 90 } } } };
      const loaded = applyResolvedFormData(inherited, DEFAULT_FORM_DATA);
      const payload = buildConfigPayload(loaded, null, null);
      const saved = applyConfigEdits(original, payload, payload);
      expect(saved).toEqual(original);
      const reloaded = JSON.parse(JSON.stringify(saved));
      expect(applyResolvedFormData({ ...inherited, ...reloaded }, DEFAULT_FORM_DATA)).toEqual(loaded);

      // Editing one flag adds exactly one override, preserving the other family
      // and the inherited service waivers, including explicit non-default values.
      for (const kind of ['Match', 'Core'] as const) {
        for (const [suffix, key] of [
          ['RequireYearEndActive', 'require_year_end_active'],
          ['AllowTerminatedNewHires', 'allow_terminated_new_hires'],
          ['AllowExperiencedTerminations', 'allow_experienced_terminations'],
        ] as const) {
          const field = `dc${kind}${suffix}` as const;
          const edited = buildConfigPayload({ ...loaded, [field]: !loaded[field] }, null, null);
          expect(applyConfigEdits(original, payload, edited)).toEqual({
            ...original, dc_plan: { [`${kind.toLowerCase()}_${key}`]: !loaded[field] },
          });
        }
      }
      const workspace = { ...original, ...inherited };
      expect(applyConfigEdits(workspace, payload, payload)).toEqual(workspace);
    },
  );

  it('keeps custom metadata attached during insertion, deletion and reordering', () => {
    const before = [{ rate: 1 }, { rate: 2 }];
    const original = [{ rate: 1, note: 'first' }, { rate: 2, note: 'second' }];
    expect(applyConfigEdits(original, before, [{ rate: 3 }, ...before]))
      .toEqual([{ rate: 3 }, ...original]);
    expect(applyConfigEdits(original, before, [before[1]]))
      .toEqual([original[1]]);
    expect(applyConfigEdits(original, before, [...before].reverse()))
      .toEqual([...original].reverse());
  });

  it('does not reuse custom metadata for duplicate rows', () => {
    expect(applyConfigEdits([{ rate: 1, note: 'a' }, { rate: 1, note: 'b' }],
      [{ rate: 1 }, { rate: 1 }], [{ rate: 1 }, { rate: 1 }, { rate: 2 }]))
      .toEqual([{ rate: 1, note: 'a' }, { rate: 1, note: 'b' }, { rate: 2 }]);
  });

  it('rejects ambiguous simultaneous edits and insertion of custom rows', () => {
    expect(() => applyConfigEdits([{ rate: 1, note: 'keep attached' }],
      [{ rate: 1 }], [{ rate: 2 }, { rate: 3 }])).toThrow('custom row settings');
  });

  it('allows replacing YAML-ordered match tiers with a single edited tier', () => {
    const original = { dc_plan: { match_tiers: [
      { employee_max: 0.03, employee_min: 0, match_rate: 1 },
      { employee_max: 0.05, employee_min: 0.03, match_rate: 0.5 },
    ] } };
    const loaded = applyResolvedFormData(original, DEFAULT_FORM_DATA);
    const before = buildConfigPayload(loaded, null, null);
    const after = buildConfigPayload({ ...loaded, dcMatchTiers: [
      { deferralMin: 0, deferralMax: 4, matchRate: 100 },
    ] }, null, null);
    expect(applyConfigEdits(original, before, after)).toEqual({ dc_plan: {
      match_tiers: [{ employee_min: 0, employee_max: 0.04, match_rate: 1 }],
    } });
  });

  it('matches reordered object keys without moving nested custom metadata', () => {
    const original = [{ rate: 1, range: { min: 0, max: 3 }, note: 'keep' }];
    const before = [{ range: { max: 3, min: 0 }, rate: 1 }];
    const after = [{ rate: 1, range: { min: 0, max: 3 } }, { rate: 2 }];
    expect(applyConfigEdits(original, before, after)).toEqual([...original, { rate: 2 }]);
  });

  it('keeps demographic null, explicit zero and removed inheritance distinct', () => {
    const before = buildConfigPayload({ ...DEFAULT_FORM_DATA, dcVoluntaryEnrollmentMode: 'specified', dcVoluntaryEnrollmentRate: '65' }, null, null);
    for (const [mode, expected] of [['demographic', { voluntary_enrollment_rate: null }], ['inherit', {}], ['specified', { voluntary_enrollment_rate: 0 }]] as const) {
      const after = buildConfigPayload({ ...DEFAULT_FORM_DATA, dcVoluntaryEnrollmentMode: mode, dcVoluntaryEnrollmentRate: '0' }, null, null);
      expect(applyConfigEdits({ dc_plan: { voluntary_enrollment_rate: 0.65 } }, before, after))
        .toEqual({ dc_plan: expected });
    }
  });
  it('keeps an unchanged sparse scenario sparse, including unknown and inactive settings', () => {
    const original = { custom: { enabled: true }, dc_plan: { match_enabled: false, tenure_graded_bands: [{ custom: 7 }] } };
    const payload = buildConfigPayload(DEFAULT_FORM_DATA, null, null);
    expect(applyConfigEdits(original, payload, payload)).toEqual(original);
  });

  it('adds only an edited override and preserves nested legacy fields', () => {
    const original = { dc_plan: { custom: { policy: 'retain' }, match_tiers: [{ employee_max: 0.06 }] } };
    const before = buildConfigPayload(DEFAULT_FORM_DATA, null, null);
    const after = buildConfigPayload({ ...DEFAULT_FORM_DATA, dcAutoEnroll: false }, null, null);
    expect(applyConfigEdits(original, before, after)).toEqual({
      dc_plan: { ...original.dc_plan, auto_enroll: false },
    });
  });

  it('retains unknown fields within edited schedule rows', () => {
    expect(applyConfigEdits(
      { tiers: [{ min: 0, max: 3, rate: 1, annotation: 'preserve' }] },
      { tiers: [{ min: 0, max: 3, rate: 1 }] },
      { tiers: [{ min: 0, max: 4, rate: 1 }] },
    )).toEqual({ tiers: [{ min: 0, max: 4, rate: 1, annotation: 'preserve' }] });
  });

  it('materializes all rows when editing an inherited array', () => {
    expect(applyConfigEdits({}, { tiers: [{ rate: 1 }, { rate: 2 }] }, { tiers: [{ rate: 1 }, { rate: 3 }] }))
      .toEqual({ tiers: [{ rate: 1 }, { rate: 3 }] });
  });

  it('removes an obsolete scenario census override without losing setup extras', () => {
    expect(applyConfigEdits(
      { setup: { census_parquet_path: 'old', custom: true } },
      { setup: { census_parquet_path: 'old' } }, {},
    )).toEqual({ setup: { custom: true } });
    expect(applyConfigEdits(
      { setup: { census_parquet_path: 'old', custom: true } },
      { setup: { census_parquet_path: 'old' } }, { setup: {} },
    )).toEqual({ setup: { custom: true } });
  });

  it('keeps the original input immutable', () => {
    const original = { simulation: { random_seed: 17 }, unknown: ['keep'] };
    const result = applyConfigEdits(original, { simulation: { random_seed: 17 } }, { simulation: { random_seed: 21 } });
    expect(original.simulation.random_seed).toBe(17);
    expect(result).toEqual({ simulation: { random_seed: 21 }, unknown: ['keep'] });
  });

  it('updates a canonical decimal alias only when its corresponding field changes', () => {
    const original = { compensation: { cola_rate: 0.07, merit_budget: 0.09 } };
    const before = { compensation: { cola_rate_percent: 7, merit_budget_percent: 9 } };
    const after = { compensation: { cola_rate_percent: 8, merit_budget_percent: 9 } };
    expect(synchronizeCompensationAliases(original, before, after))
      .toEqual({ compensation: { cola_rate: 0.08, merit_budget: 0.09 } });
  });

  it('saves promotion edits in nested fields and removes stale flat aliases', () => {
    const original = { compensation: {
      promotion_increase: 0.125, promotion_increase_percent: 12.5,
      promotion_distribution_range: 0.05, promotion_distribution_range_percent: 5,
      promotion_compensation: { base_increase_pct: 0.20, distribution_range: 0.03, max_cap_pct: 0.30 },
    } };
    const loaded = { ...DEFAULT_FORM_DATA, promoIncrease: 20, promoDistributionRange: 3 };
    const before = buildConfigPayload(loaded, null, null);
    const after = buildConfigPayload({ ...loaded, promoIncrease: 12.5, promoDistributionRange: 5 }, null, null);
    const edited = applyConfigEdits(original, before, after) as Record<string, unknown>;
    expect(synchronizeCompensationAliases(edited, before, after)).toEqual({ compensation: {
      promotion_compensation: { base_increase_pct: 0.125, distribution_range: 0.05, max_cap_pct: 0.30 },
    } });
    expect(synchronizeCompensationAliases(original, before, before)).toEqual(original);
  });
});
