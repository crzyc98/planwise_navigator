/**
 * PlanAlign Studio API Client
 *
 * Connects to the FastAPI backend at planalign_api/
 */

import type { components } from './api.generated';

const API_BASE = import.meta.env.VITE_API_URL ?? '';
const API_TOKEN = import.meta.env.VITE_PLANALIGN_API_TOKEN as string | undefined;

function authHeaders(): Record<string, string> {
  return API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {};
}

export const RUN_CONSISTENCY_EVENT = 'planalign:run-consistency';

export interface RunConsistencyDetail {
  warning: 'run_in_progress' | null;
  activeRunIds: string | null;
  resultRunIds: string | null;
}

function isScenarioRead(input: RequestInfo | URL, init?: RequestInit): boolean {
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (method !== 'GET') return false;
  const url = String(input);
  return url.includes('/scenarios') || /[?&](scenario_id|scenarios|scenario_a|scenario_b|baseline)=/.test(url);
}

export async function fetchWithAuth(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    headers: {
      ...init?.headers,
      ...authHeaders(),
    },
  });
  if (isScenarioRead(input, init)) {
    window.dispatchEvent(new CustomEvent<RunConsistencyDetail>(RUN_CONSISTENCY_EVENT, {
      detail: {
        warning: response.headers.get('X-PlanAlign-Run-Warning') as 'run_in_progress' | null,
        activeRunIds: response.headers.get('X-PlanAlign-Active-Run-Id'),
        resultRunIds: response.headers.get('X-PlanAlign-Result-Run-Id'),
      },
    }));
  }
  return response;
}

// ============================================================================
// Types (aligned with backend Pydantic models)
//
// Migrating to types generated from the API's OpenAPI schema (#661):
// `npm run generate:api-types` rewrites services/api.generated.ts. Prefer
// `Schemas['Name']` aliases over new hand-written interfaces.
// ============================================================================

type Schemas = components['schemas'];

export type Workspace = Schemas['WorkspaceResponse'];

export type WorkspaceSummary = Schemas['WorkspaceSummary'];

export type WorkspacePage = Schemas['WorkspacePage'];

export interface WorkspaceListOptions {
  q?: string;
  limit?: number;
  offset?: number;
  sort?: 'name' | 'updated' | 'last_activity';
  lifecycle?: 'active' | 'archived' | 'all';
}

export type WorkspaceCreate = Schemas['WorkspaceCreate'];
export type WorkspaceUpdate = Schemas['WorkspaceUpdate'];

export interface Scenario {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  config_overrides: Record<string, any>;
  provenance: Record<string, any> | null;
  status: 'not_run' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  last_run_at: string | null;
  last_run_id: string | null;
  results_summary: Record<string, any> | null;
}

export type ScenarioCreate = Schemas['ScenarioCreate'];

export type TimelineEvent = Schemas['TimelineEvent'];

export type YearState = Schemas['YearState'];

export type TimelineYearData = Schemas['TimelineYear'];

export type EmployeeIdentity = Schemas['EmployeeIdentity'];

export type EmployeeTimelineResponse = Schemas['EmployeeTimelineResponse'];

export type EmployeeSearchResult = Schemas['EmployeeSearchResult'];

export type EmployeeSearchResponse = Schemas['EmployeeSearchResponse'];

export interface EmployeeSearchParams {
  q?: string;
  status?: string;
  level?: number;
  year?: number;
  enrolled?: boolean;
  has_escalations?: boolean;
  page?: number;
  page_size?: number;
}

export type EventRecord = Schemas['EventRecord'];

export type EventListResponse = Schemas['EventListResponse'];

export interface EventListParams {
  simulation_year?: number;
  event_type?: string;
  event_category?: string;
  employee_id?: string;
  page?: number;
  page_size?: number;
}

export type SimulationRun = Schemas['SimulationRun'];

export type PerformanceMetrics = Schemas['PerformanceMetrics'];

// Feature 094: live run dashboard telemetry types

export type TelemetryMilestone = Schemas['TelemetryMilestone'];

export type EventTypeCounts = Schemas['EventTypeCounts'];

export type PerformanceSample = Schemas['PerformanceSample'];

export type RunTelemetrySnapshot = Schemas['RunTelemetrySnapshot'];

export type RunTelemetryUpdate = Omit<
  RunTelemetrySnapshot,
  'milestones' | 'performance_samples'
>;

export type TelemetryWsMessage =
  | { type: 'snapshot'; data: RunTelemetrySnapshot }
  | { type: 'update'; data: RunTelemetryUpdate }
  | { type: 'milestone'; data: TelemetryMilestone }
  | { type: 'heartbeat' };

export type RunTelemetryResponse = Schemas['RunTelemetryResponse'];

export type SimulationResults = Schemas['SimulationResults'];

export type BandGroupResult = Schemas['BandGroupResult'];

export type HeatmapCell = Schemas['HeatmapCell'];

export type WinnersLosersResponse = Schemas['WinnersLosersResponse'];

export type BatchJob = Schemas['BatchJob'];

export type HealthResponse = Schemas['HealthResponse'];

export type SystemStatus = Schemas['SystemStatus'];

export type WorkforceMetrics = Schemas['WorkforceMetrics'];

export type EventComparisonMetric = Schemas['EventComparisonMetric'];

export type DCPlanMetrics = Schemas['DCPlanMetrics'];

export type DeltaValue = Schemas['DeltaValue'];

export type ComparisonResponse = Schemas['ComparisonResponse'];

export type ConfigDelta = Schemas['ConfigDelta'];

export type ScenarioProvenance = Schemas['ScenarioProvenance'];

export type ConfigDiffResponse = Schemas['ConfigDiffResponse'];

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

export class ScenarioNameConflictError extends Error {
  constructor(
    public detail: string,
    public suggestedName: string
  ) {
    super(detail);
    this.name = 'ScenarioNameConflictError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const error = await response.json();
      detail = typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail);
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
  const response = await fetchWithAuth(`${API_BASE}/api/health`);
  return handleResponse<HealthResponse>(response);
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const response = await fetchWithAuth(`${API_BASE}/api/system/status`);
  return handleResponse<SystemStatus>(response);
}

export async function getDefaultConfig(): Promise<Record<string, any>> {
  const response = await fetchWithAuth(`${API_BASE}/api/config/defaults`);
  return handleResponse<Record<string, any>>(response);
}

// ============================================================================
// Workspace Endpoints
// ============================================================================

export async function listWorkspaces(options: WorkspaceListOptions = {}): Promise<WorkspacePage> {
  const params = new URLSearchParams();
  if (options.q) params.set('q', options.q);
  if (options.limit !== undefined) params.set('limit', String(options.limit));
  if (options.offset !== undefined) params.set('offset', String(options.offset));
  if (options.sort) params.set('sort', options.sort);
  if (options.lifecycle) params.set('lifecycle', options.lifecycle);
  const query = params.toString();
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces${query ? `?${query}` : ''}`);
  return handleResponse<WorkspacePage>(response);
}

export async function getWorkspace(workspaceId: string): Promise<Workspace> {
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}`);
  return handleResponse<Workspace>(response);
}

