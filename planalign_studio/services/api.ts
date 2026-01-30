/**
 * PlanAlign Studio API Client
 *
 * Connects to the FastAPI backend at planalign_api/
 */

// Dynamically determine API URL based on current page location
// This handles Codespaces, remote servers, and local development
function getApiBase(): string {
  // Check for explicit environment variable first
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // Auto-detect based on window location
  const protocol = window.location.protocol;
  const host = window.location.hostname;

  // In development, API is on port 8000
  // In production or same-origin deployment, use same port
  const port = window.location.port === '5173' || window.location.port === '3000' ? '8000' : window.location.port || '';
  const portSuffix = port ? `:${port}` : '';

  return `${protocol}//${host}${portSuffix}`;
}

const API_BASE = getApiBase();

// ============================================================================
// Types (aligned with backend Pydantic models)
// ============================================================================

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  base_config: Record<string, any>;
  storage_path: string;
}

export interface WorkspaceCreate {
  name: string;
  description?: string;
  base_config?: Record<string, any>;
}

export interface Scenario {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  config_overrides: Record<string, any>;
  status: 'not_run' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  last_run_at: string | null;
  last_run_id: string | null;
  results_summary: Record<string, any> | null;
}

export interface ScenarioCreate {
  name: string;
  description?: string;
  config_overrides?: Record<string, any>;
}

export interface SimulationRun {
  id: string;
  scenario_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  current_stage: string | null;
  current_year: number | null;
  total_years: number | null;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface SimulationTelemetry {
  run_id: string;
  progress: number;
  current_stage: string;
  current_year: number;
  total_years: number;
  performance_metrics: {
    memory_mb: number;
    memory_pressure: 'low' | 'moderate' | 'high' | 'critical';
    elapsed_seconds: number;
    events_generated: number;
    events_per_second: number;
  };
  recent_events: Array<{
    event_type: string;
    employee_id: string;
    timestamp: string;
    details: string | null;
  }>;
  timestamp: string;
}

export interface SimulationResults {
  scenario_id: string;
  run_id: string;
  start_year: number;
  end_year: number;
  final_headcount: number;
  total_growth_pct: number;
  cagr: number;
  participation_rate: number;
  workforce_progression: Array<Record<string, any>>;
  event_trends: Record<string, number[]>;
  growth_analysis: Record<string, number>;
  // E093: Compensation breakdown by employment status
  compensation_by_status: Array<{
    simulation_year: number;
    employment_status: string;
    employee_count: number;
    avg_compensation: number;
  }>;
}

export interface BatchJob {
  id: string;
  name: string;
  workspace_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  submitted_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  scenarios: Array<{
    scenario_id: string;
    name: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    progress: number;
    error_message: string | null;
  }>;
  parallel: boolean;
  export_format: string | null;
}

export interface HealthResponse {
  healthy: boolean;
  issues: string[];
  warnings: string[];
}

export interface SystemStatus {
  system_ready: boolean;
  system_message: string;
  timestamp: string;
  active_simulations: number;
  queued_simulations: number;
  total_storage_mb: number;
  storage_limit_mb: number;
  storage_percent: number;
  workspace_count: number;
  scenario_count: number;
  thread_count: number;
  recommendations: string[];
}

export interface ComparisonResponse {
  scenarios: string[];
  scenario_names: Record<string, string>;
  baseline_scenario: string;
  workforce_comparison: Array<{
    year: number;
    values: Record<string, any>;
    deltas: Record<string, any>;
  }>;
  event_comparison: Array<{
    metric: string;
    year: number;
    baseline: number;
    scenarios: Record<string, number>;
    deltas: Record<string, number>;
    delta_pcts: Record<string, number>;
  }>;
  summary_deltas: Record<string, {
    baseline: number;
    scenarios: Record<string, number>;
    deltas: Record<string, number>;
    delta_pcts: Record<string, number>;
  }>;
}

// ============================================================================
// API Error Handling
// ============================================================================

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public detail?: string
  ) {
    super(detail || statusText);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const error = await response.json();
      detail = error.detail;
    } catch {
      // Response wasn't JSON
    }
    throw new ApiError(response.status, response.statusText, detail);
  }
  return response.json();
}

