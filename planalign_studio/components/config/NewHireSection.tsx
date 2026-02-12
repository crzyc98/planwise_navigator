import React, { useState } from 'react';
import { Check, PieChart, DollarSign } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { CompensationInput } from './CompensationInput';
import { PromotionHazardEditor } from './PromotionHazardEditor';
import { analyzeAgeDistribution, analyzeCompensation, CompensationAnalysis } from '../../services/api';

const marketMultipliers: Record<string, { label: string; adjustment: number; description: string }> = {
  conservative: { label: 'Conservative', adjustment: -5, description: 'Below market (cost savings focus)' },
  baseline: { label: 'Baseline', adjustment: 0, description: 'At market (competitive positioning)' },
  competitive: { label: 'Competitive', adjustment: 5, description: 'Above market (talent attraction focus)' },
  aggressive: { label: 'Aggressive', adjustment: 10, description: 'Well above market (premium talent strategy)' },
};

export function NewHireSection() {
  const { formData, setFormData, handleChange, activeWorkspace } = useConfigContext();

  // E082: Match Census state (age distribution)
  const [matchCensusLoading, setMatchCensusLoading] = useState(false);
  const [matchCensusError, setMatchCensusError] = useState<string | null>(null);
  const [matchCensusSuccess, setMatchCensusSuccess] = useState(false);

  // E082: Match Census state (compensation)
  const [matchCompLoading, setMatchCompLoading] = useState(false);
  const [matchCompError, setMatchCompError] = useState<string | null>(null);
  const [matchCompSuccess, setMatchCompSuccess] = useState(false);
  const [compensationAnalysis, setCompensationAnalysis] = useState<CompensationAnalysis | null>(null);
  const [compLookbackYears, setCompLookbackYears] = useState<number>(4);
  const [compScaleFactor, setCompScaleFactor] = useState<number>(1.5);
  const [compScaleLocal, setCompScaleLocal] = useState<string>('1.5');

  const handleAgeWeightChange = (index: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      newHireAgeDistribution: prev.newHireAgeDistribution.map((row, i) =>
        i === index ? { ...row, weight: parseFloat(value) / 100 || 0 } : row
      )
    }));
  };

  const handleLevelPercentageChange = (index: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      newHireLevelDistribution: prev.newHireLevelDistribution.map((row, i) =>
        i === index ? { ...row, percentage: parseFloat(value) || 0 } : row
      )
    }));
  };

  const handleJobLevelCompChange = (index: number, field: 'minComp' | 'maxComp', value: string) => {
    setFormData(prev => ({
      ...prev,
      jobLevelCompensation: prev.jobLevelCompensation.map((row, i) =>
        i === index ? { ...row, [field]: parseFloat(value) || 0 } : row
      )
    }));
  };

  const handleLevelAdjustmentChange = (index: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      levelMarketAdjustments: prev.levelMarketAdjustments.map((row, i) =>
        i === index ? { ...row, adjustment: parseFloat(value) || 0 } : row
      )
    }));
  };

  const handleMatchCensus = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) {
      setMatchCensusError('Please upload a census file first');
      return;
    }
    setMatchCensusLoading(true);
    setMatchCensusError(null);
    setMatchCensusSuccess(false);
    try {
      const result = await analyzeAgeDistribution(activeWorkspace.id, formData.censusDataPath);
      setFormData(prev => ({
        ...prev,
        newHireAgeDistribution: result.distribution.map(d => ({
          age: d.age,
          weight: d.weight,
          description: d.description,
        }))
      }));
      setMatchCensusSuccess(true);
      setTimeout(() => setMatchCensusSuccess(false), 3000);
    } catch (error) {
      console.error('Failed to analyze census:', error);
      setMatchCensusError(error instanceof Error ? error.message : 'Failed to analyze census');
    } finally {
      setMatchCensusLoading(false);
    }
  };

  const handleMatchCompensation = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) {
      setMatchCompError('Please upload a census file first');
      return;
    }
    setMatchCompLoading(true);
    setMatchCompError(null);
    setMatchCompSuccess(false);
    try {
      const result = await analyzeCompensation(activeWorkspace.id, formData.censusDataPath, compLookbackYears);
      setCompensationAnalysis(result);
      const scale = compScaleFactor;
      if (!result.has_level_data && result.suggested_levels) {
        setFormData(prev => ({
          ...prev,
          jobLevelCompensation: result.suggested_levels!.map(sl => ({
            level: sl.level,
            name: sl.name,
            minComp: Math.round(sl.suggested_min * scale),
            maxComp: Math.round(sl.suggested_max * scale),
          }))
        }));
        setMatchCompSuccess(true);
        setTimeout(() => setMatchCompSuccess(false), 3000);
      } else if (result.has_level_data && result.levels) {
        setFormData(prev => ({
          ...prev,
          jobLevelCompensation: result.levels!.map(l => ({
            level: l.level,
            name: l.name,
            minComp: Math.round(l.min_compensation * scale),
            maxComp: Math.round(l.max_compensation * scale),
          }))
        }));
        setMatchCompSuccess(true);
        setTimeout(() => setMatchCompSuccess(false), 3000);
      }
    } catch (error) {
      console.error('Failed to analyze compensation:', error);
      setMatchCompError(error instanceof Error ? error.message : 'Failed to analyze compensation');
    } finally {
      setMatchCompLoading(false);
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">New Hire Compensation</h2>
        <p className="text-sm text-gray-500">Define how offers are constructed for external candidates.</p>
      </div>

      <div className="space-y-4">
        {/* Strategy Selector */}
        <div className="flex items-center space-x-4 mb-6">
          <label className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors w-1/2 ${formData.newHireStrategy === 'percentile' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
            <input type="radio" name="newHireStrategy" value="percentile" checked={formData.newHireStrategy === 'percentile'} onChange={handleChange} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300" />
            <div className="ml-3">
              <span className="block text-sm font-medium text-gray-900">Percentile Based</span>
              <span className="block text-xs text-gray-500">Offers target market percentiles (e.g., P50)</span>
            </div>
          </label>
          <label className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors w-1/2 ${formData.newHireStrategy === 'fixed' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
            <input type="radio" name="newHireStrategy" value="fixed" checked={formData.newHireStrategy === 'fixed'} onChange={handleChange} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300" />
            <div className="ml-3">
              <span className="block text-sm font-medium text-gray-900">Fixed Bands</span>
              <span className="block text-xs text-gray-500">Offers use rigid salary structures</span>
            </div>
          </label>
        </div>

        {/* Percentile Options */}
        {formData.newHireStrategy === 'percentile' && (
          <div className="bg-blue-50 p-6 rounded-lg border border-blue-100 space-y-4">
            <div>
              <label className="block text-sm font-medium text-blue-900 mb-2">Target Market Percentile</label>
              <div className="flex items-center">
                <input type="range" min="0" max="100" value={formData.targetPercentile} onChange={(e) => setFormData({...formData, targetPercentile: parseInt(e.target.value)})} className="w-full h-2 bg-blue-200 rounded-lg appearance-none cursor-pointer" />
                <span className="ml-4 font-bold text-blue-700 w-12">P{formData.targetPercentile}</span>
              </div>
              <p className="text-xs text-blue-600 mt-2">New hires will be offered salaries at the {formData.targetPercentile}th percentile.</p>
            </div>
            <div className="grid grid-cols-2 gap-4 pt-2">
              <div>
                <label className="block text-sm font-medium text-blue-900 mb-1">Offer Variance</label>
                <div className="relative rounded-md shadow-sm">
                  <input type="number" step="0.5" value={formData.newHireCompVariance} onChange={(e) => setFormData({...formData, newHireCompVariance: parseFloat(e.target.value)})} className="focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-blue-300 rounded-md p-2" />
                  <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                    <span className="text-blue-500 sm:text-sm">± %</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* E082: Age Distribution Section */}
        <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-900">New Hire Age Profile</h3>
            <button
              type="button"
              onClick={handleMatchCensus}
              disabled={matchCensusLoading || !formData.censusDataPath || formData.censusDataStatus !== 'loaded'}
              className={`inline-flex items-center px-3 py-1.5 border rounded-md text-xs font-medium transition-colors ${
                matchCensusSuccess
                  ? 'bg-green-100 border-green-300 text-green-800'
                  : (formData.censusDataPath && formData.censusDataStatus === 'loaded')
                    ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                    : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
              }`}
              title={formData.censusDataStatus !== 'loaded' ? 'Load a census file first' : 'Analyze census to match current workforce age distribution'}
            >
              {matchCensusLoading ? (
                <>
                  <svg className="animate-spin -ml-0.5 mr-1.5 h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Analyzing...
                </>
              ) : matchCensusSuccess ? (
                <><Check className="h-3 w-3 mr-1" /> Matched!</>
              ) : (
                <><PieChart className="h-3 w-3 mr-1" /> Match Census</>
              )}
            </button>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Define the age distribution for new hires. Weights should sum to 100%.
            {formData.censusDataStatus === 'loaded' && (
              <span className="text-blue-600 ml-1">Click "Match Census" to auto-fill based on your workforce.</span>
            )}
          </p>
          {matchCensusError && (
            <div className="mb-4 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">{matchCensusError}</div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-100">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Age</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Weight (%)</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {formData.newHireAgeDistribution.map((row, idx) => (
                  <tr key={row.age}>
                    <td className="px-4 py-2 text-sm text-gray-900 font-medium">{row.age}</td>
                    <td className="px-4 py-2">
                      <input type="number" step="1" min="0" max="100" value={Math.round(row.weight * 100)} onChange={(e) => handleAgeWeightChange(idx, e.target.value)} className="w-20 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-right" />
                    </td>
                    <td className="px-4 py-2 text-sm text-gray-500">{row.description}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-gray-50">
                <tr>
                  <td className="px-4 py-2 text-sm font-semibold text-gray-900">Total</td>
                  <td className="px-4 py-2 text-sm font-semibold">
                    <span className={`${Math.abs(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) - 1) > 0.01 ? 'text-red-600' : 'text-green-600'}`}>
                      {Math.round(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) * 100)}%
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500">
                    {Math.abs(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) - 1) > 0.01 && (
                      <span className="text-red-600">Weights should sum to 100%</span>
                    )}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {/* E082: Level Distribution Section */}
        <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-2">New Hire Level Distribution</h3>
          <p className="text-xs text-gray-500 mb-4">Choose how new hires are distributed across job levels.</p>
          <div className="flex items-center space-x-4 mb-4">
            <label className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${formData.levelDistributionMode === 'adaptive' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
              <input type="radio" name="levelDistributionMode" value="adaptive" checked={formData.levelDistributionMode === 'adaptive'} onChange={(e) => setFormData({...formData, levelDistributionMode: e.target.value as 'adaptive' | 'fixed'})} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300" />
              <div className="ml-2">
                <span className="block text-sm font-medium text-gray-900">Adaptive</span>
                <span className="block text-xs text-gray-500">Maintain current workforce composition</span>
              </div>
            </label>
            <label className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${formData.levelDistributionMode === 'fixed' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
              <input type="radio" name="levelDistributionMode" value="fixed" checked={formData.levelDistributionMode === 'fixed'} onChange={(e) => setFormData({...formData, levelDistributionMode: e.target.value as 'adaptive' | 'fixed'})} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300" />
              <div className="ml-2">
                <span className="block text-sm font-medium text-gray-900">Fixed Percentages</span>
                <span className="block text-xs text-gray-500">Specify exact distribution below</span>
              </div>
            </label>
          </div>

          {formData.levelDistributionMode === 'fixed' && (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-100">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Level</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Percentage (%)</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {formData.newHireLevelDistribution.map((row, idx) => (
                    <tr key={row.level}>
                      <td className="px-4 py-2 text-sm text-gray-900 font-medium">{row.level}</td>
                      <td className="px-4 py-2 text-sm text-gray-700">{row.name}</td>
                      <td className="px-4 py-2">
                        <input type="number" step="1" min="0" max="100" value={row.percentage} onChange={(e) => handleLevelPercentageChange(idx, e.target.value)} className="w-20 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-right" />
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-gray-50">
                  <tr>
                    <td className="px-4 py-2 text-sm font-semibold text-gray-900" colSpan={2}>Total</td>
                    <td className="px-4 py-2 text-sm font-semibold">
                      <span className={`${Math.abs(formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0) - 100) > 1 ? 'text-red-600' : 'text-green-600'}`}>
                        {formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0)}%
                      </span>
                      {Math.abs(formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0) - 100) > 1 && (
                        <span className="text-red-600 text-xs ml-2">Should sum to 100%</span>
                      )}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {formData.levelDistributionMode === 'adaptive' && (
            <div className="bg-blue-50 p-4 rounded-lg border border-blue-100">
              <p className="text-sm text-blue-800">
                <strong>Adaptive mode:</strong> New hires will be distributed across levels proportionally to match your current workforce composition. This maintains your existing organizational structure.
              </p>
            </div>
          )}
        </div>

        {/* E082: Job Level Compensation Ranges */}
        <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-900">Job Level Compensation Ranges</h3>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1">
                <label className="text-xs text-gray-500">Source:</label>
                <select value={compLookbackYears} onChange={(e) => setCompLookbackYears(parseInt(e.target.value))} className="text-xs border border-gray-300 rounded px-1.5 py-1 bg-white focus:ring-blue-500 focus:border-blue-500">
                  <option value={0}>All employees</option>
                  <option value={1}>Last 1 year</option>
                  <option value={2}>Last 2 years</option>
                  <option value={3}>Last 3 years</option>
                  <option value={4}>Last 4 years</option>
                  <option value={5}>Last 5 years</option>
                </select>
              </div>
              <div className="flex items-center gap-1">
                <label className="text-xs text-gray-500">Scale:</label>
                <input
                  type="number"
                  value={compScaleLocal}
                  onChange={(e) => setCompScaleLocal(e.target.value)}
                  onBlur={() => {
                    const val = parseFloat(compScaleLocal);
                    const clamped = isNaN(val) ? 1.5 : Math.min(3.0, Math.max(0.5, val));
                    setCompScaleFactor(clamped);
                    setCompScaleLocal(String(clamped));
                  }}
                  onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                  min={0.5} max={3.0} step={0.1}
                  className="text-xs border border-gray-300 rounded px-1.5 py-1 w-16 bg-white focus:ring-blue-500 focus:border-blue-500"
                  title="Scale up ranges to match tenured employee compensation levels (0.5x - 3.0x)"
                />
                <span className="text-xs text-gray-400">x</span>
              </div>
              <button
                type="button"
                onClick={handleMatchCompensation}
                disabled={matchCompLoading || !formData.censusDataPath || formData.censusDataStatus !== 'loaded'}
                className={`inline-flex items-center px-3 py-1.5 border rounded-md text-xs font-medium transition-colors ${
                  matchCompSuccess
                    ? 'bg-green-100 border-green-300 text-green-800'
                    : (formData.censusDataPath && formData.censusDataStatus === 'loaded')
                      ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                      : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                }`}
                title={formData.censusDataStatus !== 'loaded' ? 'Load a census file first' : 'Analyze census to suggest compensation ranges'}
              >
                {matchCompLoading ? (
                  <>
                    <svg className="animate-spin -ml-0.5 mr-1.5 h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Analyzing...
                  </>
                ) : matchCompSuccess ? (
                  <><Check className="h-3 w-3 mr-1" /> Applied!</>
                ) : (
                  <><DollarSign className="h-3 w-3 mr-1" /> Match Census</>
                )}
              </button>
            </div>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Define min/max compensation for each job level. Used for new hire offers.
            {formData.censusDataStatus === 'loaded' && (
              <span className="text-blue-600 ml-1">Select lookback period and click "Match Census" to derive ranges from recent hire data.</span>
            )}
          </p>
          {matchCompError && (
            <div className="mb-4 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">{matchCompError}</div>
          )}
          {compensationAnalysis && (
            <div className={`mb-4 p-2 rounded text-xs ${compensationAnalysis.recent_hires_only ? 'bg-blue-50 border border-blue-200 text-blue-700' : 'bg-yellow-50 border border-yellow-200 text-yellow-700'}`}>
              <strong>Analysis:</strong> {compensationAnalysis.analysis_type} ({compensationAnalysis.total_employees} employees)
              {compensationAnalysis.message && <div className="mt-1">{compensationAnalysis.message}</div>}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-100">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Level</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Min Compensation ($)</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Max Compensation ($)</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {formData.jobLevelCompensation.map((row, idx) => {
                  const hasRangeError = row.minComp > row.maxComp && row.minComp > 0 && row.maxComp > 0;
                  return (
                    <React.Fragment key={row.level}>
                      <tr>
                        <td className="px-4 py-2 text-sm text-gray-900 font-medium">{row.level}</td>
                        <td className="px-4 py-2 text-sm text-gray-700">{row.name}</td>
                        <td className="px-4 py-2">
                          <CompensationInput value={row.minComp} onCommit={(v) => handleJobLevelCompChange(idx, 'minComp', String(v))} hasError={hasRangeError} />
                        </td>
                        <td className="px-4 py-2">
                          <CompensationInput value={row.maxComp} onCommit={(v) => handleJobLevelCompChange(idx, 'maxComp', String(v))} hasError={hasRangeError} />
                        </td>
                      </tr>
                      {hasRangeError && (
                        <tr>
                          <td colSpan={4} className="px-4 pb-1 pt-0">
                            <span className="text-xs text-red-600">Min exceeds max</span>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* E082: Market Positioning Section */}
        <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Market Positioning</h3>
          <p className="text-xs text-gray-500 mb-4">Choose your overall compensation strategy relative to market rates.</p>
          <div className="flex gap-2 mb-4">
            {(['conservative', 'baseline', 'competitive', 'aggressive'] as const).map(scenario => (
              <button
                key={scenario}
                type="button"
                onClick={() => setFormData(prev => ({...prev, marketScenario: scenario}))}
                className={`px-3 py-2 rounded ${formData.marketScenario === scenario ? 'bg-green-500 text-white' : 'bg-gray-200'}`}
              >
                {marketMultipliers[scenario].label} ({marketMultipliers[scenario].adjustment >= 0 ? '+' : ''}{marketMultipliers[scenario].adjustment}%)
              </button>
            ))}
          </div>
          <div className="bg-blue-50 p-3 rounded-lg border border-blue-100 mb-4">
            <p className="text-xs text-blue-800">
              <strong>{marketMultipliers[formData.marketScenario]?.label || 'Baseline'}:</strong>{' '}
              {marketMultipliers[formData.marketScenario]?.description || 'At market (competitive positioning)'}
            </p>
          </div>
          <div className="mt-4">
            <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-3">Level-Specific Adjustments</h4>
            <p className="text-xs text-gray-500 mb-3">Fine-tune market positioning by job level (in addition to overall scenario).</p>
            <div className="grid grid-cols-5 gap-2">
              {(formData.levelMarketAdjustments || []).map((row, idx) => (
                <div key={row.level} className="bg-white p-2 rounded border border-gray-200">
                  <label className="block text-xs text-gray-500 mb-1 text-center">Level {row.level}</label>
                  <div className="relative">
                    <input type="number" step="1" value={row.adjustment} onChange={(e) => handleLevelAdjustmentChange(idx, e.target.value)} className="w-full shadow-sm focus:ring-fidelity-green focus:border-fidelity-green text-xs border-gray-300 rounded-md p-1 border text-center" />
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 038: Promotion Hazard Section */}
        <PromotionHazardEditor />
      </div>
    </div>
  );
}
