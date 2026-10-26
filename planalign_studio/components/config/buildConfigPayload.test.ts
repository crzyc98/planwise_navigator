import { describe, expect, it } from 'vitest';
import { applyConfigToFormData } from './ConfigContext';
import { buildConfigPayload } from './buildConfigPayload';
import { applyConfigEdits } from './configEdits';
import { DEFAULT_FORM_DATA } from './constants';
import { applyResolvedFormData } from './resolvedFormData';

const payload = (form: typeof DEFAULT_FORM_DATA) => buildConfigPayload(form, null, null);
const behavior = {
  escalation_mode: 'participant_elected' as const,
  escalation_participant_elected_signup_probability: 0.0125,
  match_magnet_downward_enabled: true,
  below_default_share_tiers: [{ max_auto_enroll_default_rate: 0.03, share: 0.1 }, { max_auto_enroll_default_rate: null, share: 0.15 }],
  below_default_steps: [{ pp: 1, weight: 0.75 }, { pp: 3, weight: 0.25 }],
};

describe('participant behavior payload and inheritance', () => {
  it('loads stored decimal settings as percentages and exports them exactly once', () => {
    const form = applyConfigToFormData({ dc_plan: behavior }, DEFAULT_FORM_DATA);
    expect(form).toMatchObject({ dcEscalationMode: 'participant_elected', dcEscalationSignupProbability: 1.25,
      dcMatchMagnetDownwardEnabled: true,
      dcBelowDefaultShareTiers: [{ max_auto_enroll_default_rate: 3, share: 10 }, { max_auto_enroll_default_rate: null, share: 15 }],
      dcBelowDefaultSteps: [{ pp: 1, weight: 75 }, { pp: 3, weight: 25 }],
    });
    expect(payload(form).dc_plan).toMatchObject(behavior);
    expect(behavior.below_default_steps[0].weight).toBe(0.75);
  });

  it('keeps shipped defaults neutral, including explicit false and zero overrides', () => {
    expect(payload(DEFAULT_FORM_DATA).dc_plan).toMatchObject({
      escalation_mode: 'automatic', escalation_participant_elected_signup_probability: 0,
      match_magnet_downward_enabled: false,
      below_default_share_tiers: [{ max_auto_enroll_default_rate: null, share: 0 }],
      below_default_steps: [{ pp: 1, weight: 0.5 }, { pp: 2, weight: 0.3 }, { pp: 3, weight: 0.2 }],
    });
    const inherited = applyConfigToFormData({ dc_plan: behavior }, DEFAULT_FORM_DATA);
    const neutral = applyConfigToFormData({ dc_plan: { escalation_mode: 'automatic',
      escalation_participant_elected_signup_probability: 0, match_magnet_downward_enabled: false,
    } }, inherited);
    expect(neutral).toMatchObject({ dcEscalationMode: 'automatic', dcEscalationSignupProbability: 0, dcMatchMagnetDownwardEnabled: false });
    expect(neutral.dcBelowDefaultShareTiers).toEqual(inherited.dcBelowDefaultShareTiers);
  });

  it.each([{}, { simulation: { random_seed: 13 } }, { dc_plan: behavior }])(
    'does not add new keys when an untouched scenario is saved: %j', original => {
      const loaded = applyResolvedFormData({ deferral_escalation_mode: 'participant_elected',
        deferral_escalation_participant_elected_signup_probability: 0.02,
        enrollment_match_magnet_downward_enabled: true,
        below_default_share_tiers: behavior.below_default_share_tiers, below_default_steps: behavior.below_default_steps,
      }, applyConfigToFormData(original, DEFAULT_FORM_DATA));
      const before = payload(loaded);
      expect(applyConfigEdits(original, before, payload(structuredClone(loaded)))).toEqual(original);
      // Saving an unrelated edit must not materialize the displayed inherited values either.
      expect(applyConfigEdits(original, before, payload({ ...loaded, seed: loaded.seed + 1 }))).toEqual({
        ...original, simulation: { ...('simulation' in original ? original.simulation : {}), random_seed: loaded.seed + 1 },
      });
    },
  );

  it('persists just the edited behavior keys in a sparse scenario', () => {
    const loaded = applyResolvedFormData({}, DEFAULT_FORM_DATA);
    const after = { ...loaded, dcEscalationSignupProbability: 1.25, dcMatchMagnetDownwardEnabled: true };
    expect(applyConfigEdits({}, payload(loaded), payload(after))).toEqual({ dc_plan: {
      escalation_participant_elected_signup_probability: 0.0125, match_magnet_downward_enabled: true,
    } });
  });
});