// ============================================================================
// System Endpoints
// ============================================================================

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/api/health`);
  return handleResponse<HealthResponse>(response);
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const response = await fetch(`${API_BASE}/api/system/status`);
  return handleResponse<SystemStatus>(response);
}

export async function getDefaultConfig(): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE}/api/config/defaults`);
  return handleResponse<Record<string, any>>(response);
}

// ============================================================================
// Workspace Endpoints
// ============================================================================

export async function listWorkspaces(): Promise<Workspace[]> {
  const response = await fetch(`${API_BASE}/api/workspaces`);
  return handleResponse<Workspace[]>(response);
}

export async function getWorkspace(workspaceId: string): Promise<Workspace> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}`);
  return handleResponse<Workspace>(response);
}

export async function createWorkspace(data: WorkspaceCreate): Promise<Workspace> {
  const response = await fetch(`${API_BASE}/api/workspaces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Workspace>(response);
}

export async function updateWorkspace(
  workspaceId: string,
  data: Partial<WorkspaceCreate>
): Promise<Workspace> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Workspace>(response);
}

export async function deleteWorkspace(workspaceId: string): Promise<{ success: boolean }> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}`, {
    method: 'DELETE',
  });
  return handleResponse<{ success: boolean }>(response);
}

// ============================================================================
// Scenario Endpoints
// ============================================================================

export async function listScenarios(workspaceId: string): Promise<Scenario[]> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/scenarios`);
  return handleResponse<Scenario[]>(response);
}

export async function getScenario(workspaceId: string, scenarioId: string): Promise<Scenario> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}`
  );
  return handleResponse<Scenario>(response);
}

export async function getScenarioConfig(
  workspaceId: string,
  scenarioId: string
): Promise<Record<string, any>> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/config`
  );
  return handleResponse<Record<string, any>>(response);
}

export async function createScenario(
  workspaceId: string,
  data: ScenarioCreate
): Promise<Scenario> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/scenarios`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Scenario>(response);
}

export async function updateScenario(
  workspaceId: string,
  scenarioId: string,
  data: Partial<ScenarioCreate>
): Promise<Scenario> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }
  );
  return handleResponse<Scenario>(response);
}

export async function deleteScenario(
  workspaceId: string,
  scenarioId: string
): Promise<{ success: boolean }> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}`,
    { method: 'DELETE' }
  );
  return handleResponse<{ success: boolean }>(response);
}

export async function getMergedConfig(
  workspaceId: string,
  scenarioId: string
): Promise<Record<string, any>> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/config`
  );
  return handleResponse<Record<string, any>>(response);
}

// ============================================================================
// Simulation Endpoints
// ============================================================================

export async function startSimulation(
  scenarioId: string,
  options?: { resume_from_checkpoint?: boolean }
): Promise<SimulationRun> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
  return handleResponse<SimulationRun>(response);
}

export async function getSimulationStatus(scenarioId: string): Promise<SimulationRun> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/run/status`);
  return handleResponse<SimulationRun>(response);
}

export async function cancelSimulation(scenarioId: string): Promise<{ success: boolean }> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/run/cancel`, {
    method: 'POST',
  });
  return handleResponse<{ success: boolean }>(response);
}

export async function resetSimulation(scenarioId: string): Promise<{
  success: boolean;
  scenario_id: string;
  previous_status: string;
  new_status: string;
  message: string;
}> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/run/reset`, {
    method: 'POST',
  });
  return handleResponse(response);
}

export async function getSimulationResults(scenarioId: string): Promise<SimulationResults> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/results`);
  return handleResponse<SimulationResults>(response);
}

export function getResultsExportUrl(workspaceId: string, scenarioId: string, format: 'excel' | 'csv' = 'excel'): string {
  // E087: Use workspace-scoped endpoint for reliable export
  return `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/results/export?format=${format}`;
}

// ============================================================================
// Batch Processing Endpoints
// ============================================================================

export async function runAllScenarios(
  workspaceId: string,
  options?: {
    scenario_ids?: string[];
    name?: string;
    parallel?: boolean;
    export_format?: 'excel' | 'csv';
  }
): Promise<BatchJob> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/run-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
  return handleResponse<BatchJob>(response);
}

export async function getBatchStatus(batchId: string): Promise<BatchJob> {
  const response = await fetch(`${API_BASE}/api/batches/${batchId}/status`);
  return handleResponse<BatchJob>(response);
}

export async function listBatchJobs(workspaceId: string): Promise<BatchJob[]> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/batches`);
  return handleResponse<BatchJob[]>(response);
}

