import React from 'react';

export type WorkflowStage =
  | 'INITIALIZATION'
  | 'FOUNDATION'
  | 'EVENT_GENERATION'
  | 'STATE_ACCUMULATION'
  | 'VALIDATION'
  | 'REPORTING';

export interface SimulationStatus {
  simulation_id: string;
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed';
  current_year: number;
  total_years: number;
  current_stage: WorkflowStage;
  progress_percent: number;
  elapsed_seconds: number;
  events_generated: number;
  performance_metrics: {
    events_per_second: number;
    memory_usage_mb: number;
    memory_pressure: 'low' | 'moderate' | 'high' | 'critical';
    cpu_percent: number;
  };
}

export interface LogEvent {
  id: string;
  timestamp: string;
  type: 'HIRE' | 'TERMINATION' | 'PROMOTION' | 'RAISE';
  details: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string;
  scenarios: string[]; // List of Config IDs belonging to this workspace
  lastRun?: string;
}

export interface Notification {
  id: string;
  title: string;
  message: string;
  timestamp: string;
  type: 'info' | 'success' | 'warning' | 'error';
  read: boolean;
}

export interface SimulationConfig {
  id: string;
  workspaceId: string; // Parent workspace
  name: string;
  description: string;

  // Simulation Settings
  startYear: number;
  endYear: number;
  seed: number;
  growthTarget: number;
  growthTolerance: number;

  // Compensation
  meritBudget?: number;
  colaRate?: number;
  promoIncrease?: number;
  promoBudget?: number;

  // New Hire
  newHireStrategy?: 'percentile' | 'fixed';
  targetPercentile?: number;
  signOnBonusAllowed?: boolean;
  signOnBonusBudget?: number;

  // Turnover
  baseTurnoverRate?: number;
  regrettableFactor?: number;
  involuntaryRate?: number;
  earlyTenureHazard?: number;

  // Hiring Plan
  hiringTargets?: Record<string, number>;

  // DC Plan
  dcEligibilityMonths?: number;
  dcAutoEnroll?: boolean;
  dcMatchPercent?: number;
  dcMatchLimit?: number;
  dcVestingSchedule?: 'immediate' | 'cliff_3' | 'graded_5';

  // Advanced
  advanced?: {
    engine: 'polars' | 'pandas';
    enableMultithreading: boolean;
    checkpointFrequency: 'year' | 'stage' | 'none';
    logLevel: 'DEBUG' | 'INFO' | 'WARNING';
    strictValidation: boolean;
  };
}

export interface ChartDataPoint {
  year: number;
  [key: string]: number | string;
}

export interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

// Batch Processing Types
export interface BatchScenario {
  scenario_id: string;
  config_id: string;
  name: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  message?: string;
}

export interface BatchJob {
  id: string;
  name: string;
  status: 'queued' | 'running' | 'completed';
  submittedAt: string;
  scenarios: BatchScenario[];
  duration?: string;
  executionMode?: 'parallel' | 'sequential';
  exportFormat?: 'excel' | 'csv';
}

export interface ComparisonMetric {
  metric: string;
  unit?: string;
  baselineValue?: number | string;
  [scenarioName: string]: string | number | undefined;
}