export async function createWorkspace(data: WorkspaceCreate): Promise<Workspace> {
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Workspace>(response);
}

export async function updateWorkspace(
  workspaceId: string,
  data: WorkspaceUpdate
): Promise<Workspace> {
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Workspace>(response);
}

export async function deleteWorkspace(workspaceId: string): Promise<{ success: boolean }> {
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}`, {
    method: 'DELETE',
  });
  return handleResponse<{ success: boolean }>(response);
}

// ============================================================================
// Scenario Endpoints
// ============================================================================

export async function listScenarios(workspaceId: string): Promise<Scenario[]> {
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}/scenarios`);
  return handleResponse<Scenario[]>(response);
}

export async function searchEmployees(
  workspaceId: string,
  scenarioId: string,
  params: EmployeeSearchParams,
): Promise<EmployeeSearchResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/scenarios/${encodeURIComponent(scenarioId)}/employees?${query}`,
  );
  if (!response.ok) throw new Error(`Employee search failed: ${response.statusText}`);
  return response.json();
}

export async function listEvents(
  workspaceId: string,
  scenarioId: string,
  params: EventListParams,
): Promise<EventListResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value));
  });
  const suffix = query.size ? `?${query}` : '';
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/scenarios/${encodeURIComponent(scenarioId)}/events${suffix}`,
  );
  if (!response.ok) throw new Error(`Event explorer failed: ${response.statusText}`);
  return response.json();
}

export async function getEmployeeTimeline(
  workspaceId: string,
  scenarioId: string,
  employeeId: string,
  params: { start_year?: number; years?: number } = {},
): Promise<EmployeeTimelineResponse> {
  const query = new URLSearchParams();
  if (params.start_year !== undefined) query.set('start_year', String(params.start_year));
  if (params.years !== undefined) query.set('years', String(params.years));
  const suffix = query.size ? `?${query}` : '';
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/scenarios/${encodeURIComponent(scenarioId)}/employees/${encodeURIComponent(employeeId.trim())}/timeline${suffix}`,
  );
  if (!response.ok) throw new Error(`Employee timeline failed: ${response.statusText}`);
  return response.json();
}

export function timelineUrl(
  workspaceId: string,
  scenarioId: string,
  employeeId: string,
  compare?: string,
): string {
  const path = `/w/${encodeURIComponent(workspaceId)}/timeline/${encodeURIComponent(scenarioId)}/${encodeURIComponent(employeeId.trim())}`;
  return compare ? `${path}?compare=${encodeURIComponent(compare)}` : path;
}

export async function getScenario(workspaceId: string, scenarioId: string): Promise<Scenario> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}`
  );
  return handleResponse<Scenario>(response);
}

export async function getScenarioConfig(
  workspaceId: string,
  scenarioId: string
): Promise<Record<string, any>> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/config`
  );
  return handleResponse<Record<string, any>>(response);
}

export async function createScenario(
  workspaceId: string,
  data: ScenarioCreate
): Promise<Scenario> {
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}/scenarios`, {
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
  const response = await fetchWithAuth(
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
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}`,
    { method: 'DELETE' }
  );
  return handleResponse<{ success: boolean }>(response);
}

export async function deleteScenarioDatabase(
  workspaceId: string,
  scenarioId: string
): Promise<{ success: boolean; deleted: boolean; message: string }> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/database`,
    { method: 'DELETE' }
  );
  return handleResponse<{ success: boolean; deleted: boolean; message: string }>(response);
}

// ============================================================================
// Simulation Endpoints
// ============================================================================

// ============================================================================
// Active Simulation Detection (Feature 045)
// ============================================================================

export type ActiveRun = Schemas['ActiveRun'];

export type ActiveSimulationsResponse = Schemas['ActiveSimulationsResponse'];

export async function getActiveSimulations(): Promise<ActiveSimulationsResponse> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/active`);
  return handleResponse<ActiveSimulationsResponse>(response);
}

export async function startSimulation(
  scenarioId: string,
  options?: { resume_from_checkpoint?: boolean }
): Promise<SimulationRun> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
  return handleResponse<SimulationRun>(response);
}

export async function getSimulationStatus(scenarioId: string): Promise<SimulationRun> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/run/status`);
  return handleResponse<SimulationRun>(response);
}

// Feature 094: full telemetry snapshot for refresh restore / polling fallback
export async function fetchRunTelemetrySnapshot(
  scenarioId: string
): Promise<RunTelemetryResponse> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/run/telemetry`);
  return handleResponse<RunTelemetryResponse>(response);
}

export async function cancelSimulation(scenarioId: string): Promise<{ success: boolean }> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/run/cancel`, {
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
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/run/reset`, {
    method: 'POST',
  });
  return handleResponse(response);
}

export async function getSimulationResults(scenarioId: string, population: string = 'all'): Promise<SimulationResults> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/results?population=${population}`);
  return handleResponse<SimulationResults>(response);
}

function filenameFromContentDisposition(response: Response, fallback: string): string {
  const disposition = response.headers.get('Content-Disposition');
  const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match ? decodeURIComponent(match[1]) : fallback;
}

export async function downloadResultsExport(
  workspaceId: string,
  scenarioId: string,
  format: 'excel' | 'csv' = 'excel',
): Promise<void> {
  // E087: Use workspace-scoped endpoint for reliable export
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/results/export?format=${format}`,
  );
  if (!response.ok) await handleResponse<never>(response);
  const extension = format === 'excel' ? 'xlsx' : 'csv';
  const filename = filenameFromContentDisposition(response, `${scenarioId}-results.${extension}`);
  saveBrowserDownload(await response.blob(), filename);
}

export async function downloadScenarioReport(
  workspaceId: string,
  scenarioId: string,
  format: 'pdf' | 'pptx' | 'html' = 'pdf',
): Promise<void> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/scenarios/${encodeURIComponent(scenarioId)}/report?format=${format}`,
  );
  if (!response.ok) await handleResponse<never>(response);
  const filename = filenameFromContentDisposition(response, `${scenarioId}-report.${format}`);
  saveBrowserDownload(await response.blob(), filename);
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
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}/run-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
  return handleResponse<BatchJob>(response);
}

export async function getBatchStatus(batchId: string): Promise<BatchJob> {
  const response = await fetchWithAuth(`${API_BASE}/api/batches/${batchId}/status`);
  return handleResponse<BatchJob>(response);
}

export async function listBatchJobs(workspaceId: string): Promise<BatchJob[]> {
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}/batches`);
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
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/comparison?${params}`
  );
  return handleResponse<ComparisonResponse>(response);
}

export async function getScenarioConfigDiff(
  workspaceId: string,
  scenarioA: string,
  scenarioB: string
): Promise<ConfigDiffResponse> {
  const params = new URLSearchParams({ scenario_a: scenarioA, scenario_b: scenarioB });
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/comparison/config-diff?${params}`
  );
  return handleResponse<ConfigDiffResponse>(response);
}

// ============================================================================
// Run Details & Artifacts Endpoints
// ============================================================================

export type Artifact = Schemas['Artifact'];

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
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/details`);
  return handleResponse<RunDetails>(response);
}

