import { NumericInput } from './NumericInput';
import type { FormData } from './types';

interface Props {
  form: FormData;
  onChange: (changes: Partial<FormData>) => void;
}

export function OptOutBandsEditor({ form, onChange }: Props) {
  return <details className="text-xs text-ink-muted">
    <summary className="cursor-pointer font-medium">Advanced: opt-out by age and income</summary>
    <p className="mt-2">Multipliers shift who opts out. Probabilities are normalized toward the {form.dcOptOutRateTarget}% target within each annual candidate cohort. Realized rates vary with deterministic draws; probabilities capped at 100% can lower the expected rate. All-zero weights fall back to the flat target.</p>
    {(['Age', 'Income'] as const).map(dimension => {
      const key = dimension === 'Age' ? 'dcOptOutMultipliersAge' : 'dcOptOutMultipliersIncome';
      const bands = form[key];
      const invalid = bands.some((band, index) => !Number.isFinite(band.min) || !Number.isFinite(band.multiplier) || band.multiplier < 0 || (index === 0 ? band.min !== 0 : band.min <= bands[index - 1].min));
      return <div key={key} className="mt-3 space-y-2">
        <table className="w-full text-sm" aria-label={`${dimension} opt-out multipliers`}>
          <thead><tr><th scope="col">Minimum {dimension === 'Age' ? 'age (years)' : 'income ($)'}</th><th scope="col">Multiplier</th><th scope="col">Actions</th></tr></thead>
          <tbody>{bands.map((band, index) => <tr key={index}>
            {(['min', 'multiplier'] as const).map(field => <td key={field}><NumericInput aria-label={`${dimension} band ${index + 1} ${field}`} value={band[field]} min={0} disabled={field === 'min' && index === 0} aria-invalid={invalid || undefined}
              onChange={event => onChange({ [key]: bands.map((row, i) => i === index ? { ...row, [field]: Number(event.target.value) } : row) })} /></td>)}
            <td><button type="button" disabled={index === 0} onClick={() => onChange({ [key]: bands.filter((_, i) => i !== index) })}>Remove</button></td>
          </tr>)}</tbody>
        </table>
        {invalid && <p role="alert">Start at zero, use strictly increasing minimums and nonnegative multipliers.</p>}
        <button type="button" onClick={() => onChange({ [key]: [...bands, { min: bands[bands.length - 1].min + (dimension === 'Age' ? 10 : 50000), multiplier: 1 }] })}>Add {dimension.toLowerCase()} band</button>
      </div>;
    })}
  </details>;
}
