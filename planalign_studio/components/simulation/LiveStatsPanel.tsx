/**
 * Live event statistics for the active simulation run (feature 094, US1).
 *
 * Counts are exact at year boundaries: the orchestrator reports per-event-type
 * totals from fct_yearly_events as each simulation year completes.
 */

import React from 'react';
import {
  UserPlus,
  UserMinus,
  TrendingUp,
  DollarSign,
  ClipboardCheck,
  Sigma,
  CalendarRange,
} from 'lucide-react';
import { RunTelemetrySnapshot } from '../../services/api';

const TILES: Array<{
  key: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accent: string;
}> = [
  { key: 'HIRE', label: 'Hires', icon: UserPlus, accent: 'text-success-ink' },
  { key: 'TERMINATION', label: 'Terminations', icon: UserMinus, accent: 'text-danger-ink' },
  { key: 'PROMOTION', label: 'Promotions', icon: TrendingUp, accent: 'text-info-ink' },
  { key: 'RAISE', label: 'Raises', icon: DollarSign, accent: 'text-warning-ink' },
  { key: 'ENROLLMENT', label: 'Enrollments', icon: ClipboardCheck, accent: 'text-info-ink' },
];

interface LiveStatsPanelProps {
  snapshot: RunTelemetrySnapshot;
}

export default function LiveStatsPanel({ snapshot }: LiveStatsPanelProps) {
  const counts = snapshot.event_counts;
  const yearIndex =
    snapshot.start_year > 0
      ? Math.min(
          Math.max(snapshot.current_year - snapshot.start_year, 0) + 1,
          snapshot.total_years
        )
      : 0;

  return (
    <div>
      {/* Year progress header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center text-sm font-medium text-ink-muted">
          <CalendarRange size={16} className="mr-2 text-fidelity-green" />
          {yearIndex > 0 ? (
            <span>
              Simulating year <span className="font-bold">{snapshot.current_year}</span>
              {' '}({yearIndex} of {snapshot.total_years})
            </span>
          ) : (
            <span>Preparing simulation…</span>
          )}
        </div>
        <span className="text-xs text-ink-subtle">
          {counts.as_of_year !== null
            ? `Counts exact through ${counts.as_of_year}`
            : 'Counts appear as each year completes'}
        </span>
      </div>

      {/* Per-year segments */}
      {snapshot.total_years > 1 && (
        <div className="flex gap-1 mb-4">
          {Array.from({ length: snapshot.total_years }, (_, idx) => {
            const year = snapshot.start_year + idx;
            const isDone =
              counts.as_of_year !== null && year <= counts.as_of_year;
            const isCurrent = !isDone && year === snapshot.current_year;
            return (
              <div key={year} className="flex-1">
                <div
                  className={`h-2 rounded-full ${
                    isDone
                      ? 'bg-fidelity-green'
                      : isCurrent
                        ? 'bg-fidelity-light animate-pulse'
                        : 'bg-surface-disabled'
                  }`}
                />
                <p className="text-[10px] text-center text-ink-subtle mt-0.5">{year}</p>
              </div>
            );
          })}
        </div>
      )}

      {/* Event count tiles */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {TILES.map(({ key, label, icon: Icon, accent }) => (
          <div key={key} className="p-3 bg-surface-subtle rounded-lg border border-border">
            <div className="flex items-center mb-1">
              <Icon size={16} className={`mr-2 ${accent}`} />
              <p className="text-xs text-ink-muted">{label}</p>
            </div>
            <p className="text-lg font-bold text-ink">
              {(counts.by_type[key] ?? 0).toLocaleString()}
            </p>
          </div>
        ))}
        <div className="p-3 bg-fidelity-green/5 rounded-lg border border-fidelity-green/20">
          <div className="flex items-center mb-1">
            <Sigma size={16} className="mr-2 text-fidelity-green" />
            <p className="text-xs text-ink-muted">Total Events</p>
          </div>
          <p className="text-lg font-bold text-fidelity-dark">
            {counts.total.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}