export async function downloadArtifact(
  scenarioId: string,
  artifactPath: string,
  filename: string,
): Promise<void> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/artifacts/${artifactPath}`);
  if (!response.ok) await handleResponse<never>(response);
  saveBrowserDownload(await response.blob(), filename);
}

// ============================================================================
// Run History Endpoints
// ============================================================================

export type RunSummary = Schemas['RunSummary'];

export async function listRuns(scenarioId: string): Promise<RunSummary[]> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/runs`);
  return handleResponse<RunSummary[]>(response);
}

export async function getRunById(scenarioId: string, runId: string): Promise<RunDetails> {
  const response = await fetchWithAuth(`${API_BASE}/api/scenarios/${scenarioId}/runs/${runId}`);
  return handleResponse<RunDetails>(response);
}

// ============================================================================
// Run Health Summary (validation outcomes for one archived run)
// ============================================================================

export type RunHealthStatus = 'clean' | 'warnings' | 'failed' | 'missing_provenance' | 'unavailable';

export type RunHealthCounts = Schemas['RunHealthCounts'];

export type RunHealthFinding = Schemas['RunHealthFinding'];

export type RunHealthReport = Schemas['RunHealthReport'];

export async function getRunHealth(scenarioId: string, runId?: string): Promise<RunHealthReport> {
  const path = runId
    ? `/api/scenarios/${scenarioId}/runs/${runId}/health`
    : `/api/scenarios/${scenarioId}/run-health`;
  const response = await fetchWithAuth(`${API_BASE}${path}`);
  return handleResponse<RunHealthReport>(response);
}

// ============================================================================
// Run Provenance Report Endpoints (111-run-provenance-report)
// ============================================================================

export type ProvenanceFinding = Schemas['EvidenceFinding'];

export type ProvenanceInputFingerprint = Schemas['InputFingerprint'];

export type ProvenanceSeedFingerprint = Schemas['SeedFingerprint'];

export type ProvenanceEventCount = Schemas['AnnualEventCount'];

export type ProvenanceReconciliation = Schemas['AnnualWorkforceReconciliation'];

export type ProvenanceValidationResult = Schemas['CapturedValidationResult'];

export type ProvenanceStageCompletion = Schemas['StageCompletion'];

export type ProvenanceReport = Schemas['ProvenanceReport'];

export type ProvenanceReportEnvelope = Schemas['ProvenanceReportEnvelope'];

export async function getRunProvenance(runId: string): Promise<ProvenanceReportEnvelope> {
  const response = await fetchWithAuth(`${API_BASE}/api/runs/${runId}/provenance`, {
    headers: { Accept: 'application/json' },
  });
  return handleResponse<ProvenanceReportEnvelope>(response);
}

export function saveBrowserDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(anchor);
}

export async function downloadRunProvenanceBundle(runId: string): Promise<void> {
  const response = await fetchWithAuth(`${API_BASE}/api/runs/${runId}/provenance`, {
    headers: { Accept: 'application/zip' },
  });
  if (!response.ok) await handleResponse<never>(response);
  saveBrowserDownload(await response.blob(), `${runId}-provenance.zip`);
}

export async function downloadRunProvenanceFile(
  runId: string,
  format: 'json' | 'markdown',
): Promise<void> {
  const envelope = await getRunProvenance(runId);
  const content = format === 'json'
    ? `${JSON.stringify(envelope.report, null, 2)}\n`
    : envelope.audit_sheet;
  const mediaType = format === 'json' ? 'application/json' : 'text/markdown';
  const extension = format === 'json' ? 'json' : 'md';
  saveBrowserDownload(
    new Blob([content], { type: `${mediaType};charset=utf-8` }),
    `${runId}-provenance.${extension}`,
  );
}

// ============================================================================
// Evidence Packs (138-evidence-pack)
// ============================================================================

export type EvidenceMetric = 'active_headcount' | 'total_compensation' | 'employer_match_cost' | 'total_employer_plan_cost' | 'participation_rate' | 'avg_deferral_rate';
export type EvidenceFigureStatus = 'defined' | 'undefined' | 'suppressed';

export type EvidenceCitation = Schemas['Citation'];

export type EvidenceFigure = Schemas['EvidenceFigure'];

export type EvidenceDriver = Schemas['DriverContribution'];

export type EvidencePackEnvelope = Schemas['EvidencePackEnvelope'];

export async function getScenarioEvidencePack(
  workspaceId: string,
  scenarioId: string,
  metric: EvidenceMetric,
  baseYear: number,
  targetYear: number,
): Promise<EvidencePackEnvelope> {
  const params = new URLSearchParams({ metric, base_year: String(baseYear), target_year: String(targetYear) });
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/evidence-pack?${params}`);
  return handleResponse<EvidencePackEnvelope>(response);
}

export type CrossScenarioEvidencePackEnvelope = Schemas['CrossScenarioEvidencePackEnvelope'];
export type CrossScenarioFigure = Schemas['CrossScenarioFigure'];

export async function getCrossScenarioEvidencePack(
  workspaceId: string,
  scenarioA: string,
  scenarioB: string,
  metric: EvidenceMetric,
  year: number,
): Promise<CrossScenarioEvidencePackEnvelope> {
  const params = new URLSearchParams({ scenario_a: scenarioA, scenario_b: scenarioB, metric, year: String(year) });
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}/evidence-pack/compare?${params}`);
  return handleResponse<CrossScenarioEvidencePackEnvelope>(response);
}

export function downloadEvidencePack(envelope: Pick<EvidencePackEnvelope, 'text_export' | 'filename'>): void {
  saveBrowserDownload(
    new Blob([envelope.text_export], { type: 'text/markdown;charset=utf-8' }),
    envelope.filename,
  );
}

// ============================================================================
// Simulation Log Endpoints (001-sim-job-logs)
// ============================================================================

export type SimulationLogLine = Schemas['SimulationLogLine'];

export type LogPage = Schemas['LogPage'];

export async function fetchRunLogs(
  scenarioId: string,
  runId: string,
  page: number = 1,
  pageSize: number = 200,
  severity?: 'INFO' | 'WARNING' | 'ERROR'
): Promise<LogPage> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });
  if (severity) params.set('severity', severity);
  const response = await fetchWithAuth(
    `${API_BASE}/api/scenarios/${scenarioId}/runs/${runId}/logs?${params}`
  );
  return handleResponse<LogPage>(response);
}

export async function downloadRunLog(scenarioId: string, runId: string): Promise<void> {
  await downloadArtifact(scenarioId, `runs/${runId}/simulation.log`, 'simulation.log');
}

// ============================================================================
// File Upload Endpoints
// ============================================================================

export type StructuredWarning = Schemas['StructuredWarning'];

export type DataQualitySample = Schemas['DataQualitySample'];

export type DataQualityWarning = Schemas['DataQualityWarning'];

export type FileUploadResponse = Schemas['FileUploadResponse'];

export type FileValidationResponse = Schemas['FileValidationResponse'];

