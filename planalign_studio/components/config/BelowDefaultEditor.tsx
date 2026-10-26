import { useState } from 'react';
import { NumericInput } from './NumericInput';
import { applicableBelowDefaultTier, belowDefaultSummary, belowDefaultWeightTotal, invalidBelowDefaultCeiling, invalidBelowDefaultWeights, validateBelowDefaultSettings } from './participantBehaviorConfig';
import type { FormData } from './types';

interface Props {
  form: FormData;
  onChange: (changes: Partial<FormData>) => void;
}

const inputClass = 'w-20 px-2 py-1 border border-border-strong rounded text-sm disabled:bg-surface-disabled';
const buttonClass = 'px-3 py-1.5 text-sm border border-border-strong rounded-lg disabled:opacity-50';
const errorId = 'dcplan-below-default-errors';

function errorProps(invalid: boolean, active: boolean) {
  return { 'aria-invalid': invalid && active || undefined, 'aria-describedby': invalid && active ? errorId : undefined };
}

function renderShareTiers({ form, onChange, applicable }: Props & { applicable: number }) {
  const tiers = form.dcBelowDefaultShareTiers;
  const lastCeiling = tiers[tiers.length - 2]?.max_auto_enroll_default_rate ?? 0;
  const updateTier = (index: number, changes: Partial<FormData['dcBelowDefaultShareTiers'][number]>) =>
    onChange({ dcBelowDefaultShareTiers: tiers.map((tier, row) => row === index ? { ...tier, ...changes } : tier) });
  return <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Share choosing below the default by auto-enrollment default</caption>
          <thead><tr className="border-b border-border"><th scope="col" className="text-left p-2">Auto-enrollment default</th><th scope="col" className="text-left p-2">Choose below</th><th scope="col" className="text-left p-2">Actions</th></tr></thead>
          <tbody>{tiers.map((tier, index) => <tr key={index} className={`border-b border-border ${index === applicable && form.dcAutoEnroll ? 'bg-info-surface' : ''}`}>
            <td className="p-2">
              {tier.max_auto_enroll_default_rate === null ? tiers.length === 1 ? 'All auto-enrollment defaults' : `Default above ${lastCeiling}%` : <span className="inline-flex items-center gap-2 whitespace-nowrap">Default up to
                <NumericInput aria-label={`Tier ${index + 1} auto-enrollment default ceiling`} value={tier.max_auto_enroll_default_rate} min={0} max={100} className={inputClass}
                  {...errorProps(invalidBelowDefaultCeiling(tiers, index), form.dcAutoEnroll)}
                  onChange={event => updateTier(index, { max_auto_enroll_default_rate: Number(event.target.value) })} />%</span>}
              {index === applicable && form.dcAutoEnroll && <span className="block text-xs text-info-ink">Applies to current default</span>}
            </td>
            <td className="p-2 whitespace-nowrap"><NumericInput aria-label={`Tier ${index + 1} share choosing below`} value={tier.share} min={0} max={100} className={inputClass}
              onChange={event => updateTier(index, { share: Number(event.target.value) })} /> % choose below</td>
            <td className="p-2">{tier.max_auto_enroll_default_rate !== null && <button type="button" className={buttonClass} aria-label={`Remove below-default tier ${index + 1}`}
              onClick={() => onChange({ dcBelowDefaultShareTiers: tiers.filter((_, row) => row !== index) })}>Remove</button>}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <button type="button" className={buttonClass} disabled={lastCeiling >= 100} onClick={() => onChange({
        dcBelowDefaultShareTiers: [...tiers.slice(0, -1), { max_auto_enroll_default_rate: tiers.length === 1 ? 3 : Math.min(100, lastCeiling + 1), share: 0 }, ...tiers.slice(-1)],
      })}>Add tier</button>
  </>;
}

function renderSteps({ form, onChange }: Props) {
  const steps = form.dcBelowDefaultSteps;
  const updateStep = (index: number, changes: Partial<FormData['dcBelowDefaultSteps'][number]>) =>
    onChange({ dcBelowDefaultSteps: steps.map((step, row) => row === index ? { ...step, ...changes } : step) });
  return <>
      <h5 id="dcplan-below-default-steps-title" className="text-sm font-semibold text-ink">How far below the default they start</h5>
      <p className="text-xs text-ink-muted">How far below the default those employees start. Rates never go below 1%.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-labelledby="dcplan-below-default-steps-title">
          <thead><tr className="border-b border-border"><th scope="col" className="text-left p-2">Reduction</th><th scope="col" className="text-left p-2">Share of below-default starters</th><th scope="col" className="text-left p-2">Actions</th></tr></thead>
          <tbody>{steps.map((step, index) => <tr key={index} className="border-b border-border">
            <td className="p-2"><NumericInput aria-label={`Below-default reduction ${index + 1} in percentage points`} value={step.pp} integer min={1} className={inputClass}
              onChange={event => updateStep(index, { pp: Number(event.target.value) })} /> pp</td>
            <td className="p-2"><NumericInput aria-label={`Below-default reduction ${index + 1} weight`} value={step.weight} min={0} max={100} className={inputClass}
              {...errorProps(invalidBelowDefaultWeights(steps), form.dcAutoEnroll)}
              onChange={event => updateStep(index, { weight: Number(event.target.value) })} /> %</td>
            <td className="p-2"><button type="button" className={buttonClass} disabled={steps.length === 1} aria-label={`Remove below-default reduction ${index + 1}`}
              onClick={() => onChange({ dcBelowDefaultSteps: steps.filter((_, row) => row !== index) })}>Remove</button></td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">Total weight: {belowDefaultWeightTotal(steps)}%</p>
      <button type="button" className={buttonClass} onClick={() => onChange({ dcBelowDefaultSteps: [...steps, { pp: Math.max(0, ...steps.map(step => step.pp)) + 1, weight: 0 }] })}>Add reduction</button>
  </>;
}

export function BelowDefaultEditor({ form, onChange }: Props) {
  const [showTiers, setShowTiers] = useState(false);
  const errors = validateBelowDefaultSettings(form);
  const applicable = errors.length ? -1 : applicableBelowDefaultTier(form);
  const singleTier = form.dcBelowDefaultShareTiers.length === 1 && form.dcBelowDefaultShareTiers[0].max_auto_enroll_default_rate === null;

  return <div className="sm:col-span-6 mt-4 space-y-3">
    <h4 id="dcplan-below-default-title" className="text-sm font-semibold text-ink">Choosing a rate below the auto-enrollment default</h4>
    <p className="text-xs text-ink-muted">Of employees who enroll on their own before automatic enrollment applies, the share who start below the plan's default rate. Everyone else starts at the default or higher. Only the row that matches your plan's default is used.</p>
    <p className="text-xs text-ink-muted">Current plan auto-enrollment default: {form.dcDefaultDeferral}%. {belowDefaultSummary(form)}</p>
    {!form.dcAutoEnroll && <p className="text-xs text-ink-muted">Inactive while auto-enrollment is off. Saved values are retained.</p>}
    {form.dcAutoEnroll && errors.length > 0 && <div id={errorId} role="alert" className="rounded border border-danger-border bg-danger-surface p-3 text-xs text-danger-ink">
      {errors.map(error => <p key={error}>{error}</p>)}
    </div>}
    <fieldset disabled={!form.dcAutoEnroll} aria-labelledby="dcplan-below-default-title" className="min-w-0 space-y-4 disabled:opacity-60">
      <div id="dcplan-below-default-shares">
      {singleTier && !showTiers ? <div className="space-y-2">
        <label htmlFor="dcplan-below-default-share" className="flex items-center gap-2 text-sm text-ink-muted">Start below the default
          <NumericInput id="dcplan-below-default-share" aria-label="Start below the default" aria-describedby="dcplan-below-default-share-help" value={form.dcBelowDefaultShareTiers[0].share} min={0} max={100} className={inputClass}
            onChange={event => onChange({ dcBelowDefaultShareTiers: [{ ...form.dcBelowDefaultShareTiers[0], share: Number(event.target.value) }] })} /> %
        </label>
        <p id="dcplan-below-default-share-help" className="text-xs text-ink-muted">At the current {form.dcDefaultDeferral}% default.</p>
      </div> : renderShareTiers({ form, onChange, applicable })}
      </div>
      {singleTier && <button type="button" aria-expanded={showTiers} aria-controls="dcplan-below-default-shares" className="text-sm text-fidelity-green underline disabled:opacity-50" onClick={() => setShowTiers(!showTiers)}>
        {showTiers ? 'Use one share for all defaults' : 'Vary by auto-enrollment default…'}
      </button>}
      {renderSteps({ form, onChange })}
    </fieldset>
  </div>;
}
