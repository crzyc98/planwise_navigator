import React, { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { AlertCircle, Loader2 } from 'lucide-react';

import { CensusTieOut, CensusTieOutRow, getCensusTieOut, Scenario, updateScenario } from '../services/api';

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
  // The sign follows the shown figure, so a value that rounds to zero reads "+0".
  if (unit === 'rate') {
    const points = Math.abs(value * 100).toFixed(1);
    return `${value < 0 && Number(points) !== 0 ? '-' : '+'}${points} pts`;
  }
  const whole = Math.abs(Math.round(value));
  const sign = value < 0 && whole !== 0 ? '-' : '+';
  return `${sign}${unit === 'dollars' ? '$' : ''}${whole.toLocaleString('en-US')}`;
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
      <p className="text-sm text-ink-muted mb-4">{tieOut.source_note}</p>
      <TieOutTable tieOut={tieOut} />
    </>
  );
}

export interface TieOutState {
  tieOut: CensusTieOut | null;
  loading: boolean;
  failed: boolean;
}

const LOADING: TieOutState = { tieOut: null, loading: true, failed: false };
const FAILED: TieOutState = { tieOut: null, loading: false, failed: true };

/**
 * Load one scenario's tie-out. Every state is set whole, so a new load or a
 * failure never leaves the previous scenario's rows (or gap count) on screen.
 */
export async function loadTieOutState(
  fetchTieOut: () => Promise<CensusTieOut>,
  setState: (state: TieOutState) => void,
  isCancelled: () => boolean,
): Promise<void> {
  setState(LOADING);
  try {
    const tieOut = await fetchTieOut();
    if (!isCancelled()) setState({ tieOut, loading: false, failed: false });
  } catch {
    if (!isCancelled()) setState(FAILED);
  }
}

export type MarkStatus = 'idle' | 'saving' | 'failed';

/** Save the current-plan mark; `onSaved` gets the updated scenario. */
export async function saveCurrentPlanMark(
  save: (marked: boolean) => Promise<Scenario>,
  marked: boolean,
  setStatus: (status: MarkStatus) => void,
  onSaved: (scenario: Scenario) => void,
): Promise<void> {
  setStatus('saving');
  try {
    onSaved(await save(marked));
    setStatus('idle');
  } catch {
    setStatus('failed');
  }
}

export interface CurrentPlanMark {
  marked: boolean;
  status: MarkStatus;
  onToggle: () => void;
}

function MarkLine({ marked, status, onToggle }: Readonly<CurrentPlanMark>) {
  return (
    <p className="text-sm text-ink-muted mb-4">
      {marked
        ? 'Marked as the current plan. '
        : 'Not marked as the current plan. Gaps are expected if this scenario changes the plan design. '}
      <button
        type="button"
        className="text-brand-ink hover:underline disabled:opacity-50"
        disabled={status === 'saving'}
        onClick={onToggle}
      >
        {marked ? 'Unmark' : 'Mark as current plan'}
      </button>
      {status === 'failed' && <span className="ml-2">The mark couldn't be saved. Try again.</span>}
    </p>
  );
}

export function CensusTieOutView({ tieOut, loading, failed, mark }: Readonly<TieOutState & {
  mark: CurrentPlanMark;
}>) {
  // Only the current plan should tie out; elsewhere gaps are expected, so no count.
  const gaps = mark.marked && tieOut?.available
    ? tieOut.rows.filter(row => row.status === 'gap').length
    : 0;
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
      <MarkLine {...mark} />
      <Body tieOut={tieOut} loading={loading} failed={failed} />
    </section>
  );
}

export default function CensusTieOutPanel({ workspaceId, scenarioId, marked, onMarkSaved }: Readonly<{
  workspaceId: string;
  scenarioId: string;
  /** Whether the scenario is marked as modeling the current plan. */
  marked: boolean;
  onMarkSaved: (scenario: Scenario) => void;
}>) {
  const [state, setState] = useState<TieOutState>(LOADING);
  const [markStatus, setMarkStatus] = useState<MarkStatus>('idle');
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const focused = searchParams.get('focus') === CENSUS_TIE_OUT_ANCHOR;

  useEffect(() => {
    let cancelled = false;
    void loadTieOutState(() => getCensusTieOut(workspaceId, scenarioId), setState, () => cancelled);
    return () => { cancelled = true; };
  }, [workspaceId, scenarioId]);

  // Scroll once the panel has its final height, and again on each new link click.
  useEffect(() => {
    if (focused && !state.loading) {
      document.getElementById(CENSUS_TIE_OUT_ANCHOR)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [focused, state.loading, location.key]);

  useEffect(() => setMarkStatus('idle'), [scenarioId]);

  const mark: CurrentPlanMark = {
    marked,
    status: markStatus,
    onToggle: () => void saveCurrentPlanMark(
      value => updateScenario(workspaceId, scenarioId, { models_current_plan: value }),
      !marked,
      setMarkStatus,
      onMarkSaved,
    ),
  };
  return <CensusTieOutView {...state} mark={mark} />;
}
