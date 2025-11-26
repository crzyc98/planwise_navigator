/**
 * PlanAlign Studio API Client
 *
 * Connects to the FastAPI backend at planalign_api/
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

export async function getSimulationResults(scenarioId: string): Promise<SimulationResults> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/results`);
  return handleResponse<SimulationResults>(response);
}

export function getResultsExportUrl(scenarioId: string, format: 'excel' | 'csv' = 'excel'): string {
  return `${API_BASE}/api/scenarios/${scenarioId}/results/export?format=${format}`;
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
}

export async function getRunDetails(scenarioId: string): Promise<RunDetails> {
  const response = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/details`);
  return handleResponse<RunDetails>(response);
}

export function getArtifactDownloadUrl(scenarioId: string, artifactPath: string): string {
  return `${API_BASE}/api/scenarios/${scenarioId}/artifacts/${artifactPath}`;
}
