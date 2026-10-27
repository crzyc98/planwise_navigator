import { describe, expect, it } from 'vitest';
import { DEFAULT_FORM_DATA } from './constants';
import { deferralRateChangesSummary, rateChangeGroups, validateDeferralRateChangeSettings } from './participantBehaviorConfig';

const form = { ...DEFAULT_FORM_DATA, dcDeferralRateChangesEnabled: true };

describe('contribution rate change validation', () => {
  it('accepts shipped values and annual probability boundaries', () => {
    expect(validateDeferralRateChangeSettings(form)).toEqual([]);
    expect(validateDeferralRateChangeSettings({ ...form,
      dcDeferralRateChangesWithEscalationIncreaseProbability: 100,
      dcDeferralRateChangesWithEscalationDecreaseProbability: 0,
      dcDeferralRateChangesWithoutEscalationIncreaseProbability: 0,
      dcDeferralRateChangesWithoutEscalationDecreaseProbability: 100,
      dcDeferralRateChangesStopProbability: 0, dcDeferralRateChangesRestartProbability: 100,
    })).toEqual([]);
  });

  const probabilityKeys = [...rateChangeGroups.flatMap(([, raise, lower]) => [raise, lower]),
    'dcDeferralRateChangesStopProbability', 'dcDeferralRateChangesRestartProbability'] as const;
  it.each(probabilityKeys.flatMap(key => [-0.01, 100.01, Number.NaN, Infinity].map(value => ({ key, value }))))(
    'rejects an out-of-range annual chance: %j', ({ key, value }) => {
      expect(validateDeferralRateChangeSettings({ ...form, [key]: value })).toContain('Each annual chance must be between 0% and 100%.');
    });

  it.each(rateChangeGroups)('enforces the raise + lower + stop limit for %s', (label, raise, lower) => {
    const atLimit = { ...form, [raise]: 50, [lower]: 48.5 };
    expect(validateDeferralRateChangeSettings(atLimit)).toEqual([]);
    expect(validateDeferralRateChangeSettings({ ...atLimit, [lower]: 48.51 }))
      .toContain(`${label}: raise, lower and stop chances together must be no more than 100%.`);
    // Restart is a separate draw for stopped employees, not part of the group total.
    expect(validateDeferralRateChangeSettings({ ...atLimit, dcDeferralRateChangesRestartProbability: 100 })).toEqual([]);
  });

  it.each(['dcDeferralRateChangesIncreaseSteps', 'dcDeferralRateChangesDecreaseSteps'] as const)(
    'rejects empty, duplicate, nonpositive, fractional and invalid-weight steps for %s', key => {
      for (const steps of [[], [{ pp: 0, weight: 100 }], [{ pp: -1, weight: 100 }],
        [{ pp: 1.5, weight: 100 }], [{ pp: Infinity, weight: 100 }],
        [{ pp: 1, weight: 50 }, { pp: 1, weight: 50 }], [{ pp: 1, weight: 99 }],
        [{ pp: 1, weight: -10 }, { pp: 2, weight: 110 }], [{ pp: 1, weight: Number.NaN }]]) {
        expect(validateDeferralRateChangeSettings({ ...form, [key]: steps }).length).toBeGreaterThan(0);
      }
      expect(validateDeferralRateChangeSettings({ ...form, [key]: [{ pp: 2, weight: 33.3 }, { pp: 5, weight: 66.7 }] })).toEqual([]);
    });

  it.each([0, 366, 1.5, Number.NaN])('rejects an active invalid notice window: %s', days => {
    const changed = { ...form, dcDeferralRateChangesPostEscalationDecreaseWindowDays: days };
    expect(validateDeferralRateChangeSettings(changed)).toContain('The notice response window must be a whole number from 1 to 365 days.');
    expect(validateDeferralRateChangeSettings({ ...changed, dcAutoEscalation: false })).toEqual([]);
  });

  it.each([1, 365])('accepts notice window boundary %s', days => {
    expect(validateDeferralRateChangeSettings({ ...form, dcDeferralRateChangesPostEscalationDecreaseWindowDays: days })).toEqual([]);
  });

  it('summarizes inactive, active, invalid and automatic-increase-off states in plain language', () => {
    expect(deferralRateChangesSummary({ ...DEFAULT_FORM_DATA, dcDeferralRateChangesEnabled: false })).toBe('Contribution rate changes off; settings inactive and saved values retained.');
    expect(deferralRateChangesSummary(form)).toBe('In automatic increases: 8.5% raise, 8.2% lower; Not in automatic increases: 8.5% raise, 8.2% lower; 1.5% stop, 40% restart each year. Notice responses within 90 days; stay in automatic increases.');
    expect(deferralRateChangesSummary({ ...form, dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation: true })).toContain('leave automatic increases');
    expect(deferralRateChangesSummary({ ...form, dcAutoEscalation: false })).toContain('Notice responses inactive while automatic increases are off; saved settings retained.');
    expect(deferralRateChangesSummary({ ...form, dcDeferralRateChangesStopProbability: 100 })).toContain('settings need attention');
  });
});