export async function uploadCensusFile(
  workspaceId: string,
  file: File
): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetchWithAuth(
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
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/validate-path`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }
  );
  return handleResponse<FileValidationResponse>(response);
}

export async function setCensusPath(
  workspaceId: string,
  filePath: string
): Promise<{ success: boolean; file_path: string; row_count: number }> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/set-census-path`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }
  );
  return handleResponse<{ success: boolean; file_path: string; row_count: number }>(response);
}

// E082: Analyze age distribution from census data
export type AgeDistributionAnalysis = Schemas['AgeDistributionResponse'];

export async function analyzeAgeDistribution(
  workspaceId: string,
  filePath: string,
  asOfDate?: string
): Promise<AgeDistributionAnalysis> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-age-distribution`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, as_of_date: asOfDate }),
    }
  );
  return handleResponse<AgeDistributionAnalysis>(response);
}

// 093: Analyze part-time percentage from census data
export type PartTimePctAnalysis = Schemas['PartTimePctResponse'];

export async function analyzePartTimePct(
  workspaceId: string,
  filePath: string
): Promise<PartTimePctAnalysis> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-part-time-pct`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    }
  );
  return handleResponse<PartTimePctAnalysis>(response);
}

// E082: Analyze compensation distribution from census data
export type CompensationAnalysis = Schemas['CompensationByLevelResponse'];

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
  const response = await fetchWithAuth(
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

export type CompensationSolverRequest = Schemas['CompensationSolverRequest'];

export type LevelDistribution = Schemas['LevelDistributionResponse'];

export type CompensationSolverResponse = Schemas['CompensationSolverResponse'];

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
  const response = await fetchWithAuth(
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

export type TemplateListResponse = Schemas['TemplateListResponse'];

export async function listTemplates(): Promise<TemplateListResponse> {
  const response = await fetchWithAuth(`${API_BASE}/api/templates`);
  return handleResponse<TemplateListResponse>(response);
}

export async function getTemplate(templateId: string): Promise<Template> {
  const response = await fetchWithAuth(`${API_BASE}/api/templates/${templateId}`);
  return handleResponse<Template>(response);
}

// ============================================================================
// DC Plan Analytics Endpoints (E085)
// ============================================================================

export type ContributionYearSummary = Schemas['ContributionYearSummary'];

export type DeferralRateBucket = Schemas['DeferralRateBucket'];

export type DeferralDistributionYear = Schemas['DeferralDistributionYear'];

export type ParticipationByMethod = Schemas['ParticipationByMethod'];

export type EscalationMetrics = Schemas['EscalationMetrics'];

export type IRSLimitMetrics = Schemas['IRSLimitMetrics'];

export type DCPlanCohort = 'all' | 'new_hires' | 'baseline';
export type DCPlanPopulation =
  | 'all_eligible'
  | 'active_eligible'
  | 'terminated_eligible';

export type DCPlanAnalytics = Schemas['DCPlanAnalytics'];

export type DCPlanComparisonResponse = Schemas['DCPlanComparisonResponse'];

export type GrandfatheredCostYear = Schemas['GrandfatheredCostYear'];

export type GrandfatheredCostSeries = Schemas['GrandfatheredCostSeries'];

export type GrandfatheredCostComparisonResponse = Schemas['GrandfatheredCostComparisonResponse'];

export async function getDCPlanAnalytics(
  workspaceId: string,
  scenarioId: string,
  activeOnly: boolean = false,
  effectiveRate: boolean = false,
  cohort: DCPlanCohort = 'all',
  population?: DCPlanPopulation
): Promise<DCPlanAnalytics> {
  const params = new URLSearchParams();
  if (activeOnly) params.set('active_only', 'true');
  if (effectiveRate) params.set('effective_rate', 'true');
  if (cohort !== 'all') params.set('cohort', cohort);
  if (population) params.set('population', population);
  const qs = params.toString() ? `?${params}` : '';
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/analytics/dc-plan${qs}`
  );
  return handleResponse<DCPlanAnalytics>(response);
}

export async function compareDCPlanAnalytics(
  workspaceId: string,
  scenarioIds: string[],
  activeOnly: boolean = false,
  effectiveRate: boolean = false,
  cohort: DCPlanCohort = 'all',
  population?: DCPlanPopulation
): Promise<DCPlanComparisonResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
  });
  if (activeOnly) params.set('active_only', 'true');
  if (effectiveRate) params.set('effective_rate', 'true');
  if (cohort !== 'all') params.set('cohort', cohort);
  if (population) params.set('population', population);
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/dc-plan/compare?${params}`
  );
  return handleResponse<DCPlanComparisonResponse>(response);
}

export async function compareGrandfatheredCost(
  workspaceId: string,
  baselineScenarioId: string,
  scenarioIds: string[],
  cutoffYear: number,
  scheduleType: VestingScheduleType,
  forfeiturePolicy: ForfeiturePolicy
): Promise<GrandfatheredCostComparisonResponse> {
  const params = new URLSearchParams({
    baseline_scenario: baselineScenarioId,
    scenarios: scenarioIds.join(','),
    cutoff_year: String(cutoffYear),
    schedule_type: scheduleType,
    forfeiture_policy: forfeiturePolicy,
  });
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/dc-plan/grandfathered-cost?${params}`
  );
  return handleResponse<GrandfatheredCostComparisonResponse>(response);
}

export async function getWinnersLosersComparison(
  workspaceId: string,
  planA: string,
  planB: string
): Promise<WinnersLosersResponse> {
  const params = new URLSearchParams({ plan_a: planA, plan_b: planB });
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/winners-losers?${params}`
  );
  return handleResponse<WinnersLosersResponse>(response);
}

// ============================================================================
// Band Configuration Endpoints (E003: Studio Band Configuration Management)
// ============================================================================

export type Band = Schemas['Band'];

export type BandConfig = Schemas['BandConfig'];

export interface BandValidationError {
  band_type: 'age' | 'tenure';
  error_type: 'gap' | 'overlap' | 'invalid_range' | 'coverage';
  message: string;
  band_ids: number[];
}

export type BandAnalysisRequest = Schemas['BandAnalysisRequest'];

export type DistributionStats = Schemas['DistributionStats'];

export type BandAnalysisResult = Schemas['BandAnalysisResult'];

/**
 * Get band configurations (age and tenure bands) from dbt seed files.
 */
export async function getBandConfigs(workspaceId: string): Promise<BandConfig> {
  const response = await fetchWithAuth(
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
  filePath: string,
  asOfDate?: string
): Promise<BandAnalysisResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-age-bands`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, as_of_date: asOfDate }),
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
  filePath: string,
  asOfDate?: string
): Promise<BandAnalysisResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-tenure-bands`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, as_of_date: asOfDate }),
    }
  );
  return handleResponse<BandAnalysisResult>(response);
}

// ============================================================================
// Turnover Rate Analysis Endpoints (Feature 056)
// ============================================================================

export type TurnoverRateSuggestion = Schemas['TurnoverRateSuggestion'];

export type TurnoverAnalysisResult = Schemas['TurnoverAnalysisResult'];

/**
 * Analyze census data for turnover rate suggestions.
 * Calculates experienced and new hire termination rates from census termination data.
 */
