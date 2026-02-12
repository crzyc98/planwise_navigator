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

export interface CoreGradedTier {
  serviceYearsMin: number;
  serviceYearsMax: number | null;
  rate: number;
}

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
  dcAutoEscalation: boolean;
  dcEscalationRate: number;
  dcEscalationCap: number;

  // DC Plan - Auto-Enrollment Advanced
  dcAutoEnrollWindowDays: number;
  dcAutoEnrollOptOutGracePeriod: number;
  dcAutoEnrollScope: string;
  dcAutoEnrollHireDateCutoff: string;

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
