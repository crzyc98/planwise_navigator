import { HelpCircle } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';

export function TurnoverSection() {
  const { formData, inputProps } = useConfigContext();

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Workforce & Turnover</h2>
        <p className="text-sm text-gray-500">Model employee attrition rates and retention risks.</p>
      </div>

      {/* Core Workforce Parameters */}
      <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
        <h4 className="text-sm font-semibold text-orange-900 mb-3 uppercase tracking-wider">Core Termination Rates</h4>
        <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
          <InputField
            label="Total Termination Rate"
            {...inputProps('totalTerminationRate')}
            type="number"
            step="0.1"
            suffix="%"
            helper="Overall annual termination rate for experienced employees"
          />
          <InputField
            label="New Hire Termination Rate"
            {...inputProps('newHireTerminationRate')}
            type="number"
            step="0.1"
            suffix="%"
            helper="First-year termination rate (typically higher than overall)"
          />
        </div>
      </div>

      <div className="bg-blue-50 rounded-lg p-4 border border-blue-100">
        <h4 className="text-sm font-medium text-blue-900 mb-2 flex items-center">
          <HelpCircle size={16} className="mr-2 text-blue-500"/> Calculated Projection
        </h4>
        <p className="text-sm text-blue-800">
          Based on these inputs, an organization of 1,000 employees will see approximately <span className="font-bold">{Math.round(1000 * (Number(formData.totalTerminationRate) / 100))}</span> experienced employee exits per year, plus <span className="font-bold">{Math.round(100 * (Number(formData.newHireTerminationRate) / 100))}</span> first-year exits per 100 new hires.
        </p>
      </div>

      <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
        <h4 className="text-sm font-medium text-gray-700 mb-2">How Termination Works</h4>
        <p className="text-xs text-gray-600">
          The simulation uses deterministic termination selection based on workforce growth targets.
          Employees are selected for termination to achieve the configured termination rates while
          maintaining workforce growth objectives. Hazard-based modeling (age/tenure multipliers)
          is available in the analytics layer for reporting purposes.
        </p>
      </div>
    </div>
  );
}
