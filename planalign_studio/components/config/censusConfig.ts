import type { FileValidationResponse } from '../../services/api';
import type { FormData } from './types';

function sectionPath(section: unknown): string | undefined {
  if (!section || typeof section !== 'object' || !('census_parquet_path' in section)) return undefined;
  return typeof section.census_parquet_path === 'string' ? section.census_parquet_path : undefined;
}

export function extractCensusPath(config: unknown): string | undefined {
  if (!config || typeof config !== 'object') return undefined;
  const path = sectionPath('setup' in config ? config.setup : undefined)
    || sectionPath('data_sources' in config ? config.data_sources : undefined);
  return path && path !== 'data/census_preprocessed.parquet' ? path : undefined;
}

type CensusFields = Pick<FormData,
  'censusDataPath' | 'censusDataStatus' | 'censusDataSource' | 'censusRowCount' | 'censusLastModified'>;
type Validation = Pick<FileValidationResponse, 'valid' | 'exists' | 'row_count' | 'last_modified'>;

/** Use a workspace fallback only for a missing scenario file, never an invalid one. */
export async function resolveCensusFields(
  scenario: unknown,
  workspace: unknown,
  validate: (path: string) => Promise<Validation>,
): Promise<CensusFields> {
  const workspacePath = extractCensusPath(workspace);
  let path = extractCensusPath(scenario) || workspacePath || '';
  if (!path) {
    return { censusDataPath: '', censusDataStatus: '', censusDataSource: 'workspace', censusRowCount: 0, censusLastModified: '' };
  }
  let result = await validate(path);
  if (!result.exists && workspacePath && path !== workspacePath) {
    path = workspacePath;
    result = await validate(path);
  }
  return {
    censusDataPath: path,
    censusDataSource: path === workspacePath ? 'workspace' : 'scenario',
    censusDataStatus: result.valid ? 'loaded' : 'error',
    censusRowCount: result.row_count ?? 0,
    censusLastModified: result.last_modified?.split('T')[0] ?? '',
  };
}
