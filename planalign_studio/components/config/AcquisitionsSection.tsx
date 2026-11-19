import { useEffect, useId, useState } from 'react';
import { useConfigContext } from './ConfigContext';
import { NumericInput } from './NumericInput';
import type { AcquisitionRow } from './types';
import {
  MAX_ACQUISITIONS, MAX_ACQUISITION_HEADCOUNT, acquisitionIssues, describeAcquisitions, estimatedAnnualPay, newAcquisitionRow,
  renameAcquisition, staffAveragePay, totalAcquiredHeadcount, type AcquisitionIssues,
} from './acquisitions';
import { AcquisitionOverrideFields, AcquisitionPlanFields } from './AcquisitionSettingsFields';
import { analyzeCompensation } from '../../services/api';

const INPUT = 'block w-full rounded-md border border-border-strong p-2 shadow-sm focus:border-brand-green focus:ring-brand-green sm:text-sm';

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
}

// minimumFractionDigits is explicit: without it some runtimes print "$15.0M" for a round figure.
const money = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', notation: 'compact', minimumFractionDigits: 0, maximumFractionDigits: 1 });

interface RowProps {
  row: AcquisitionRow;
  index: number;
  issues: AcquisitionIssues;
  onRename: (name: string) => void;
  onChange: (changes: Partial<AcquisitionRow>) => void;
  onRemove: () => void;
}

function AcquisitionEditorRow({ row, index, issues, onRename, onChange, onRemove }: RowProps) {
  const errorId = useId();
  const { errors, warnings } = issues;
  const described = errors.length || warnings.length ? errorId : undefined;
  return (
    <li className="rounded-lg border border-border p-3 space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end">
        <label className="text-sm font-medium text-ink-muted">Name
          <input aria-label={`Acquisition ${index + 1} name`} value={row.name} onChange={event => onRename(event.target.value)} aria-describedby={described} className={`mt-1 ${INPUT}`} />
        </label>
        <label className="text-sm font-medium text-ink-muted">Headcount
          <NumericInput aria-label={`Acquisition ${index + 1} headcount`} value={row.headcount} integer min={1} max={MAX_ACQUISITION_HEADCOUNT}
            onChange={event => onChange({ headcount: Number(event.target.value) })} aria-describedby={described} className={`mt-1 ${INPUT}`} />
        </label>
        <label className="text-sm font-medium text-ink-muted">Effective date
          <input type="date" aria-label={`Acquisition ${index + 1} effective date`} value={row.effectiveDate} onChange={event => onChange({ effectiveDate: event.target.value })} aria-describedby={described} className={`mt-1 ${INPUT}`} />
        </label>
        <button type="button" onClick={onRemove} className="px-3 py-2 text-sm text-danger-ink hover:underline">Remove</button>
      </div>
      {row.id && <p className="text-xs text-ink-subtle">Id: {row.id}</p>}
      <AcquisitionPlanFields row={row} index={index} onChange={onChange} />
      <AcquisitionOverrideFields row={row} index={index} onChange={onChange} />
      {described && (
        <ul id={errorId} role="alert" className="text-sm">
          {errors.map(error => <li key={error} className="text-danger-ink">{error}</li>)}
          {warnings.map(warning => <li key={warning} className="text-warning-ink">{warning}</li>)}
        </ul>
      )}
    </li>
  );
}

type StaffPay = { status: 'none' | 'loading' | 'unavailable' } | { status: 'loaded'; value: number };

/** Average active pay from the scenario's census, fetched only when a group needs it. */
function useStaffAveragePay(needed: boolean): StaffPay {
  const { formData, activeWorkspace } = useConfigContext();
  const workspaceId = activeWorkspace?.id;
  const censusPath = formData.censusDataPath;
  const ready = needed && Boolean(workspaceId && censusPath) && formData.censusDataStatus === 'loaded';
  const [state, setState] = useState<{ key: string; pay: StaffPay } | null>(null);
  const key = `${workspaceId}|${censusPath}`;
  useEffect(() => {
    if (!ready || !workspaceId) return;
    let cancelled = false;
    analyzeCompensation(workspaceId, censusPath, 0)
      .then(analysis => {
        const value = staffAveragePay(analysis);
        if (!cancelled) setState({ key, pay: value === null ? { status: 'unavailable' } : { status: 'loaded', value } });
      })
      .catch(() => { if (!cancelled) setState({ key, pay: { status: 'unavailable' } }); });
    return () => { cancelled = true; };
  }, [ready, workspaceId, censusPath, key]);
  if (!ready) return { status: 'none' };
  return state?.key === key ? state.pay : { status: 'loading' };
}