export async function analyzeTurnoverRates(
  workspaceId: string,
  filePath: string,
  asOfDate?: string
): Promise<TurnoverAnalysisResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-turnover`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, as_of_date: asOfDate }),
    }
  );
  return handleResponse<TurnoverAnalysisResult>(response);
}

// ============================================================================
// Opt-Out Rate Census Analysis (Feature 085)
// ============================================================================

export type OptOutRateAnalysisRequest = Schemas['OptOutRateAnalysisRequest'];

export type OptOutRateAnalysisResult = Schemas['OptOutRateAnalysisResult'];

/**
 * Analyze census data for opt-out rate suggestion.
 * Calculates non-participant rate among employees hired within a tenure lookback window.
 */
export async function analyzeOptOutRate(
  workspaceId: string,
  request: OptOutRateAnalysisRequest
): Promise<OptOutRateAnalysisResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-opt-out-rate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: request.file_path,
        lookback_years: request.lookback_years ?? 3,
      }),
    }
  );
  return handleResponse<OptOutRateAnalysisResult>(response);
}

// ============================================================================
// Voluntary Deferral Segment Census Analysis
// ============================================================================

export type DeferralSegmentAnalysisRequest = Schemas['DeferralSegmentAnalysisRequest'];

export type DeferralSegment = Schemas['DeferralSegment'];

export type DeferralSegmentAnalysisResult = Schemas['DeferralSegmentAnalysisResult'];

/**
 * Analyze census data for per-segment starting deferral rate suggestions.
 * Averages only participants, since the configured rates are conditional on enrolling.
 */
export async function analyzeDeferralSegments(
  workspaceId: string,
  request: DeferralSegmentAnalysisRequest
): Promise<DeferralSegmentAnalysisResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-deferral-segments`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: request.file_path,
        ...(request.as_of_date ? { as_of_date: request.as_of_date } : {}),
      }),
    }
  );
  return handleResponse<DeferralSegmentAnalysisResult>(response);
}

// ============================================================================
// Pre-Simulation Census Analysis
// ============================================================================

export type CensusAnalysisRequest = Schemas['CensusAnalysisRequest'];

export type CensusMetrics = Schemas['CensusMetrics'];

export type CensusSegmentMetrics = Schemas['CensusSegmentMetrics'];

export type CensusDataQualityIssue = Schemas['CensusDataQualityIssue'];

export type CensusDeferralRateBucket = Schemas['CensusDeferralRateBucket'];

export type CensusAnalysisResult = Schemas['CensusAnalysisResult'];

/**
 * Analyze the raw/staged census for participation, savings-rate, and cost-proxy
 * metrics -- the same lens as Overview/DC Plan, computed pre-simulation.
 */
export async function analyzeCensus(
  workspaceId: string,
  request: CensusAnalysisRequest
): Promise<CensusAnalysisResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analyze-census`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: request.file_path,
        ...(request.as_of_date ? { as_of_date: request.as_of_date } : {}),
      }),
    }
  );
  return handleResponse<CensusAnalysisResult>(response);
}

// ============================================================================
// Promotion Hazard Configuration Endpoints (Feature 038)
// ============================================================================

export type PromotionHazardBase = Schemas['PromotionHazardBase'];

export type PromotionHazardAgeMultiplier = Schemas['PromotionHazardAgeMultiplier'];

export type PromotionHazardTenureMultiplier = Schemas['PromotionHazardTenureMultiplier'];

export type PromotionHazardConfig = Schemas['PromotionHazardConfig'];

/**
 * Get promotion hazard configuration from dbt seed files.
 */
export async function getPromotionHazardConfig(workspaceId: string): Promise<PromotionHazardConfig> {
  const response = await fetchWithAuth(
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
export type VestingScheduleType = Schemas['VestingScheduleType'];

/**
 * Vesting schedule metadata for display.
 */
export type VestingScheduleInfo = Schemas['VestingScheduleInfo'];

/**
 * Response for listing all vesting schedules.
 */
export type VestingScheduleListResponse = Schemas['VestingScheduleListResponse'];

/**
 * Configuration for a vesting schedule in analysis request.
 */
export type VestingScheduleConfig = Schemas['VestingScheduleConfig-Input'];

/**
 * Request body for vesting analysis.
 */
export type VestingAnalysisRequest = Schemas['VestingAnalysisRequest'];

/**
 * Summary statistics for vesting analysis.
 */
export type VestingAnalysisSummary = Schemas['VestingAnalysisSummary'];

/**
 * Vesting breakdown by tenure band.
 */
export type TenureBandSummary = Schemas['TenureBandSummary'];

/**
 * Employee-level vesting detail.
 */
export type EmployeeVestingDetail = Schemas['EmployeeVestingDetail'];

/**
 * Full vesting analysis response.
 */
export type VestingAnalysisResponse = Schemas['VestingAnalysisResponse'];

/**
 * Available simulation years for a scenario.
 */
export type ScenarioYearsResponse = Schemas['ScenarioYearsResponse'];

/**
 * Forfeitures for one scenario in one simulation year.
 */
export type ForfeitureYearRow = Schemas['ForfeitureYearRow'];

/**
 * What the plan does with forfeited employer money (issue #444).
 *
 * These are not three flavours of the same subtraction: only the first two
 * reduce the sponsor's outlay. Under `reallocate_to_participants` the money
 * goes to remaining participants' accounts and the sponsor still funds the
 * full match, so the employer cost offset is $0.
 */
export type ForfeiturePolicy =
  | 'offset_employer_contributions'
  | 'pay_plan_expenses'
  | 'reallocate_to_participants';

/**
 * The forfeiture offset applied to one simulation year's employer cost.
 *
 * Forfeitures from year N terminations are recognized and applied in year
 * N + 1, so `source_year` is always `simulation_year - 1`.
 */
export type EmployerCostOffsetRow = Schemas['EmployerCostOffsetRow'];

/**
 * One scenario's forfeitures across every simulation year it contains.
 */
export type ScenarioForfeitureSeries = Schemas['ScenarioForfeitureSeries'];

/**
 * A requested scenario excluded from the projection, with the reason.
 */
export type SkippedScenario = Schemas['SkippedScenario'];

/**
 * Multi-year, multi-scenario forfeitures under a single vesting schedule.
 */
export type ForfeitureProjectionResponse = Schemas['ForfeitureProjectionResponse'];

export interface ForfeitureProjectionParams {
  scenarioIds: string[];
  scheduleType: VestingScheduleType;
  requireHoursCredit?: boolean;
  hoursThreshold?: number;
  forfeiturePolicy?: ForfeiturePolicy;
}

/**
 * Get list of all available vesting schedules.
 */
export async function listVestingSchedules(): Promise<VestingScheduleListResponse> {
  const response = await fetchWithAuth(`${API_BASE}/api/vesting/schedules`);
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
  const response = await fetchWithAuth(
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
 * Report annual forfeitures under one vesting schedule, for every simulation
 * year, across a selected set of scenarios.
 *
 * This is a reporting view, not the current-vs-proposed comparison served by
 * analyzeVesting. A scenario whose database is missing comes back in `skipped`
 * rather than failing the request.
 */
export async function getForfeitureProjection(
  workspaceId: string,
  params: ForfeitureProjectionParams
): Promise<ForfeitureProjectionResponse> {
  const query = new URLSearchParams({
    scenarios: params.scenarioIds.join(','),
    schedule_type: params.scheduleType,
  });
  if (params.requireHoursCredit !== undefined) {
    query.set('require_hours_credit', String(params.requireHoursCredit));
  }
  if (params.hoursThreshold !== undefined) {
    query.set('hours_threshold', String(params.hoursThreshold));
  }
  if (params.forfeiturePolicy !== undefined) {
    query.set('forfeiture_policy', params.forfeiturePolicy);
  }
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/vesting/forfeitures?${query}`
  );
  return handleResponse<ForfeitureProjectionResponse>(response);
}

