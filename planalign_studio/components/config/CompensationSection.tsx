import { Target } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { solveCompensationGrowth, CompensationSolverResponse } from '../../services/api';
import { useSuggestionPreview } from './useSuggestionPreview';

export function CompensationSection({ variant = 'full' }: { variant?: 'full' | 'essentials' }) {
  const { formData, setFormData, inputProps, activeWorkspace, scenarioId, scenarioLoading } = useConfigContext();
  const scope = JSON.stringify([activeWorkspace?.id, scenarioId]);
  const preview = useSuggestionPreview<CompensationSolverResponse>(JSON.stringify([
    formData, scenarioLoading,
  ]), scope);
  const result = preview.value;
  const fields = [
    ['COLA / Inflation', 'colaRate', result?.cola_rate],
    ['Merit Budget', 'meritBudget', result?.merit_budget],
    ['Avg. Promotion Increase', 'promoIncrease', result?.promotion_increase],
    ['Promotion Budget', 'promoBudget', result?.promotion_budget],
  ] as const;
  const calculate = () => preview.calculate(() => solveCompensationGrowth(activeWorkspace.id, {
    file_path: formData.censusDataPath || undefined,
    target_growth_rate: Number(formData.targetCompensationGrowth) / 100,
    promotion_increase: Number(formData.promoIncrease) / 100,
    turnover_rate: Number(formData.totalTerminationRate) / 100,
    workforce_growth_rate: Number(formData.targetGrowthRate) / 100,
    new_hire_comp_ratio: 0.85,
  }));

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">Compensation growth</h2>
        <p className="text-sm text-ink-muted">Review the current draft pay assumptions and optionally calculate a suggestion.</p>
      </div>
      <div className="bg-info-surface p-4 rounded-lg border border-info-border space-y-3">
        <h3 className="text-sm font-semibold text-info-ink flex items-center gap-2"><Target size={18} /> Compensation target helper</h3>
        <p className="text-xs text-info-ink">The target guides a simplified estimate; it does not guarantee simulated compensation growth. The solver assumes new-hire compensation is 85% of average compensation, independently of your configured pay ranges.</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-44"><InputField label="Target compensation growth" {...inputProps('targetCompensationGrowth')} type="number" step="0.5" suffix="%" /></div>
          <button type="button" onClick={calculate} disabled={preview.pending || scenarioLoading || !activeWorkspace?.id}
            className="px-3 py-2 text-sm bg-info-solid text-ink-inverse rounded-md disabled:opacity-50">
            {preview.pending ? 'Calculating…' : 'Calculate suggested settings'}
          </button>
        </div>
        {preview.error && <p role="alert" className="text-sm text-danger-ink">{preview.error}</p>}
        {result && (
          <div className="bg-surface-raised rounded-lg border border-info-border p-3 space-y-3" aria-label="Compensation suggestion preview">
            <h4 className="font-medium text-ink">Suggested settings — not applied</h4>
            <p className="text-xs text-ink-muted">Source: {formData.censusDataPath || 'solver defaults (no census selected)'}. The solver uses the current turnover and headcount growth assumptions.</p>
            {preview.stale && <p role="status" className="text-sm text-warning-ink">Needs recalculation: inputs have changed.</p>}
            <table className="w-full text-sm"><thead><tr className="text-left"><th>Assumption</th><th>Current draft</th><th>Suggested</th></tr></thead>
              <tbody>{fields.map(([label, field, suggested]) => <tr key={field}><th className="text-left font-normal py-1">{label}</th><td>{formData[field]}%</td><td>{suggested?.toFixed(1)}%</td></tr>)}</tbody>
            </table>
            <p className="text-xs text-ink-muted">Solver estimate: {result.achieved_growth_rate.toFixed(1)}% average growth. Promotion budget is saved for reference and is not enforced by the engine. Nested promotion overrides can supersede the displayed promotion inputs.</p>
            {result.warnings.map((warning, index) => <p key={index} className="text-xs text-warning-ink">{warning}</p>)}
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={preview.stale} className="px-3 py-2 rounded bg-info-solid text-ink-inverse text-sm disabled:opacity-50"
                onClick={() => preview.apply(suggestion => setFormData(previous => ({ ...previous, colaRate: suggestion.cola_rate, meritBudget: suggestion.merit_budget, promoIncrease: suggestion.promotion_increase, promoBudget: suggestion.promotion_budget })))}>Apply suggested settings</button>
              <button type="button" onClick={preview.cancel} className="px-3 py-2 rounded border border-border text-sm">Cancel</button>
            </div>
          </div>
        )}
      </div>
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink">Current draft pay assumptions</h3>
        <p className="text-xs text-ink-muted">These inputs are saved when you choose Save. Applying a suggestion only updates this draft. Promotion increase and spread can be superseded by nested configuration overrides; the run's resolved configuration determines engine behavior.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-6">
          <InputField label="COLA / Inflation" {...inputProps('colaRate')} type="number" step="0.1" suffix="%" />
          <InputField label="Merit Budget" {...inputProps('meritBudget')} type="number" step="0.1" suffix="%" />
          <InputField label="Avg. Promotion Increase" {...inputProps('promoIncrease')} type="number" step="0.5" suffix="%" helper="Base promotion input; nested overrides may take precedence." />
          <InputField label="Promotion increase spread" {...inputProps('promoDistributionRange')} type="number" step="0.5" suffix="± %" />
          <InputField label="Promotion Budget" {...inputProps('promoBudget')} type="number" step="0.1" suffix="% of payroll" helper="Saved for reference; not enforced by the engine." />
          {variant === 'full' && <InputField label="Promotion Rate Multiplier" {...inputProps('promoRateMultiplier')} type="number" step="0.1" suffix="×" helper="Multiplier applied to promotion rates; 1 means no adjustment." />}
        </div>
      </div>
    </div>
  );
}