// ============================================================================
// Comparison Endpoints
// ============================================================================

export async function compareScenarios(
  workspaceId: string,
  scenarioIds: string[],
  baselineId: string
): Promise<ComparisonResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
    baseline: baselineId,
  });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/comparison?${params}`
  );
  return handleResponse<ComparisonResponse>(response);
}

// ============================================================================
// Run Details & Artifacts Endpoints
// ============================================================================

export interface Artifact {
  name: string;
  type: 'excel' | 'yaml' | 'duckdb' | 'json' | 'text' | 'other';
  size_bytes: number;
  path: string;
  created_at: string | null;
}

export interface RunDetails {
  id: string;
  scenario_id: string;
  scenario_name: string;
  workspace_id: string;
  workspace_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'not_run';

  // Timing
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;

  // Simulation info
  start_year: number | null;
  end_year: number | null;
  total_years: number | null;

  // Results summary
  final_headcount: number | null;
  total_events: number | null;
  participation_rate: number | null;

  // Configuration snapshot
  config: Record<string, any> | null;

  // Artifacts
  artifacts: Artifact[];

  // Error info
  error_message: string | null;

  // E087: Storage location info
  storage_path: string | null;
}

export async function getRunDetails(scenarioId: string): Promise<RunDetails> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/details`);
  return handleResponse<RunDetails>(response);
}

export function getArtifactDownloadUrl(scenarioId: string, artifactPath: string): string {
  return `${API_BASE}/api/scenarios/${scenarioId}/artifacts/${artifactPath}`;
}

// ============================================================================
// Run History Endpoints
// ============================================================================

export interface RunSummary {
  id: string;
  scenario_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  start_year: number | null;
  end_year: number | null;
  total_events: number | null;
  final_headcount: number | null;
  artifact_count: number;
}

export async function listRuns(scenarioId: string): Promise<RunSummary[]> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/runs`);
  return handleResponse<RunSummary[]>(response);
}

export async function getRunById(scenarioId: string, runId: string): Promise<RunDetails> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/runs/${runId}`);
  return handleResponse<RunDetails>(response);
}

// ============================================================================
// File Upload Endpoints
// ============================================================================

export interface FileUploadResponse {
  success: boolean;
  file_path: string;
  file_name: string;
  file_size_bytes: number;
  row_count: number;
  columns: string[];
  upload_timestamp: string;
  validation_warnings: string[];
}

export interface FileValidationResponse {
  valid: boolean;
  file_path: string;
  exists: boolean;
  readable: boolean;
  file_size_bytes?: number;
  row_count?: number;
  columns?: string[];
  last_modified?: string;
  error_message?: string;
}

export async function uploadCensusFile(
  workspaceId: string,
  file: File
): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/upload`,
    {
      method: 'POST',
      body: formData,
    }
  );
  return handleResponse<FileUploadResponse>(response);
}

export async function validateFilePath(
  workspaceId: string,
  filePath: string
): Promise<FileValidationResponse> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/validate-path`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }
  );
  return handleResponse<FileValidationResponse>(response);
}

// E082: Analyze age distribution from census data
export interface AgeDistributionAnalysis {
  total_employees: number;
  recent_hires_only?: boolean;
  analysis_type?: string;
  distribution: Array<{
    age: number;
    weight: number;
    description: string;
    count: number;
  }>;
  source_file: string;
}

