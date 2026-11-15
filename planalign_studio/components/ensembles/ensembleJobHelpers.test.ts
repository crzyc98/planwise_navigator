import { describe, expect, it } from 'vitest';

import type { EnsembleEstimate, EnsembleJob } from '../../services/api';
import {
  RANGE_DISCLAIMER,
  estimateSummary,
  formatDisk,
  formatDuration,
  parseSeedCount,
  progressLabel,
  startMismatch,
  statusCopy,
  timeBasisLabel,
  yearRange,
} from './ensembleJobHelpers';

const estimate: EnsembleEstimate = {
  seed_count: 10,
  seeds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
  start_year: 2026,
  end_year: 2030,
  run_count: 10,
  seconds_per_run: 150,
  estimated_seconds: 1500,
  time_basis: 'measured',
  estimated_disk_mib: 2048,
};

function job(overrides: Partial<EnsembleJob>): EnsembleJob {
  return {
    job_id: 'j1',
    workspace_id: 'w1',
    scenario_id: 's1',
    scenario_name: 'Baseline',
    status: 'running',
    seed_count: 10,
    seeds: estimate.seeds,
    start_year: 2026,
    end_year: 2030,
    estimate,
    created_at: '2026-11-15T00:00:00Z',
    started_at: null,
    completed_at: null,
    progress: { seeds_total: 10, seeds_completed: 0, seeds_failed: 0, current_seed: null, updated_at: null },
    failed_seeds: [],
    error: null,
    output: null,
    ...overrides,
  };
}

describe('seed count', () => {
  it('accepts whole numbers the API allows and rejects the rest', () => {
    expect(parseSeedCount('10')).toBe(10);
    expect(parseSeedCount(' 5 ')).toBe(5);
    expect(parseSeedCount('50')).toBe(50);
    expect(parseSeedCount('4')).toBeNull();
    expect(parseSeedCount('51')).toBeNull();
    expect(parseSeedCount('7.5')).toBeNull();
    expect(parseSeedCount('')).toBeNull();
  });
});

describe('estimate formatting', () => {
  it('rounds time to minutes and hours', () => {
    expect(formatDuration(20)).toBe('under 1 min');
    expect(formatDuration(1500)).toBe('about 25 min');
    expect(formatDuration(3600)).toBe('about 1 h');
    expect(formatDuration(7800)).toBe('about 2 h 10 min');
  });

  it('shows disk in MB, then GB', () => {
    expect(formatDisk(0.2)).toBe('1 MB');
    expect(formatDisk(512.4)).toBe('512 MB');
    expect(formatDisk(2048)).toBe('2.0 GB');
  });

  it('says whether the time was measured', () => {
    expect(timeBasisLabel('measured')).toBe("Based on this scenario's last run.");
    expect(timeBasisLabel('default')).toBe("Rough estimate; this scenario hasn't run yet.");
  });

  it('summarizes runs, years, time and disk', () => {
    expect(estimateSummary(estimate)).toBe('10 runs of 2026–2030, about 25 min, up to 2.0 GB of disk while it runs.');
  });
});

describe('year range', () => {
  it('collapses a one-year ensemble to a single year', () => {
    expect(yearRange(2026, 2030)).toBe('2026–2030');
    expect(yearRange(2026, 2026)).toBe('2026');
  });

  it('formats one-year estimates the same way', () => {
    expect(estimateSummary({ ...estimate, end_year: 2026, run_count: 1 })).toBe(
      '1 run of 2026, about 25 min, up to 2.0 GB of disk while it runs.'
    );
  });
});

describe('start mismatch', () => {
  it('says nothing when the job matches what was reviewed', () => {
    expect(startMismatch(estimate, job({}))).toBeNull();
  });

  it('names the new years when the scenario changed', () => {
    expect(startMismatch(estimate, job({ end_year: 2031 }))).toBe(
      'Started with 2026–2031 instead of the reviewed 2026–2030 because the scenario changed.'
    );
  });

  it('flags different seeds when the years match', () => {
    expect(startMismatch(estimate, job({ seeds: estimate.seeds.map((seed) => seed + 100) }))).toBe(
      'Started with different seeds than the reviewed estimate because the scenario changed.'
    );
  });
});

describe('job status copy', () => {
  it('says a queued job is waiting for another simulation', () => {
    const queued = job({ status: 'queued' });
    expect(statusCopy(queued)).toMatchObject({ label: 'Queued', tone: 'info' });
    expect(progressLabel(queued)).toBe('Waiting for another simulation to finish');
  });

  it('counts seeds done and failed and names the current seed', () => {
    const running = job({
      progress: { seeds_total: 10, seeds_completed: 3, seeds_failed: 1, current_seed: 42, updated_at: null },
    });
    expect(progressLabel(running)).toBe('3 of 10 seeds done, 1 failed · running seed 42');
  });

  it('explains a partial result', () => {
    const partial = job({ status: 'partial', failed_seeds: [3, 7] });
    expect(statusCopy(partial)).toEqual({
      label: 'Partial',
      tone: 'warning',
      detail: '2 of 10 seeds failed; the results use the 8 that finished.',
    });
  });

  it('labels a restart as interrupted and keeps the server explanation', () => {
    const message = 'Studio restarted while this ensemble was queued. Start it again to get a result.';
    expect(statusCopy(job({ status: 'failed', error: { kind: 'interrupted', message } }))).toEqual({
      label: 'Interrupted',
      tone: 'danger',
      detail: message,
    });
  });

  it('reads failed and cancelled outcomes plainly', () => {
    const failed = statusCopy(job({ status: 'failed', error: { kind: 'no_seeds', message: 'Every seed failed.' } }));
    expect(failed).toEqual({ label: 'Failed', tone: 'danger', detail: 'Every seed failed.' });
    expect(statusCopy(job({ status: 'cancelled' }))).toMatchObject({ label: 'Cancelled', tone: 'neutral' });
    expect(statusCopy(job({ status: 'completed' }))).toEqual({ label: 'Completed', tone: 'success', detail: null });
  });
});

describe('range disclaimer', () => {
  it('names the seeded draws, excludes enrollment, and never says confidence interval', () => {
    expect(RANGE_DISCLAIMER).toMatch(/hiring, termination and promotion/);
    expect(RANGE_DISCLAIMER).toMatch(/Enrollment draws don't change with the seed/);
    expect(RANGE_DISCLAIMER.toLowerCase()).not.toContain('confidence');
  });
});
