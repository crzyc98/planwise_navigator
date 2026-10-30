import { NumericInput } from './NumericInput';
import React, { useState } from 'react';
import { PieChart, DollarSign, Clock } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { CompensationInput } from './CompensationInput';
import { useSuggestionPreview } from './useSuggestionPreview';
import type { FormData } from './types';
import { analyzeAgeDistribution, analyzeCompensation, analyzePartTimePct, CompensationAnalysis } from '../../services/api';

const marketMultipliers: Record<string, { label: string; adjustment: number; description: string }> = {
  conservative: { label: 'Conservative', adjustment: -5, description: 'Below market (cost savings focus)' },
  baseline: { label: 'Baseline', adjustment: 0, description: 'At market (competitive positioning)' },
  competitive: { label: 'Competitive', adjustment: 5, description: 'Above market (talent attraction focus)' },
  aggressive: { label: 'Aggressive', adjustment: 10, description: 'Well above market (premium talent strategy)' },
};

export function NewHireSection({ variant = 'full' }: { variant?: 'full' | 'essentials' }) {
  const essentials = variant === 'essentials';
  const { formData, setFormData, handleChange, activeWorkspace, scenarioId, scenarioLoading } = useConfigContext();
  const [compLookbackYears, setCompLookbackYears] = useState<number>(4);
  const [compScaleFactor, setCompScaleFactor] = useState<number>(1.5);
  const [compScaleLocal, setCompScaleLocal] = useState<string>('1.5');
  const preview = useSuggestionPreview<{
    update: Partial<FormData>; description: string; before: string; after: string;
    analysis?: CompensationAnalysis;
  }>(JSON.stringify([formData, compLookbackYears, compScaleLocal, scenarioLoading]), JSON.stringify([activeWorkspace?.id, scenarioId]));
  // The three census buttons share one preview; show it beside the button that requested it.
  const [suggestionSource, setSuggestionSource] = useState<'age' | 'partTime' | 'comp' | null>(null);
  const suggest = (source: typeof suggestionSource, calculateValue: Parameters<typeof preview.calculate>[0]) => {
    setSuggestionSource(source);
    return preview.calculate(calculateValue);
  };
  const matchCensusLoading = preview.pending;
  const matchPartTimeLoading = preview.pending;
  const matchCompLoading = preview.pending;
  const compensationAnalysis = preview.value?.analysis;
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

  const handleMatchCensus = () => suggest('age', async () => {
    const result = await analyzeAgeDistribution(activeWorkspace.id, formData.censusDataPath);
    return {
      update: { newHireAgeDistribution: result.distribution.map(d => ({ age: d.age, weight: d.weight, description: d.description })) },
      description: `${result.analysis_type}; ${result.total_employees} employees, as of ${result.as_of_date} (${result.as_of_date_source}). ${result.fallback_notice || ''}`,
      before: formData.newHireAgeDistribution.map(row => `Age ${row.age}: ${(row.weight * 100).toFixed(1)}%`).join('; '),
      after: result.distribution.map(row => `Age ${row.age}: ${(row.weight * 100).toFixed(1)}%`).join('; '),
    };
  });

  const handleMatchPartTime = () => suggest('partTime', async () => {
    const result = await analyzePartTimePct(activeWorkspace.id, formData.censusDataPath);
    if (!result.column_present) throw new Error('Census file has no scheduled hours column.');
    const percentage = Math.round(result.part_time_pct * 1000) / 10;
    return {
      update: { partTimeNewHirePct: percentage },
      description: `Scheduled hours analysis: ${result.part_time_count} part-time employees / ${result.headcount} active employees. Annual hours below 1,000 identify part-time employees.`,
      before: `Part-time new hires: ${formData.partTimeNewHirePct}%`,
      after: `Part-time new hires: ${percentage}%`,
    };
  });

  const handleMatchCompensation = () => suggest('comp', async () => {
    const result = await analyzeCompensation(activeWorkspace.id, formData.censusDataPath, compLookbackYears);
    const levels = result.has_level_data
      ? result.levels?.map(row => ({ level: row.level, name: row.name, minComp: Math.round(row.min_compensation * compScaleFactor), maxComp: Math.round(row.max_compensation * compScaleFactor) }))
      : result.suggested_levels?.map(row => ({ level: row.level, name: row.name, minComp: Math.round(row.suggested_min * compScaleFactor), maxComp: Math.round(row.suggested_max * compScaleFactor) }));
    if (!levels?.length) throw new Error(result.message || 'No compensation ranges could be derived.');
    const describe = (rows: typeof levels) => rows.map(row => `${row.name}: $${row.minComp.toLocaleString()}–$${row.maxComp.toLocaleString()}`).join('; ');
    return {
      update: { jobLevelCompensation: levels }, analysis: result,
      description: `${result.analysis_type}; ${result.total_employees} employees. Lookback: ${compLookbackYears === 0 ? 'all employees' : `last ${compLookbackYears} years`}; scaling: ${compScaleFactor}×. ${result.message || ''}`,
      before: describe(formData.jobLevelCompensation), after: describe(levels),
    };
  });

  const suggestionPanel = (source: typeof suggestionSource) => source === suggestionSource && (<>
    {preview.error && <p role="alert" className="text-sm text-danger-ink">{preview.error}</p>}
    {preview.value && <div className="bg-info-surface rounded-lg border border-info-border p-4 space-y-2" aria-label="Census suggestion preview">
      <h3 className="font-medium text-info-ink">Census suggestion — not applied</h3>
      <p className="text-xs text-info-ink">Source: {formData.censusDataPath}. {preview.value.description}</p>
      {preview.stale && <p role="status" className="text-sm text-warning-ink">Needs recalculation: inputs have changed.</p>}
      <p className="text-sm text-ink"><strong>Current draft:</strong> {preview.value.before}</p>
      <p className="text-sm text-ink"><strong>Suggested:</strong> {preview.value.after}</p>
      <div className="flex gap-2">
        <button type="button" disabled={preview.stale} onClick={() => preview.apply(value => setFormData(previous => ({ ...previous, ...value.update })))} className="px-3 py-2 rounded bg-info-solid text-ink-inverse text-sm disabled:opacity-50">Apply census suggestion</button>
        <button type="button" onClick={preview.cancel} className="px-3 py-2 rounded border border-border text-sm">Cancel</button>
      </div>
    </div>}
  </>);

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">New-hire assumptions</h2>
        <p className="text-sm text-ink-muted">Review age profile, pay ranges, part-time share and market assumptions for new hires.</p>
      </div>


      <div className="space-y-2">
        <label htmlFor="newhire-salary-growth" className="block text-sm font-medium text-ink">Annual starting-pay growth (%)</label>
        <div className="flex items-center gap-2">
          <NumericInput id="newhire-salary-growth" type="number" min="0" max="25" step="0.1" value={formData.newHireSalaryGrowthPercent} onChange={(e) => setFormData(prev => ({ ...prev, newHireSalaryGrowthPercent: parseFloat(e.target.value) }))} className="focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-border rounded-md p-2" />
          <button type="button" onClick={() => setFormData(prev => ({ ...prev, newHireSalaryGrowthPercent: prev.colaRate }))} className="px-3 py-2 rounded bg-surface-disabled text-sm whitespace-nowrap">Match COLA</button>
        </div>
        <p className="text-xs text-ink-muted">Raises new-hire salary ranges each year after the first simulation year. Ranges are entered in first-year dollars.</p>
      </div>

      <div className="space-y-4">
        {!essentials && (<fieldset disabled className="space-y-4">
        <legend className="text-sm font-medium text-ink">Legacy offer controls (unsupported)</legend>
        <p className="text-xs text-ink-muted">Strategy, target percentile and offer variance are retained from configuration but are not used by the current engine. These values are read-only.</p>
        {/* Strategy Selector */}
        <div className="flex items-center space-x-4 mb-6">
          <label htmlFor="newhire-strategy-percentile" className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors w-1/2 ${formData.newHireStrategy === 'percentile' ? 'bg-success-surface border-fidelity-green ring-1 ring-fidelity-green' : 'bg-surface-raised border-border hover:bg-surface-subtle'}`}>
            <input id="newhire-strategy-percentile" type="radio" name="newHireStrategy" value="percentile" checked={formData.newHireStrategy === 'percentile'} onChange={handleChange} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-border-strong" />
            <div className="ml-3">
              <span className="block text-sm font-medium text-ink">Percentile Based</span>
              <span className="block text-xs text-ink-muted">Offers target market percentiles (e.g., P50)</span>
            </div>
          </label>
          <label htmlFor="newhire-strategy-fixed" className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors w-1/2 ${formData.newHireStrategy === 'fixed' ? 'bg-success-surface border-fidelity-green ring-1 ring-fidelity-green' : 'bg-surface-raised border-border hover:bg-surface-subtle'}`}>
            <input id="newhire-strategy-fixed" type="radio" name="newHireStrategy" value="fixed" checked={formData.newHireStrategy === 'fixed'} onChange={handleChange} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-border-strong" />
            <div className="ml-3">
              <span className="block text-sm font-medium text-ink">Fixed Bands</span>
              <span className="block text-xs text-ink-muted">Offers use rigid salary structures</span>
            </div>
          </label>
        </div>

        {/* Percentile Options */}
        {formData.newHireStrategy === 'percentile' && (
          <div className="bg-info-surface p-6 rounded-lg border border-info-border space-y-4">
            <div>
              <label htmlFor="newhire-target-percentile" className="block text-sm font-medium text-info-ink mb-2">Target Market Percentile</label>
              <div className="flex items-center">
                <input id="newhire-target-percentile" type="range" min="0" max="100" value={formData.targetPercentile} onChange={(e) => setFormData({...formData, targetPercentile: parseInt(e.target.value)})} className="w-full h-2 bg-info-surface rounded-lg appearance-none cursor-pointer" />
                <span className="ml-4 font-bold text-info-ink w-12">P{formData.targetPercentile}</span>
              </div>
              <p className="text-xs text-info-ink mt-2">Retained target percentile: {formData.targetPercentile}. This setting does not affect current engine outputs.</p>
            </div>
            <div className="grid grid-cols-2 gap-4 pt-2">
              <div>
                <label htmlFor="newhire-offer-variance" className="block text-sm font-medium text-info-ink mb-1">Offer Variance</label>
                <div className="relative rounded-md shadow-sm">
                  <NumericInput id="newhire-offer-variance" type="number" step="0.5" value={formData.newHireCompVariance} onChange={(e) => setFormData({...formData, newHireCompVariance: parseFloat(e.target.value)})} className="focus:ring-focus focus:border-info-border block w-full sm:text-sm border-info-border rounded-md p-2" />
                  <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                    <span className="text-info-ink sm:text-sm">± %</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
        </fieldset>)}

        {/* E082: Age Distribution Section */}
        <div className="bg-surface-subtle p-6 rounded-lg border border-border mt-6">
          <div className="flex flex-wrap gap-3 items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-ink">New Hire Age Profile</h3>
            <button
              type="button"
              onClick={handleMatchCensus}
              disabled={matchCensusLoading || !formData.censusDataPath || formData.censusDataStatus !== 'loaded' || scenarioLoading}
              className={`inline-flex items-center px-3 py-1.5 border rounded-md text-xs font-medium transition-colors ${(formData.censusDataPath && formData.censusDataStatus === 'loaded') ? 'bg-info-surface border-info-border text-info-ink hover:bg-info-surface' : 'bg-surface-subtle border-border text-ink-subtle cursor-not-allowed'}`}
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
              ) : (
                <><PieChart className="h-3 w-3 mr-1" /> Suggest from census</>
              )}
            </button>
          </div>
          <p className="text-xs text-ink-muted mb-4">
            Define the age distribution for new hires. Weights should sum to 100%.
            {formData.censusDataStatus === 'loaded' && (
              <span className="text-info-ink ml-1">Click "Suggest from census" to preview values from your workforce.</span>
            )}
          </p>
          {suggestionPanel('age')}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-surface-subtle">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Age</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Weight (%)</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Description</th>
                </tr>
              </thead>
              <tbody className="bg-surface-raised divide-y divide-border">
                {formData.newHireAgeDistribution.map((row, idx) => (
                  <tr key={row.age}>
                    <td className="px-4 py-2 text-sm text-ink font-medium">{row.age}</td>
                    <td className="px-4 py-2">
                      <NumericInput type="number" step="1" min="0" max="100" value={Number((row.weight * 100).toFixed(10))} onChange={(e) => handleAgeWeightChange(idx, e.target.value)} className="w-20 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-right" />
                    </td>
                    <td className="px-4 py-2 text-sm text-ink-muted">{row.description}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-surface-subtle">
                <tr>
                  <td className="px-4 py-2 text-sm font-semibold text-ink">Total</td>
                  <td className="px-4 py-2 text-sm font-semibold">
                    <span className={`${Math.abs(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) - 1) > 0.01 ? 'text-danger-ink' : 'text-success-ink'}`}>
                      {Math.round(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) * 100)}%
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-ink-muted">
                    {Math.abs(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) - 1) > 0.01 && (
                      <span className="text-danger-ink">Weights should sum to 100%</span>
                    )}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {!essentials && (<>
        {/* 093: Part-Time New Hires Section */}
        <div className="bg-surface-subtle p-6 rounded-lg border border-border mt-6">
          <div className="flex flex-wrap gap-3 items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-ink">Part-Time New Hires</h3>
            <button
              type="button"
              onClick={handleMatchPartTime}
              disabled={matchPartTimeLoading || !formData.censusDataPath || formData.censusDataStatus !== 'loaded' || scenarioLoading}
              className={`inline-flex items-center px-3 py-1.5 border rounded-md text-xs font-medium transition-colors ${(formData.censusDataPath && formData.censusDataStatus === 'loaded') ? 'bg-info-surface border-info-border text-info-ink hover:bg-info-surface' : 'bg-surface-subtle border-border text-ink-subtle cursor-not-allowed'}`}
              title={formData.censusDataStatus !== 'loaded' ? 'Load a census file first' : 'Analyze census to match current part-time workforce percentage'}
            >
              {matchPartTimeLoading ? (
                <>
                  <svg className="animate-spin -ml-0.5 mr-1.5 h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Analyzing...
                </>
              ) : (
                <><Clock className="h-3 w-3 mr-1" /> Suggest from census</>
              )}
            </button>
          </div>
          <p className="text-xs text-ink-muted mb-4">
            Fraction of new hires assigned a 20 hrs/week part-time schedule. Part-time employees accrue
            fewer annual hours, which affects 1,000-hour eligibility requirements.
            {formData.censusDataStatus === 'loaded' && (
              <span className="text-info-ink ml-1">Click "Suggest from census" to preview values from your workforce's scheduled hours.</span>
            )}
          </p>
          {suggestionPanel('partTime')}
          <div className="flex items-center space-x-3">
            <label htmlFor="part-time-new-hire-pct" className="text-sm font-medium text-ink-muted">
              Part-Time New Hire %
            </label>
            <NumericInput
              id="part-time-new-hire-pct"
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={formData.partTimeNewHirePct}
              onChange={(e) => setFormData(prev => ({ ...prev, partTimeNewHirePct: parseFloat(e.target.value) || 0 }))}
              className="w-24 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1.5 border text-right"
            />
            <span className="text-sm text-ink-muted">%</span>
          </div>
        </div>

        {/* E082: Level Distribution Section */}
        <fieldset disabled className="bg-surface-subtle p-6 rounded-lg border border-border mt-6">
          <legend className="text-sm font-semibold text-ink">Legacy level distribution (unsupported)</legend>
          <p className="text-xs text-ink-muted mb-4">Stored mode and percentages are retained for compatibility. They are not passed to the current engine and are read-only.</p>
          <div className="flex items-center space-x-4 mb-4">
            <label htmlFor="newhire-level-dist-adaptive" className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${formData.levelDistributionMode === 'adaptive' ? 'bg-success-surface border-fidelity-green ring-1 ring-fidelity-green' : 'bg-surface-raised border-border hover:bg-surface-subtle'}`}>
              <input id="newhire-level-dist-adaptive" type="radio" name="levelDistributionMode" value="adaptive" checked={formData.levelDistributionMode === 'adaptive'} onChange={(e) => setFormData({...formData, levelDistributionMode: e.target.value})} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-border-strong" />
              <div className="ml-2">
                <span className="block text-sm font-medium text-ink">Adaptive</span>
                <span className="block text-xs text-ink-muted">Maintain current workforce composition</span>
              </div>
            </label>
            <label htmlFor="newhire-level-dist-fixed" className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${formData.levelDistributionMode === 'fixed' ? 'bg-success-surface border-fidelity-green ring-1 ring-fidelity-green' : 'bg-surface-raised border-border hover:bg-surface-subtle'}`}>
              <input id="newhire-level-dist-fixed" type="radio" name="levelDistributionMode" value="fixed" checked={formData.levelDistributionMode === 'fixed'} onChange={(e) => setFormData({...formData, levelDistributionMode: e.target.value})} className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-border-strong" />
              <div className="ml-2">
                <span className="block text-sm font-medium text-ink">Fixed Percentages</span>
                <span className="block text-xs text-ink-muted">Specify exact distribution below</span>
              </div>
            </label>
          </div>

          {formData.levelDistributionMode === 'fixed' && (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-border">
                <thead className="bg-surface-subtle">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Level</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Name</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Percentage (%)</th>
                  </tr>
                </thead>
                <tbody className="bg-surface-raised divide-y divide-border">
                  {formData.newHireLevelDistribution.map((row, idx) => (
                    <tr key={row.level}>
                      <td className="px-4 py-2 text-sm text-ink font-medium">{row.level}</td>
                      <td className="px-4 py-2 text-sm text-ink-muted">{row.name}</td>
                      <td className="px-4 py-2">
                        <NumericInput type="number" step="1" min="0" max="100" value={row.percentage} onChange={(e) => handleLevelPercentageChange(idx, e.target.value)} className="w-20 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-border-strong rounded-md p-1 border text-right" />
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-surface-subtle">
                  <tr>
                    <td className="px-4 py-2 text-sm font-semibold text-ink" colSpan={2}>Total</td>
                    <td className="px-4 py-2 text-sm font-semibold">
                      <span className={`${Math.abs(formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0) - 100) > 1 ? 'text-danger-ink' : 'text-success-ink'}`}>
                        {formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0)}%
                      </span>
                      {Math.abs(formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0) - 100) > 1 && (
                        <span className="text-danger-ink text-xs ml-2">Should sum to 100%</span>
                      )}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {formData.levelDistributionMode === 'adaptive' && (
            <div className="bg-info-surface p-4 rounded-lg border border-info-border">
              <p className="text-sm text-info-ink">
                <strong>Retained adaptive mode:</strong> This legacy selection does not control current simulation outputs.
              </p>
            </div>
          )}
        </fieldset>
        </>)}

        {/* E082: Job Level Compensation Ranges */}
        <div className="bg-surface-subtle p-6 rounded-lg border border-border mt-6">
          <div className="flex flex-wrap gap-3 items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-ink">Job Level Compensation Ranges</h3>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1">
                <label htmlFor="newhire-comp-source" className="text-xs text-ink-muted">Source:</label>
                <select id="newhire-comp-source" value={compLookbackYears} onChange={(e) => setCompLookbackYears(parseInt(e.target.value))} className="text-xs border border-border-strong rounded px-1.5 py-1 bg-surface-raised focus:ring-focus focus:border-info-border">
                  <option value={0}>All employees</option>
                  <option value={1}>Last 1 year</option>
                  <option value={2}>Last 2 years</option>
                  <option value={3}>Last 3 years</option>
                  <option value={4}>Last 4 years</option>
                  <option value={5}>Last 5 years</option>
                </select>
              </div>
              <div className="flex items-center gap-1">
                <label htmlFor="newhire-comp-scale" className="text-xs text-ink-muted">Scale:</label>
                <NumericInput
                  id="newhire-comp-scale"
                  type="number"
                  value={compScaleLocal}
                  onChange={(e) => setCompScaleLocal(e.target.value)}
                  onBlur={() => {
                    const val = parseFloat(compScaleLocal);
                    if (!Number.isFinite(val) || val < 0.5 || val > 3) return;
                    setCompScaleFactor(val);
                    setCompScaleLocal(String(val));
                  }}
                  onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                  min={0.5} max={3.0} step={0.1}
                  className="text-xs border border-border-strong rounded px-1.5 py-1 w-16 bg-surface-raised focus:ring-focus focus:border-info-border"
                  title="Scale up ranges to match tenured employee compensation levels (0.5x - 3.0x)"
                />
                <span className="text-xs text-ink-subtle">x</span>
              </div>
              <button
                type="button"
                onClick={handleMatchCompensation}
                disabled={matchCompLoading || !formData.censusDataPath || formData.censusDataStatus !== 'loaded' || scenarioLoading}
                className={`inline-flex items-center px-3 py-1.5 border rounded-md text-xs font-medium transition-colors ${(formData.censusDataPath && formData.censusDataStatus === 'loaded') ? 'bg-info-surface border-info-border text-info-ink hover:bg-info-surface' : 'bg-surface-subtle border-border text-ink-subtle cursor-not-allowed'}`}
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
                ) : (
                  <><DollarSign className="h-3 w-3 mr-1" /> Suggest from census</>
                )}
              </button>
            </div>
          </div>
          <p className="text-xs text-ink-muted mb-4">
            Define min/max compensation for each job level. Used for new hire offers.
            {formData.censusDataStatus === 'loaded' && (
              <span className="text-info-ink ml-1">Select lookback period and click "Suggest from census" to derive ranges from recent hire data.</span>
            )}
          </p>
          {suggestionPanel('comp')}
          {compensationAnalysis && (
            <div className={`mb-4 p-2 rounded text-xs ${compensationAnalysis.recent_hires_only ? 'bg-info-surface border border-info-border text-info-ink' : 'bg-warning-surface border border-warning-border text-warning-ink'}`}>
              <strong>Analysis:</strong> {compensationAnalysis.analysis_type} ({compensationAnalysis.total_employees} employees)
              {compensationAnalysis.message && <div className="mt-1">{compensationAnalysis.message}</div>}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-surface-subtle">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Level</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Name</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Min Compensation ($)</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Max Compensation ($)</th>
                </tr>
              </thead>
              <tbody className="bg-surface-raised divide-y divide-border">
                {formData.jobLevelCompensation.map((row, idx) => {
                  const hasRangeError = row.minComp > row.maxComp && row.minComp > 0 && row.maxComp > 0;
                  return (
                    <React.Fragment key={row.level}>
                      <tr>
                        <td className="px-4 py-2 text-sm text-ink font-medium">{row.level}</td>
                        <td className="px-4 py-2 text-sm text-ink-muted">{row.name}</td>
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
                            <span className="text-xs text-danger-ink">Min exceeds max</span>
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

        {!essentials && (<>
        {/* E082: Market Positioning Section */}
        <div className="bg-surface-subtle p-6 rounded-lg border border-border mt-6">
          <h3 className="text-sm font-semibold text-ink mb-2">Market Positioning</h3>
          <p className="text-xs text-ink-muted mb-4">Choose your overall compensation strategy relative to market rates.</p>
          <div className="flex gap-2 mb-4">
            {(['conservative', 'baseline', 'competitive', 'aggressive'] as const).map(scenario => (
              <button
                key={scenario}
                type="button"
                onClick={() => setFormData(prev => ({...prev, marketScenario: scenario}))}
                className={`px-3 py-2 rounded ${formData.marketScenario === scenario ? 'bg-success-solid text-ink-inverse' : 'bg-surface-disabled'}`}
              >
                {marketMultipliers[scenario].label} ({marketMultipliers[scenario].adjustment >= 0 ? '+' : ''}{marketMultipliers[scenario].adjustment}%)
              </button>
            ))}
          </div>
          <div className="bg-info-surface p-3 rounded-lg border border-info-border mb-4">
            <p className="text-xs text-info-ink">
              <strong>{marketMultipliers[formData.marketScenario]?.label || 'Baseline'}:</strong>{' '}
              {marketMultipliers[formData.marketScenario]?.description || 'At market (competitive positioning)'}
            </p>
          </div>
          <fieldset disabled className="mt-4">
            <h4 className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-3">Level-Specific Adjustments</h4>
            <p className="text-xs text-ink-muted mb-3">Level-specific adjustments are retained but have no current engine consumer. They are read-only.</p>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {(formData.levelMarketAdjustments || []).map((row, idx) => (
                <div key={row.level} className="bg-surface-raised p-2 rounded border border-border">
                  <label htmlFor={`newhire-level-adj-${row.level}`} className="block text-xs text-ink-muted mb-1 text-center">Level {row.level}</label>
                  <div className="relative">
                    <NumericInput id={`newhire-level-adj-${row.level}`} type="number" step="1" value={row.adjustment} onChange={(e) => handleLevelAdjustmentChange(idx, e.target.value)} className="w-full shadow-sm focus:ring-fidelity-green focus:border-fidelity-green text-xs border-border-strong rounded-md p-1 border text-center" />
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-subtle text-xs">%</span>
                  </div>
                </div>
              ))}
            </div>
          </fieldset>
        </div>

        {/* Promotion hazards are grouped with advanced workforce settings. */}
        </>)}
      </div>
    </div>
  );
}
