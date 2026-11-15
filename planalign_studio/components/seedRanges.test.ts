import { describe, expect, it } from 'vitest';
import type { ScenarioCostRange } from '../services/api';
import {
  buildSeedRangeView,
  describeDifference,
  formatCostBand,
  formatDifference,
  seedRangeHiddenReason,
  SEED_RANGE_FOOTNOTE,
} from './seedRanges';

function range(id: string, overrides: Partial<ScenarioCostRange> = {}): ScenarioCostRange {
  return {
    scenario_id: id,
    job_id: `ens_${id}`,
    completed_at: null,
    start_year: 2026,
    end_year: 2027,
    years: [
      { year: 2026, p10: 900_000, p90: 1_100_000, n_seeds: 10 },
      { year: 2027, p10: 950_000, p90: 1_150_000, n_seeds: 10 },
    ],
    total: { p10: 1_850_000, p90: 2_250_000, n_seeds: 10 },
    paired: false,
    difference_years: [],
    difference_total: null,
    reason: null,
    ...overrides,
  };
}

const paired = range('p', {
  paired: true,
  difference_total: { min: -80_000, max: -40_000, p10: -75_000, p90: -45_000, n_seeds: 10 },
});
const years = new Map([['a', [2026, 2027]], ['p', [2026, 2027]], ['b', [2026, 2027]]]);

describe('buildSeedRangeView', () => {
  it('keeps bands and the paired difference when years match', () => {
    const view = buildSeedRangeView([range('a'), paired], years, 'a');

    expect(view.notes).toEqual([]);
    expect(view.rows.get('a')?.difference).toBeNull();
    expect(view.rows.get('p')?.difference).toMatchObject({ min: -80_000, max: -40_000 });
    expect(view.rows.get('p')?.years.get(2027)).toMatchObject({ p10: 950_000 });
  });

  it('leaves scenarios without an ensemble untouched and silent', () => {
    const bare = range('b', { job_id: null, years: [], total: null, reason: 'No finished ensemble for this scenario.' });
    const view = buildSeedRangeView([range('a'), paired, bare], years, 'a');

    expect(view.rows.has('b')).toBe(false);
    expect(view.notes).toEqual([]);
  });

  it('says why an unpaired ensemble has no difference, but keeps its band', () => {
    const reason = "Its ensemble used different seeds from the anchor's, so they aren't paired.";
    const view = buildSeedRangeView([range('a'), range('p', { reason })], years, 'a');

    expect(view.notes).toEqual([{ scenarioId: 'p', reason }]);
    expect(view.rows.get('p')?.total).not.toBeNull();
    expect(view.rows.get('p')?.difference).toBeNull();
  });

  it('drops ranges whose ensemble covers other years than the results shown', () => {
    const view = buildSeedRangeView(
      [range('a', { end_year: 2028 }), paired],
      years,
      'a',
    );

    expect(view.rows.has('a')).toBe(false);
    expect(view.notes[0]).toMatchObject({ scenarioId: 'a' });
    expect(view.rows.get('p')?.difference).toBeNull();
    expect(view.notes[1].reason).toMatch(/anchor's ensemble doesn't cover/);
  });
});

describe('formatting', () => {
  it('formats a band and a one-sided saving', () => {
    expect(formatCostBand({ p10: 1_850_000, p90: 2_250_000, n_seeds: 10 })).toBe('$1.85M–$2.25M');
    expect(formatDifference({ min: -80_000, max: -40_000, n_seeds: 10 })).toBe('saves $40.0K–$80.0K');
    expect(formatDifference({ min: 1_000, max: 3_000, n_seeds: 10 })).toBe('adds $1.0K–$3.0K');
    expect(formatDifference({ min: -10_000, max: 30_000, n_seeds: 10 })).toBe('−$10.0K to +$30.0K');
  });

  it('describes the paired range in a sentence, never as a confidence interval', () => {
    const text = describeDifference(-60_000, { min: -80_000, max: -40_000, n_seeds: 10 });

    expect(text).toBe('Costs $60.0K less than the anchor; across 10 seeds the saving ranges from $40.0K to $80.0K.');
    expect(`${text} ${SEED_RANGE_FOOTNOTE}`).not.toMatch(/confidence/i);
    expect(SEED_RANGE_FOOTNOTE).toMatch(/not enrollment/);
  });

  it('hides ranges beside numbers the ensemble does not measure', () => {
    expect(seedRangeHiddenReason('all', false)).toBeNull();
    expect(seedRangeHiddenReason('all', true)).toMatch(/grandfathering/);
    expect(seedRangeHiddenReason('new_hires', false)).toMatch(/cohort/);
  });
});
