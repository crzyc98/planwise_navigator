import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';

export function SimulationSection({ variant = 'full' }: { variant?: 'full' | 'essentials' }) {
  const { inputProps, formData } = useConfigContext();
  const essentials = variant === 'essentials';
  const first = Number(formData.startYear);
  const last = Number(formData.endYear);
  const validYears = String(formData.startYear).trim() !== '' && String(formData.endYear).trim() !== '' && Number.isInteger(first) && Number.isInteger(last) && first <= last;

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">Projection period</h2>
        <p className="text-sm text-ink-muted">{validYears ? `${last - first + 1} projection year${last === first ? '' : 's'}, including both endpoints.` : 'Choose a valid projection period.'}</p>
      </div>

      <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
        <div className="col-span-full grid grid-cols-1 sm:grid-cols-2 gap-4">
          <InputField label="First projection year" {...inputProps('startYear')} type="number" width="col-span-1" />
          <InputField label="Last projection year" {...inputProps('endYear')} type="number" width="col-span-1" />
        </div>
        {!validYears && <p role="alert" className="col-span-full text-sm text-danger-ink">Use whole years. Last projection year must be at least the first projection year.</p>}
        {validYears && last - first + 1 > 10 && <p className="col-span-full text-sm text-ink-muted">Projecting more than 10 years may increase processing time.</p>}

        {!essentials && (
          <InputField
            label="Random Seed"
            {...inputProps('seed')}
            type="number"
            helper="Fixed seed (e.g., 42) ensures identical runs."
          />
        )}

        {!essentials && <InputField
          label="Annual headcount growth"
          {...inputProps('targetGrowthRate')}
          type="number"
          step="0.1"
          suffix="%"
          helper="Target annual workforce growth as a percentage (e.g., 3 for 3%)"
        />}
      </div>
    </div>
  );
}
