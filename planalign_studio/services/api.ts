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

export async function deleteScenarioDatabase(
  workspaceId: string,
  scenarioId: string
): Promise<{ success: boolean; deleted: boolean; message: string }> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/database`,
    { method: 'DELETE' }
  );
  return handleResponse<{ success: boolean; deleted: boolean; message: string }>(response);
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

// ============================================================================
// Active Simulation Detection (Feature 045)
// ============================================================================

export interface ActiveRun {
  run_id: string;
  scenario_id: string;
  status: string;
  progress: number;
  current_stage: string | null;
  started_at: string;
}

export interface ActiveSimulationsResponse {
  active_runs: ActiveRun[];
}

export async function getActiveSimulations(): Promise<ActiveSimulationsResponse> {
  const response = await fetch(`${API_BASE}/api/scenarios/active`);
  return handleResponse<ActiveSimulationsResponse>(response);
}

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
// Promotion Hazard Configuration Endpoints (Feature 038)
// ============================================================================

export interface PromotionHazardBase {
  base_rate: number;
  level_dampener_factor: number;
}

export interface PromotionHazardAgeMultiplier {
  age_band: string;
  multiplier: number;
}

export interface PromotionHazardTenureMultiplier {
  tenure_band: string;
  multiplier: number;
}

export interface PromotionHazardConfig {
  base: PromotionHazardBase;
  age_multipliers: PromotionHazardAgeMultiplier[];
  tenure_multipliers: PromotionHazardTenureMultiplier[];
}

export interface PromotionHazardSaveResponse {
  success: boolean;
  errors: string[];
  message: string;
}

/**
 * Get promotion hazard configuration from dbt seed files.
 */
export async function getPromotionHazardConfig(workspaceId: string): Promise<PromotionHazardConfig> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/config/promotion-hazards`
  );
  return handleResponse<PromotionHazardConfig>(response);
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
 * Available simulation years for a scenario.
 */
export interface ScenarioYearsResponse {
  years: number[];
  default_year: number;
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

/**
 * Get available simulation years for vesting analysis in a scenario.
 */
export async function getScenarioYears(
  workspaceId: string,
  scenarioId: string
): Promise<ScenarioYearsResponse> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/analytics/vesting/years`
  );
  return handleResponse<ScenarioYearsResponse>(response);
}

// ============================================================================
// Workspace Export/Import Endpoints (Feature 031)
// ============================================================================

/**
 * Export/Import types aligned with backend models.
 */
export interface ExportManifest {
  version: string;
  export_date: string;
  app_version: string;
  workspace_id: string;
  workspace_name: string;
  contents: {
    scenario_count: number;
    scenarios: string[];
    file_count: number;
    total_size_bytes: number;
    checksum_sha256: string;
  };
}

export interface ExportResult {
  workspace_id: string;
  workspace_name: string;
  filename: string;
  size_bytes: number;
  status: 'success' | 'failed';
  error?: string;
}

export interface BulkExportStatus {
  operation_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
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

export interface ImportResponse {
  workspace_id: string;
  name: string;
  scenario_count: number;
  status: 'success' | 'partial';
  warnings: string[];
}

export interface BulkImportStatus {
  operation_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  total: number;
  completed: number;
  current_file?: string;
  results: ImportResponse[];
}

/**
 * Export a single workspace as a 7z archive.
 * Returns the download URL for the exported archive.
 */
export function getExportWorkspaceUrl(workspaceId: string): string {
  return `${API_BASE}/api/workspaces/${workspaceId}/export`;
}

/**
 * Export a single workspace and trigger browser download.
 */
export async function exportWorkspace(workspaceId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/export`, {
    method: 'POST',
  });

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

  // Get filename from Content-Disposition header
  const contentDisposition = response.headers.get('Content-Disposition');
  let filename = 'workspace_export.7z';
  if (contentDisposition) {
    const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
    if (filenameMatch) {
      filename = filenameMatch[1];
    }
  }

  // Trigger download
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

/**
 * Start bulk export of multiple workspaces.
 */
export async function bulkExportWorkspaces(
  workspaceIds: string[]
): Promise<BulkExportStatus> {
  const response = await fetch(`${API_BASE}/api/workspaces/bulk-export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_ids: workspaceIds }),
  });
  return handleResponse<BulkExportStatus>(response);
}

/**
 * Get status of a bulk export operation.
 */
export async function getBulkExportStatus(
  operationId: string
): Promise<BulkExportStatus> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/bulk-export/${operationId}`
  );
  return handleResponse<BulkExportStatus>(response);
}

