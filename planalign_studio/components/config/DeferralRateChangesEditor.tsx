import { DistributionTable } from './DistributionTable';
import { NumericInput } from './NumericInput';
import { invalidRateChangeStep, rateChangeGroups, validateDeferralRateChangeSettings } from './participantBehaviorConfig';
import type { FormData } from './types';

interface Props {
  form: FormData;
  onChange: (changes: Partial<FormData>) => void;
}

const inputClass = 'w-20 px-2 py-1 border border-border-strong rounded text-sm disabled:bg-surface-disabled';
const errorId = 'dcplan-rate-changes-errors';

function StepTable({ form, onChange, direction }: Props & { direction: 'raise' | 'lower' }) {
  const key = direction === 'raise' ? 'dcDeferralRateChangesIncreaseSteps' : 'dcDeferralRateChangesDecreaseSteps';
  const steps = form[key];
  const titleId = `dcplan-rate-changes-${direction}`;
  return <div className="min-w-0 space-y-2">
    <h4 id={titleId} className="text-sm font-semibold text-ink">How much people {direction}</h4>
    <DistributionTable titleId={titleId} rows={steps.map(step => ({ value: step.pp, share: step.weight }))}
      valueHeading="Percentage points" shareHeading="Weight" rowLabel={`${direction === 'raise' ? 'Raise' : 'Lower'} step`} valueSuffix="percentage points" integer
      active={form.dcDeferralRateChangesEnabled} errorId={errorId} invalidValue={index => invalidRateChangeStep(steps, index)}
      onChange={(index, changes) => onChange({ [key]: steps.map((step, row) => row === index
        ? { pp: changes.value ?? step.pp, weight: changes.share ?? step.weight } : step) })}
      onRemove={index => onChange({ [key]: steps.filter((_, row) => row !== index) })}
      onAdd={() => onChange({ [key]: [...steps, { pp: Math.max(0, ...steps.map(step => step.pp)) + 1, weight: 0 }] })}
      addLabel={`Add ${direction} step`} />
  </div>;
}

export function DeferralRateChangesEditor({ form, onChange }: Props) {
  const errors = validateDeferralRateChangeSettings(form);
  return <div className="sm:col-span-6 space-y-4">
    <p className="text-xs text-ink-muted">On by default. Each year, some participants raise or lower their rate, stop contributing, or restart. At most one change per person per year.</p>
    {!form.dcDeferralRateChangesEnabled && <p className="text-xs text-ink-muted">Inactive while contribution rate changes are off. Saved values are retained.</p>}
    {form.dcDeferralRateChangesEnabled && errors.length > 0 && <div id={errorId} role="alert" className="rounded border border-danger-border bg-danger-surface p-3 text-xs text-danger-ink">
      {errors.map(error => <p key={error}>{error}</p>)}
    </div>}
    <fieldset disabled={!form.dcDeferralRateChangesEnabled} aria-label="Contribution rate change settings" className="min-w-0 space-y-4 disabled:opacity-60">
      <h4 id="dcplan-rate-changes-chances" className="text-sm font-semibold text-ink">Chance each year</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-labelledby="dcplan-rate-changes-chances">
          <thead><tr className="border-b border-border"><th scope="col" className="text-left p-2">Employees</th><th scope="col" className="text-left p-2">Raise their rate</th><th scope="col" className="text-left p-2">Lower their rate</th></tr></thead>
          <tbody>{rateChangeGroups.map(([label, raise, lower]) => <tr key={label} className="border-b border-border">
            <th scope="row" className="text-left p-2 font-medium">{label}</th>
            {[raise, lower].map((key, index) => <td key={key} className="p-2 whitespace-nowrap"><NumericInput name={key} aria-label={`${label}: ${index === 0 ? 'Raise' : 'Lower'} their rate`} value={form[key]} min={0} max={100} className={inputClass}
              onChange={event => onChange({ [key]: Number(event.target.value) })} /> %</td>)}
          </tr>)}</tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">For each group, raise, lower and stop chances together must be no more than 100%.</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {([['dcDeferralRateChangesStopProbability', 'Stop contributing'], ['dcDeferralRateChangesRestartProbability', 'Restart after stopping']] as const).map(([key, label]) => <label key={key} htmlFor={key} className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">{label}
          <NumericInput id={key} name={key} value={form[key]} min={0} max={100} className={inputClass} onChange={event => onChange({ [key]: Number(event.target.value) })} /> %
        </label>)}
      </div>
      <p className="text-xs text-ink-muted">Stopped employees stay enrolled at 0%; a restart returns them to their earlier rate.</p>
      <p className="text-xs text-ink-muted">Step weights in each table must add up to 100%. Decreases never go below 1%.</p>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <StepTable form={form} onChange={onChange} direction="raise" />
        <StepTable form={form} onChange={onChange} direction="lower" />
      </div>
      <h4 className="text-sm font-semibold text-ink">Responses to automatic-increase notices</h4>
      {!form.dcAutoEscalation && <p className="text-xs text-ink-muted">Inactive while automatic increases are off. Saved values are retained.</p>}
      <fieldset disabled={!form.dcAutoEscalation} aria-label="Automatic-increase notice responses" className="min-w-0 space-y-3 disabled:opacity-60">
        <label htmlFor="dcDeferralRateChangesPostEscalationDecreaseWindowDays" className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">Decreases by people who just received an automatic increase happen within
          <NumericInput id="dcDeferralRateChangesPostEscalationDecreaseWindowDays" name="dcDeferralRateChangesPostEscalationDecreaseWindowDays" value={form.dcDeferralRateChangesPostEscalationDecreaseWindowDays} min={1} max={365} integer showStepper className={inputClass}
            onChange={event => onChange({ dcDeferralRateChangesPostEscalationDecreaseWindowDays: Number(event.target.value) })} /> days of it
        </label>
        <label htmlFor="dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation" className="flex items-center gap-2 text-sm text-ink-muted">
          <input id="dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation" name="dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation" type="checkbox" checked={form.dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation} className="h-4 w-4 text-fidelity-green rounded"
            onChange={event => onChange({ dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation: event.target.checked })} />
          These people also leave automatic increases
        </label>
      </fieldset>
    </fieldset>
  </div>;
}
