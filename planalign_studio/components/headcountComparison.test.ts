import { describe, expect, it } from 'vitest';
import { buildHeadcountComparison } from './headcountComparison';

function scenario(name: string, rows: Array<[number, number]>) {
  return {
    scenario: { id: name, name },
    results: { workforce_progression: rows.map(([simulation_year, headcount]) => ({ simulation_year, headcount })) },
  };
}

describe('headcount comparison year coverage', () => {
  it('sorts equal horizons and preserves observed zero headcount', () => {
    expect(buildHeadcountComparison([
      scenario('A', [[2026, 0], [2025, 100]]),
      scenario('B', [[2025, 200], [2026, 210]]),
    ])).toEqual({
      workforce: [{ year: 2025, A: 100, B: 200 }, { year: 2026, A: 0, B: 210 }],
      hasMissingYears: false,
      commonYearCount: 2,
    });
  });

  it('marks missing interior observations as null', () => {
    const comparison = buildHeadcountComparison([
      scenario('A', [[2025, 100], [2027, 110]]),
      scenario('B', [[2025, 200], [2026, 210], [2027, 220]]),
    ]);
    expect(comparison.workforce[1]).toEqual({ year: 2026, A: null, B: 210 });
    expect(comparison.hasMissingYears).toBe(true);
    expect(comparison.commonYearCount).toBe(2);
  });

  it('includes interior gaps shared by every scenario', () => {
    const comparison = buildHeadcountComparison([scenario('A', [[2025, 100], [2027, 110]])]);
    expect(comparison.workforce[1]).toEqual({ year: 2026, A: null });
    expect(comparison.hasMissingYears).toBe(true);
  });

  it('handles partially overlapping horizons', () => {
    expect(buildHeadcountComparison([
      scenario('A', [[2025, 100], [2026, 110]]),
      scenario('B', [[2026, 200], [2027, 210]]),
    ])).toEqual({
      workforce: [{ year: 2025, A: 100, B: null }, { year: 2026, A: 110, B: 200 }, { year: 2027, A: null, B: 210 }],
      hasMissingYears: true,
      commonYearCount: 1,
    });
  });

  it('handles disjoint horizons without inventing zero observations', () => {
    expect(buildHeadcountComparison([
      scenario('A', [[2025, 100]]), scenario('B', [[2027, 200]]),
    ])).toEqual({
      workforce: [{ year: 2025, A: 100, B: null }, { year: 2026, A: null, B: null }, { year: 2027, A: null, B: 200 }],
      hasMissingYears: true,
      commonYearCount: 0,
    });
  });

  it('handles empty results', () => {
    expect(buildHeadcountComparison([])).toEqual({ workforce: [], hasMissingYears: false, commonYearCount: 0 });
    const comparison = buildHeadcountComparison([scenario('A', []), scenario('B', [[2025, 0]])]);
    expect(comparison.workforce).toEqual([{ year: 2025, A: null, B: 0 }]);
    expect(comparison.commonYearCount).toBe(0);
    expect(comparison.hasMissingYears).toBe(true);
  });
});