/**
 * Download an individual archive from bulk export.
 */
export function getBulkExportDownloadUrl(
  operationId: string,
  workspaceId: string
): string {
  return `${API_BASE}/api/workspaces/bulk-export/${operationId}/download/${workspaceId}`;
}

/**
 * Validate an archive before import.
 * Returns validation result with any conflicts or warnings.
 */
export async function validateImport(
  file: File
): Promise<ImportValidationResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/api/workspaces/import/validate`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<ImportValidationResponse>(response);
}

/**
 * Import a workspace from a 7z archive.
 */
export async function importWorkspace(
  file: File,
  conflictResolution?: 'rename' | 'replace' | 'skip',
  newName?: string
): Promise<ImportResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (conflictResolution) {
    formData.append('conflict_resolution', conflictResolution);
  }
  if (newName) {
    formData.append('new_name', newName);
  }

  const response = await fetch(`${API_BASE}/api/workspaces/import`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<ImportResponse>(response);
}

/**
 * Bulk import multiple archives.
 */
export async function bulkImportWorkspaces(
  files: File[],
  defaultResolution: 'rename' | 'replace' | 'skip' = 'rename'
): Promise<BulkImportStatus> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });
  formData.append('default_resolution', defaultResolution);

  const response = await fetch(`${API_BASE}/api/workspaces/bulk-import`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<BulkImportStatus>(response);
}

/**
 * Get status of a bulk import operation.
 */
export async function getBulkImportStatus(
  operationId: string
): Promise<BulkImportStatus> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/bulk-import/${operationId}`
  );
  return handleResponse<BulkImportStatus>(response);
}

// ============================================================================
// NDT Testing Endpoints (Feature 050)
// ============================================================================

export interface ACPEmployeeDetail {
  employee_id: string;
  is_hce: boolean;
  is_enrolled: boolean;
  employer_match_amount: number;
  eligible_compensation: number;
  individual_acp: number;
  prior_year_compensation: number | null;
}

export interface ACPScenarioResult {
  scenario_id: string;
  scenario_name: string;
  simulation_year: number;
  test_result: 'pass' | 'fail' | 'error';
  test_message?: string;
  hce_count: number;
  nhce_count: number;
  excluded_count: number;
  eligible_not_enrolled_count: number;
  hce_average_acp: number;
  nhce_average_acp: number;
  basic_test_threshold: number;
  alternative_test_threshold: number;
  applied_test: 'basic' | 'alternative';
  applied_threshold: number;
  margin: number;
  hce_threshold_used: number;
  employees?: ACPEmployeeDetail[];
}

export interface ACPTestResponse {
  test_type: string;
  year: number;
  results: ACPScenarioResult[];
}

export interface NDTAvailableYearsResponse {
  years: number[];
  default_year: number | null;
}

/**
 * Run ACP non-discrimination test for one or more scenarios.
 */
export async function runACPTest(
  workspaceId: string,
  scenarioIds: string[],
  year: number,
  includeEmployees: boolean = false
): Promise<ACPTestResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
    year: year.toString(),
    include_employees: includeEmployees.toString(),
  });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/acp?${params}`
  );
  return handleResponse<ACPTestResponse>(response);
}

/**
 * Get available simulation years for NDT testing.
 */
export async function getNDTAvailableYears(
  workspaceId: string,
  scenarioId: string
): Promise<NDTAvailableYearsResponse> {
  const params = new URLSearchParams({ scenario_id: scenarioId });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/available-years?${params}`
  );
  return handleResponse<NDTAvailableYearsResponse>(response);
}

// ============================================================================
// NDT 401(a)(4) General Test (Feature 051)
// ============================================================================

export interface Section401a4EmployeeDetail {
  employee_id: string;
  is_hce: boolean;
  employer_nec_amount: number;
  employer_match_amount: number;
  total_employer_amount: number;
  plan_compensation: number;
  contribution_rate: number;
  years_of_service: number;
}

