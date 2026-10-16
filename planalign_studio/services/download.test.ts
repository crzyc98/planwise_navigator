import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { downloadArtifact, saveBrowserDownload } from './api';

describe('browser downloads', () => {
  const anchor = { href: '', download: '', click: vi.fn() };
  const createObjectURL = vi.fn(() => 'blob:download');
  const revokeObjectURL = vi.fn();
  const appendChild = vi.fn();
  const removeChild = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('window', {
      URL: { createObjectURL, revokeObjectURL },
      setTimeout,
      dispatchEvent: vi.fn(),
    });
    vi.stubGlobal('document', {
      createElement: () => anchor,
      body: { appendChild, removeChild },
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.resetAllMocks();
  });

  it.each([
    ['results.xlsx', 12],
    ['simulation.duckdb', 150],
  ])('keeps %s (%i MiB) available after the click, then releases it', async (filename, sizeMiB) => {
    const blob = new Blob([new Uint8Array(sizeMiB * 1024 * 1024)]);
    let finishBody!: (blob: Blob) => void;
    const body = new Promise<Blob>((resolve) => { finishBody = resolve; });
    const response = new Response(null);
    vi.spyOn(response, 'blob').mockReturnValue(body);
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);

    const download = downloadArtifact('scenario-1', `runs/run-1/${filename}`, filename);
    await vi.advanceTimersByTimeAsync(0);
    expect(anchor.click).not.toHaveBeenCalled();
    finishBody(blob);
    await download;

    expect(fetchMock.mock.calls[0][0]).toContain(`/scenarios/scenario-1/artifacts/runs/run-1/${filename}`);
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(anchor.download).toBe(filename);
    expect(anchor.click).toHaveBeenCalledOnce();
    expect(removeChild).toHaveBeenCalledWith(anchor);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    await vi.runAllTimersAsync();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:download');
  });

  it('surfaces server errors without saving an error response as a workbook', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Artifact not found' }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    )));

    await expect(downloadArtifact('scenario-1', 'missing.xlsx', 'results.xlsx'))
      .rejects.toThrow('Artifact not found');
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(anchor.click).not.toHaveBeenCalled();
  });

  it('cleans up even if the browser rejects the click', async () => {
    anchor.click.mockImplementationOnce(() => { throw new Error('Download rejected'); });
    expect(() => saveBrowserDownload(new Blob(['data']), 'results.xlsx'))
      .toThrow('Download rejected');
    expect(removeChild).toHaveBeenCalledWith(anchor);
    await vi.runAllTimersAsync();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
  });
});