export async function analyzeAgeDistribution(
  workspaceId: string,
  filePath: string
): Promise<AgeDistributionAnalysis> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-age-distribution`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }
  );
  return handleResponse<AgeDistributionAnalysis>(response);
}

// E082: Analyze compensation distribution from census data
export interface CompensationAnalysis {
  total_employees: number;
  recent_hires_only: boolean;
  lookback_years?: number;
  has_level_data: boolean;
  analysis_type: string;
  message?: string;
  // When has_level_data is true
  levels?: Array<{
    level: number;
    name: string;
    employee_count: number;
    min_compensation: number;
    max_compensation: number;
    median_compensation: number;
    p25_compensation: number;
    p75_compensation: number;
    avg_compensation: number;
  }>;
  // When has_level_data is false
  overall_stats?: {
    min_compensation: number;
    max_compensation: number;
    median_compensation: number;
    p10_compensation: number;
    p25_compensation: number;
    p75_compensation: number;
    p90_compensation: number;
    avg_compensation: number;
  };
  suggested_levels?: Array<{
    level: number;
    name: string;
    suggested_min: number;
    suggested_max: number;
    percentile_range: string;
  }>;
  source_file: string;
}

/**
 * Analyze compensation ranges from census data.
 * @param workspaceId - The workspace ID
 * @param filePath - Path to the census file
 * @param lookbackYears - Number of years to look back for recent hires (default 4, 0 = all employees)
 */
export async function analyzeCompensation(
  workspaceId: string,
  filePath: string,
  lookbackYears: number = 4
): Promise<CompensationAnalysis> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-compensation-by-level`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, lookback_years: lookbackYears }),
    }
  );
  return handleResponse<CompensationAnalysis>(response);
}

// ============================================================================
// Compensation Growth Solver
// ============================================================================

export interface CompensationSolverRequest {
  file_path?: string;
  target_growth_rate: number; // As decimal, e.g., 0.02 for 2%
  promotion_increase?: number; // Lock promotion increase (as decimal)
  cola_to_merit_ratio?: number; // Ratio of COLA to merit
  // Workforce dynamics (critical for accurate growth modeling)
  turnover_rate?: number; // Annual turnover rate as decimal (e.g., 0.15 = 15%)
  workforce_growth_rate?: number; // Annual workforce growth as decimal (e.g., 0.03 = 3%)
  new_hire_comp_ratio?: number; // New hire avg comp as ratio of current avg (e.g., 0.85 = 85%)
}

export interface LevelDistribution {
  level: number;
  name: string;
  headcount: number;
  percentage: number;
  avg_compensation: number;
  promotion_rate: number;
}

export interface CompensationSolverResponse {
  target_growth_rate: number; // As percentage (2.0 for 2%)
  cola_rate: number; // As percentage
  merit_budget: number; // As percentage
  promotion_increase: number; // As percentage
  promotion_budget: number; // As percentage
  achieved_growth_rate: number;
  growth_gap: number;
  // Growth breakdown (how each factor contributes)
  cola_contribution: number;
  merit_contribution: number;
  promo_contribution: number;
  turnover_contribution: number; // Impact of turnover/new hires (usually negative)
  // Workforce context
  total_headcount: number;
  avg_compensation: number;
  weighted_promotion_rate: number;
  // Workforce dynamics used in calculation
  turnover_rate: number;
  workforce_growth_rate: number;
  new_hire_comp_ratio: number;
  // Recommendations for new hire compensation
  recommended_new_hire_ratio: number; // % of avg comp to hire at
  recommended_scale_factor: number; // Multiplier for census-derived ranges
  level_distribution?: LevelDistribution[];
  warnings: string[];
}

/**
 * Solve for compensation parameters given a target growth rate.
 *
 * This is the "magic button" - tell us your target average compensation growth
 * (e.g., 2% per year) and we'll calculate the COLA, merit, promotion increase,
 * and promotion budget needed to achieve that target.
 */