/**
 * Get available simulation years for vesting analysis in a scenario.
 */
export async function getScenarioYears(
  workspaceId: string,
  scenarioId: string
): Promise<ScenarioYearsResponse> {
  const response = await fetchWithAuth(
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
export type ExportManifest = Schemas['ExportManifest'];

export type ExportResult = Schemas['ExportResult'];

export type BulkExportStatus = Schemas['BulkExportStatus'];

export type ImportConflict = Schemas['ImportConflict'];

export type ImportValidationResponse = Schemas['ImportValidationResponse'];

export type ImportResponse = Schemas['ImportResponse'];

export type BulkImportStatus = Schemas['BulkImportStatus'];

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
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/${workspaceId}/export`, {
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
    const filenameMatch = /filename="?([^"]+)"?/.exec(contentDisposition);
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
  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/bulk-export`, {
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
  const response = await fetchWithAuth(
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

  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/import/validate`, {
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

  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/import`, {
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

  const response = await fetchWithAuth(`${API_BASE}/api/workspaces/bulk-import`, {
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
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/bulk-import/${operationId}`
  );
  return handleResponse<BulkImportStatus>(response);
}

// ============================================================================
// NDT Testing Endpoints (Feature 050)
// ============================================================================

export type ACPEmployeeDetail = Schemas['ACPEmployeeDetail'];

export type TestResult = 'pass' | 'fail' | 'error';

export type ACPScenarioResult = Schemas['ACPScenarioResult'];

export type ACPTestResponse = Schemas['ACPTestResponse'];

export type NDTAvailableYearsResponse = Schemas['AvailableYearsResponse'];

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
  const response = await fetchWithAuth(
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
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/available-years?${params}`
  );
  return handleResponse<NDTAvailableYearsResponse>(response);
}

// ============================================================================
// NDT 401(a)(4) General Test (Feature 051)
// ============================================================================

export type Section401a4EmployeeDetail = Schemas['Section401a4EmployeeDetail'];

export type Section401a4ScenarioResult = Schemas['Section401a4ScenarioResult'];

export type Section401a4TestResponse = Schemas['Section401a4TestResponse'];

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
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/401a4?${params}`
  );
  return handleResponse<Section401a4TestResponse>(response);
}

// ============================================================================
// NDT 415 Annual Additions Limit Test (Feature 051)
// ============================================================================

export type Section415EmployeeDetail = Schemas['Section415EmployeeDetail'];

export type Section415ScenarioResult = Schemas['Section415ScenarioResult'];

export type Section415TestResponse = Schemas['Section415TestResponse'];

// ============================================================================
// NDT ADP (Actual Deferral Percentage) Test (Feature 052)
// ============================================================================

export type ADPEmployeeDetail = Schemas['ADPEmployeeDetail'];

export type ADPScenarioResult = Schemas['ADPScenarioResult'];

export type ADPTestResponse = Schemas['ADPTestResponse'];

/**
 * Run ADP non-discrimination test for one or more scenarios.
 */
export async function runADPTest(
  workspaceId: string,
  scenarioIds: string[],
  year: number,
  includeEmployees: boolean = false,
  safeHarbor: boolean = false,
  testingMethod: 'current' | 'prior' = 'current'
): Promise<ADPTestResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
    year: year.toString(),
    include_employees: includeEmployees.toString(),
    safe_harbor: safeHarbor.toString(),
    testing_method: testingMethod,
  });
  const response = await fetchWithAuth(
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
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/415?${params}`
  );
  return handleResponse<Section415TestResponse>(response);
}

// ============================================================================
// Apply Workforce Parameters (Feature 072)
// ============================================================================

export type ScenarioApplyOutcome = Schemas['ScenarioApplyOutcome'];

export type WorkforceParamsApplyResult = Schemas['WorkforceParamsApplyResult'];

/**
 * Apply workforce parameters from a source scenario to multiple target scenarios.
 * Copies workforce assumptions (compensation, turnover, hiring, demographics, seed configs)
 * while preserving DC plan parameters in each target.
 */
export async function applyWorkforceParams(
  workspaceId: string,
  sourceScenarioId: string,
  targetScenarioIds: string[]
): Promise<WorkforceParamsApplyResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${sourceScenarioId}/apply-workforce-params`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_scenario_ids: targetScenarioIds }),
    }
  );
  return handleResponse<WorkforceParamsApplyResult>(response);
}

// ============================================================================
// Calibration Endpoints (Feature 105 - Fast Compensation Calibration)
// ============================================================================

export type CalibrationParams = Schemas['CalibrationParameterSet'];

export type CalibrationRunRequest = Schemas['CalibrationRunRequest'];

export type AutoCalibrationSettings = Schemas['AutoCalibrationSettings'];

export type AutoCalibrationRequest = Schemas['AutoCalibrationRequest'];

export type OptimizationIteration = Schemas['OptimizationIteration'];

export type AutoCalibrationOutcome = Schemas['AutoCalibrationResult'];

export type CalibrationContext = Schemas['CalibrationContext-Output'];

export interface AutoCalibrationResponse {
  run_id: string;
  outcome: AutoCalibrationOutcome;
  context: CalibrationContext;
}

export type PerYearCompensationResult = Schemas['PerYearCompensationResult'];

export interface CalibrationRunResponse {
  run_id: string;
  results: PerYearCompensationResult[];
}

/** Acknowledgement returned by the (now async) calibration POST endpoints. */
export type CalibrationStartResponse = Schemas['CalibrationStartResponse'];

/** Background calibration job record (issue #380). */
export type CalibrationJob = Schemas['CalibrationJob'];

export async function getCalibrationRun(runId: string): Promise<CalibrationJob> {
  const response = await fetchWithAuth(`${API_BASE}/api/calibration/runs/${runId}`);
  return handleResponse<CalibrationJob>(response);
}

const CALIBRATION_POLL_MS = 2000;

/** Poll a calibration job until it reaches a terminal state. */
async function awaitCalibrationJob(runId: string): Promise<CalibrationJob> {
  for (;;) {
    const job = await getCalibrationRun(runId);
    if (job.status === 'completed') return job;
    if (job.status === 'failed') {
      throw new ApiError(
        job.error_status ?? 500,
        'Calibration failed',
        job.error ?? undefined
      );
    }
    await new Promise((resolve) => setTimeout(resolve, CALIBRATION_POLL_MS));
  }
}

/**
 * Run a comp-only calibration. The backend enqueues a background job and this
 * wrapper polls it to completion, so callers keep the old request/response
 * shape while the HTTP requests stay short-lived (issue #380).
 */
export async function runCalibration(
  request: CalibrationRunRequest
): Promise<CalibrationRunResponse> {
  const response = await fetchWithAuth(`${API_BASE}/api/calibration/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const started = await handleResponse<CalibrationStartResponse>(response);
  const job = await awaitCalibrationJob(started.run_id);
  return { run_id: job.run_id, results: job.results ?? [] };
}

/**
 * Auto-calibrate: search until every annual YoY avg-comp result is within the
 * requested tolerance (workforce growth is set directly — it is deterministic).
 * Runs several fast comp-only builds (a few minutes); enqueued as a
 * background job and polled to completion (issue #380).
 */
export async function optimizeCalibration(
  request: AutoCalibrationRequest
): Promise<AutoCalibrationResponse> {
  const response = await fetchWithAuth(`${API_BASE}/api/calibration/optimize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const started = await handleResponse<CalibrationStartResponse>(response);
  const job = await awaitCalibrationJob(started.run_id);
  if (!job.outcome) {
    throw new ApiError(500, 'Calibration failed', 'Job completed without an outcome');
  }
  if (!job.context) {
    throw new ApiError(500, 'Calibration failed', 'Job completed without target context');
  }
  return { run_id: job.run_id, outcome: job.outcome, context: job.context };
}

export type CalibrationApplyResult = Schemas['CalibrationApplyResult'];

export async function applyCalibrationCandidate(
  context: CalibrationContext,
  outcome: AutoCalibrationOutcome,
): Promise<CalibrationApplyResult> {
  const response = await fetchWithAuth(`${API_BASE}/api/calibration/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      context,
      best_params: outcome.best_params,
      target_comp_growth_pct: outcome.target_comp_growth_pct,
    }),
  });
  return handleResponse<CalibrationApplyResult>(response);
}

