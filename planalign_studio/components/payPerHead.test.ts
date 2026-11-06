import { describe, expect, it } from 'vitest';
import { buildPayPerHeadYears, meanGrowthPct } from './payPerHead';

const status = (simulation_year: number, employment_status: string, employee_count: number) => ({
  simulation_year, employment_status, employee_count,
});

describe('total pay per year-end head', () => {
  const progression = [
    { simulation_year: 2026, total_compensation: 1_155_000 },
    { simulation_year: 2025, total_compensation: 1_000_000 },
  ];
  const byStatus = [
    status(2025, 'continuous_active', 8),
    status(2025, 'new_hire_active', 2),
    status(2025, 'experienced_termination', 3),
    status(2026, 'continuous_active', 11),
    status(2026, 'new_hire_termination', 1),
  ];

  it('divides everyone\'s pay by active heads only, oldest year first', () => {
    const years = buildPayPerHeadYears(progression, byStatus);
    expect(years.map(year => [year.year, year.yearEndHeadcount, year.payPerHead])).toEqual([
      [2025, 10, 100_000],
      [2026, 11, 105_000],
    ]);
  });

  it('measures growth from the prior year and averages it', () => {
    const years = buildPayPerHeadYears(progression, byStatus);
    expect(years[0].growthPct).toBeNull();
    expect(years[1].growthPct).toBeCloseTo(5);
    expect(meanGrowthPct(years)).toBeCloseTo(5);
  });

  it('skips years with no active employees', () => {
    expect(buildPayPerHeadYears(progression, [status(2025, 'experienced_termination', 3)])).toEqual([]);
    expect(meanGrowthPct([])).toBeNull();
  });
});
