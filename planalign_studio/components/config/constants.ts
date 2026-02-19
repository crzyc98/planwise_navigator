// Shared constants for ConfigStudio section components
// Extracted from ConfigStudio.tsx lines 21-64 and 205-337

import type { MatchTier, MatchTemplate, FormData } from './types';

// Helper to calculate match cap from tiers: sum of (tier_width * match_rate)
export const calculateMatchCap = (tiers: MatchTier[]): number => {
  return tiers.reduce((sum, tier) => {
    const tierWidth = (tier.deferralMax - tier.deferralMin) / 100;
    const matchRate = tier.matchRate / 100;
    return sum + (tierWidth * matchRate);
  }, 0);
};

export const MATCH_TEMPLATES: Record<string, MatchTemplate> = {
  simple: {
    name: 'Simple Match',
    tiers: [{ deferralMin: 0, deferralMax: 6, matchRate: 50 }],
    isSafeHarbor: false,
  },
  tiered: {
    name: 'Tiered Match',
    tiers: [
      { deferralMin: 0, deferralMax: 3, matchRate: 100 },
      { deferralMin: 3, deferralMax: 5, matchRate: 50 },
    ],
    isSafeHarbor: false,
  },
  stretch: {
    name: 'Stretch Match',
    tiers: [{ deferralMin: 0, deferralMax: 12, matchRate: 25 }],
    isSafeHarbor: false,
  },
  safe_harbor: {
    name: 'Safe Harbor Basic',
    tiers: [
      { deferralMin: 0, deferralMax: 3, matchRate: 100 },
      { deferralMin: 3, deferralMax: 5, matchRate: 50 },
    ],
    isSafeHarbor: true,
  },
  qaca: {
    name: 'QACA Safe Harbor',
    tiers: [
      { deferralMin: 0, deferralMax: 1, matchRate: 100 },
      { deferralMin: 1, deferralMax: 6, matchRate: 50 },
    ],
    isSafeHarbor: true,
  },
};

export const DEFAULT_FORM_DATA: FormData = {
  // Data Sources
  censusDataPath: 'data/census_preprocessed.parquet',
  censusDataStatus: 'loaded',
  censusRowCount: 1000,
  censusLastModified: '2025-01-15',

  // Simulation
  name: 'Baseline 2025-2027',
  startYear: 2025,
  endYear: 2027,
  seed: 42,
  targetGrowthRate: 3.0,

  // Compensation
  meritBudget: 3.5,
  colaRate: 2.0,
  promoIncrease: 12.5,
  promoDistributionRange: 5.0,
  promoBudget: 1.5,
  promoRateMultiplier: 1.0,

  // New Hire
  newHireStrategy: 'percentile',
  targetPercentile: 50,
  newHireCompVariance: 5.0,
  newHireAgeDistribution: [
    { age: 22, weight: 0.05, description: 'Recent college graduates' },
    { age: 25, weight: 0.15, description: 'Early career' },
    { age: 28, weight: 0.20, description: 'Established early career' },
    { age: 32, weight: 0.25, description: 'Mid-career switchers' },
    { age: 35, weight: 0.15, description: 'Experienced hires' },
    { age: 40, weight: 0.10, description: 'Senior experienced' },
    { age: 45, weight: 0.08, description: 'Mature professionals' },
    { age: 50, weight: 0.02, description: 'Late career changes' },
  ],
  levelDistributionMode: 'adaptive',
  newHireLevelDistribution: [
    { level: 1, name: 'Staff', percentage: 50 },
    { level: 2, name: 'Manager', percentage: 25 },
    { level: 3, name: 'Sr Manager', percentage: 15 },
    { level: 4, name: 'Director', percentage: 8 },
    { level: 5, name: 'VP', percentage: 2 },
  ],
  jobLevelCompensation: [
    { level: 1, name: 'Staff', minComp: 56000, maxComp: 80000 },
    { level: 2, name: 'Manager', minComp: 81000, maxComp: 120000 },
    { level: 3, name: 'Sr Manager', minComp: 121000, maxComp: 160000 },
    { level: 4, name: 'Director', minComp: 161000, maxComp: 300000 },
    { level: 5, name: 'VP', minComp: 275000, maxComp: 500000 },
  ],
  marketScenario: 'baseline',
  levelMarketAdjustments: [
    { level: 1, adjustment: 0 },
    { level: 2, adjustment: 0 },
    { level: 3, adjustment: 0 },
    { level: 4, adjustment: 0 },
    { level: 5, adjustment: 0 },
  ],

  // Turnover
  totalTerminationRate: 12.0,
  newHireTerminationRate: 25.0,

  // DC Plan - Basic
  dcEligibilityMonths: 3,
  dcAutoEnroll: true,
  dcDefaultDeferral: 3.0,
  dcMatchTemplate: 'tiered',
  dcMatchTiers: [
    { deferralMin: 0, deferralMax: 3, matchRate: 100 },
    { deferralMin: 3, deferralMax: 5, matchRate: 50 },
  ],
  dcMatchMode: 'deferral_based',
  dcTenureMatchTiers: [],
  dcPointsMatchTiers: [],
  dcAutoEscalation: true,
  dcEscalationRate: 1.0,
  dcEscalationCap: 10.0,

  // DC Plan - Auto-Enrollment Advanced
  dcAutoEnrollWindowDays: 45,
  dcAutoEnrollOptOutGracePeriod: 30,
  dcAutoEnrollScope: 'new_hires_only',
  dcAutoEnrollHireDateCutoff: '2020-01-01',

  // DC Plan - Match Eligibility
  dcMatchMinTenureYears: 0,
  dcMatchRequireYearEndActive: true,
  dcMatchMinHoursAnnual: 1000,
  dcMatchAllowTerminatedNewHires: false,
  dcMatchAllowExperiencedTerminations: false,

  // DC Plan - Core Contribution
  dcCoreEnabled: true,
  dcCoreContributionRate: 1.0,
  dcCoreStatus: 'flat',
  dcCoreGradedSchedule: [
    { serviceYearsMin: 0, serviceYearsMax: 2, rate: 1.0 },
    { serviceYearsMin: 3, serviceYearsMax: 5, rate: 2.0 },
    { serviceYearsMin: 6, serviceYearsMax: null, rate: 3.0 },
  ],
  dcCorePointsSchedule: [
    { minPoints: 0, maxPoints: 40, rate: 1.0 },
    { minPoints: 40, maxPoints: 75, rate: 2.0 },
    { minPoints: 75, maxPoints: null, rate: 3.0 },
  ],
  dcCoreMinTenureYears: 0,
  dcCoreRequireYearEndActive: true,
  dcCoreMinHoursAnnual: 1000,
  dcCoreAllowTerminatedNewHires: false,
  dcCoreAllowExperiencedTerminations: false,

  // DC Plan - Auto-Escalation Advanced
  dcEscalationEffectiveDay: '01-01',
  dcEscalationDelayYears: 1,
  dcEscalationHireDateCutoff: '2020-01-01',

  // Advanced
  engine: 'sql',
  enableMultithreading: true,
  checkpointFrequency: 'year',
  memoryLimitGB: 4.0,
  logLevel: 'INFO',
  strictValidation: true,
};
