export interface PayPerHeadYear {
  year: number;
  totalPay: number;
  yearEndHeadcount: number;
  payPerHead: number;
  growthPct: number | null;
}

interface ProgressionRow {
  simulation_year: number;
  total_compensation: number;
}

interface StatusRow {
  simulation_year: number;
  employment_status: string;
  employee_count: number;
}

/**
 * The calibration metric: total pay for the year, including leavers, over
 * active headcount at year end. Needs the unfiltered "all" population.
 */
export function buildPayPerHeadYears(progression: ProgressionRow[], byStatus: StatusRow[]): PayPerHeadYear[] {
  const years: PayPerHeadYear[] = [];
  for (const row of [...progression].sort((a, b) => a.simulation_year - b.simulation_year)) {
    const yearEndHeadcount = byStatus
      .filter(status => status.simulation_year === row.simulation_year
        && (status.employment_status || '').includes('active'))
      .reduce((sum, status) => sum + (status.employee_count || 0), 0);
    if (yearEndHeadcount === 0) continue;
    const payPerHead = row.total_compensation / yearEndHeadcount;
    const prior = years[years.length - 1];
    years.push({
      year: row.simulation_year,
      totalPay: row.total_compensation,
      yearEndHeadcount,
      payPerHead,
      growthPct: prior ? (payPerHead / prior.payPerHead - 1) * 100 : null,
    });
  }
  return years;
}

/** Average of the annual growth rates, as calibration reports its horizon mean. */
export function meanGrowthPct(years: PayPerHeadYear[]): number | null {
  const growth = years.flatMap(year => (year.growthPct === null ? [] : [year.growthPct]));
  return growth.length ? growth.reduce((sum, value) => sum + value, 0) / growth.length : null;
}
