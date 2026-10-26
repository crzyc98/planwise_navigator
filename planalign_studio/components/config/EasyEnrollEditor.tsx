import { DistributionTable } from './DistributionTable';
import { NumericInput } from './NumericInput';
import { invalidEasyEnrollRate, validateEasyEnrollSettings } from './participantBehaviorConfig';
import type { FormData } from './types';

interface Props {
  form: FormData;
  onChange: (changes: Partial<FormData>) => void;
}

export function EasyEnrollEditor({ form, onChange }: Props) {
  const packages = form.dcEasyEnrollPackages;
  const errors = validateEasyEnrollSettings(form);
  const errorId = 'dcplan-easy-enroll-errors';
  return <div className="sm:col-span-6 space-y-4">
    <p className="text-xs text-ink-muted">Employees who enroll on their own, before any auto-enrollment, can pick a preset package instead of choosing a rate. Auto-enrolled employees never use Easy Enroll.</p>
    {!form.dcEasyEnrollEnabled && <p className="text-xs text-ink-muted">Inactive while Easy Enroll is off. Saved values are retained.</p>}
    {form.dcEasyEnrollEnabled && errors.length > 0 && <div id={errorId} role="alert" className="rounded border border-danger-border bg-danger-surface p-3 text-xs text-danger-ink">
      {errors.map(error => <p key={error}>{error}</p>)}
    </div>}
    <fieldset disabled={!form.dcEasyEnrollEnabled} aria-label="Easy Enroll settings" className="min-w-0 space-y-4 disabled:opacity-60">
      <h4 id="dcplan-easy-enroll-shares" className="text-sm font-semibold text-ink">Share of self-enrollees who use Easy Enroll</h4>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-labelledby="dcplan-easy-enroll-shares">
        {([
          ['dcEasyEnrollShareWithAutoEnrollment', 'Plans with auto-enrollment', form.dcAutoEnroll],
          ['dcEasyEnrollShareWithoutAutoEnrollment', 'Plans without auto-enrollment', !form.dcAutoEnroll],
        ] as const).map(([key, label, applicable]) => <div key={key} className={`rounded p-3 ${applicable ? 'bg-info-surface' : 'opacity-60'}`}>
          <label htmlFor={key} className="block text-sm font-medium text-ink-muted">{label}</label>
          <div className="mt-2 flex items-center gap-2"><NumericInput id={key} name={key} value={form[key]} min={0} max={100} className="w-20 px-2 py-1 border border-border-strong rounded text-sm disabled:bg-surface-disabled"
            onChange={event => onChange({ [key]: Number(event.target.value) })} /> %</div>
          <p className={`mt-1 text-xs ${applicable ? 'text-info-ink' : 'text-ink-muted'}`}>{applicable ? 'Applies to this plan' : 'Inactive for this plan; saved value retained.'}</p>
        </div>)}
      </div>
      <h4 id="dcplan-easy-enroll-packages" className="text-sm font-semibold text-ink">Easy Enroll packages</h4>
      <p className="text-xs text-ink-muted">Each row is a preset contribution rate and the share of Easy Enroll members who choose it. Shares must add up to 100%.</p>
      <DistributionTable titleId="dcplan-easy-enroll-packages" rows={packages.map(pkg => ({ value: pkg.rate, share: pkg.share }))}
        valueHeading="Contribution rate" shareHeading="Chosen by" rowLabel="Easy Enroll package" removeLabel="Easy Enroll package" valueSuffix="% contribution" shareSuffix=" of members" max={100}
        active={form.dcEasyEnrollEnabled} errorId={errorId} invalidValue={index => invalidEasyEnrollRate(packages, index)}
        onChange={(index, changes) => onChange({ dcEasyEnrollPackages: packages.map((pkg, row) => row === index
          ? { rate: changes.value ?? pkg.rate, share: changes.share ?? pkg.share } : pkg) })}
        onRemove={index => onChange({ dcEasyEnrollPackages: packages.filter((_, row) => row !== index) })}
        onAdd={() => onChange({ dcEasyEnrollPackages: [...packages, { rate: Math.max(0, ...packages.map(pkg => pkg.rate)) + 1, share: 0 }] })}
        addLabel="Add package" />
      <label htmlFor="dcplan-easy-enroll-cap" className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">Automatic increases for Easy Enroll members stop at
        <NumericInput id="dcplan-easy-enroll-cap" name="dcEasyEnrollEscalationCap" value={form.dcEasyEnrollEscalationCap} min={0} max={100} className="w-20 px-2 py-1 border border-border-strong rounded text-sm disabled:bg-surface-disabled"
          onChange={event => onChange({ dcEasyEnrollEscalationCap: Number(event.target.value) })} /> %
      </label>
      <p className="text-xs text-ink-muted">Easy Enroll members get automatic increases even when plan-wide automatic increases are off.</p>
    </fieldset>
  </div>;
}
