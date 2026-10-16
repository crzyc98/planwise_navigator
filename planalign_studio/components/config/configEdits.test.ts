import { describe, expect, it } from 'vitest';
import { applyConfigEdits, synchronizeCompensationAliases } from './configEdits';
import { buildConfigPayload } from './buildConfigPayload';
import { DEFAULT_FORM_DATA } from './constants';
import { applyResolvedFormData } from './resolvedFormData';

describe('lossless configuration edits', () => {
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
});
