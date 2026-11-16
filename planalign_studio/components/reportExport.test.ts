import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, downloadScenarioReport, scenarioReportUrl } from '../services/api';
import { REPORT_BASIS_NOTE, reportBasisNote, reportRequest } from './reportExport';

const ids = ['a', 'b', 'c', 'd', 'e', 'f'];

describe('reportRequest', () => {
  it('uses the anchor as the path scenario and sends the rest as compare', () => {
    const request = reportRequest(ids, 'c', 'pptx');
    expect(request).toEqual({
      scenarioId: 'c',
      options: { format: 'pptx', compare: ['a', 'b', 'd', 'e', 'f'], anchor: 'c' },
    });
  });

  it('falls back to the first selected scenario when the anchor is not selected', () => {
    expect(reportRequest(ids, '', 'pdf')?.options.anchor).toBe('a');
    expect(reportRequest(ids, 'zzz', 'pdf')?.scenarioId).toBe('a');
  });

  it('returns null with nothing selected', () => {
    expect(reportRequest([], 'a', 'pdf')).toBeNull();
  });
});

describe('scenarioReportUrl', () => {
  it('carries format, all selected scenarios and the anchor for six scenarios', () => {
    for (const format of ['pdf', 'pptx'] as const) {
      const request = reportRequest(ids, 'd', format)!;
      const url = new URL(scenarioReportUrl('ws 1', request.scenarioId, request.options), 'http://x');
      expect(url.pathname).toMatch(/\/api\/workspaces\/ws%201\/scenarios\/d\/report$/);
      expect(url.searchParams.get('format')).toBe(format);
      expect(url.searchParams.get('compare')).toBe('a,b,c,e,f');
      expect(url.searchParams.get('anchor')).toBe('d');
    }
  });

  it('omits compare for a single scenario', () => {
    const url = new URL(scenarioReportUrl('w', 's', { format: 'pdf', anchor: 's' }), 'http://x');
    expect(url.searchParams.has('compare')).toBe(false);
  });
});

describe('downloadScenarioReport errors', () => {
  afterEach(() => vi.unstubAllGlobals());

  // Vitest runs in node here; fetchWithAuth only needs window to broadcast events.
  const stubFetch = (response: Response) => {
    vi.stubGlobal('window', { dispatchEvent: vi.fn() });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
  };

  it("surfaces the server's message on 501", async () => {
    const detail = "PowerPoint reports need the python-pptx package, which isn't installed.";
    stubFetch(new Response(JSON.stringify({ detail }), { status: 501 }));
    await expect(downloadScenarioReport('w', 's', { format: 'pptx' })).rejects.toMatchObject({
      status: 501,
      message: detail,
    });
  });

  it('falls back to a plain message when a 501 has no detail', async () => {
    stubFetch(new Response('', { status: 501 }));
    const error = await downloadScenarioReport('w', 's', { format: 'pdf' }).catch(e => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toMatch(/PDF reports.*renderer isn't installed/);
  });
});

describe('reportBasisNote', () => {
  const base = { cohort: 'all', costView: 'gross', grandfatherExisting: false } as const;

  it('says nothing when the view already matches the report basis', () => {
    expect(reportBasisNote(base)).toBeNull();
  });

  it.each([
    { cohort: 'new_hires' },
    { cohort: 'baseline' },
    { costView: 'net' },
    { grandfatherExisting: true },
  ] as const)('notes the difference when %o is set', override => {
    expect(reportBasisNote({ ...base, ...override })).toBe(REPORT_BASIS_NOTE);
  });
});