// ============================================================================
// Optimizer Endpoints (Roadmap 7/8, issue #461 / #557 — plan-design optimizer)
// ============================================================================

export type LeverKind = 'discrete' | 'continuous';
export type LeverValue = string | number | boolean;

export type LeverSpec = Schemas['LeverSpec'];

export type DesignSpaceSpec = Schemas['DesignSpaceSpec'];

export type ObjectiveDirection = 'minimize' | 'maximize';

export type ObjectiveTerm = Schemas['ObjectiveTerm'];

export type ConstraintOperator = '<=' | '>=' | '<' | '>' | '==';

export type ConstraintSpec = Schemas['ConstraintSpec'];

export type ObjectiveConstraintSpec = Schemas['ObjectiveConstraintSpec'];

export type BaselineSpec = Schemas['BaselineSpec'];

/**
 * The spec Studio sends. Hand-written on purpose: the backend accepts any dict
 * here so /optimizer/validate can report an invalid spec instead of a 422.
 */
export type OptimizerSpecPayload = {
  design_space: DesignSpaceSpec;
  objective: ObjectiveConstraintSpec;
  baseline: BaselineSpec;
};

export type ConstraintResult = Schemas['ConstraintResult'];

export type CandidateStatus = 'feasible' | 'infeasible' | 'non_evaluable' | 'failed';

export type Candidate = Schemas['Candidate'];

export type OptimizerRun = Schemas['OptimizerRun'];

export type OptimizerValidateRequest = Schemas['OptimizerValidateRequest'];

export type OptimizerValidateResponse = Schemas['OptimizerValidateResponse'];

export type OptimizerRunRequest = Schemas['OptimizerRunRequest'];

export type OptimizerStartResponse = Schemas['OptimizerStartResponse'];

export type OptimizerJob = Schemas['OptimizerJob'];

export interface PromoteCandidateParams {
  workspaceId: string;
  sourceScenarioId: string;
  name: string;
  description?: string;
  force?: boolean;
}

/** Cheap, synchronous spec validation + optional seed-phase preview. Always
 * resolves 200; a bad spec is reported via `valid`/`error`, never thrown. */
