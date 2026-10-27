import type { components } from '../../services/api.generated';
import type { BelowDefaultStep, BelowDefaultTier, DeferralChangeStep, DeferralChangeShare, EasyEnrollPackage, FormData } from './types';

type BehaviorConfig = Pick<components['schemas']['StudioDCPlanConfig'],
  'escalation_mode' | 'escalation_participant_elected_signup_probability' |
  'match_magnet_downward_enabled' | 'below_default_share_tiers' | 'below_default_steps' |
  'easy_enroll_enabled' | 'easy_enroll_channel_share_without_auto_enrollment' |
  'easy_enroll_channel_share_with_auto_enrollment' | 'easy_enroll_packages' | 'easy_enroll_escalation_cap' |
  'deferral_rate_changes_enabled' |
  'deferral_rate_changes_with_escalation_increase_probability' |
  'deferral_rate_changes_with_escalation_decrease_probability' |
  'deferral_rate_changes_without_escalation_increase_probability' |
  'deferral_rate_changes_without_escalation_decrease_probability' |
  'deferral_rate_changes_increase_steps' |
  'deferral_rate_changes_decrease_shares' |
  'deferral_rate_changes_post_escalation_decrease_window_days' |
  'deferral_rate_changes_post_escalation_decrease_leaves_escalation' |
  'deferral_rate_changes_stop_probability' |
  'deferral_rate_changes_restart_probability'>;

const percent = (value: number) => Number((value * 100).toFixed(10));

export const tiersToPercent = (tiers: BelowDefaultTier[]): BelowDefaultTier[] => tiers.map(tier => ({
  max_auto_enroll_default_rate: tier.max_auto_enroll_default_rate === null ? null : percent(tier.max_auto_enroll_default_rate),
  share: percent(tier.share),
}));
export const stepsToPercent = (steps: BelowDefaultStep[]): BelowDefaultStep[] => steps.map(step => ({
  pp: step.pp, weight: percent(step.weight),
}));

export const sharesToPercent = (shares: DeferralChangeShare[]): DeferralChangeShare[] => shares.map(row => ({
  share: percent(row.share), weight: percent(row.weight),
}));

export const packagesToPercent = (packages: EasyEnrollPackage[]): EasyEnrollPackage[] => packages.map(pkg => ({
  rate: percent(pkg.rate), share: percent(pkg.share),
}));

