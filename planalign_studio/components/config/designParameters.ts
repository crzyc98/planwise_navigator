// One plan design in the engine's typed contract (planalign_orchestrator/config/plan_design.py,
// PlanDesignParameters), built from and read back into Studio's form fields.
// Match and flat/service core rates are fractions; age and points core rates are percents.
import { calculateMatchCap } from './constants';
import { CORE_FORMULA_KEYS, MATCH_FORMULA_KEYS } from './types';
import type { DesignFormula, FormData, MatchTier } from './types';

type Json = Record<string, unknown>;
type Row = Record<string, unknown>;

const fraction = (percent: number | string): number => Number(percent) / 100;
// Avoid binary floating-point artifacts in controls and comparisons.
const percent = (value: unknown): number => Number((Number(value) * 100).toFixed(10));
const rows = (value: unknown): Row[] => (Array.isArray(value) ? value : []) as Row[];
const upper = (value: unknown): number | null => (typeof value === 'number' ? value : null);
const asJson = (value: unknown): Json =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Json : {};

export const MATCH_FAMILIES = ['deferral_based', 'graded_by_service', 'tenure_graded', 'points_based'] as const;
export const CORE_FAMILIES = ['flat', 'graded_by_service', 'points_based', 'age_banded'] as const;
const matchFamily = (mode: string): string => (mode === 'tenure_based' ? 'tenure_graded' : mode);

export function pickFormula(form: DesignFormula): DesignFormula {
  const keys = [...MATCH_FORMULA_KEYS, ...CORE_FORMULA_KEYS];
  return Object.fromEntries(keys.map(key => [key, structuredClone(form[key])])) as DesignFormula;
}

const deferralTiers = (tiers: MatchTier[]) => tiers.map(tier => ({
  employee_min: fraction(tier.deferralMin), employee_max: fraction(tier.deferralMax), match_rate: fraction(tier.matchRate),
}));

const MATCH_SCHEDULES: Record<string, (formula: DesignFormula) => Json> = {
  deferral_based: formula => ({ tiers: deferralTiers(formula.dcMatchTiers) }),
  graded_by_service: formula => ({ graded_schedule: formula.dcTenureMatchTiers.map(tier => ({
    min_value: tier.minYears, max_value: tier.maxYears,
    match_rate: fraction(tier.matchRate), max_deferral_pct: fraction(tier.maxDeferralPct),
  })) }),
  tenure_graded: formula => ({ tenure_graded_bands: formula.dcTenureGradedBands.map(band => ({
    min_years: band.minYears, max_years: band.maxYears, tiers: deferralTiers(band.tiers),
  })) }),
  points_based: formula => ({ points_tiers: formula.dcPointsMatchTiers.map(tier => ({
    min_value: tier.minPoints, max_value: tier.maxPoints,
    match_rate: fraction(tier.matchRate), max_deferral_pct: fraction(tier.maxDeferralPct),
  })) }),
};

function matchParameters(formula: DesignFormula): Json {
  const family = matchFamily(formula.dcMatchMode);
  return {
    family,
    match_template: formula.dcMatchTemplate,
    cap_percent: calculateMatchCap(formula.dcMatchTiers),
    ...MATCH_SCHEDULES[family]?.(formula),
  };
}

const CORE_SCHEDULES: Record<string, (formula: DesignFormula) => Json> = {
  flat: () => ({}),
  graded_by_service: formula => ({ graded_schedule: formula.dcCoreGradedSchedule.map(tier => ({
    min_years: tier.serviceYearsMin, max_years: tier.serviceYearsMax, rate: fraction(tier.rate),
  })) }),
  points_based: formula => ({
    points_schedule: formula.dcCorePointsSchedule.map(tier => ({
      min_points: tier.minPoints, max_points: tier.maxPoints, rate: Number(tier.rate),
    })),
    ...(formula.dcCorePointsMinServiceEnabled ? {
      points_min_service_years: Number(formula.dcCorePointsMinServiceYears),
      points_pre_service_rate: Number(formula.dcCorePointsPreServiceRate),
    } : {}),
  }),
  age_banded: formula => ({ age_schedule: formula.dcCoreAgeSchedule.map(tier => ({
    min_age: tier.minAge, max_age: tier.maxAge, rate: Number(tier.rate),
  })) }),
};

function coreParameters(formula: DesignFormula): Json {
  const levelMode = formula.dcCoreIntegrationLevelMode;
  return {
    family: formula.dcCoreStatus,
    contribution_rate: fraction(formula.dcCoreContributionRate),
    ...CORE_SCHEDULES[formula.dcCoreStatus]?.(formula),
    integration_enabled: Boolean(formula.dcCoreIntegrationEnabled),
    integration_level_mode: levelMode,
    integration_level_value: levelMode === 'ss_wage_base' ? null : Number(formula.dcCoreIntegrationLevelValue),
    integration_disparity_rate: fraction(formula.dcCoreIntegrationDisparityRate),
  };
}