export async function validateOptimizerSpec(
  request: OptimizerValidateRequest
): Promise<OptimizerValidateResponse> {
  const response = await fetchWithAuth(`${API_BASE}/api/optimizer/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<OptimizerValidateResponse>(response);
}

export async function getOptimizerRun(runId: string): Promise<OptimizerJob> {
  const response = await fetchWithAuth(`${API_BASE}/api/optimizer/runs/${runId}`);
  return handleResponse<OptimizerJob>(response);
}

const OPTIMIZER_POLL_MS = 2000;

/** Poll an optimizer job until it reaches a terminal state. */
async function awaitOptimizerJob(runId: string): Promise<OptimizerJob> {
  for (;;) {
    const job = await getOptimizerRun(runId);
    if (job.status === 'completed') return job;
    if (job.status === 'failed') {
      throw new ApiError(job.error_status ?? 500, 'Optimizer run failed', job.error ?? undefined);
    }
    await new Promise((resolve) => setTimeout(resolve, OPTIMIZER_POLL_MS));
  }
}

/**
 * Run a plan-design optimizer search. The backend enqueues a background job
 * (each candidate is an isolated scenario simulation, so this can take
 * several minutes) and this wrapper polls it to completion.
 */
export async function runOptimizer(request: OptimizerRunRequest): Promise<OptimizerJob> {
  const response = await fetchWithAuth(`${API_BASE}/api/optimizer/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const started = await handleResponse<OptimizerStartResponse>(response);
  return awaitOptimizerJob(started.run_id);
}

/** Drill down to one candidate's already-computed result (permalink/deep-link
 * use; the same data is already present on a completed OptimizerJob). */
export async function getOptimizerCandidate(
  runId: string,
  candidateId: string
): Promise<Candidate> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/optimizer/runs/${runId}/candidates/${candidateId}`
  );
  return handleResponse<Candidate>(response);
}

/** Create an editable scenario from an optimizer candidate. */
export async function promoteOptimizerCandidate(
  runId: string,
  candidateId: string,
  params: PromoteCandidateParams
): Promise<Scenario> {
  const response = await fetchWithAuth(
    `${API_BASE}/api/optimizer/runs/${runId}/candidates/${candidateId}/promote`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace_id: params.workspaceId,
        source_scenario_id: params.sourceScenarioId,
        name: params.name,
        description: params.description,
        force: params.force ?? false,
      }),
    }
  );

  if (response.status === 409) {
    const error: { detail?: unknown; suggested_name?: unknown } = await response.json();
    const detail = typeof error.detail === 'string' ? error.detail : 'scenario name already exists';
    const suggestedName = typeof error.suggested_name === 'string' ? error.suggested_name : params.name;
    throw new ScenarioNameConflictError(detail, suggestedName);
  }

  return handleResponse<Scenario>(response);
}

// ---------------------------------------------------------------------------
// Ensembles (#554) -- Studio band charts over a seed-ensemble aggregate DB.
// ---------------------------------------------------------------------------

export type EnsembleDistributionRow = Schemas['MetricDistribution'];

export type EnsembleRiskStatement = Schemas['RiskStatement'];

export type EnsembleAttributionRow = Schemas['AttributionShare'];

export type EnsembleDatabaseSummary = Schemas['EnsembleDatabaseSummary'];

/** List ensemble databases under a scan root (defaults to the server's configured root). */
export async function discoverEnsembleDatabases(root?: string): Promise<EnsembleDatabaseSummary[]> {
  const params = new URLSearchParams();
  if (root) params.set('root', root);
  const query = params.toString();
  const response = await fetchWithAuth(`${API_BASE}/api/ensembles/discover${query ? `?${query}` : ''}`);
  return handleResponse<EnsembleDatabaseSummary[]>(response);
}

export async function getEnsembleDistributions(
  database: string,
  scenarioId: string,
  ensembleId: string
): Promise<EnsembleDistributionRow[]> {
  const params = new URLSearchParams({ database, ensemble_scenario_id: scenarioId, ensemble_id: ensembleId });
  const response = await fetchWithAuth(`${API_BASE}/api/ensembles/distributions?${params}`);
  return handleResponse<EnsembleDistributionRow[]>(response);
}

/** Thresholds aren't persisted anywhere -- evaluated on demand against stored seed evidence. */
export async function getEnsembleRisk(
  database: string,
  scenarioId: string,
  ensembleId: string,
  thresholds: { metric: string; value: number }[]
): Promise<EnsembleRiskStatement[]> {
  const params = new URLSearchParams({ database, ensemble_scenario_id: scenarioId, ensemble_id: ensembleId });
  for (const threshold of thresholds) params.append('threshold', `${threshold.metric}:${threshold.value}`);
  const response = await fetchWithAuth(`${API_BASE}/api/ensembles/risk?${params}`);
  return handleResponse<EnsembleRiskStatement[]>(response);
}

export async function getEnsembleAttribution(
  database: string,
  scenarioId: string,
  ensembleId: string
): Promise<EnsembleAttributionRow[]> {
  const params = new URLSearchParams({ database, ensemble_scenario_id: scenarioId, ensemble_id: ensembleId });
  const response = await fetchWithAuth(`${API_BASE}/api/ensembles/attribution?${params}`);
  return handleResponse<EnsembleAttributionRow[]>(response);
}

// ---------------------------------------------------------------------------
// Parameter fit & backtest (#588) -- fit simulation parameters from census
// history, score them against held-out years, apply a pack to a new scenario.
// ---------------------------------------------------------------------------

export type FitHistorySet = Schemas['HistorySet'];
export type FitSnapshotInfo = Schemas['SnapshotInfo'];
export type FitSplitOption = Schemas['SplitOption'];
export type ParamFitRequest = Schemas['ParamFitRequest-Input'];
export type ParamFitThresholds = Schemas['ThresholdsModel-Input'];
export type ParamFitOptions = Schemas['FitOptionsModel-Input'];
export type ParamFitJob = Schemas['ParamFitJob'];
export type ParamFitJobSummary = Schemas['ParamFitJobSummary'];
export type ParamFitResult = Schemas['ParamFitResult'];
export type ParamFitProgress = Schemas['JobProgress'];
export type ParamFitStatus = ParamFitJob['status'];
export type ParamPackApplyPreview = Schemas['ApplyPreview'];
export type ParamPackAcknowledgement = ParamPackApplyPreview['required_acknowledgements'][number];
export type ParamPackApplyRequest = Schemas['ApplyRequest'];

const paramFitsBase = (workspaceId: string) =>
  `${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}`;

/** Upload 2-5 annual census snapshots; the server validates them with the fitter. */
export async function uploadFitHistory(workspaceId: string, files: File[]): Promise<FitHistorySet> {
  const formData = new FormData();
  for (const file of files) formData.append('files', file);
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/fit-history`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<FitHistorySet>(response);
}

export async function listFitHistory(workspaceId: string): Promise<FitHistorySet[]> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/fit-history`);
  return handleResponse<FitHistorySet[]>(response);
}

export async function deleteFitHistory(workspaceId: string, historyId: string): Promise<void> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/fit-history/${historyId}`, {
    method: 'DELETE',
  });
  if (!response.ok) await handleResponse<never>(response);
}

/** Enqueue a fit or fit+backtest job; returns immediately (202). */
export async function startParamFit(workspaceId: string, request: ParamFitRequest): Promise<ParamFitJob> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/param-fits`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<ParamFitJob>(response);
}

export async function listParamFits(workspaceId: string): Promise<ParamFitJobSummary[]> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/param-fits`);
  return handleResponse<ParamFitJobSummary[]>(response);
}

export async function getParamFit(workspaceId: string, jobId: string): Promise<ParamFitJob> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/param-fits/${jobId}`);
  return handleResponse<ParamFitJob>(response);
}

export async function cancelParamFit(workspaceId: string, jobId: string): Promise<ParamFitJob> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/param-fits/${jobId}/cancel`, {
    method: 'POST',
  });
  return handleResponse<ParamFitJob>(response);
}

/** The written fit report or backtest scorecard, as Markdown. */
export async function getParamFitReport(
  workspaceId: string,
  jobId: string,
  kind: 'fit' | 'scorecard'
): Promise<string> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/param-fits/${jobId}/reports/${kind}`);
  if (!response.ok) await handleResponse<never>(response);
  return response.text();
}

export async function getParamPackApplyPreview(
  workspaceId: string,
  jobId: string,
  sourceScenarioId: string
): Promise<ParamPackApplyPreview> {
  const params = new URLSearchParams({ source_scenario_id: sourceScenarioId });
  const response = await fetchWithAuth(
    `${paramFitsBase(workspaceId)}/param-fits/${jobId}/apply-preview?${params}`
  );
  return handleResponse<ParamPackApplyPreview>(response);
}

/** A refused apply: stale inputs or missing acknowledgements, each spelled out. */
export class ParamPackApplyError extends ApiError {
  constructor(
    status: number,
    detail: string,
    public stale: { reason: string; message: string }[] = [],
    public missingAcknowledgements: string[] = []
  ) {
    super(status, detail, detail);
    this.name = 'ParamPackApplyError';
  }
}

/** Create a NEW scenario from a reviewed pack. The source scenario is never modified. */
export async function applyParamPack(
  workspaceId: string,
  jobId: string,
  request: ParamPackApplyRequest
): Promise<Scenario> {
  const response = await fetchWithAuth(`${paramFitsBase(workspaceId)}/param-fits/${jobId}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (response.status === 409 || response.status === 422) {
    const body: {
      detail?: unknown;
      suggested_name?: unknown;
      stale?: { reason: string; message: string }[];
      missing_acknowledgements?: string[];
    } = await response.json();
    const detail = typeof body.detail === 'string' ? body.detail : 'The pack could not be applied.';
    if (typeof body.suggested_name === 'string') {
      throw new ScenarioNameConflictError(detail, body.suggested_name);
    }
    throw new ParamPackApplyError(response.status, detail, body.stale ?? [], body.missing_acknowledgements ?? []);
  }
  return handleResponse<Scenario>(response);
}
