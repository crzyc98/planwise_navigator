import { Link } from 'react-router-dom';
import { Scale } from 'lucide-react';
import type { MinimumWageYear } from '../services/api';
import { formatHourlyRate, formatStepDate } from './config/minimumWage';

const count = (value: number | null | undefined) => (value == null ? '—' : value.toLocaleString('en-US'));
const dollars = (value: number | null | undefined) => (value == null ? '—' : `$${Math.round(value).toLocaleString('en-US')}`);

const TH = 'px-4 py-2 text-right text-xs font-medium text-ink-muted uppercase';
const TD = 'px-4 py-2 text-sm text-ink text-right whitespace-nowrap';

interface Props {
  rows: MinimumWageYear[] | undefined;
  /** Workspace-scoped path of the scenario comparison page. */
  comparePath: string;
}

/** A run's minimum wage by year (#1231); renders nothing for a run without one. */
export default function MinimumWagePanel({ rows, comparePath }: Readonly<Props>) {
  if (!rows || rows.length === 0) return null;
  return (
    <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border" aria-label="Minimum wage by year">
      <div className="flex items-center mb-4">
        <Scale size={20} className="text-brand-ink mr-2" />
        <h3 className="text-lg font-semibold text-ink">Minimum wage</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-border">
          <thead>
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Year</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">New minimum</th>
              <th className={TH}>People raised</th>
              <th className={TH}>Added annual pay</th>
              <th className={TH}>Census staff with no rate</th>
              <th className={TH}>Hires not covered</th>
              <th className={TH}>Raised, still active</th>
              <th className={TH}>Added pay at year end (est.)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map(row => (
              <tr key={row.simulation_year}>
                <td className="px-4 py-2 text-sm text-ink">{row.simulation_year}</td>
                <td className="px-4 py-2 text-sm text-ink whitespace-nowrap">
                  {row.minimum_hourly_rate == null || !row.effective_date
                    ? '—'
                    : `${formatHourlyRate(row.minimum_hourly_rate)} from ${formatStepDate(row.effective_date)}`}
                </td>
                <td className={TD}>{count(row.people_raised)}</td>
                <td className={TD}>{dollars(row.added_annual_pay)}</td>
                <td className={TD}>{count(row.people_without_rate)}</td>
                <td className={TD}>{count(row.people_not_covered)}</td>
                <td className={TD}>{count(row.raised_still_active)}</td>
                <td className={TD}>{dollars(row.estimated_added_pay)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 space-y-1 text-xs text-ink-muted">
        <p>
          People raised and added annual pay are counted on each step's date. Census staff with no hourly rate are never raised,
          and simulated hires and acquired members have no rate, so they aren't covered.
        </p>
        <p>
          Added pay at year end is an estimate: for everyone a step raised who is still active, their year-end pay times the share of it the
          minimum wage added. It fades as those people leave.
        </p>
        <p>
          Added employer contributions can't be separated within one run. To see them by year, open{' '}
          <Link to={comparePath} className="text-brand-ink hover:underline">Cost Comparison</Link> and compare this scenario with the same
          scenario without the minimum wage.
        </p>
      </div>
    </div>
  );
}
