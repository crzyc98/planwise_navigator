// Checks a grandfathered design before save, in the terms the engine enforces
// (planalign_orchestrator/config/plan_design.py), so problems surface before a run.
import { CORE_FAMILIES } from './designParameters';
import { newHireFormula } from './grandfatheredDesign';
import type { DesignFormula, FormData, GrandfatheredDesignForm } from './types';

interface Band { min: number; max: number | null; rate: number }

// Same rule as check_identifier: the id is written into SQL as a literal.
const DESIGN_ID = /^[A-Za-z0-9 _.:-]{1,128}$/;
function isDate(value: string): boolean {
  const date = new Date(`${value}T00:00:00Z`);
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value);
}

function cutoffErrors(design: GrandfatheredDesignForm): string[] {
  return isDate(design.cutoff) ? [] : ['Enter the hire-date cutoff as a full date, for example 2026-01-01.'];
}

function idError(id: string, label: string): string | null {
  if (!id.trim()) return `Enter a name for the ${label} design.`;
  if (id !== id.trim() || !DESIGN_ID.test(id)) {
    return `The ${label} design name "${id}" can use only letters, numbers, spaces and _ . : - (up to 128 characters, no spaces at the start or end).`;
  }
  return null;
}

function idErrors(design: GrandfatheredDesignForm, inherited: string[]): string[] {
  const errors = [idError(design.existingDesignId, 'existing-employee'), idError(design.newHireDesignId, 'new-hire')]
    .filter((error): error is string => error !== null);
  if (!errors.length && design.existingDesignId === design.newHireDesignId) {
    errors.push('Give the existing-employee and new-hire designs different names.');
  }
  const names = [design.existingDesignId, design.newHireDesignId].sort();
  if (!errors.length && inherited.length && names.join('\n') !== inherited.join('\n')) {
    errors.push(`The workspace already defines plan designs named ${inherited.map(id => `“${id}”`).join(' and ')}. Use the same names in this scenario: a scenario adds to the workspace’s designs rather than replacing them.`);
  }
  return errors;
}

/** Schedule rows must start below where they end, stay within `maxRate`%, and not overlap. */
function bandErrors(label: string, bands: Band[], maxRate: number): string[] {
  if (!bands.length) return [`${label}: add at least one tier.`];
  const errors: string[] = [];
  if (bands.some(band => band.max !== null && band.max <= band.min)) errors.push(`${label}: each tier must end above where it starts.`);
  if (bands.some(band => !(band.rate >= 0 && band.rate <= maxRate))) errors.push(`${label}: rates must be between 0% and ${maxRate}%.`);
  const sorted = [...bands].sort((a, b) => a.min - b.min);
  if (sorted.some((band, index) => index > 0 && (sorted[index - 1].max ?? Infinity) > band.min)) errors.push(`${label}: tiers overlap.`);
  return errors;
}

function matchErrors(label: string, formula: DesignFormula): string[] {
  const name = `${label} match`;
  const deferral = (tiers: DesignFormula['dcMatchTiers']) =>
    tiers.map(tier => ({ min: tier.deferralMin, max: tier.deferralMax, rate: tier.matchRate }));
  switch (formula.dcMatchMode) {
    case 'deferral_based': return bandErrors(name, deferral(formula.dcMatchTiers), 100);
    case 'graded_by_service': return bandErrors(name, formula.dcTenureMatchTiers.map(tier => ({ min: tier.minYears, max: tier.maxYears, rate: tier.matchRate })), 100);
    case 'points_based': return bandErrors(name, formula.dcPointsMatchTiers.map(tier => ({ min: tier.minPoints, max: tier.maxPoints, rate: tier.matchRate })), 100);
    case 'tenure_graded':
    case 'tenure_based':
      if (!formula.dcTenureGradedBands.length) return [`${name}: add at least one service band.`];
      return formula.dcTenureGradedBands.flatMap((band, index) => bandErrors(`${name}, service band ${index + 1}`, deferral(band.tiers), 100));
    default: return [`${name}: the saved calculation mode "${formula.dcMatchMode}" can't be used in a two-design plan. Choose one of the listed modes.`];
  }
}

function coreScheduleErrors(name: string, formula: DesignFormula): string[] {
  switch (formula.dcCoreStatus) {
    case 'graded_by_service': return bandErrors(name, formula.dcCoreGradedSchedule.map(tier => ({ min: tier.serviceYearsMin, max: tier.serviceYearsMax, rate: tier.rate })), 100);
    case 'age_banded': return bandErrors(name, formula.dcCoreAgeSchedule.map(tier => ({ min: tier.minAge, max: tier.maxAge, rate: tier.rate })), 100);
    case 'points_based': return [
      ...bandErrors(name, formula.dcCorePointsSchedule.map(tier => ({ min: tier.minPoints, max: tier.maxPoints, rate: tier.rate })), 100),
      ...(formula.dcCorePointsMinServiceEnabled && !(Number.isInteger(Number(formula.dcCorePointsMinServiceYears)) && Number(formula.dcCorePointsMinServiceYears) >= 1)
        ? [`${name}: the minimum service must be a whole number of years, 1 or more.`] : []),
    ];
    default: return Number(formula.dcCoreContributionRate) >= 0 && Number(formula.dcCoreContributionRate) <= 100
      ? [] : [`${name}: the rate must be between 0% and 100%.`];
  }
}

function coreErrors(label: string, formula: DesignFormula): string[] {
  const name = `${label} core contribution`;
  if (!(CORE_FAMILIES as readonly string[]).includes(formula.dcCoreStatus)) {
    return [`${name}: the saved contribution type "${formula.dcCoreStatus}" can't be used in a two-design plan. Choose one of the listed types.`];
  }
  const missingLevel = formula.dcCoreIntegrationEnabled && formula.dcCoreIntegrationLevelMode !== 'ss_wage_base'
    && (formula.dcCoreIntegrationLevelValue === null || String(formula.dcCoreIntegrationLevelValue).trim() === '');
  return [...coreScheduleErrors(name, formula), ...(missingLevel ? [`${name}: enter the Social Security integration level.`] : [])];
}

function formulaErrors(label: string, formula: DesignFormula, design: GrandfatheredDesignForm, isNewHire: boolean): string[] {
  const match = !isNewHire || design.changeMatch ? matchErrors(label, formula) : [];
  const core = !isNewHire || design.changeCore ? coreErrors(label, formula) : [];
  return [...match, ...core];
}

/**
 * Problems that would stop a run, in plain words. Empty when the feature is off.
 * `inherited` lists design names a scenario inherits from its workspace.
 */
export function grandfatheredDesignErrors(form: FormData, inherited: string[] = []): string[] {
  const design = form.dcGrandfather;
  if (!design?.enabled) return [];
  const sameDesign = design.changeMatch || design.changeCore
    ? [] : ['Choose what is different for new hires: the employer match, the core contribution, or both.'];
  const escalation = Number(form.dcEscalationRate) > Number(form.dcEscalationCap)
    ? ['Automatic contribution increases: the yearly increase can’t be larger than the cap.'] : [];
  return [
    ...cutoffErrors(design),
    ...idErrors(design, inherited),
    ...sameDesign,
    ...formulaErrors('Existing employees’', form, design, false),
    ...formulaErrors('New hires’', newHireFormula(form, design), design, true),
    ...escalation,
  ];
}
