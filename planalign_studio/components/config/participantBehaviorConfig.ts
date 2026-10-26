import type { components } from '../../services/api.generated';
import type { BelowDefaultStep, BelowDefaultTier, FormData } from './types';

type BehaviorConfig = Pick<components['schemas']['StudioDCPlanConfig'],
  'escalation_mode' | 'escalation_participant_elected_signup_probability' |
  'match_magnet_downward_enabled' | 'below_default_share_tiers' | 'below_default_steps'>;

const percent = (value: number) => Number((value * 100).toFixed(10));

export const tiersToPercent = (tiers: BelowDefaultTier[]): BelowDefaultTier[] => tiers.map(tier => ({
  max_auto_enroll_default_rate: tier.max_auto_enroll_default_rate === null ? null : percent(tier.max_auto_enroll_default_rate),
  share: percent(tier.share),
}));
export const stepsToPercent = (steps: BelowDefaultStep[]): BelowDefaultStep[] => steps.map(step => ({
  pp: step.pp, weight: percent(step.weight),
}));

export function participantBehaviorFormFields(config: BehaviorConfig, form: FormData): Partial<FormData> {
  return {
    dcEscalationMode: config.escalation_mode ?? form.dcEscalationMode,
    dcEscalationSignupProbability: config.escalation_participant_elected_signup_probability == null
      ? form.dcEscalationSignupProbability : percent(config.escalation_participant_elected_signup_probability),
    dcMatchMagnetDownwardEnabled: config.match_magnet_downward_enabled ?? form.dcMatchMagnetDownwardEnabled,
    dcBelowDefaultShareTiers: config.below_default_share_tiers == null
      ? form.dcBelowDefaultShareTiers : tiersToPercent(config.below_default_share_tiers),
    dcBelowDefaultSteps: config.below_default_steps == null
      ? form.dcBelowDefaultSteps : stepsToPercent(config.below_default_steps),
  };
}

const inRange = (value: number) => Number.isFinite(value) && value >= 0 && value <= 100;

export function invalidBelowDefaultCeiling(tiers: BelowDefaultTier[], index: number): boolean {
  const ceiling = tiers[index].max_auto_enroll_default_rate;
  const previous = tiers.slice(0, index).flatMap(tier => tier.max_auto_enroll_default_rate === null ? [] : [tier.max_auto_enroll_default_rate]).at(-1);
  return ceiling !== null && (!inRange(ceiling) || (previous != null && ceiling <= previous));
}

export const belowDefaultWeightTotal = (steps: BelowDefaultStep[]): number =>
  Number(steps.reduce((sum, step) => sum + step.weight, 0).toFixed(6));

export const invalidBelowDefaultWeights = (steps: BelowDefaultStep[]): boolean =>
  !steps.length || steps.some(step => !inRange(step.weight))
    || Math.abs(steps.reduce((sum, step) => sum + step.weight, 0) - 100) > 0.0001;

function validateTiers(tiers: BelowDefaultTier[]): string[] {
  const errors: string[] = [];
  if (tiers.filter(tier => tier.max_auto_enroll_default_rate === null).length !== 1
    || tiers.at(-1)?.max_auto_enroll_default_rate !== null) {
    errors.push('The last row must cover all higher defaults.');
  }
  if (tiers.some((_, index) => invalidBelowDefaultCeiling(tiers, index))) {
    errors.push("Each 'default up to' value must be 0–100% and higher than the row above.");
  }
  if (tiers.some(tier => !inRange(tier.share))) errors.push('Each share choosing below the default must be between 0% and 100%.');
  return errors;
}

function validateSteps(steps: BelowDefaultStep[]): string[] {
  const errors: string[] = [];
  if (steps.some(step => !Number.isInteger(step.pp) || step.pp <= 0)) errors.push('Reductions must be positive whole percentage points.');
  if (!steps.length || Math.abs(steps.reduce((sum, step) => sum + step.weight, 0) - 100) > 0.0001) {
    errors.push(`Weights must add up to 100% (now ${belowDefaultWeightTotal(steps)}%).`);
  }
  if (steps.some(step => !inRange(step.weight))) errors.push('Each weight must be between 0% and 100%.');
  return errors;
}

export function validateBelowDefaultSettings(form: FormData): string[] {
  return [...validateTiers(form.dcBelowDefaultShareTiers), ...validateSteps(form.dcBelowDefaultSteps)];
}

export function applicableBelowDefaultTier(form: FormData): number {
  return form.dcBelowDefaultShareTiers.findIndex(tier =>
    tier.max_auto_enroll_default_rate === null || Number(form.dcDefaultDeferral) <= tier.max_auto_enroll_default_rate);
}

export function belowDefaultSummary(form: FormData): string {
  if (!form.dcAutoEnroll) return 'Below-default choices inactive while auto-enrollment is off; saved settings retained.';
  if (validateBelowDefaultSettings(form).length) return 'Below-default choices need attention: check tier order and step weights.';
  const index = applicableBelowDefaultTier(form);
  const share = form.dcBelowDefaultShareTiers[index]?.share;
  if (share === 0) return `At the ${form.dcDefaultDeferral}% default, no one starts below it.`;
  return `At the ${form.dcDefaultDeferral}% default, ${share}% start below it (${form.dcBelowDefaultSteps.map(step => `${step.pp} pp: ${step.weight}%`).join(', ')}).`;
}
