import { useEffect, useId, useState } from 'react';
import { analyzeMinimumWage, type MinimumWagePreview, type MinimumWageStepInput } from '../../services/api';
import { useConfigContext } from './ConfigContext';
import { NumericInput } from './NumericInput';
import type { MinimumWageRow } from './types';
import {
  MAX_MINIMUM_HOURLY_RATE, MAX_MINIMUM_WAGE_STEPS, censusRateStatus, describeMinimumWage, formatHourlyRate, formatStepDate,
  minimumWageIssues, newMinimumWageRow, previewableSteps, type CensusRateStatus, type MinimumWageIssues,
} from './minimumWage';

const INPUT = 'block w-full rounded-md border border-border-strong p-2 shadow-sm focus:border-brand-green focus:ring-brand-green sm:text-sm disabled:opacity-50';

const COLUMN_HELP: ReadonlyArray<readonly [string, string]> = [
  ['hourly_rate', 'the base hourly rate (preferred)'],
  ['hours_worked', 'all paid hours in the census year'],
  ['scheduled_hours_per_week', 'scheduled weekly hours'],
];

const dollars = (value: number) => `$${Math.round(value).toLocaleString('en-US')}`;
const people = (count: number) => `${count.toLocaleString('en-US')} ${count === 1 ? 'person' : 'people'}`;

interface PreviewState {
  key: string;
  censusPath: string;
  data: MinimumWagePreview | null;
  error: string;
}