export interface Section401a4ScenarioResult {
  scenario_id: string;
  scenario_name: string;
  simulation_year: number;
  test_result: 'pass' | 'fail' | 'error';
  test_message?: string;
  applied_test: 'ratio' | 'general';
  hce_count: number;
  nhce_count: number;
  excluded_count: number;
  hce_average_rate: number;
  nhce_average_rate: number;
  hce_median_rate: number;
  nhce_median_rate: number;
  ratio: number;
  ratio_test_threshold: number;
  margin: number;
  include_match: boolean;
  service_risk_flag: boolean;
  service_risk_detail?: string;
  hce_threshold_used: number;
  employees?: Section401a4EmployeeDetail[];
}

export interface Section401a4TestResponse {
  test_type: string;
  year: number;
  results: Section401a4ScenarioResult[];
}

/**
 * Run 401(a)(4) general nondiscrimination test for one or more scenarios.
 */
export async function run401a4Test(
  workspaceId: string,
  scenarioIds: string[],
  year: number,
  includeEmployees: boolean = false,
  includeMatch: boolean = false
): Promise<Section401a4TestResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
    year: year.toString(),
    include_employees: includeEmployees.toString(),
    include_match: includeMatch.toString(),
  });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/401a4?${params}`
  );
  return handleResponse<Section401a4TestResponse>(response);
}

// ============================================================================
// NDT 415 Annual Additions Limit Test (Feature 051)
// ============================================================================

export interface Section415EmployeeDetail {
  employee_id: string;
  status: 'pass' | 'at_risk' | 'breach';
  employee_deferrals: number;
  employer_match: number;
  employer_nec: number;
  total_annual_additions: number;
  gross_compensation: number;
  applicable_limit: number;
  headroom: number;
  utilization_pct: number;
}

export interface Section415ScenarioResult {
  scenario_id: string;
  scenario_name: string;
  simulation_year: number;
  test_result: 'pass' | 'fail' | 'error';
  test_message?: string;
  total_participants: number;
  excluded_count: number;
  breach_count: number;
  at_risk_count: number;
  passing_count: number;
  max_utilization_pct: number;
  warning_threshold_pct: number;
  annual_additions_limit: number;
  employees?: Section415EmployeeDetail[];
}

export interface Section415TestResponse {
  test_type: string;
  year: number;
  results: Section415ScenarioResult[];
}

// ============================================================================
// NDT ADP (Actual Deferral Percentage) Test (Feature 052)
// ============================================================================

export interface ADPEmployeeDetail {
  employee_id: string;
  is_hce: boolean;
  employee_deferrals: number;
  plan_compensation: number;
  individual_adp: number;
  prior_year_compensation: number | null;
}

export interface ADPScenarioResult {
  scenario_id: string;
  scenario_name: string;
  simulation_year: number;
  test_result: 'pass' | 'fail' | 'exempt' | 'error';
  test_message?: string;
  hce_count: number;
  nhce_count: number;
  excluded_count: number;
  hce_average_adp: number;
  nhce_average_adp: number;
  basic_test_threshold: number;
  alternative_test_threshold: number;
  applied_test: 'basic' | 'alternative';
  applied_threshold: number;
  margin: number;
  excess_hce_amount: number | null;
  testing_method: 'current' | 'prior';
  safe_harbor: boolean;
  hce_threshold_used: number;
  employees?: ADPEmployeeDetail[];
}

export interface ADPTestResponse {
  test_type: string;
  year: number;
  results: ADPScenarioResult[];
}

/**
 * Run ADP non-discrimination test for one or more scenarios.
 */
export async function runADPTest(
  workspaceId: string,
  scenarioIds: string[],
  year: number,
  includeEmployees: boolean = false,
  safeHarbor: boolean = false,
  testingMethod: string = 'current'
): Promise<ADPTestResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
    year: year.toString(),
    include_employees: includeEmployees.toString(),
    safe_harbor: safeHarbor.toString(),
    testing_method: testingMethod,
  });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/adp?${params}`
  );
  return handleResponse<ADPTestResponse>(response);
}

/**
 * Run Section 415 annual additions limit test for one or more scenarios.
 */
export async function run415Test(
  workspaceId: string,
  scenarioIds: string[],
  year: number,
  includeEmployees: boolean = false,
  warningThreshold: number = 0.95
): Promise<Section415TestResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
    year: year.toString(),
    include_employees: includeEmployees.toString(),
    warning_threshold: warningThreshold.toString(),
  });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/415?${params}`
  );
  return handleResponse<Section415TestResponse>(response);
}
