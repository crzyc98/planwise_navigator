// Formula checks shared by the plan-wide editors and the grandfathered new-hire design.
import type { FormData } from './types';

type CoreRateFields = Pick<FormData, 'dcCoreStatus' | 'dcCoreContributionRate' | 'dcCoreGradedSchedule' | 'dcCorePointsSchedule' | 'dcCoreAgeSchedule'>;
type CoreIntegrationFields = CoreRateFields & Pick<FormData, 'dcCoreIntegrationEnabled' | 'dcCoreIntegrationDisparityRate'>;

/**
 * The lowest base core rate any employee could receive, as a percentage.
 *
 * Mirrors `min_schedule_rate` in permitted_disparity.py: with a varying
 * schedule, §401(l) binds on the *lowest* band, since an employee in that band
 * may not receive a disparity exceeding their own base rate.
 */
export function minCoreBaseRatePercent(formData: CoreRateFields): number | null {
  const tierMin = (tiers: Array<{ rate: number }>) =>
    tiers.length ? Math.min(...tiers.map((t) => Number(t.rate) || 0)) : null;

  switch (formData.dcCoreStatus) {
    case 'graded_by_service':
      return tierMin(formData.dcCoreGradedSchedule ?? []);
    case 'points_based':
      return tierMin(formData.dcCorePointsSchedule ?? []);
    case 'age_banded':
      return tierMin(formData.dcCoreAgeSchedule ?? []);
    default:
      return Number(formData.dcCoreContributionRate) || 0;
  }
}

/**
 * Warn when the disparity rate exceeds the base rate — the §401(l) constraint
 * that needs no wage-base lookup and is by far the most common violation.
 *
 * Deliberately partial. The permitted-disparity *factor* (5.7% / 5.4% / 4.3%,
 * by integration level relative to that year's taxable wage base) depends on
 * seed data the browser does not have, so the server stays authoritative and
 * this never claims a configuration is legal — only that one is not.
 */
export function validateCoreIntegration(formData: CoreIntegrationFields): string[] {
  if (!formData.dcCoreIntegrationEnabled) return [];

  const disparity = Number(formData.dcCoreIntegrationDisparityRate) || 0;
  const baseRate = minCoreBaseRatePercent(formData);
  const warnings: string[] = [];

  if (baseRate !== null && disparity > baseRate) {
    const scope =
      formData.dcCoreStatus === 'flat'
        ? 'the base core rate'
        : 'the lowest band of the core schedule';
    warnings.push(
      `Disparity rate ${disparity}% exceeds ${scope} (${baseRate}%). Under §401(l) the ` +
        `disparity may not exceed the base rate, so this run will be rejected. Either ` +
        `raise the base rate to ${disparity}% or lower the disparity to ${baseRate}%.`
    );
  }

  if (disparity > 5.7) {
    warnings.push(
      `Disparity rate ${disparity}% exceeds the maximum permitted disparity factor of 5.7%.`
    );
  }

  return warnings;
}

export function validateMatchTiers(
  tiers: Array<{ min: number; max: number | null }>,
  label: string,
): string[] {
  const warnings: string[] = [];
  if (tiers.length === 0) return warnings;
  const sorted = [...tiers].sort((a, b) => a.min - b.min);
  if (sorted[0].min !== 0) {
    warnings.push(`First tier starts at ${sorted[0].min} — should start at 0 to cover all employees`);
  }
  for (let i = 0; i < sorted.length; i++) {
    const t = sorted[i];
    if (t.max !== null && t.max <= t.min) {
      warnings.push(`Tier ${i + 1}: max (${t.max}) must be greater than min (${t.min})`);
    }
  }
  for (let i = 0; i < sorted.length - 1; i++) {
    const currMax = sorted[i].max;
    const nextMin = sorted[i + 1].min;
    if (currMax === null) {
      warnings.push(`Tier ${i + 1} has no upper bound but is not the last tier — tiers after it will never apply`);
      continue;
    }
    if (currMax < nextMin) {
      warnings.push(`Gap: ${label} ${currMax}–${nextMin} is not covered between tier ${i + 1} and ${i + 2}`);
    } else if (currMax > nextMin) {
      warnings.push(`Overlap: ${label} ${nextMin}–${currMax} is covered by both tier ${i + 1} and ${i + 2}`);
    }
  }
  return warnings;
}
