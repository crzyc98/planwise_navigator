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

  it.each(['results.xlsx', 'simulation.duckdb'])('streams %s through a signed URL', async (filename) => {
    const response = new Response(JSON.stringify({ url: '/api/artifact-download/signed-ticket' }));
    const blobSpy = vi.spyOn(response, 'blob');
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);

    await downloadArtifact('scenario-1', `runs/run-1/${filename}`, filename);

    expect(fetchMock.mock.calls[0][0]).toContain(`/scenarios/scenario-1/artifact-download-url/runs/run-1/${filename}`);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    expect(anchor.href).toContain('/api/artifact-download/signed-ticket');
    expect(anchor.download).toBe(filename);
    expect(anchor.click).toHaveBeenCalledOnce();
    expect(removeChild).toHaveBeenCalledWith(anchor);
    expect(blobSpy).not.toHaveBeenCalled();
    expect(createObjectURL).not.toHaveBeenCalled();
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

  it('removes the signed download link if the click fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ url: '/api/artifact-download/signed-ticket' }),
    )));
    anchor.click.mockImplementationOnce(() => { throw new Error('Download rejected'); });
    await expect(downloadArtifact('scenario-1', 'runs/run-1/results.xlsx', 'results.xlsx'))
      .rejects.toThrow('Download rejected');
    expect(removeChild).toHaveBeenCalledWith(anchor);
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
