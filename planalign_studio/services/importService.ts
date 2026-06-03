/**
 * Import Service — API client for all data import endpoints.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? '';

// ============================================================================
// Types
// ============================================================================

export type ImportStatus =
  | 'uploaded'
  | 'mapping_in_progress'
  | 'generating'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type InferredType = 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'timestamp' | 'unknown';
export type OutputType = 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'timestamp';
export type TransformType = 'rename' | 'string_case' | 'date_parse' | 'null_replace' | 'null_drop' | 'calculated_field';

export interface DetectedColumn {
  name: string;
  inferred_type: InferredType;
  null_count: number;
  sample_values: string[];
}

export interface Transformation {
  transform_type: TransformType;
  params: Record<string, unknown>;
}

export interface FieldMapping {
  mapping_id?: string;
  import_id?: string;
  input_column: string;
  output_column: string;
  output_type: OutputType;
  is_required?: boolean;
  is_excluded?: boolean;
  transformations: Transformation[];
}

export interface ImportSession {
  import_id: string;
  correlation_id: string;
  workspace_id: string;
  original_filename: string;
  source_format: 'csv' | 'xlsx';
  sheet_name: string | null;
  available_sheets: string[];
  row_count: number;
  column_count: number;
  detected_columns: DetectedColumn[];
  preview_rows: Record<string, unknown>[];
  status: ImportStatus;
  created_at: string;
  created_by: string;
  mapping_saved_at: string | null;
  parquet_file_id: string | null;
  error_message: string | null;
  error_rows: Record<string, unknown>[];
  encoding_warnings: string[];
  encoding_used: string;
}

export interface ParquetColumn {
  name: string;
  type: OutputType;
}

export interface ParquetFile {
  file_id: string;
  workspace_id: string;
  import_id: string;
  filename: string;
  storage_path: string;
  original_filename: string;
  row_count: number;
  file_size_bytes: number;
  schema: ParquetColumn[];
  created_at: string;
  created_by: string;
}

export interface MappingValidationError {
  field: string;
  input_column: string;
  message: string;
}

export interface MappingSaveResponse {
  import_id: string;
  status: ImportStatus;
  mapping_saved_at: string;
  validation_errors: MappingValidationError[];
  output_column_count: number;
}

export interface TransformationWarning {
  input_column: string;
  rows_affected: number;
  message: string;
}

export interface PreviewResponse {
  import_id: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total_row_count: number;
  preview_row_count: number;
}

export interface MappedPreviewResponse extends PreviewResponse {
  transformation_warnings: TransformationWarning[];
}

export interface GenerateResponse {
  import_id: string;
  correlation_id: string;
  status: ImportStatus;
  started_at: string;
}

export interface ParquetFilesResponse {
  parquet_files: ParquetFile[];
  total_count: number;
}

export interface MappingTemplateSummary {
  template_id: string;
  name: string;
  description: string | null;
  field_count: number;
  created_at: string;
  created_by: string;
}

export interface MappingTemplatesResponse {
  templates: MappingTemplateSummary[];
}

export interface SaveTemplateResponse {
  template_id: string;
  name: string;
  created_at: string;
}

// ============================================================================
// API functions
// ============================================================================

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function uploadFile(workspaceId: string, file: File): Promise<ImportSession> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/upload`, {
    method: 'POST',
    body: form,
  });
  return handleResponse<ImportSession>(res);
}

export async function selectSheet(workspaceId: string, importId: string, sheetName: string): Promise<ImportSession> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}/sheet`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sheet_name: sheetName }),
  });
  return handleResponse<ImportSession>(res);
}

export async function saveMapping(
  workspaceId: string,
  importId: string,
  fieldMappings: FieldMapping[],
): Promise<MappingSaveResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}/mapping`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field_mappings: fieldMappings }),
  });
  return handleResponse<MappingSaveResponse>(res);
}

export async function getRawPreview(workspaceId: string, importId: string): Promise<PreviewResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}/preview`);
  return handleResponse<PreviewResponse>(res);
}

export async function getMappedPreview(workspaceId: string, importId: string): Promise<MappedPreviewResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}/mapped-preview`);
  return handleResponse<MappedPreviewResponse>(res);
}

export async function getImportStatus(workspaceId: string, importId: string): Promise<ImportSession> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}`);
  return handleResponse<ImportSession>(res);
}

export async function generateParquet(workspaceId: string, importId: string): Promise<GenerateResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  return handleResponse<GenerateResponse>(res);
}

export async function listParquetFiles(workspaceId: string): Promise<ParquetFilesResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/parquet-files`);
  return handleResponse<ParquetFilesResponse>(res);
}

export function downloadParquetFileUrl(workspaceId: string, fileId: string): string {
  return `${API_BASE}/api/workspaces/${workspaceId}/parquet-files/${fileId}/download`;
}

export async function deleteParquetFile(workspaceId: string, fileId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/parquet-files/${fileId}`, {
    method: 'DELETE',
  });
  if (res.status === 204) return;
  const text = await res.text().catch(() => res.statusText);
  throw new Error(`HTTP ${res.status}: ${text}`);
}

export async function listTemplates(workspaceId: string): Promise<MappingTemplatesResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/mapping-templates`);
  return handleResponse<MappingTemplatesResponse>(res);
}

export async function saveTemplate(
  workspaceId: string,
  importId: string,
  name: string,
  description?: string,
): Promise<SaveTemplateResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/mapping-templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ import_id: importId, name, description }),
  });
  return handleResponse<SaveTemplateResponse>(res);
}

export async function applyTemplate(
  workspaceId: string,
  importId: string,
  templateId: string,
): Promise<MappingSaveResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}/apply-template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template_id: templateId }),
  });
  return handleResponse<MappingSaveResponse>(res);
}
