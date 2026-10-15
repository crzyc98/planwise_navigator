import { NumericInput } from './NumericInput';
import React from 'react';
import { useConfigContext } from './ConfigContext';
import type { FormData } from './types';

export function EnrollmentRateInput({ kind }: { kind: 'voluntary' | 'optOut' }) {
  const { formData, setFormData, workspaceConfig, originalConfig, scenarioId } = useConfigContext();
  const voluntary = kind === 'voluntary';
  const field = voluntary ? 'dcVoluntaryEnrollmentRate' : 'dcNewHireOptOutRate';
  const modeField = voluntary ? 'dcVoluntaryEnrollmentMode' : 'dcNewHireOptOutMode';
  const key = voluntary ? 'voluntary_enrollment_rate' : 'new_hire_opt_out_rate';
  const mode = formData[modeField] ?? (formData[field] === '' ? 'demographic' : 'specified');
  const source = scenarioId ? workspaceConfig : originalConfig;
  const legacy = Object.prototype.hasOwnProperty.call(originalConfig.enrollment?.auto_enrollment ?? {}, key)
    ? originalConfig.enrollment.auto_enrollment[key] : source.enrollment?.auto_enrollment?.[key];
  const inherited = scenarioId && Object.prototype.hasOwnProperty.call(source.dc_plan ?? {}, key)
    ? source.dc_plan[key]
    : legacy;
  const inheritedText = inherited == null ? 'demographic model' : `${Number(inherited) * 100}%`;
  const disabled = !voluntary && !formData.dcAutoEnroll;
  const label = voluntary ? 'New-hire voluntary enrollment' : 'New-hire opt-outs after automatic enrollment';
  const value = formData[field];
  return <fieldset disabled={disabled} className="sm:col-span-3 space-y-2 disabled:opacity-60">
    <legend className="text-sm font-medium text-ink">{label}</legend>
    <label className="block text-xs text-ink-muted" htmlFor={`${field}-mode`}>Rate source</label>
    <select id={`${field}-mode`} value={mode} className="block w-full rounded-md border border-border bg-surface p-2 text-ink"
      onChange={event => setFormData(previous => ({ ...previous, [modeField]: event.target.value as FormData['dcVoluntaryEnrollmentMode'] }))}>
      <option value="inherit">{scenarioId ? 'Use inherited setting' : 'Use inherited engine setting'} ({inheritedText})</option>
      <option value="demographic">Use demographic model</option>
      <option value="specified">Specify a percentage</option>
    </select>
    {mode === 'specified' && <>
      <label className="block text-xs text-ink-muted" htmlFor={field}>Specified percentage (0–100%)</label>
      <NumericInput id={field} type="number" min={0} max={100} step="1" value={value} required
        className="block w-full rounded-md border border-border bg-surface p-2 text-ink"
        onChange={event => setFormData(previous => ({ ...previous, [field]: event.target.value }))} />
      {(value === '' || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 100) &&
        <p role="alert" className="text-xs text-danger-ink">Enter a percentage from 0 to 100. Zero is an explicit 0% rate.</p>}
    </>}
    <p className="text-xs text-ink-muted">{disabled ? 'Inactive while automatic enrollment is off; the saved setting is retained.' : voluntary
      ? 'Share of eligible new hires who enroll voluntarily in their hire year. Continuing employees use demographic assumptions.'
      : 'Share of automatically enrolled new hires who opt out. Continuing employees use demographic assumptions.'}</p>
    {mode === 'demographic' && <p className="text-xs text-ink-muted">Explicitly clears any inherited flat rate for this decision.</p>}
  </fieldset>;
}
