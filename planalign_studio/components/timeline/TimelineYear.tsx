import React from 'react';
import { TimelineYearData } from '../../services/api';

const money = (value: number | null) => value == null ? '—' : value.toLocaleString(undefined, { style: 'currency', currency: 'USD' });
const percent = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`;

export default function TimelineYear({ year }: Readonly<{ year: TimelineYearData }>) {
  const state = year.state;
  return (
    <section className="grid gap-4 rounded-xl border border-gray-200 bg-white p-4 lg:grid-cols-[minmax(0,2fr)_minmax(240px,1fr)]">
      <div>
        <h3 className="mb-3 text-lg font-semibold text-gray-900">{year.simulation_year}</h3>
        {year.events.length === 0 ? (
          <p className="rounded-lg bg-gray-50 p-3 text-sm text-gray-500">No events this year</p>
        ) : (
          <ol className="relative ml-2 space-y-4 border-l-2 border-fidelity-green/30 pl-5">
            {year.events.map((event) => (
              <li key={`${event.source}-${event.event_id}`}>
                <span className="absolute -left-1.5 mt-1.5 h-2.5 w-2.5 rounded-full bg-fidelity-green" />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-semibold text-fidelity-green">{event.event_type.replaceAll('_', ' ')}</span>
                  <time className="text-xs text-gray-500">{event.effective_date}</time>
                </div>
                {event.event_details && (
                  <p className="mt-1 break-all text-sm text-gray-700">{event.event_details}</p>
                )}
                <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-gray-500">
                  {event.compensation_amount != null && <span>Amount {money(event.compensation_amount)}</span>}
                  {event.previous_compensation != null && <span>Previous {money(event.previous_compensation)}</span>}
                  {event.deferral_rate != null && <span>Deferral {percent(event.deferral_rate)}</span>}
                  {event.prev_deferral_rate != null && <span>Previous deferral {percent(event.prev_deferral_rate)}</span>}
                  {event.level_id != null && <span>Level {event.level_id}</span>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
      <aside className="rounded-lg bg-slate-50 p-3 text-sm">
        <h4 className="mb-2 font-semibold text-gray-800">Year-end state</h4>
        {!state ? <p className="text-gray-500">No snapshot for this year</p> : (
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt>Status</dt><dd>{state.employment_status ?? '—'}</dd>
            <dt>Compensation</dt><dd>{money(state.current_compensation)}</dd>
            <dt>Level</dt><dd>{state.level_id ?? '—'}</dd>
            <dt>Age / tenure</dt><dd>{state.current_age ?? '—'} / {state.current_tenure ?? '—'}</dd>
            <dt>Eligibility</dt><dd>{state.eligibility_status ?? '—'}</dd>
            <dt>Enrolled</dt><dd>{state.is_enrolled == null ? '—' : state.is_enrolled ? 'Yes' : 'No'}</dd>
            <dt>Deferral</dt><dd>{percent(state.current_deferral_rate)}</dd>
            <dt>Escalations</dt><dd>{state.total_deferral_escalations ?? '—'}</dd>
            <dt>Employee</dt><dd>{money(state.ytd_contributions)}</dd>
            <dt>Match</dt><dd>{money(state.employer_match_amount)}</dd>
            <dt>Core</dt><dd>{money(state.employer_core_amount)}</dd>
            <dt>IRS limit</dt><dd>{state.irs_limit_reached == null ? '—' : state.irs_limit_reached ? 'Reached' : 'Not reached'}</dd>
          </dl>
        )}
      </aside>
    </section>
  );
}
