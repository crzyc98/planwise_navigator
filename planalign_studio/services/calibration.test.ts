import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError, CalibrationStatusUnavailable, optimizeCalibration, retrieveCalibrationResult,
  type AutoCalibrationRequest,
} from './api';

const completed = {
  run_id: 'autocal-test', status: 'completed',
  context: { workspace_id: 'workspace', scenario_id: 'baseline' },
  outcome: { results: [{ simulation_year: 2027 }], best_params: { cola_rate: 0.02 } },
};
const json = (body: unknown) => new Response(JSON.stringify(body));
const fetchMock = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('calibration result retrieval', () => {
  it('survives network and proxy failures and returns the original candidate without another POST', async () => {
    fetchMock.mockResolvedValueOnce(json({ run_id: 'autocal-test' }))
      .mockResolvedValueOnce(json({ status: 'running' }))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response('Gateway timeout', { status: 504 }))
      .mockResolvedValueOnce(json(completed));
    const pending = optimizeCalibration({} as AutoCalibrationRequest);
    await vi.runAllTimersAsync();
    expect(await pending).toEqual({ run_id: completed.run_id, outcome: completed.outcome, context: completed.context });
    expect(fetchMock.mock.calls.filter(([, init]) => init.method === 'POST')).toHaveLength(1);
    for (const [url, init] of fetchMock.mock.calls.slice(1)) {
      expect(url).toContain('/calibration/runs/autocal-test');
      expect(init.cache).toBe('no-store');
      expect(init.signal).toBeInstanceOf(AbortSignal);
    }
  });

  it('retains the run ID after repeated status failures and can retrieve that same result later', async () => {
    fetchMock.mockRejectedValue(new TypeError('Disconnected'));
    const pending = retrieveCalibrationResult('autocal-test').catch(error => error);
    await vi.runAllTimersAsync();
    const error = await pending;
    expect(error).toBeInstanceOf(CalibrationStatusUnavailable);
    expect(error.runId).toBe('autocal-test');
    expect(fetchMock).toHaveBeenCalledTimes(5);
    fetchMock.mockResolvedValueOnce(json(completed));
    expect((await retrieveCalibrationResult(error.runId)).outcome).toEqual(completed.outcome);
    expect(fetchMock.mock.calls.every(([, init]) => !init.method)).toBe(true);
  });

  it('does not retry or conceal a reported engine failure', async () => {
    fetchMock.mockResolvedValue(json({ status: 'failed', error: 'Calibration job failed: error_id=abc', error_status: 500 }));
    await expect(retrieveCalibrationResult('autocal-test')).rejects.toThrow('error_id=abc');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('tells the user to start again when the server job is gone', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Run not found' }), { status: 404 }));
    const error: unknown = await retrieveCalibrationResult('autocal-test').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(CalibrationStatusUnavailable);
    expect(error).toMatchObject({
      status: 404,
      message: 'Calibration run no longer available; start again.',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    { ...completed, outcome: null },
    { ...completed, context: null },
    { ...completed, outcome: { ...completed.outcome, results: [] } },
  ])('rejects a completed job without an applicable result', async job => {
    fetchMock.mockResolvedValue(json(job));
    await expect(retrieveCalibrationResult('autocal-test')).rejects.toBeInstanceOf(ApiError);
  });
});
