import { describe, expect, it, vi } from 'vitest';
import { extractCensusPath, resolveCensusFields } from './censusConfig';
import { buildConfigPayload } from './buildConfigPayload';
import { DEFAULT_FORM_DATA } from './constants';

const config = (path: string) => ({ setup: { census_parquet_path: path } });
const valid = { valid: true, exists: true, row_count: 12, last_modified: '2026-10-14T00:00:00Z' };
const missing = { valid: false, exists: false, row_count: null, last_modified: null };

describe('effective census for loading and copying scenarios', () => {
  it('uses backend setup precedence for legacy data_sources scenarios', async () => {
    const scenario = { data_sources: { census_parquet_path: 'legacy.parquet' } };
    const validate = vi.fn().mockResolvedValue(valid);
    expect(extractCensusPath(scenario)).toBeUndefined();
    const fields = await resolveCensusFields(scenario, config('workspace.parquet'), validate);
    expect(validate).toHaveBeenCalledWith('workspace.parquet');
    expect(fields.censusDataSource).toBe('workspace');
    expect(fields.censusDataPath).toBe('workspace.parquet');
  });

  it('checks an explicit setup default before the workspace fallback', async () => {
    const scenario = {
      setup: { census_parquet_path: 'data/census_preprocessed.parquet' },
      data_sources: { census_parquet_path: 'legacy.parquet' },
    };
    const validate = vi.fn().mockResolvedValue(valid);
    const fields = await resolveCensusFields(scenario, config('workspace.parquet'), validate);
    expect(validate).toHaveBeenCalledWith('data/census_preprocessed.parquet');
    expect(fields.censusDataSource).toBe('scenario');
  });

  it('falls back from a deleted import and saves workspace inheritance', async () => {
    const validate = vi.fn().mockResolvedValueOnce(missing).mockResolvedValueOnce(valid);
    const fields = await resolveCensusFields(config('old.parquet'), config('current.parquet'), validate);
    expect(validate.mock.calls).toEqual([['old.parquet'], ['current.parquet']]);
    expect(fields).toEqual({
      censusDataPath: 'current.parquet', censusDataSource: 'workspace',
      censusDataStatus: 'loaded', censusRowCount: 12, censusLastModified: '2026-10-14',
    });
    const payload = buildConfigPayload({ ...DEFAULT_FORM_DATA, ...fields }, null, null, {
      isScenario: true, workspacePath: 'current.parquet',
    });
    expect(payload.setup).toBeUndefined();
    expect(payload.data_sources).toBeUndefined();
  });

  it('preserves a valid distinct scenario file when saving', async () => {
    const validate = vi.fn().mockResolvedValue(valid);
    const fields = await resolveCensusFields(config('custom.parquet'), config('workspace.parquet'), validate);
    expect(validate).toHaveBeenCalledTimes(1);
    expect(fields.censusDataSource).toBe('scenario');
    const payload = buildConfigPayload({ ...DEFAULT_FORM_DATA, ...fields }, null, null, {
      isScenario: true, workspacePath: 'workspace.parquet',
    });
    expect(payload.setup.census_parquet_path).toBe('custom.parquet');
    expect(payload.data_sources.census_parquet_path).toBe('custom.parquet');
  });

  it('validates inherited census and preserves it when saving workspace defaults', async () => {
    const fields = await resolveCensusFields({}, config('workspace.parquet'), async () => valid);
    const payload = buildConfigPayload({ ...DEFAULT_FORM_DATA, ...fields }, null, null, { isScenario: false });
    expect(payload.setup.census_parquet_path).toBe('workspace.parquet');
  });

  it('keeps inheritance when a copied scenario uses a newly uploaded workspace census', async () => {
    const fields = await resolveCensusFields({}, config('new.parquet'), async () => valid);
    const payload = buildConfigPayload({ ...DEFAULT_FORM_DATA, ...fields }, null, null, {
      isScenario: true, workspacePath: 'cached-old.parquet',
    });
    expect(payload.setup).toBeUndefined();
  });

  it('does not replace an existing invalid file with another census', async () => {
    const validate = vi.fn().mockResolvedValue({ ...missing, exists: true });
    const fields = await resolveCensusFields(config('invalid.parquet'), config('workspace.parquet'), validate);
    expect(validate).toHaveBeenCalledTimes(1);
    expect(fields.censusDataPath).toBe('invalid.parquet');
    expect(fields.censusDataStatus).toBe('error');
  });

  it('does not reinterpret a network failure as a missing file', async () => {
    const validate = vi.fn().mockRejectedValue(new Error('offline'));
    await expect(resolveCensusFields(config('custom'), config('workspace'), validate)).rejects.toThrow('offline');
    expect(validate).toHaveBeenCalledTimes(1);
  });

  it('clears old census state when no path is configured', async () => {
    const validate = vi.fn();
    const fields = await resolveCensusFields({}, {}, validate);
    expect(fields.censusDataPath).toBe('');
    expect(fields.censusRowCount).toBe(0);
    expect(fields.censusLastModified).toBe('');
    expect(validate).not.toHaveBeenCalled();
  });

  it('reports a missing workspace fallback without keeping prior row counts', async () => {
    const fields = await resolveCensusFields(config('old'), config('workspace'), async () => missing);
    expect(fields.censusDataStatus).toBe('error');
    expect(fields.censusRowCount).toBe(0);
  });

  it('does not pin a scenario to the same census as its workspace', () => {
    const payload = buildConfigPayload({ ...DEFAULT_FORM_DATA, censusDataPath: 'workspace' }, null, null, {
      isScenario: true, workspacePath: 'workspace',
    });
    expect(payload.setup).toBeUndefined();
  });
});
