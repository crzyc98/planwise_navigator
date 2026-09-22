import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';

import { EventRecord, timelineUrl } from '../../services/api';

type EventFieldKey = keyof EventRecord;

export function formatEventField(key: EventFieldKey, value: EventRecord[EventFieldKey] | undefined): string {
  if (value === null || value === undefined) return '—';
  if (key === 'compensation_amount' || key === 'previous_compensation') {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value));
  }
  if (key === 'effective_date' || key === 'created_at') {
    const date = new Date(String(value));
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }
  return String(value);
}

interface FieldProps {
  event: EventRecord;
  field: EventFieldKey;
  label: string;
}

function Field({ event, field, label }: Readonly<FieldProps>) {
  return <div><dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</dt><dd className="mt-1 break-words text-sm text-ink">{formatEventField(field, event[field])}</dd></div>;
}

interface Props {
  workspaceId: string;
  scenarioId: string;
  event: EventRecord;
  onClose: () => void;
}

export default function EventDetailDrawer({ workspaceId, scenarioId, event, onClose }: Readonly<Props>) {
  useEffect(() => {
    const handleKeyDown = (keyboardEvent: KeyboardEvent) => {
      if (keyboardEvent.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/40" role="presentation" onMouseDown={onClose}>
      <aside className="ml-auto h-full w-full max-w-xl overflow-y-auto bg-surface p-6 shadow-xl" role="dialog" aria-modal="true" aria-label="Event details" onMouseDown={(mouseEvent) => mouseEvent.stopPropagation()}>
        <header className="mb-6 flex items-start justify-between gap-4"><div><h2 className="text-xl font-bold text-ink">Event details</h2><p className="text-sm text-ink-muted">{event.event_type}</p></div><button className="rounded p-2 text-ink-muted hover:bg-surface-subtle" onClick={onClose} aria-label="Close event details"><X size={20} /></button></header>
        <div className="space-y-6">
          <section><h3 className="mb-3 font-semibold text-ink">Identity</h3><dl className="grid gap-3 sm:grid-cols-2"><Field event={event} field="event_id" label="Event ID" /><Field event={event} field="event_type" label="Event type" /><Field event={event} field="event_category" label="Event category" /><Field event={event} field="event_sequence" label="Event sequence" /></dl></section>
          <section><h3 className="mb-3 font-semibold text-ink">Effective date</h3><dl><Field event={event} field="effective_date" label="Effective date" /></dl></section>
          <section><h3 className="mb-3 font-semibold text-ink">Scenario and plan design</h3><dl className="grid gap-3 sm:grid-cols-2"><Field event={event} field="scenario_id" label="Scenario ID" /><Field event={event} field="plan_design_id" label="Plan design ID" /></dl></section>
          <section><h3 className="mb-3 font-semibold text-ink">Employee</h3><dl className="grid gap-3 sm:grid-cols-2"><div><dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">Employee ID</dt><dd className="mt-1 text-sm"><Link className="font-medium text-fidelity-green hover:underline" to={timelineUrl(workspaceId, scenarioId, event.employee_id)}>{event.employee_id}</Link></dd></div><Field event={event} field="employee_ssn" label="Employee SSN" /><Field event={event} field="employee_age" label="Employee age" /><Field event={event} field="employee_tenure" label="Employee tenure" /><Field event={event} field="level_id" label="Level ID" /><Field event={event} field="age_band" label="Age band" /><Field event={event} field="tenure_band" label="Tenure band" /></dl></section>
          <section><h3 className="mb-3 font-semibold text-ink">Payload</h3><dl className="grid gap-3 sm:grid-cols-2"><Field event={event} field="event_details" label="Event details" /><Field event={event} field="compensation_amount" label="Compensation amount" /><Field event={event} field="previous_compensation" label="Previous compensation" /><Field event={event} field="employee_deferral_rate" label="Employee deferral rate" /><Field event={event} field="prev_employee_deferral_rate" label="Previous deferral rate" /><Field event={event} field="event_probability" label="Event probability" /></dl></section>
          <section><h3 className="mb-3 font-semibold text-ink">Provenance</h3><dl className="grid gap-3 sm:grid-cols-2"><Field event={event} field="parameter_scenario_id" label="Parameter scenario ID" /><Field event={event} field="parameter_source" label="Parameter source" /><Field event={event} field="data_quality_flag" label="Data quality flag" /><Field event={event} field="created_at" label="Created at" /></dl></section>
        </div>
      </aside>
    </div>
  );
}