/** Terms both designs share: they come from the plan-wide settings on the DC Plan page. */
export function sharedParameters(form: FormData): Json {
  return {
    auto_enrollment: {
      default_deferral_rate: fraction(form.dcDefaultDeferral),
      window_days: Number(form.dcAutoEnrollWindowDays),
      scope: form.dcAutoEnrollScope === 'new_hires_only' ? 'new_hires_only' : 'all_eligible_employees',
      reenrollment_sweep: {
        enabled: Boolean(form.dcReenrollmentSweepEnabled),
        interval_years: Number(form.dcReenrollmentSweepIntervalYears),
        first_year: form.dcReenrollmentSweepFirstYear === '' ? null : Number(form.dcReenrollmentSweepFirstYear),
        method: form.dcReenrollmentSweepMethod,
        include_non_contributors: Boolean(form.dcReenrollmentSweepIncludeNonContributors),
        include_below_default: Boolean(form.dcReenrollmentSweepIncludeBelowDefault),
        include_below_aip_cap: Boolean(form.dcReenrollmentSweepIncludeBelowAipCap),
        decline_probability: fraction(form.dcReenrollmentSweepDeclineProbability),
      },
    },
    deferral_escalation: { increment: fraction(form.dcEscalationRate), cap: fraction(form.dcEscalationCap) },
    // The engine counts each modeled month as 30 days, as for dc_plan.eligibility_months.
    eligibility: { waiting_period_days: Math.trunc(Number(form.dcEligibilityMonths)) * 30 },
  };
}

/** A complete design: `formula` for match and core, the plan-wide settings for the rest. */
export function designParameters(form: FormData, formula: DesignFormula = form): Json {
  return { match: matchParameters(formula), employer_core: coreParameters(formula), ...sharedParameters(form) };
}

const readTiers = (value: unknown): MatchTier[] => rows(value).map(tier => ({
  deferralMin: percent(tier.employee_min), deferralMax: percent(tier.employee_max), matchRate: percent(tier.match_rate),
}));
const readBands = (value: unknown) => rows(value).map(band => ({
  min: Number(band.min_value), max: upper(band.max_value),
  matchRate: percent(band.match_rate), maxDeferralPct: percent(band.max_deferral_pct),
}));

function readMatch(match: Json): Partial<DesignFormula> | null {
  const family = matchFamily(String(match.family ?? ''));
  if (!(MATCH_FAMILIES as readonly string[]).includes(family)) return null;
  const read: Partial<DesignFormula> = { dcMatchMode: family };
  if (typeof match.match_template === 'string') read.dcMatchTemplate = match.match_template;
  if (family === 'deferral_based') read.dcMatchTiers = readTiers(match.tiers);
  if (family === 'graded_by_service') read.dcTenureMatchTiers = readBands(match.graded_schedule)
    .map(({ min, max, ...rates }) => ({ minYears: min, maxYears: max, ...rates }));
  if (family === 'points_based') read.dcPointsMatchTiers = readBands(match.points_tiers)
    .map(({ min, max, ...rates }) => ({ minPoints: min, maxPoints: max, ...rates }));
  if (family === 'tenure_graded') read.dcTenureGradedBands = rows(match.tenure_graded_bands).map(band => ({
    minYears: Number(band.min_years), maxYears: upper(band.max_years), tiers: readTiers(band.tiers),
  }));
  return read;
}

function readCoreSchedule(core: Json, family: string): Partial<DesignFormula> {
  if (family === 'graded_by_service') return { dcCoreGradedSchedule: rows(core.graded_schedule).map(tier => ({
    serviceYearsMin: Number(tier.min_years), serviceYearsMax: upper(tier.max_years), rate: percent(tier.rate),
  })) };
  if (family === 'age_banded') return { dcCoreAgeSchedule: rows(core.age_schedule).map(tier => ({
    minAge: Number(tier.min_age), maxAge: upper(tier.max_age), rate: Number(tier.rate),
  })) };
  if (family !== 'points_based') return {};
  const minService = typeof core.points_min_service_years === 'number';
  return {
    dcCorePointsSchedule: rows(core.points_schedule).map(tier => ({
      minPoints: Number(tier.min_points), maxPoints: upper(tier.max_points), rate: Number(tier.rate),
    })),
    dcCorePointsMinServiceEnabled: minService,
    ...(minService ? {
      dcCorePointsMinServiceYears: Number(core.points_min_service_years),
      dcCorePointsPreServiceRate: Number(core.points_pre_service_rate),
    } : {}),
  };
}

function readCore(core: Json): Partial<DesignFormula> | null {
  const family = String(core.family ?? '');
  if (!(CORE_FAMILIES as readonly string[]).includes(family)) return null;
  const mode = core.integration_level_mode;
  return {
    dcCoreStatus: family,
    dcCoreContributionRate: percent(core.contribution_rate),
    ...readCoreSchedule(core, family),
    dcCoreIntegrationEnabled: core.integration_enabled === true,
    ...(mode === 'ss_wage_base' || mode === 'percent_of_ss_wage_base' || mode === 'fixed_dollar'
      ? { dcCoreIntegrationLevelMode: mode } : {}),
    dcCoreIntegrationLevelValue: upper(core.integration_level_value),
    dcCoreIntegrationDisparityRate: percent(core.integration_disparity_rate ?? 0),
  };
}

/** Read a saved design's match and core into form fields; null if Studio can't edit its formula. */
export function formulaFromDesign(design: unknown, fallback: DesignFormula): DesignFormula | null {
  const match = readMatch(asJson(asJson(design).match));
  const core = readCore(asJson(asJson(design).employer_core));
  return match && core ? { ...pickFormula(fallback), ...match, ...core } : null;
}

const isEmpty = (value: unknown): boolean =>
  value === undefined || value === null || (Array.isArray(value) && value.length === 0);

/** Deep equality that tolerates float noise and treats absent, null and [] as the same. */
export function sameSettings(left: unknown, right: unknown): boolean {
  if (typeof left === 'number' && typeof right === 'number') return Math.abs(left - right) < 1e-9;
  if (isEmpty(left) && isEmpty(right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((value, index) => sameSettings(value, right[index]));
  }
  if (typeof left !== 'object' || typeof right !== 'object' || left === null || right === null
    || Array.isArray(left) || Array.isArray(right)) return left === right;
  const a = left as Json;
  const b = right as Json;
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].every(key => sameSettings(a[key], b[key]));
}
