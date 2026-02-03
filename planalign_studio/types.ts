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
  description: string | null;
  scenarios?: string[]; // List of Config IDs belonging to this workspace
  lastRun?: string;
  created_at: string;
  updated_at: string;
  base_config: Record<string, any>;
  storage_path: string;
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

  // E082: New Hire Demographics
  newHireAgeDistribution?: Array<{
    age: number;
    weight: number;
    description: string;
  }>;
  levelDistributionMode?: 'adaptive' | 'fixed';
  newHireLevelDistribution?: Array<{
    level: number;
    name: string;
    percentage: number;
  }>;

  // Turnover
  baseTurnoverRate?: number;
  regrettableFactor?: number;
  involuntaryRate?: number;
  earlyTenureHazard?: number;

  // DC Plan
  dcEligibilityMonths?: number;
  dcAutoEnroll?: boolean;
  dcMatchPercent?: number;
  dcMatchLimit?: number;
  dcVestingSchedule?: 'immediate' | 'cliff_3' | 'graded_5';

  // Advanced
  advanced?: {
    // Engine field accepts legacy values for backward compatibility
    // All simulations now use SQL mode regardless of this setting
    engine?: 'polars' | 'pandas';
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

// Export/Import Types (031-workspace-export)
export interface ManifestContents {
  scenario_count: number;
  scenarios: string[];
  file_count: number;
  total_size_bytes: number;
  checksum_sha256: string;
}

export interface ExportManifest {
  version: string;
  export_date: string;
  app_version: string;
  workspace_id: string;
  workspace_name: string;
  contents: ManifestContents;
}

export type ExportStatus = 'success' | 'failed';

export interface ExportResult {
  workspace_id: string;
  workspace_name: string;
  filename: string;
  size_bytes: number;
  status: ExportStatus;
  error?: string;
}

export interface BulkExportRequest {
  workspace_ids: string[];
}

export type BulkOperationStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface BulkExportStatus {
  operation_id: string;
  status: BulkOperationStatus;
  total: number;
  completed: number;
  current_workspace?: string;
  results: ExportResult[];
}

export interface ImportConflict {
  existing_workspace_id: string;
  existing_workspace_name: string;
  suggested_name: string;
}

export interface ImportValidationResponse {
  valid: boolean;
  manifest?: ExportManifest;
  conflict?: ImportConflict;
  warnings: string[];
  errors: string[];
}

export type ConflictResolution = 'rename' | 'replace' | 'skip';

export type ImportStatus = 'success' | 'partial';

export interface ImportResponse {
  workspace_id: string;
  name: string;
  scenario_count: number;
  status: ImportStatus;
  warnings: string[];
}

export interface BulkImportStatus {
  operation_id: string;
  status: BulkOperationStatus;
  total: number;
  completed: number;
  current_file?: string;
  results: ImportResponse[];
}