/** The census check and estimate for the entered steps, debounced. */
function useMinimumWagePreview(workspaceId: string | undefined, censusPath: string, steps: MinimumWageStepInput[]) {
  const key = JSON.stringify([workspaceId ?? '', censusPath, steps]);
  const [state, setState] = useState<PreviewState>({ key: '', censusPath: '', data: null, error: '' });
  useEffect(() => {
    const [id, path, input] = JSON.parse(key) as [string, string, MinimumWageStepInput[]];
    if (!id || !path) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      analyzeMinimumWage(id, path, input)
        .then(data => { if (!cancelled) setState({ key, censusPath: path, data, error: '' }); })
        .catch((error: unknown) => {
          if (!cancelled) setState({ key, censusPath: path, data: null, error: error instanceof Error ? error.message : String(error) });
        });
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [key]);
  const sameCensus = state.censusPath === censusPath;
  return {
    data: sameCensus ? state.data : null,
    error: sameCensus ? state.error : '',
    pending: state.key !== key,
  };
}

function MissingRates({ status }: { status: Extract<CensusRateStatus, { kind: 'no_rates' }> }) {
  return (
    <div className="rounded-lg border border-warning-border bg-warning-surface p-3 text-sm text-warning-ink space-y-2">
      <p>
        {status.columnsPresent.length === 0
          ? 'This census has no hourly rates, so a minimum wage can\'t be modeled: annual pay alone can\'t tell a low hourly rate from few hours worked.'
          : `This census has ${status.columnsPresent.join(', ')} but no usable hourly rate: every row is blank or outside ${formatHourlyRate(status.minimumRate)}–${formatHourlyRate(status.maximumRate)} an hour.`}
      </p>
      <p>Ask the sponsor to send one of these columns for each hourly employee:</p>
      <ul className="list-disc pl-5">
        {COLUMN_HELP.map(([column, meaning]) => <li key={column}><span className="font-mono">{column}</span>: {meaning}</li>)}
      </ul>
    </div>
  );
}

export function CensusNotice({ status }: { status: CensusRateStatus }) {
  switch (status.kind) {
    case 'no_census':
      return <p className="text-sm text-ink-muted">Choose a census in Data Sources first. A minimum wage needs each hourly employee's rate from the census.</p>;
    case 'checking':
      return <p role="status" className="text-sm text-ink-muted">Checking the census for hourly rates…</p>;
    case 'error':
      return <p role="alert" className="text-sm text-danger-ink">Couldn't check the census for hourly rates: {status.message}</p>;
    case 'no_rates':
      return <MissingRates status={status} />;
    case 'ready':
      return (
        <p className="text-sm text-ink-muted">
          {status.withRate.toLocaleString('en-US')} of {status.headcount.toLocaleString('en-US')} active employees on the census have an hourly rate. People without one are never raised.
        </p>
      );
  }
}

interface RowProps {
  row: MinimumWageRow;
  index: number;
  issues: MinimumWageIssues;
  disabled: boolean;
  onChange: (changes: Partial<MinimumWageRow>) => void;
  onRemove: () => void;
}

function MinimumWageEditorRow({ row, index, issues, disabled, onChange, onRemove }: RowProps) {
  const errorId = useId();
  const { errors, warnings } = issues;
  const described = errors.length || warnings.length ? errorId : undefined;
  return (
    <li className="rounded-lg border border-border p-3 space-y-2">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <label className="text-sm font-medium text-ink-muted">New minimum ($ an hour)
          <NumericInput aria-label={`Minimum wage step ${index + 1} hourly rate`} value={row.hourlyRate} min={0} max={MAX_MINIMUM_HOURLY_RATE} disabled={disabled}
            onChange={event => onChange({ hourlyRate: Number(event.target.value) })} aria-describedby={described} className={`mt-1 ${INPUT}`} />
        </label>
        <label className="text-sm font-medium text-ink-muted">Effective date
          <input type="date" aria-label={`Minimum wage step ${index + 1} effective date`} value={row.effectiveDate} disabled={disabled}
            onChange={event => onChange({ effectiveDate: event.target.value })} aria-describedby={described} className={`mt-1 ${INPUT}`} />
        </label>
        <button type="button" onClick={onRemove} className="px-3 py-2 text-sm text-danger-ink hover:underline">Remove</button>
      </div>
      {described && (
        <ul id={errorId} role="alert" className="text-sm">
          {errors.map(error => <li key={error} className="text-danger-ink">{error}</li>)}
          {warnings.map(warning => <li key={warning} className="text-warning-ink">{warning}</li>)}
        </ul>
      )}
    </li>
  );
}

export function CensusEstimate({ preview, pending }: { preview: MinimumWagePreview; pending: boolean }) {
  const withRate = preview.hourly_rate_summary?.with_rate ?? 0;
  const withoutRate = preview.headcount - withRate;
  return (
    <div className="rounded-lg border border-border bg-surface-subtle p-3 text-sm text-ink-muted" aria-label="Minimum wage census estimate">
      <p className="font-semibold text-ink">Census estimate{pending && <span className="ml-2 font-normal text-ink-subtle">Updating…</span>}</p>
      <ul className="mt-1 space-y-0.5">
        {preview.steps.map(step => (
          <li key={step.effective_date}>
            {formatHourlyRate(step.hourly_rate)} from {formatStepDate(step.effective_date)}: {people(step.people_below)} below it, adding {dollars(step.added_annual_pay)} a year in pay.
          </li>
        ))}
      </ul>
      <p className="mt-1">{withoutRate.toLocaleString('en-US')} of {preview.headcount.toLocaleString('en-US')} active employees on the census have no hourly rate and won't be raised.</p>
      <p className="mt-1 text-xs">
        This is an estimate from the census as of its date. The run applies raises, promotions and turnover before each step, so its numbers will differ.
        Simulated hires have no hourly rate and aren't covered, so the effect fades as census staff leave.
      </p>
    </div>
  );
}

/** compensation.minimum_wage: a new hourly minimum from a date, for census staff with a rate (#1231). */
export function MinimumWageSection() {
  const { formData, setFormData, activeWorkspace } = useConfigContext();
  const rows = formData.minimumWage;
  const issues = minimumWageIssues(rows, Number(formData.startYear), Number(formData.endYear));
  const steps = previewableSteps(rows);
  const preview = useMinimumWagePreview(activeWorkspace?.id, formData.censusDataPath, steps);
  const status = censusRateStatus(formData.censusDataPath, preview);
  const blocked = status.kind === 'no_census' || status.kind === 'no_rates';
  const update = (next: MinimumWageRow[]) => setFormData(prev => ({ ...prev, minimumWage: next }));
  const add = () => update([...rows, newMinimumWageRow()]);
  return (
    <details className="rounded-lg border border-border p-4">
      <summary className="cursor-pointer text-ink marker:text-ink-muted">
        <span className="font-semibold">Minimum wage</span>
        <span className="block mt-2 text-sm text-ink-muted">Raises census staff below a new hourly minimum on a date: {describeMinimumWage(rows)}.</span>
        {issues.some(item => item.errors.length > 0) && <span className="block mt-1 text-sm text-danger-ink">Some minimum wage steps need attention before saving.</span>}
        {issues.some(item => item.warnings.length > 0) && <span className="block mt-1 text-sm text-warning-ink">Some minimum wage steps fall outside the simulated years and won't apply in this run.</span>}
      </summary>
      <div className="pt-4 space-y-3">
        <CensusNotice status={status} />
        {blocked && rows.length > 0 && (
          <p role="alert" className="text-sm text-danger-ink">A run with a minimum wage on this census will be rejected. Remove the steps below or use a census with hourly rates.</p>
        )}
        {rows.length > 0 && (
          <ul className="space-y-3">
            {rows.map((row, index) => (
              <MinimumWageEditorRow key={row.rowKey} row={row} index={index} issues={issues[index]} disabled={blocked}
                onChange={changes => update(rows.map((item, i) => (i === index ? { ...item, ...changes } : item)))}
                onRemove={() => update(rows.filter((_, i) => i !== index))} />
            ))}
          </ul>
        )}
        {status.kind === 'ready' && preview.data && preview.data.steps.length > 0 && <CensusEstimate preview={preview.data} pending={preview.pending} />}
        <button type="button" onClick={add} disabled={blocked || status.kind === 'checking' || rows.length >= MAX_MINIMUM_WAGE_STEPS}
          className="px-3 py-1.5 text-sm rounded-lg border border-border-strong text-ink hover:bg-surface-subtle disabled:opacity-50 disabled:cursor-not-allowed">
          {rows.length === 0 ? 'Add a minimum wage' : 'Add another step'}
        </button>
      </div>
    </details>
  );
}
