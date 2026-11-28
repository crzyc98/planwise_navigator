// Plain-language descriptions of a grandfathered design for the panel summary and cohort preview.
import type { DesignFormula, FormData, GrandfatheredDesignForm } from './types';

const range = (min: number, max: number | null, unit: string) => `${min}–${max ?? '∞'} ${unit}`;

export function matchFormulaSummary(formula: DesignFormula): string {
  switch (formula.dcMatchMode) {
    case 'deferral_based': return formula.dcMatchTiers.map(tier => tier.deferralMin === 0
      ? `${tier.matchRate}% on the first ${tier.deferralMax}%`
      : `${tier.matchRate}% on the next ${Number((tier.deferralMax - tier.deferralMin).toFixed(2))}%`).join(', ') || 'No tiers';
    case 'graded_by_service': return `By years of service: ${formula.dcTenureMatchTiers.map(tier => `${range(tier.minYears, tier.maxYears, 'years')}: ${tier.matchRate}% match on contributions up to ${tier.maxDeferralPct}%`).join('; ')}`;
    case 'tenure_graded':
    case 'tenure_based': return `By years of service, ${formula.dcTenureGradedBands.length} bands`;
    case 'points_based': return `By age + service points: ${formula.dcPointsMatchTiers.map(tier => `${range(tier.minPoints, tier.maxPoints, 'points')}: ${tier.matchRate}% match on contributions up to ${tier.maxDeferralPct}%`).join('; ')}`;
    default: return `Saved custom mode: ${formula.dcMatchMode}`;
  }
}

export function coreFormulaSummary(formula: DesignFormula): string {
  const integration = formula.dcCoreIntegrationEnabled ? `, plus ${formula.dcCoreIntegrationDisparityRate}% above the integration level` : '';
  switch (formula.dcCoreStatus) {
    case 'flat': return `${formula.dcCoreContributionRate}% of pay${integration}`;
    case 'graded_by_service': return `By years of service: ${formula.dcCoreGradedSchedule.map(tier => `${range(tier.serviceYearsMin, tier.serviceYearsMax, 'years')}: ${tier.rate}%`).join('; ')}${integration}`;
    case 'age_banded': return `By age: ${formula.dcCoreAgeSchedule.map(tier => `ages ${tier.minAge}–${tier.maxAge ?? '∞'}: ${tier.rate}%`).join('; ')}${integration}`;
    case 'points_based': return `By age + service points: ${formula.dcCorePointsSchedule.map(tier => `${range(tier.minPoints, tier.maxPoints, 'points')}: ${tier.rate}%`).join('; ')}${integration}`;
    default: return `Saved custom mode: ${formula.dcCoreStatus}`;
  }
}

const changes = (design: GrandfatheredDesignForm): string =>
  [design.changeMatch && 'match', design.changeCore && 'core contribution'].filter(Boolean).join(' and ');

export function grandfatheredDesignSummary(form: FormData, locked: boolean): string {
  const design = form.dcGrandfather;
  if (locked) return 'Plan designs were set up outside this editor. Studio keeps them unchanged when you save.';
  if (!design?.enabled) {
    return design?.savedActive
      ? 'Off. Saving removes the new-hire design; everyone will use the plan on this page.'
      : 'Off. Everyone uses the plan on this page.';
  }
  const different = changes(design);
  return `Employees hired on or after ${design.cutoff || '(no date)'} get “${design.newHireDesignId}”${different ? ` with a different ${different}` : ''}; everyone hired earlier keeps “${design.existingDesignId}”.`;
}
