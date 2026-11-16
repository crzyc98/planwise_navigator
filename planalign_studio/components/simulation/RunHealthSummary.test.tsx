import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CensusTieOutLine } from './RunHealthSummary';
import { RunHealthReport } from '../../services/api';

vi.mock('../../services/api', () => ({}));

const report: RunHealthReport = {
  status: 'clean', scenario_id: 's', run_id: 'run', disposition: null,
  counts: { passed: 3, warning: 0, failed: 0, total: 3 }, findings: [], census_tie_out: null,
};

const render = (value: RunHealthReport) => renderToStaticMarkup(
  <MemoryRouter initialEntries={['/w/ws/analytics']}>
    <Routes>
      <Route path="/w/:workspaceId/*" element={<CensusTieOutLine scenarioId="s" report={value} />} />
    </Routes>
  </MemoryRouter>,
);

describe('Run health census tie-out line', () => {
  it('shows one line linking to the Overview tie-out panel when rows differ', () => {
    const message = '2 census tie-out rows differ from the census: Participation, Employer match';
    const html = render({ ...report, census_tie_out: { labels: ['Participation', 'Employer match'], message } });
    expect(html.match(/data-run-health-tie-out/g)).toHaveLength(1);
    expect(html).toContain(message);
    expect(html).toContain('href="/w/ws/analytics?scenario=s&amp;focus=census-tie-out"');
    expect(html).not.toContain('danger');
  });

  it('shows nothing when the tie-out has no gap', () => {
    expect(render(report)).toBe('');
  });
});
