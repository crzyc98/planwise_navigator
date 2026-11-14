import React, { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { AlertCircle, Loader2 } from 'lucide-react';

import { CensusTieOut, CensusTieOutRow, getCensusTieOut } from '../services/api';

/** Element id of the panel; `?focus=census-tie-out` on Overview scrolls to it. */
export const CENSUS_TIE_OUT_ANCHOR = 'census-tie-out';

/** Overview link that opens a scenario and scrolls to its tie-out panel. */
export const censusTieOutPath = (scenarioId: string): string =>
  `/analytics?scenario=${encodeURIComponent(scenarioId)}&focus=${CENSUS_TIE_OUT_ANCHOR}`;

type Unit = CensusTieOutRow['unit'];

/** Same rules as the scenario report, so the two read identically. */
export function formatTieOutValue(unit: Unit, value: number | null): string {
  if (value === null) return '—';
  if (unit === 'rate') return `${(value * 100).toFixed(1)}%`;
  const whole = Math.round(value).toLocaleString('en-US');
  return unit === 'dollars' ? `$${whole}` : whole;
}

export function formatTieOutDifference(unit: Unit, value: number | null): string {
  if (value === null) return '—';
  const sign = value < 0 ? '-' : '+';
  if (unit === 'rate') return `${sign}${Math.abs(value * 100).toFixed(1)} pts`;
  const whole = Math.abs(Math.round(value)).toLocaleString('en-US');
  return `${sign}${unit === 'dollars' ? '$' : ''}${whole}`;
}

const STATUS_TEXT: Record<CensusTieOutRow['status'], string> = {
  ties: 'Ties',
  gap: 'Gap',
  not_in_census: 'Not in census',
};

function StatusCell({ status }: Readonly<{ status: CensusTieOutRow['status'] }>) {
  if (status === 'gap') {
    return (
      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-warning-surface text-warning-ink">
        {STATUS_TEXT.gap}
      </span>
    );
  }
  return <span className="text-sm text-ink-muted">{STATUS_TEXT[status]}</span>;
}

function TieOutTable({ tieOut }: Readonly<{ tieOut: CensusTieOut }>) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-border">
        <thead>
          <tr>
            <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Metric</th>
            <th className="px-4 py-2 text-right text-xs font-medium text-ink-muted uppercase">Census {tieOut.census_year}</th>
            <th className="px-4 py-2 text-right text-xs font-medium text-ink-muted uppercase">Simulated {tieOut.first_simulated_year}</th>
            <th className="px-4 py-2 text-right text-xs font-medium text-ink-muted uppercase">Difference</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {tieOut.rows.map(row => (
            <tr key={row.metric} data-tie-out-status={row.status} title={row.definition}>
              <td className="px-4 py-2 text-sm text-ink">
                {row.label}
                {row.status === 'gap' && (
                  <p className="mt-0.5 text-xs text-ink-muted max-w-xl">{row.message}</p>
                )}
              </td>
              <td className="px-4 py-2 text-sm text-ink text-right align-top whitespace-nowrap">
                {formatTieOutValue(row.unit, row.census_value)}
              </td>
              <td className="px-4 py-2 text-sm text-ink text-right align-top whitespace-nowrap">
                {formatTieOutValue(row.unit, row.simulated_value)}
              </td>
              <td className="px-4 py-2 text-sm text-ink-muted text-right align-top whitespace-nowrap">
                {formatTieOutDifference(row.unit, row.difference)}
              </td>
              <td className="px-4 py-2 align-top whitespace-nowrap">
                <StatusCell status={row.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Source({ tieOut }: Readonly<{ tieOut: CensusTieOut }>) {
  const file = tieOut.census_file ?? 'the archived census';
  return (
    <p className="text-sm text-ink-muted mb-4">
      Compares {file} (census year {tieOut.census_year}) with {tieOut.first_simulated_year}, the first
      simulated year, allowing for one year of the configured growth and raises. Meaningful only for a
      scenario that models the current plan.
    </p>
  );
}

function Notice({ icon, children }: Readonly<{ icon: React.ReactNode; children: React.ReactNode }>) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted">
      {icon}
      {children}
    </div>
  );
}

function Body({ tieOut, loading, failed }: Readonly<{
  tieOut: CensusTieOut | null;
  loading: boolean;
  failed: boolean;
}>) {
  if (loading) {
    return <Notice icon={<Loader2 size={15} className="animate-spin" />}>Loading census tie-out...</Notice>;
  }
  if (failed || !tieOut) {
    return <Notice icon={<AlertCircle size={15} />}>Census tie-out is not available right now.</Notice>;
  }
  if (!tieOut.available) {
    return <p className="text-sm text-ink-muted">{tieOut.unavailable_reason}</p>;
  }
  return (
    <>
      <Source tieOut={tieOut} />
      <TieOutTable tieOut={tieOut} />
    </>
  );
}

export function CensusTieOutView({ tieOut, loading, failed }: Readonly<{
  tieOut: CensusTieOut | null;
  loading: boolean;
  failed: boolean;
}>) {
  const gaps = tieOut?.available ? tieOut.rows.filter(row => row.status === 'gap').length : 0;
  return (
    <section
      id={CENSUS_TIE_OUT_ANCHOR}
      className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border scroll-mt-6"
    >
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold text-ink">Census Tie-out</h3>
        {gaps > 0 && (
          <span className="inline-flex px-2.5 py-0.5 rounded-full border text-xs font-medium border-warning-border bg-warning-surface text-warning-ink">
            {gaps} {gaps === 1 ? 'gap' : 'gaps'}
          </span>
        )}
      </div>
      <Body tieOut={tieOut} loading={loading} failed={failed} />
    </section>
  );
}

export default function CensusTieOutPanel({ workspaceId, scenarioId }: Readonly<{
  workspaceId: string;
  scenarioId: string;
}>) {
  const [tieOut, setTieOut] = useState<CensusTieOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const focused = searchParams.get('focus') === CENSUS_TIE_OUT_ANCHOR;

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      try {
        setLoading(true);
        setFailed(false);
        const response = await getCensusTieOut(workspaceId, scenarioId);
        if (!cancelled) setTieOut(response);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [workspaceId, scenarioId]);

  // Scroll once the panel has its final height, and again on each new link click.
  useEffect(() => {
    if (focused && !loading) {
      document.getElementById(CENSUS_TIE_OUT_ANCHOR)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [focused, loading, location.key]);

  return <CensusTieOutView tieOut={tieOut} loading={loading} failed={failed} />;
}
