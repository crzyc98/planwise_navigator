import { AlertTriangle } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';

export function SimulationSection() {
  const { inputProps } = useConfigContext();

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Simulation Parameters</h2>
        <p className="text-sm text-gray-500">Define the temporal scope and reproducibility settings.</p>
      </div>

      <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
        <div className="col-span-6 grid grid-cols-2 gap-4">
          <InputField label="Start Year" {...inputProps('startYear')} type="number" width="col-span-1" />
          <InputField label="End Year" {...inputProps('endYear')} type="number" width="col-span-1" />
        </div>

        <InputField
          label="Random Seed"
          {...inputProps('seed')}
          type="number"
          helper="Fixed seed (e.g., 42) ensures identical runs."
        />

        <InputField
          label="Target Growth Rate"
          {...inputProps('targetGrowthRate')}
          type="number"
          step="0.1"
          suffix="%"
          helper="Target annual workforce growth (e.g., 3% = 0.03)"
        />

        <div className="sm:col-span-6 pt-4">
          <div className="rounded-md bg-yellow-50 p-4 border border-yellow-100">
            <div className="flex">
              <AlertTriangle className="h-5 w-5 text-yellow-400" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800">Validation Note</h3>
                <div className="mt-1 text-sm text-yellow-700">
                  <p>End year must be greater than Start year. Large gaps ({'>'} 10 years) may significantly increase processing time.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
