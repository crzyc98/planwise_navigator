// Shared TypeScript types for ConfigStudio section components
// Extracted from ConfigStudio.tsx lines 8-18 and formData shape

export interface MatchTier {
  deferralMin: number;
  deferralMax: number;
  matchRate: number;
}

export interface MatchTemplate {
  name: string;
  tiers: MatchTier[];
  isSafeHarbor: boolean;
}

export interface AgeDistributionRow {
  age: number;
  weight: number;
  description: string;
}

export interface LevelDistributionRow {
  level: number;
  name: string;
  percentage: number;
}

export interface JobLevelCompRow {
  level: number;
  name: string;
  minComp: number;
  maxComp: number;
}

export interface LevelMarketAdjustmentRow {
  level: number;
  adjustment: number;
}

export interface TenureMatchTier {
  minYears: number;
  maxYears: number | null;
  matchRate: number;
  maxDeferralPct: number;
}

export interface PointsMatchTier {
  minPoints: number;
  maxPoints: number | null;
  matchRate: number;
  maxDeferralPct: number;
}

// Feature 099: tenure-graded multi-tier match — each band carries its own
// ordered, cumulative deferral-rate tier list (reuses MatchTier's
// deferralMin/deferralMax/matchRate shape), superseding the single-tier
// TenureMatchTier above.
export interface TenureGradedBand {
  minYears: number;
  maxYears: number | null;
  tiers: MatchTier[];
}

export interface CoreGradedTier {
  serviceYearsMin: number;
  serviceYearsMax: number | null;
  rate: number;
}

export interface PointsCoreTier {
  minPoints: number;
  maxPoints: number | null;
  rate: number;
}

export interface AgeCoreTier {
  minAge: number;
  maxAge: number | null;
  rate: number;
}

// Age x income segments used to assign a starting deferral rate to voluntary
// enrollees. Boundaries live in the engine (int_voluntary_enrollment_decision.sql);
// these labels only describe them.
export const DEFERRAL_AGE_SEGMENTS = [
  { key: 'young', label: 'Young', range: '< 31' },
  { key: 'mid_career', label: 'Mid-Career', range: '31-45' },
  { key: 'mature', label: 'Mature', range: '46-55' },
  { key: 'senior', label: 'Senior', range: '56+' },
] as const;

export const DEFERRAL_INCOME_SEGMENTS = [
  { key: 'low', label: 'Low', range: '< $50k' },
  { key: 'moderate', label: 'Moderate', range: '$50k-$100k' },
  { key: 'high', label: 'High', range: '$100k-$200k' },
  { key: 'executive', label: 'Executive', range: '$200k+' },
] as const;

export type DeferralAgeSegment = (typeof DEFERRAL_AGE_SEGMENTS)[number]['key'];
export type DeferralIncomeSegment = (typeof DEFERRAL_INCOME_SEGMENTS)[number]['key'];
export type DeferralSegmentKey = `${DeferralAgeSegment}_${DeferralIncomeSegment}`;

/** Percent values (0-100) keyed by segment. Converted to decimals on save. */
export type VoluntaryDeferralBaseRates = Record<DeferralSegmentKey, number>;

export type CoreIntegrationLevelMode =
  | 'ss_wage_base'
  | 'percent_of_ss_wage_base'
  | 'fixed_dollar';

export interface FormData {
  // Data Sources
  censusDataPath: string;
  censusDataStatus: string;
  censusRowCount: number;
  censusLastModified: string;

  // Simulation
  name: string;
  startYear: number;
  endYear: number;
  seed: number;
  targetGrowthRate: number;

  // Compensation
  targetCompensationGrowth: number;
  meritBudget: number;
  colaRate: number;
  promoIncrease: number;
  promoDistributionRange: number;
  promoBudget: number;
  promoRateMultiplier: number;

  // New Hire
  newHireStrategy: string;
  targetPercentile: number;
  newHireCompVariance: number;
  newHireAgeDistribution: AgeDistributionRow[];
  levelDistributionMode: string;
  newHireLevelDistribution: LevelDistributionRow[];
  jobLevelCompensation: JobLevelCompRow[];
  marketScenario: string;
  levelMarketAdjustments: LevelMarketAdjustmentRow[];
  partTimeNewHirePct: number;

