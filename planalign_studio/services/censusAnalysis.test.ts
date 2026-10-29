import { afterEach, expect, it, vi } from 'vitest';
import { analyzeCensus } from './api';

afterEach(() => vi.unstubAllGlobals());

it.each(['all', 'active', 'terminated'] as const)(
  'sends the %s population selection to the census API',
  async employeeStatus => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);

    await analyzeCensus('workspace', {
      file_path: 'census.csv',
      as_of_date: '2024-12-31',
      employee_status: employeeStatus,
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/workspaces/workspace/analyze-census');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({
      file_path: 'census.csv',
      as_of_date: '2024-12-31',
      employee_status: employeeStatus,
    });
  },
);
