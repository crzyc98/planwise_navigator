import { useState } from 'react';
import { AlertTriangle, Target, Sparkles, Check, X } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { solveCompensationGrowth, CompensationSolverResponse } from '../../services/api';

export function CompensationSection() {
  const { formData, setFormData, handleChange, inputProps, activeWorkspace } = useConfigContext();

  const [targetCompGrowth, setTargetCompGrowth] = useState<number>(5.0);
  const [solverStatus, setSolverStatus] = useState<'idle' | 'solving' | 'success' | 'error'>('idle');
  const [solverResult, setSolverResult] = useState<CompensationSolverResponse | null>(null);
  const [solverError, setSolverError] = useState<string>('');

  const handleSolveCompensation = async () => {
    if (!activeWorkspace?.id) {
      setSolverError('No workspace selected');
      setSolverStatus('error');
      return;
    }

    setSolverStatus('solving');
    setSolverError('');
    setSolverResult(null);

    try {
      const result = await solveCompensationGrowth(activeWorkspace.id, {
        file_path: formData.censusDataPath || undefined,
        target_growth_rate: targetCompGrowth / 100,
        promotion_increase: Number(formData.promoIncrease) / 100,
        turnover_rate: Number(formData.totalTerminationRate) / 100,
        workforce_growth_rate: Number(formData.targetGrowthRate) / 100,
        new_hire_comp_ratio: 0.85,
      });

      setSolverResult(result);
      setSolverStatus('success');

      setFormData(prev => ({
        ...prev,
        colaRate: result.cola_rate,
        meritBudget: result.merit_budget,
        promoIncrease: result.promotion_increase,
        promoBudget: result.promotion_budget,
      }));
    } catch (error) {
      console.error('Failed to solve compensation:', error);
      setSolverError(error instanceof Error ? error.message : 'Failed to solve');
      setSolverStatus('error');
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Compensation Strategy</h2>
        <p className="text-sm text-gray-500">Set annual increase budgets and promotion guidelines.</p>
      </div>

      {/* Target Growth Solver - Magic Button */}
      <div className="bg-gradient-to-r from-purple-50 to-indigo-50 p-5 rounded-xl border border-purple-200 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 bg-purple-100 rounded-lg p-2.5">
            <Target className="h-6 w-6 text-purple-600" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-purple-900">Target Compensation Growth</h3>
            <p className="text-xs text-purple-700 mt-0.5">
              Enter your target average compensation growth rate and we'll calculate the COLA, merit, and promotion settings needed.
            </p>
            <div className="mt-3 flex items-end gap-3">
              <div className="flex-shrink-0 w-32">
                <label className="block text-xs font-medium text-purple-800 mb-1">Target Growth</label>
                <div className="relative">
                  <input
                    type="number"
                    value={targetCompGrowth}
                    onChange={(e) => setTargetCompGrowth(parseFloat(e.target.value) || 0)}
                    step="0.5"
                    min="0"
                    max="20"
                    className="w-full px-3 py-2 text-sm border border-purple-300 rounded-md focus:ring-purple-500 focus:border-purple-500 bg-white"
                  />
                  <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                    <span className="text-purple-500 text-sm">%</span>
                  </div>
                </div>
              </div>
              <button
                onClick={handleSolveCompensation}
                disabled={solverStatus === 'solving'}
                className={`
                  flex items-center gap-2 px-4 py-2 rounded-md font-medium text-sm transition-all
                  ${solverStatus === 'solving'
                    ? 'bg-purple-200 text-purple-400 cursor-wait'
                    : 'bg-purple-600 text-white hover:bg-purple-700 shadow-sm hover:shadow'
                  }
                `}
              >
                <Sparkles className="h-4 w-4" />
                {solverStatus === 'solving' ? 'Calculating...' : 'Calculate Settings'}
              </button>
            </div>

            {/* Solver Results */}
            {solverStatus === 'success' && solverResult && (
              <div className="mt-4 p-3 bg-white rounded-lg border border-purple-200">
                <div className="flex items-center gap-2 mb-2">
                  <Check className="h-4 w-4 text-green-600" />
                  <span className="text-sm font-medium text-green-800">Settings Applied!</span>
                </div>
                <div className="grid grid-cols-4 gap-3 text-center">
                  <div>
                    <div className="text-lg font-bold text-purple-900">{solverResult.cola_rate.toFixed(1)}%</div>
                    <div className="text-xs text-gray-500">COLA</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-purple-900">{solverResult.merit_budget.toFixed(1)}%</div>
                    <div className="text-xs text-gray-500">Merit</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-purple-900">{solverResult.promotion_increase.toFixed(1)}%</div>
                    <div className="text-xs text-gray-500">Promo Inc.</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-purple-900">{solverResult.promotion_budget.toFixed(1)}%</div>
                    <div className="text-xs text-gray-500">Promo Budget</div>
                  </div>
                </div>
                <div className="mt-2 pt-2 border-t border-purple-100">
                  <p className="text-xs text-gray-600">
                    <span className="font-medium">Stayer raises:</span>{' '}
                    COLA {solverResult.cola_contribution.toFixed(1)}% +
                    Merit {solverResult.merit_contribution.toFixed(1)}% +
                    Promotions {solverResult.promo_contribution.toFixed(1)}%
                  </p>
                  <p className="text-xs text-gray-600 mt-1">
                    <span className="font-medium">Workforce dynamics:</span>{' '}
                    <span className={solverResult.turnover_contribution < 0 ? 'text-red-600' : 'text-green-600'}>
                      {solverResult.turnover_contribution >= 0 ? '+' : ''}{solverResult.turnover_contribution.toFixed(1)}%
                    </span>
                    <span className="text-gray-400 ml-1">
                      (turnover {solverResult.turnover_rate.toFixed(0)}%, growth {solverResult.workforce_growth_rate.toFixed(0)}%, new hires @ {solverResult.new_hire_comp_ratio.toFixed(0)}% avg)
                    </span>
                  </p>
                  <p className="text-xs mt-1">
                    <span className="font-medium">Net avg comp growth:</span>
                    <span className="font-semibold text-purple-700"> {solverResult.achieved_growth_rate.toFixed(1)}%</span>
                  </p>
                </div>
                {solverResult.recommended_scale_factor > 1.05 && (
                  <div className="mt-2 pt-2 border-t border-purple-100 bg-blue-50 -mx-3 px-3 py-2 rounded">
                    <p className="text-xs text-blue-800">
                      <span className="font-semibold">Recommendation:</span> With standard raises (~5%), hire at{' '}
                      <span className="font-bold">{solverResult.recommended_new_hire_ratio.toFixed(0)}%</span> of avg comp.
                      Use <span className="font-bold">{solverResult.recommended_scale_factor.toFixed(1)}x</span> scale in Job Level Compensation Ranges.
                    </p>
                  </div>
                )}
                {solverResult.warnings.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-purple-100">
                    {solverResult.warnings.map((warning, idx) => (
                      <p key={idx} className="text-xs text-amber-600 flex items-start gap-1">
                        <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                        {warning}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            {solverStatus === 'error' && (
              <div className="mt-3 p-2 bg-red-50 rounded border border-red-200">
                <p className="text-xs text-red-700 flex items-center gap-1">
                  <X className="h-3 w-3" />
                  {solverError}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">Annual Review</h3>
        <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
          <InputField label="Merit Budget" {...inputProps('meritBudget')} type="number" step="0.1" suffix="%" helper="Avg. annual performance increase" />
          <InputField label="COLA / Inflation" {...inputProps('colaRate')} type="number" step="0.1" suffix="%" helper="Cost of living adjustment" />
        </div>

        <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider pt-4">Promotions</h3>
        <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
          <InputField label="Avg. Promotion Increase" {...inputProps('promoIncrease')} type="number" step="0.5" suffix="%" helper="Base pay bump on promotion" />

          <div className="sm:col-span-3">
            <label className="block text-sm font-medium text-gray-700">Distribution Range</label>
            <div className="mt-1 relative rounded-md shadow-sm">
              <input
                type="number"
                step="0.5"
                name="promoDistributionRange"
                value={formData.promoDistributionRange}
                onChange={handleChange}
                className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
              />
              <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                <span className="text-gray-500 sm:text-sm">± %</span>
              </div>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Increases vary by ±{formData.promoDistributionRange}% (Range: {Number(formData.promoIncrease) - Number(formData.promoDistributionRange)}% - {Number(formData.promoIncrease) + Number(formData.promoDistributionRange)}%)
            </p>
          </div>

          <div className="col-span-6 h-px bg-gray-200 my-1"></div>

          <InputField label="Promotion Budget" {...inputProps('promoBudget')} type="number" step="0.1" suffix="% of payroll" helper="Budget allocated for level-ups" />

          <div className="col-span-6 h-px bg-gray-200 my-1"></div>

          <div className="col-span-6 sm:col-span-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Promotion Rate Multiplier
            </label>
            <div className="relative rounded-md shadow-sm">
              <input
                type="number"
                step="0.1"
                min="0"
                max="5"
                name="promoRateMultiplier"
                value={formData.promoRateMultiplier}
                onChange={handleChange}
                className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
              />
              <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                <span className="text-gray-500 sm:text-sm">×</span>
              </div>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Multiplier applied to seed promotion rates (1.0 = use defaults, 1.5 = 50% more promotions)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