  // Turnover
  totalTerminationRate: number;
  newHireTerminationRate: number;

  // DC Plan - Basic
  dcEligibilityMonths: number;
  dcAutoEnroll: boolean;
  dcDefaultDeferral: number;
  dcMatchTemplate: string;
  dcMatchTiers: MatchTier[];
  dcMatchMode: string;
  dcTenureMatchTiers: TenureMatchTier[];
  dcPointsMatchTiers: PointsMatchTier[];
  dcTenureGradedBands: TenureGradedBand[];
  dcAutoEscalation: boolean;
  dcEscalationRate: number;
  dcEscalationCap: number;

  // DC Plan - Auto-Enrollment Advanced
  dcAutoEnrollWindowDays: number;
  dcAutoEnrollOptOutGracePeriod: number;
  dcAutoEnrollScope: string;
  dcAutoEnrollHireDateCutoff: string;

  // DC Plan - Auto-Enrollment Opt-Out Rate
  dcOptOutRateTarget: number;

  // DC Plan - New-hire enrollment rates (issue #652). Empty string = unset,
  // which keeps the demographic model. Any value is an exact percentage.
  dcVoluntaryEnrollmentRate: string;
  dcNewHireOptOutRate: string;
  // DC Plan - upward deferral spread, whole percentage points ('0' or '' = off)
  dcDeferralSpreadMaxLift: string;

  // DC Plan - Starting deferral rate per age x income segment, as percents
  dcVoluntaryDeferralBaseRates: VoluntaryDeferralBaseRates;

  // DC Plan - Match Magnet dial (Feature 102)
  dcMatchMagnetEnabled: boolean;
  dcMatchMagnetProbability: number; // percent (0-100)
  dcMaxVoluntaryDeferral: number;   // percent (1-100)

  // DC Plan - Match-Responsive Deferral Adjustment
  dcMatchResponseEnabled: boolean;
  dcMatchResponseUpwardParticipation: number; // percent (0-100)
  dcMatchResponseDownwardEnabled: boolean;
  dcMatchResponseDownwardParticipation: number; // percent (0-100)

  // DC Plan - Match Enable/Disable
  dcMatchEnabled: boolean;

  // DC Plan - Match Eligibility
  dcMatchMinTenureYears: number;
  dcMatchRequireYearEndActive: boolean;
  dcMatchMinHoursAnnual: number;
  dcMatchAllowTerminatedNewHires: boolean;
  dcMatchAllowExperiencedTerminations: boolean;

  // DC Plan - Core Contribution
  dcCoreEnabled: boolean;
  dcCoreContributionRate: number;
  dcCoreStatus: string;
  dcCoreGradedSchedule: CoreGradedTier[];
  dcCorePointsSchedule: PointsCoreTier[];
  dcCoreAgeSchedule: AgeCoreTier[];
  // Social Security integration (permitted disparity, §401(l)). A modifier on
  // whatever base rate dcCoreStatus resolved — not a fifth core status.
  dcCoreIntegrationEnabled: boolean;
  dcCoreIntegrationLevelMode: CoreIntegrationLevelMode;
  dcCoreIntegrationLevelValue: number | null;
  dcCoreIntegrationDisparityRate: number;
  dcCoreMinTenureYears: number;
  dcCoreRequireYearEndActive: boolean;
  dcCoreMinHoursAnnual: number;
  dcCoreAllowTerminatedNewHires: boolean;
  dcCoreAllowExperiencedTerminations: boolean;

  // DC Plan - Auto-Escalation Advanced
  dcEscalationEffectiveDay: string;
  dcEscalationDelayYears: number;
  dcEscalationHireDateCutoff: string;

  // Advanced
  engine: string;
  enableMultithreading: boolean;
  checkpointFrequency: string;
  memoryLimitGB: number;
  logLevel: string;
  strictValidation: boolean;
}
