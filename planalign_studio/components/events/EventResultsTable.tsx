import React from 'react';
import { Link } from 'react-router-dom';

import { EventRecord, timelineUrl } from '../../services/api';

interface Props {
  workspaceId: string;
  scenarioId: string;
  events: EventRecord[];
  onSelect: (event: EventRecord) => void;
}

function formatCurrency(value: number | null): string {
  return value === null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

export default function EventResultsTable({ workspaceId, scenarioId, events, onSelect }: Readonly<Props>) {
  if (!events.length) return <p className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-ink-muted">No events match these filters.</p>;

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface-raised">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border bg-surface-subtle text-ink-muted"><tr><th className="px-4 py-3">Effective date</th><th className="px-4 py-3">Type</th><th className="px-4 py-3">Category</th><th className="px-4 py-3">Employee</th><th className="px-4 py-3">Year</th><th className="px-4 py-3">Compensation</th><th className="px-4 py-3"><span className="sr-only">Details</span></th></tr></thead>
        <tbody>{events.map((event) => <tr key={event.event_id} className="border-b border-border last:border-0 hover:bg-surface-subtle"><td className="px-4 py-3">{new Date(event.effective_date).toLocaleDateString()}</td><td className="px-4 py-3">{event.event_type}</td><td className="px-4 py-3">{event.event_category ?? '—'}</td><td className="px-4 py-3"><Link className="font-medium text-fidelity-green hover:underline" to={timelineUrl(workspaceId, scenarioId, event.employee_id)}>{event.employee_id}</Link></td><td className="px-4 py-3">{event.simulation_year}</td><td className="px-4 py-3">{formatCurrency(event.compensation_amount)}</td><td className="px-4 py-3"><button className="rounded border border-border px-2 py-1 text-xs font-medium text-ink hover:bg-surface" onClick={() => onSelect(event)}>Details</button></td></tr>)}</tbody>
      </table>
    </div>
  );
}