export async function solveCompensationGrowth(
  workspaceId: string,
  request: CompensationSolverRequest
): Promise<CompensationSolverResponse> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/solve-compensation-growth`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }
  );
  return handleResponse<CompensationSolverResponse>(response);
}

// ============================================================================
// Template Endpoints
// ============================================================================

export interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  config: Record<string, any>;
}

export interface TemplateListResponse {
  templates: Template[];
}

export async function listTemplates(): Promise<TemplateListResponse> {
  const response = await fetch(`${API_BASE}/api/templates`);
  return handleResponse<TemplateListResponse>(response);
}

export async function getTemplate(templateId: string): Promise<Template> {
  const response = await fetch(`${API_BASE}/api/templates/${templateId}`);
  return handleResponse<Template>(response);
}

// ============================================================================
// DC Plan Analytics Endpoints (E085)
// ============================================================================

export interface ContributionYearSummary {
  year: number;
  total_employee_contributions: number;
  total_employer_match: number;
  total_employer_core: number;
  total_all_contributions: number;
  participant_count: number;
  // E104: New fields for cost comparison
  average_deferral_rate: number;
  participation_rate: number;
  total_employer_cost: number;
  // E013: Employer cost ratio metrics
  total_compensation: number;
  employer_cost_rate: number;
}

export interface DeferralRateBucket {
  bucket: string;
  count: number;
  percentage: number;
}

export interface ParticipationByMethod {
  auto_enrolled: number;
  voluntary_enrolled: number;
  census_enrolled: number;
}

export interface EscalationMetrics {
  employees_with_escalations: number;
  avg_escalation_count: number;
  total_escalation_amount: number;
}

export interface IRSLimitMetrics {
  employees_at_irs_limit: number;
  irs_limit_rate: number;
}

export interface DCPlanAnalytics {
  scenario_id: string;
  scenario_name: string;
  total_eligible: number;
  total_enrolled: number;
  participation_rate: number;
  participation_by_method: ParticipationByMethod;
  contribution_by_year: ContributionYearSummary[];
  total_employee_contributions: number;
  total_employer_match: number;
  total_employer_core: number;
  total_all_contributions: number;
  deferral_rate_distribution: DeferralRateBucket[];
  escalation_metrics: EscalationMetrics;
  irs_limit_metrics: IRSLimitMetrics;
  // E104: New fields for cost comparison
  average_deferral_rate: number;
  total_employer_cost: number;
  // E013: Employer cost ratio metrics
  total_compensation: number;
  employer_cost_rate: number;
}

export interface DCPlanComparisonResponse {
  scenarios: string[];
  scenario_names: Record<string, string>;
  analytics: DCPlanAnalytics[];
}

export async function getDCPlanAnalytics(
  workspaceId: string,
  scenarioId: string
): Promise<DCPlanAnalytics> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/analytics/dc-plan`
  );
  return handleResponse<DCPlanAnalytics>(response);
}

export async function compareDCPlanAnalytics(
  workspaceId: string,
  scenarioIds: string[]
): Promise<DCPlanComparisonResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
  });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/dc-plan/compare?${params}`
  );
  return handleResponse<DCPlanComparisonResponse>(response);
}

// ============================================================================
// Band Configuration Endpoints (E003: Studio Band Configuration Management)
// ============================================================================

export interface Band {
  band_id: number;
  band_label: string;
  min_value: number;
  max_value: number;
  display_order: number;
}

export interface BandConfig {
  age_bands: Band[];
  tenure_bands: Band[];
}

export interface BandValidationError {
  band_type: 'age' | 'tenure';
  error_type: 'gap' | 'overlap' | 'invalid_range' | 'coverage';
  message: string;
  band_ids: number[];
}

export interface BandSaveRequest {
  age_bands: Band[];
  tenure_bands: Band[];
}

export interface BandSaveResponse {
  success: boolean;
  validation_errors: BandValidationError[];
  message: string;
}

export interface BandAnalysisRequest {
  file_path: string;
}

export interface DistributionStats {
  total_employees: number;
  min_value: number;
  max_value: number;
  median_value: number;
  mean_value: number;
  percentiles: Record<number, number>;
}

export interface BandAnalysisResult {
  suggested_bands: Band[];
  distribution_stats: DistributionStats;
  analysis_type: string;
  source_file: string;
}

/**
 * Get band configurations (age and tenure bands) from dbt seed files.
 */
export async function getBandConfigs(workspaceId: string): Promise<BandConfig> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/config/bands`
  );
  return handleResponse<BandConfig>(response);
}

/**
 * Save band configurations to dbt seed files.
 * Validates for [min, max) convention, no gaps, no overlaps.
 */
