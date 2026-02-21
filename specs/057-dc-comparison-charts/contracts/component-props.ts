/**
 * Contract: DC Plan Comparison Charts Component Props
 * Feature: 057-dc-comparison-charts
 *
 * These types define the interface between ScenarioComparison.tsx (parent)
 * and the DCPlanComparisonSection (child component).
 *
 * No backend changes required — all data sourced from existing
 * compareDCPlanAnalytics endpoint.
 */

import { DCPlanComparisonResponse } from '../../planalign_studio/services/api';

// --- Props for the DC Plan Comparison Section ---

export interface DCPlanComparisonSectionProps {
  /** Comparison data from the API (null while loading) */
  comparisonData: DCPlanComparisonResponse | null;
  /** Whether data is currently being fetched */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Ordered list of scenario names for consistent chart rendering */
  scenarioNames: string[];
  /** Color assigned to each scenario name */
  scenarioColors: Record<string, string>;
}

// --- Recharts Data Shapes ---

/** Data point for trend line charts (one per simulation year) */
export interface TrendDataPoint {
  year: number;
  /** Dynamic keys: scenario display names → metric values */
  [scenarioName: string]: number | undefined;
}

/** Data point for contribution breakdown grouped bar chart (one per scenario) */
export interface ContributionBreakdownPoint {
  name: string;
  employee: number;
  match: number;
  core: number;
}

/** Row in the summary comparison table */
export interface SummaryMetricRow {
  metric: string;
  unit: 'percent' | 'currency';
  /** Which direction is favorable (green) */
  favorableDirection: 'higher' | 'lower';
  /** Scenario name → metric value */
  values: Record<string, number>;
  /** Scenario name → absolute delta from baseline */
  deltas: Record<string, number>;
  /** Scenario name → percentage delta from baseline */
  deltaPcts: Record<string, number>;
}

// --- Formatting ---

/** Format currency values for chart display */
export type CurrencyFormatter = (value: number) => string;

/** Format percentage values for chart display */
export type PercentFormatter = (value: number, decimals?: number) => string;