export function participantBehaviorFormFields(config: BehaviorConfig, form: FormData): Partial<FormData> {
  return {
    dcDeferralRateChangesEnabled: config.deferral_rate_changes_enabled ?? form.dcDeferralRateChangesEnabled,
    dcDeferralRateChangesWithEscalationIncreaseProbability: config.deferral_rate_changes_with_escalation_increase_probability == null
      ? form.dcDeferralRateChangesWithEscalationIncreaseProbability : percent(config.deferral_rate_changes_with_escalation_increase_probability),
    dcDeferralRateChangesWithEscalationDecreaseProbability: config.deferral_rate_changes_with_escalation_decrease_probability == null
      ? form.dcDeferralRateChangesWithEscalationDecreaseProbability : percent(config.deferral_rate_changes_with_escalation_decrease_probability),
    dcDeferralRateChangesWithoutEscalationIncreaseProbability: config.deferral_rate_changes_without_escalation_increase_probability == null
      ? form.dcDeferralRateChangesWithoutEscalationIncreaseProbability : percent(config.deferral_rate_changes_without_escalation_increase_probability),
    dcDeferralRateChangesWithoutEscalationDecreaseProbability: config.deferral_rate_changes_without_escalation_decrease_probability == null
      ? form.dcDeferralRateChangesWithoutEscalationDecreaseProbability : percent(config.deferral_rate_changes_without_escalation_decrease_probability),
    dcDeferralRateChangesIncreaseSteps: config.deferral_rate_changes_increase_steps == null
      ? form.dcDeferralRateChangesIncreaseSteps : stepsToPercent(config.deferral_rate_changes_increase_steps),
    dcDeferralRateChangesDecreaseShares: config.deferral_rate_changes_decrease_shares == null
      ? form.dcDeferralRateChangesDecreaseShares : sharesToPercent(config.deferral_rate_changes_decrease_shares),
    dcDeferralRateChangesPostEscalationDecreaseWindowDays: config.deferral_rate_changes_post_escalation_decrease_window_days ?? form.dcDeferralRateChangesPostEscalationDecreaseWindowDays,
    dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation: config.deferral_rate_changes_post_escalation_decrease_leaves_escalation ?? form.dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation,
    dcDeferralRateChangesStopProbability: config.deferral_rate_changes_stop_probability == null
      ? form.dcDeferralRateChangesStopProbability : percent(config.deferral_rate_changes_stop_probability),
    dcDeferralRateChangesRestartProbability: config.deferral_rate_changes_restart_probability == null
      ? form.dcDeferralRateChangesRestartProbability : percent(config.deferral_rate_changes_restart_probability),
    dcEasyEnrollEnabled: config.easy_enroll_enabled ?? form.dcEasyEnrollEnabled,
    dcEasyEnrollShareWithoutAutoEnrollment: config.easy_enroll_channel_share_without_auto_enrollment == null
      ? form.dcEasyEnrollShareWithoutAutoEnrollment : percent(config.easy_enroll_channel_share_without_auto_enrollment),
    dcEasyEnrollShareWithAutoEnrollment: config.easy_enroll_channel_share_with_auto_enrollment == null
      ? form.dcEasyEnrollShareWithAutoEnrollment : percent(config.easy_enroll_channel_share_with_auto_enrollment),
    dcEasyEnrollPackages: config.easy_enroll_packages == null
      ? form.dcEasyEnrollPackages : packagesToPercent(config.easy_enroll_packages),
    dcEasyEnrollEscalationCap: config.easy_enroll_escalation_cap == null
      ? form.dcEasyEnrollEscalationCap : percent(config.easy_enroll_escalation_cap),
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

export const distributionTotal = (shares: number[]): number =>
  Number(shares.reduce((sum, share) => sum + share, 0).toFixed(6));

export const invalidDistribution = (shares: number[]): boolean =>
  !shares.length || shares.some(share => !inRange(share))
    || Math.abs(shares.reduce((sum, share) => sum + share, 0) - 100) > 0.0001;

export function invalidEasyEnrollRate(packages: EasyEnrollPackage[], index: number): boolean {
  const rate = packages[index].rate;
  return !inRange(rate) || rate <= 0 || packages.some((pkg, row) => row !== index && pkg.rate === rate);
}

export function validateEasyEnrollSettings(form: FormData): string[] {
  const packages = form.dcEasyEnrollPackages;
  const errors: string[] = [];
  if (!packages.length) errors.push('Add at least one Easy Enroll package.');
  if (packages.some((_, index) => invalidEasyEnrollRate(packages, index))) {
    errors.push('Package contribution rates must be unique and greater than 0%, up to 100%.');
  }
  if (invalidDistribution(packages.map(pkg => pkg.share))) {
    errors.push(`Package shares must be between 0% and 100% and add up to 100% (now ${distributionTotal(packages.map(pkg => pkg.share))}%).`);
  }
  if (![form.dcEasyEnrollShareWithAutoEnrollment, form.dcEasyEnrollShareWithoutAutoEnrollment].every(value => inRange(Number(value)))) {
    errors.push('Each share of self-enrollees must be between 0% and 100%.');
  }
  if (!inRange(Number(form.dcEasyEnrollEscalationCap))) errors.push('The Easy Enroll automatic increase limit must be between 0% and 100%.');
  return errors;
}

export function easyEnrollSummary(form: FormData): string {
  if (!form.dcEasyEnrollEnabled) return 'Easy Enroll off; package settings inactive and saved values retained.';
  if (validateEasyEnrollSettings(form).length) return 'Easy Enroll settings need attention: check package rates, shares and automatic increase limit.';
  const share = form.dcAutoEnroll ? form.dcEasyEnrollShareWithAutoEnrollment : form.dcEasyEnrollShareWithoutAutoEnrollment;
  return `${share}% of self-enrollees use Easy Enroll; packages: ${form.dcEasyEnrollPackages.map(pkg => `${pkg.rate}% contribution chosen by ${pkg.share}%`).join(', ')}. Automatic increases stop at ${form.dcEasyEnrollEscalationCap}%, even when plan-wide automatic increases are off.`;
}

export const rateChangeGroups = [
  ['In automatic increases', 'dcDeferralRateChangesWithEscalationIncreaseProbability', 'dcDeferralRateChangesWithEscalationDecreaseProbability'],
  ['Not in automatic increases', 'dcDeferralRateChangesWithoutEscalationIncreaseProbability', 'dcDeferralRateChangesWithoutEscalationDecreaseProbability'],
] as const;

export function invalidRateChangeStep(steps: DeferralChangeStep[], index: number): boolean {
  const pp = steps[index].pp;
  return !Number.isInteger(pp) || pp <= 0 || steps.some((step, row) => row !== index && step.pp === pp);
}

export function validateDeferralRateChangeSettings(form: FormData): string[] {
  const errors: string[] = [];
  const probabilities = rateChangeGroups.flatMap(([, raise, lower]) => [form[raise], form[lower]]);
  if (![...probabilities, form.dcDeferralRateChangesStopProbability, form.dcDeferralRateChangesRestartProbability].every(inRange)) {
    errors.push('Each annual chance must be between 0% and 100%.');
  }
  for (const [label, raise, lower] of rateChangeGroups) {
    if (form[raise] + form[lower] + form.dcDeferralRateChangesStopProbability > 100 + 1e-8) {
      errors.push(`${label}: raise, lower and stop chances together must be no more than 100%.`);
    }
  }
  for (const [label, steps] of [['Raise', form.dcDeferralRateChangesIncreaseSteps]] as const) {
    if (!steps.length || steps.some((_, index) => invalidRateChangeStep(steps, index))) {
      errors.push(`${label} steps must be unique positive whole percentage points.`);
    }
    if (invalidDistribution(steps.map(step => step.weight))) {
      errors.push(`${label} weights must be between 0% and 100% and add up to 100% (now ${distributionTotal(steps.map(step => step.weight))}%).`);
    }
  }
  const shares = form.dcDeferralRateChangesDecreaseShares;
  if (!shares.length || shares.some(row => !Number.isFinite(row.share) || row.share <= 0 || row.share >= 100)) {
    errors.push('Lower shares must be greater than 0% and less than 100%.');
  }
  if (invalidDistribution(shares.map(row => row.weight))) errors.push('Lower weights must be between 0% and 100% and add up to 100%.');
  const days = form.dcDeferralRateChangesPostEscalationDecreaseWindowDays;
  if (form.dcAutoEscalation && (!Number.isInteger(days) || days < 1 || days > 365)) {
    errors.push('The notice response window must be a whole number from 1 to 365 days.');
  }
  return errors;
}

export function deferralRateChangesSummary(form: FormData): string {
  if (!form.dcDeferralRateChangesEnabled) return 'Contribution rate changes off; settings inactive and saved values retained.';
  if (validateDeferralRateChangeSettings(form).length) return 'Contribution rate change settings need attention: check annual chances, steps and notice response window.';
  const groups = rateChangeGroups.map(([label, raise, lower]) => `${label}: ${form[raise]}% raise, ${form[lower]}% lower`).join('; ');
  const response = form.dcAutoEscalation
    ? `Notice responses within ${form.dcDeferralRateChangesPostEscalationDecreaseWindowDays} days; ${form.dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation ? 'leave' : 'stay in'} automatic increases.`
    : 'Notice responses inactive while automatic increases are off; saved settings retained.';
  return `${groups}; ${form.dcDeferralRateChangesStopProbability}% stop, ${form.dcDeferralRateChangesRestartProbability}% restart each year. ${response} Lower cuts: ${form.dcDeferralRateChangesDecreaseShares.map(row => `${row.share}% of current rate: ${row.weight}%`).join(', ')}.`;
}
