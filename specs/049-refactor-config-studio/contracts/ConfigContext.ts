/**
 * ConfigContext Type Contract
 *
 * This file defines the interface contract for the ConfigContext that
 * all section components consume. It is a DESIGN ARTIFACT, not runtime code.
 *
 * The actual implementation will live in:
 *   planalign_studio/components/config/ConfigContext.tsx
 */

import type { Scenario, BandConfig, PromotionHazardConfig, Workspace } from '../../services/api';

// --- Shared Types ---

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

// --- FormData ---

export interface FormData {
  // Data Sources
  censusDataPath: string;
  censusDataStatus: 'not_loaded' | 'loaded' | 'error';
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
  newHireStrategy: 'percentile' | 'fixed';
  targetPercentile: number;
  newHireCompVariance: number;
  newHireAgeDistribution: AgeDistributionRow[];
  levelDistributionMode: 'adaptive' | 'fixed';
  newHireLevelDistribution: LevelDistributionRow[];
  jobLevelCompensation: JobLevelCompRow[];
  marketScenario: 'conservative' | 'baseline' | 'competitive' | 'aggressive';
  levelMarketAdjustments: LevelMarketAdjustmentRow[];

  // Turnover
  totalTerminationRate: number;
  newHireTerminationRate: number;

  // DC Plan - Basic
  dcEligibilityMonths: number;
  dcAutoEnroll: boolean;
  dcDefaultDeferral: number;
  dcMatchTemplate: 'simple' | 'tiered' | 'stretch' | 'safe_harbor' | 'qaca';
  dcMatchTiers: MatchTier[];
  dcMatchMode: 'deferral_based' | 'graded_by_service' | 'tenure_based' | 'points_based';
  dcTenureMatchTiers: TenureMatchTier[];
  dcPointsMatchTiers: PointsMatchTier[];
  dcAutoEscalation: boolean;
  dcEscalationRate: number;
  dcEscalationCap: number;

  // DC Plan - Auto-Enrollment Advanced
  dcAutoEnrollWindowDays: number;
  dcAutoEnrollOptOutGracePeriod: number;
  dcAutoEnrollScope: 'new_hires_only' | 'all_eligible';
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
  dcCoreStatus: 'none' | 'flat' | 'graded_by_service';
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
  checkpointFrequency: 'year' | 'stage' | 'none';
  memoryLimitGB: number;
  logLevel: string;
  strictValidation: boolean;
}

// --- Context Type ---

export interface ConfigContextType {
  // Form state
  formData: FormData;
  setFormData: React.Dispatch<React.SetStateAction<FormData>>;
  savedFormData: FormData | null;

  // Seed config state (needed for dirty-tracking)
  promotionHazardConfig: PromotionHazardConfig | null;
  setPromotionHazardConfig: React.Dispatch<React.SetStateAction<PromotionHazardConfig | null>>;
  savedPromotionHazardConfig: PromotionHazardConfig | null;
  bandConfig: BandConfig | null;
  setBandConfig: React.Dispatch<React.SetStateAction<BandConfig | null>>;
  savedBandConfig: BandConfig | null;

  // Dirty tracking
  dirtySections: Set<string>;
  isDirty: boolean;

  // Save
  handleSaveConfig: () => Promise<void>;
  saveStatus: 'idle' | 'saving' | 'success' | 'error';
  saveMessage: string;

  // Generic handlers
  handleChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  inputProps: (name: string) => { name: string; value: any; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void };

  // Route/workspace context (pass-through)
  activeWorkspace: Workspace;
  currentScenario: Scenario | null;
  scenarioId: string | undefined;
}
