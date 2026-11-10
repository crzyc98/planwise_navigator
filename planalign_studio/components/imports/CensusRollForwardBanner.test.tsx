import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { CensusRollForwardView } from './CensusRollForwardBanner';
import { CensusRollForwardJob, CensusStatus } from '../../services/api';

vi.mock('../../services/api', () => ({}));

const behind: CensusStatus = {
  census_year: 2024, start_year: 2026, behind: true, bridge_year: 2025, active_job: null,
};

const job = (overrides: Partial<CensusRollForwardJob>): CensusRollForwardJob => ({
  id: 'job', workspace_id: 'ws', bridge_year: 2025, status: 'queued',
  submitted_at: '2026-11-10T00:00:00Z', completed_at: null, summary: null, error_message: null,
  ...overrides,
});

const render = (props: Partial<React.ComponentProps<typeof CensusRollForwardView>>) =>
  renderToStaticMarkup(
    <CensusRollForwardView status={behind} job={null} error={null} onStart={() => undefined} {...props} />,
  );

describe('Census roll-forward banner', () => {
  it('offers a roll-forward when the census is two years behind', () => {
    const html = render({});
    expect(html).toContain('Your census is from 2024, but simulations start in 2026');
    expect(html).toContain('Roll forward to 2025');
  });

  it('names a multi-year gap', () => {
    const html = render({ status: { ...behind, census_year: 2022 } });
    expect(html).toContain('2023–2025 has no');
  });

  it('shows nothing for a current census', () => {
    expect(render({ status: { ...behind, behind: false, bridge_year: null } })).toBe('');
    expect(render({ status: null })).toBe('');
  });

  it('says when it is waiting behind a running simulation', () => {
    expect(render({ job: job({ status: 'queued' }) })).toContain('Waiting for a running simulation');
    expect(render({ job: job({ status: 'running' }) })).toContain('Simulating 2025');
  });

  it('summarizes a finished roll-forward', () => {
    const html = render({
      job: job({
        status: 'completed',
        summary: {
          census_year: 2024, bridge_year: 2025, hires: 1524, terminations: 1321,
          ending_headcount: 6967, simulated_employees: 1143, census_path: '/w/data/census_bridge_2025.parquet',
        },
      }),
    });
    expect(html).toContain('Census rolled forward to 2025 and now in use');
    expect(html).toContain('1,524 hires');
    expect(html).toContain('The 2024 census stays in Imported Files');
  });

  it('shows a failure and lets the analyst try again', () => {
    const html = render({ job: job({ status: 'failed', error_message: 'Census roll-forward failed (error_id: x)' }) });
    expect(html).toContain('Census roll-forward failed (error_id: x)');
    expect(html).toContain('Try again');
  });
});