function estimateNote(staffPay: StaffPay): string {
  if (staffPay.status === 'loaded') {
    return `Pay is an estimate: headcount × your census's average active pay (${money.format(staffPay.value)}), adjusted for any pay override. The run samples real staff, so its figures will differ.`;
  }
  if (staffPay.status === 'loading') return "Estimating pay from your census…";
  if (staffPay.status === 'unavailable') return "Couldn't read average pay from your census, so pay is estimated only for groups with a set amount.";
  return 'Load a census file to estimate pay for groups that follow staff pay.';
}

function AcquisitionPreview({ rows }: { rows: AcquisitionRow[] }) {
  const staffPay = useStaffAveragePay(rows.some(row => row.pay.kind !== 'amount'));
  const average = staffPay.status === 'loaded' ? staffPay.value : null;
  const estimates = rows.map(row => estimatedAnnualPay(row, average));
  const total = totalAcquiredHeadcount(rows);
  const totalPay = estimates.every(estimate => estimate !== null)
    ? estimates.reduce<number>((sum, estimate) => sum + (estimate ?? 0), 0)
    : null;
  return (
    <div className="rounded-lg border border-border bg-surface-subtle p-3 text-sm text-ink-muted">
      <p className="font-semibold text-ink">What this adds</p>
      <ul className="mt-1 space-y-0.5">
        {rows.map((row, index) => {
          const estimate = estimates[index];
          return (
            <li key={row.rowKey}>
              {row.name.trim() || `Acquisition ${index + 1}`}: {Number.isFinite(row.headcount) ? row.headcount.toLocaleString() : 0} people join on {row.effectiveDate ? formatDate(row.effectiveDate) : 'a date not yet chosen'}
              {estimate !== null && <>, about {money.format(estimate)} a year in pay</>}
            </li>
          );
        })}
      </ul>
      <p className="mt-1 font-medium text-ink">
        Total: {total.toLocaleString()} {total === 1 ? 'person' : 'people'}{totalPay !== null && <>, about {money.format(totalPay)} a year in pay</>}
      </p>
      <p className="mt-1 text-xs">{estimateNote(staffPay)}</p>
    </div>
  );
}

/** workforce.acquisitions: groups added on a date, on top of organic hiring (#1228). */
export function AcquisitionsSection() {
  const { formData, setFormData, savedFormData } = useConfigContext();
  const rows = formData.acquisitions;
  const savedIds = new Set((savedFormData?.acquisitions ?? []).map(row => row.id));
  const issues = acquisitionIssues(rows, Number(formData.startYear), Number(formData.endYear));
  const invalid = issues.some(item => item.errors.length > 0);
  const outsideYears = issues.some(item => item.warnings.length > 0);
  const update = (next: AcquisitionRow[]) => setFormData(prev => ({ ...prev, acquisitions: next }));
  const add = () => update([...rows, newAcquisitionRow()]);
  return (
    <details className="rounded-lg border border-border p-4">
      <summary className="cursor-pointer text-ink marker:text-ink-muted">
        <span className="font-semibold">Acquisitions</span>
        <span className="block mt-2 text-sm text-ink-muted">Groups that join on a date, on top of organic hiring: {describeAcquisitions(rows)}.</span>
        {invalid && <span className="block mt-1 text-sm text-danger-ink">Some acquisitions need attention before saving.</span>}
        {outsideYears && <span className="block mt-1 text-sm text-warning-ink">Some acquisitions fall outside the simulated years and won't join in this run.</span>}
      </summary>
      <div className="pt-4 space-y-3">
        {rows.length > 0 && (
          <ul className="space-y-3">
            {rows.map((row, index) => (
              <AcquisitionEditorRow key={row.rowKey} row={row} index={index} issues={issues[index]}
                onRename={name => update(renameAcquisition(rows, index, name, savedIds))}
                onChange={changes => update(rows.map((item, i) => (i === index ? { ...item, ...changes } : item)))}
                onRemove={() => update(rows.filter((_, i) => i !== index))} />
            ))}
          </ul>
        )}
        {rows.length > 0 && <AcquisitionPreview rows={rows} />}
        <button type="button" onClick={add} disabled={rows.length >= MAX_ACQUISITIONS}
          className="px-3 py-1.5 text-sm rounded-lg border border-border-strong text-ink hover:bg-surface-subtle disabled:opacity-50 disabled:cursor-not-allowed">
          Add acquisition
        </button>
      </div>
    </details>
  );
}