export async function saveBandConfigs(
  workspaceId: string,
  request: BandSaveRequest
): Promise<BandSaveResponse> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/config/bands`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }
  );
  return handleResponse<BandSaveResponse>(response);
}

/**
 * Analyze census data for age band suggestions.
 * Uses percentile-based boundary detection focusing on recent hires.
 */
export async function analyzeAgeBands(
  workspaceId: string,
  filePath: string
): Promise<BandAnalysisResult> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-age-bands`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }
  );
  return handleResponse<BandAnalysisResult>(response);
}

/**
 * Analyze census data for tenure band suggestions.
 * Uses percentile-based boundary detection.
 */
export async function analyzeTenureBands(
  workspaceId: string,
  filePath: string
): Promise<BandAnalysisResult> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-tenure-bands`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }
  );
  return handleResponse<BandAnalysisResult>(response);
}

// ============================================================================
// Vesting Analysis Endpoints (Feature 025)
// ============================================================================

/**
 * Vesting schedule type enum values.
 * Maps to VestingScheduleType in backend.
 */
export type VestingScheduleType =
  | 'immediate'
  | 'cliff_2_year'
  | 'cliff_3_year'
  | 'cliff_4_year'
  | 'qaca_2_year'
  | 'graded_3_year'
  | 'graded_4_year'
  | 'graded_5_year';

/**
 * Vesting schedule metadata for display.
 */
export interface VestingScheduleInfo {
  schedule_type: VestingScheduleType;
  name: string;
  description: string;
  percentages: Record<number, number>;
}

/**
 * Response for listing all vesting schedules.
 */
export interface VestingScheduleListResponse {
  schedules: VestingScheduleInfo[];
}

/**
 * Configuration for a vesting schedule in analysis request.
 */
export interface VestingScheduleConfig {
  schedule_type: VestingScheduleType;
  name: string;
  require_hours_credit?: boolean;
  hours_threshold?: number;
}

/**
 * Request body for vesting analysis.
 */
export interface VestingAnalysisRequest {
  current_schedule: VestingScheduleConfig;
  proposed_schedule: VestingScheduleConfig;
  simulation_year?: number;
}

/**
 * Summary statistics for vesting analysis.
 */
export interface VestingAnalysisSummary {
  analysis_year: number;
  terminated_employee_count: number;
  total_employer_contributions: number;
  current_total_vested: number;
  current_total_forfeited: number;
  proposed_total_vested: number;
  proposed_total_forfeited: number;
  forfeiture_variance: number;
  forfeiture_variance_pct: number;
}

/**
 * Vesting breakdown by tenure band.
 */
export interface TenureBandSummary {
  tenure_band: string;
  employee_count: number;
  total_contributions: number;
  current_forfeitures: number;
  proposed_forfeitures: number;
  forfeiture_variance: number;
}

/**
 * Employee-level vesting detail.
 */
export interface EmployeeVestingDetail {
  employee_id: string;
  hire_date: string;
  termination_date: string;
  tenure_years: number;
  tenure_band: string;
  annual_hours_worked: number;
  total_employer_contributions: number;
  current_vesting_pct: number;
  current_vested_amount: number;
  current_forfeiture: number;
  proposed_vesting_pct: number;
  proposed_vested_amount: number;
  proposed_forfeiture: number;
  forfeiture_variance: number;
}

/**
 * Full vesting analysis response.
 */
export interface VestingAnalysisResponse {
  scenario_id: string;
  scenario_name: string;
  current_schedule: VestingScheduleConfig;
  proposed_schedule: VestingScheduleConfig;
  summary: VestingAnalysisSummary;
  by_tenure_band: TenureBandSummary[];
  employee_details: EmployeeVestingDetail[];
}

/**
 * Get list of all available vesting schedules.
 */
export async function listVestingSchedules(): Promise<VestingScheduleListResponse> {
  const response = await fetch(`${API_BASE}/api/vesting/schedules`);
  return handleResponse<VestingScheduleListResponse>(response);
}

/**
 * Run vesting analysis comparing two schedules.
 * Compares current vs proposed vesting schedules and projects
 * forfeiture differences for terminated employees.
 */
export async function analyzeVesting(
  workspaceId: string,
  scenarioId: string,
  request: VestingAnalysisRequest
): Promise<VestingAnalysisResponse> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/analytics/vesting`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }
  );
  return handleResponse<VestingAnalysisResponse>(response);
}
