import { useState } from 'react';
import { HelpCircle, BarChart3, AlertTriangle, CheckCircle } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { analyzeTurnoverRates, TurnoverAnalysisResult } from '../../services/api';
import { useSuggestionPreview } from './useSuggestionPreview';

export function TurnoverSection({ variant = 'full' }: { variant?: 'full' | 'essentials' }) {
  const { formData, setFormData, inputProps, activeWorkspace, scenarioId, scenarioLoading } = useConfigContext();
  const essentials = variant === 'essentials';

  const [asOfYear, setAsOfYear] = useState('');
  const preview = useSuggestionPreview<TurnoverAnalysisResult>(JSON.stringify([formData, asOfYear, scenarioLoading]), JSON.stringify([activeWorkspace?.id, scenarioId]));
  const { value: analysis, pending: analyzing, error: analysisError } = preview;

  const handleMatchCensus = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) return;
    await preview.calculate(() => analyzeTurnoverRates(
        activeWorkspace.id,
        formData.censusDataPath,
        asOfYear ? `${asOfYear}-12-31` : undefined,
      ));
  };

  const handleApplySuggestions = () => {
    preview.apply(analysis => setFormData(prev => ({
      ...prev,
      ...(analysis.experienced_rate ? { totalTerminationRate: parseFloat((analysis.experienced_rate.rate * 100).toFixed(1)) } : {}),
      ...(analysis.new_hire_rate ? { newHireTerminationRate: parseFloat((analysis.new_hire_rate.rate * 100).toFixed(1)) } : {}),
    })));
  };

  const confidenceBadge = (confidence: string) => {
    const colors = {
      high: 'bg-success-surface text-success-ink',
      moderate: 'bg-warning-surface text-warning-ink',
      low: 'bg-danger-surface text-danger-ink',
    };
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[confidence as keyof typeof colors] || colors.low}`}>
        {confidence === 'low' && <AlertTriangle size={10} className="mr-1" />}
        {confidence === 'high' && <CheckCircle size={10} className="mr-1" />}
        {confidence} confidence
      </span>
    );
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">Headcount and turnover</h2>
        <p className="text-sm text-ink-muted">Headcount growth sets the annual net target. Hiring also replaces employee exits, so total hiring can exceed the growth target.</p>
      </div>

      {/* Core Workforce Parameters */}
      <div className="bg-surface-subtle rounded-lg p-4 border border-border">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h4 className="text-sm font-semibold text-ink">Annual assumptions</h4>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-warning-ink">Census year
              <input value={asOfYear} onChange={(event) => setAsOfYear(event.target.value)} placeholder="Inferred" inputMode="numeric" className="ml-1 w-20 rounded border border-warning-border bg-surface-raised px-2 py-1 text-sm" />
            </label>
            <button
              onClick={handleMatchCensus}
              disabled={analyzing || !formData.censusDataPath || scenarioLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-warning-solid text-ink-inverse rounded-lg hover:bg-warning-solid-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title={!formData.censusDataPath ? 'Upload a census file first' : 'Analyze census to suggest termination rates'}
            >
              <BarChart3 size={14} />
              {analyzing ? 'Analyzing...' : 'Suggest from census'}
            </button>
          </div>
        </div>

        {/* Error message */}
        {analysisError && (
          <div className="mb-3 p-3 bg-danger-surface border border-danger-border rounded-lg">
            <p className="text-sm text-danger-ink">{analysisError}</p>
            <button onClick={preview.cancel} className="mt-1 text-xs text-danger-ink hover:text-danger-ink underline">
              Dismiss
            </button>
          </div>
        )}

        {/* Suggestion panel */}
        {analysis && (
          <div className="mb-4 bg-info-surface border border-info-border rounded-lg p-4">
            {preview.stale && <p role="status" className="text-warning-ink text-sm mb-2">Needs recalculation: inputs have changed.</p>}
            <p className="text-xs text-info-ink mb-2">Source: {formData.censusDataPath}. Rates use the census analysis exposure window; review sample counts and confidence before applying.</p>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex-1">
                <h4 className="text-info-ink font-medium">Suggested Termination Rates</h4>
                <p className="text-sm text-info-ink mt-1">
                  Based on {analysis.total_employees.toLocaleString()} employees ({analysis.total_terminated.toLocaleString()} terminated)
                  {' '}as of {analysis.as_of_date} ({analysis.as_of_date_source})
                </p>
              </div>
              <div className="flex gap-2 ml-4">
                <button onClick={preview.cancel}
                  className="px-3 py-1.5 text-sm text-ink-muted bg-surface-raised border border-border-strong rounded-lg hover:bg-surface-subtle">
                  Cancel
                </button>
                {(analysis.experienced_rate || analysis.new_hire_rate) && (
                  <button onClick={handleApplySuggestions} disabled={preview.stale}
                    className="px-3 py-1.5 text-sm bg-info-solid text-ink-inverse rounded-lg hover:bg-info-solid-hover">
                    Apply suggested rates
                  </button>
                )}
              </div>
            </div>

            {/* Info message when no rates could be derived */}
            {analysis.message && !analysis.experienced_rate && !analysis.new_hire_rate && (
              <div className="mt-3 p-3 bg-warning-surface border border-warning-border rounded-lg">
                <p className="text-sm text-warning-ink">{analysis.message}</p>
              </div>
            )}

            {/* Rate suggestions table */}
            {(analysis.experienced_rate || analysis.new_hire_rate) && (
              <div className="mt-3">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-info-border">
                      <th className="text-left py-2 text-info-ink font-medium">Rate</th>
                      <th className="text-right py-2 text-info-ink font-medium">Suggested</th>
                      <th className="text-right py-2 text-info-ink font-medium">Current</th>
                      <th className="text-right py-2 text-info-ink font-medium">Sample</th>
                      <th className="text-left py-2 pl-3 text-info-ink font-medium">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.experienced_rate && (
                      <tr className="border-b border-info-border">
                        <td className="py-2 text-info-ink">Experienced</td>
                        <td className="py-2 text-right font-semibold text-info-ink">
                          {(analysis.experienced_rate.rate * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-ink-muted">
                          {Number(formData.totalTerminationRate).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-info-ink">
                          {analysis.experienced_rate.terminated_count} / {analysis.experienced_rate.sample_size}
                        </td>
                        <td className="py-2 pl-3">
                          {confidenceBadge(analysis.experienced_rate.confidence)}
                        </td>
                      </tr>
                    )}
                    {analysis.new_hire_rate && (
                      <tr>
                        <td className="py-2 text-info-ink">New Hire</td>
                        <td className="py-2 text-right font-semibold text-info-ink">
                          {(analysis.new_hire_rate.rate * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-ink-muted">
                          {Number(formData.newHireTerminationRate).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-info-ink">
                          {analysis.new_hire_rate.terminated_count} / {analysis.new_hire_rate.sample_size}
                        </td>
                        <td className="py-2 pl-3">
                          {confidenceBadge(analysis.new_hire_rate.confidence)}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>

                {/* Partial results message */}
                {analysis.message && (
                  <p className="mt-2 text-xs text-info-ink italic">{analysis.message}</p>
                )}

                {/* Low confidence warning */}
                {((analysis.experienced_rate?.confidence === 'low') || (analysis.new_hire_rate?.confidence === 'low')) && (
                  <div className="mt-2 flex items-start gap-1.5 text-xs text-warning-ink bg-warning-surface rounded p-2">
                    <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
                    <span>
                      Small sample size (&lt;10 terminated employees). Suggested rates may not be statistically reliable.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
          {essentials && <InputField label="Annual headcount growth" {...inputProps('targetGrowthRate')} type="number" step="0.1" suffix="%" helper="Net workforce growth target, in addition to replacement hiring." />}
          <InputField
            label="Experienced-employee turnover"
            {...inputProps('totalTerminationRate')}
            type="number"
            step="0.1"
            suffix="%"
            helper="Overall annual termination rate for experienced employees"
          />
          <InputField
            label="New-hire turnover assumption"
            {...inputProps('newHireTerminationRate')}
            type="number"
            step="0.1"
            suffix="%"
            helper="Also affects prior-year surviving hires in later-year workforce planning."
          />
        </div>
      </div>

      <div className="bg-info-surface rounded-lg p-4 border border-info-border">
        <h4 className="text-sm font-medium text-info-ink mb-2 flex items-center">
          <HelpCircle size={16} className="mr-2 text-info-ink"/> Calculated Projection
        </h4>
        <p className="text-sm text-info-ink">
          Based on these inputs, an organization of 1,000 employees will see approximately <span className="font-bold">{Math.round(1000 * (Number(formData.totalTerminationRate) / 100))}</span> experienced employee exits per year, plus <span className="font-bold">{Math.round(100 * (Number(formData.newHireTerminationRate) / 100))}</span> first-year exits per 100 new hires.
        </p>
      </div>

      {!essentials && (
      <div className="bg-surface-subtle rounded-lg p-4 border border-border">
        <h4 className="text-sm font-medium text-ink-muted mb-2">How Termination Works</h4>
        <p className="text-xs text-ink-muted">
          The simulation uses deterministic termination selection based on workforce growth targets.
          Employees are selected for termination to achieve the configured termination rates while
          maintaining workforce growth objectives. Hazard-based modeling (age/tenure multipliers)
          is available in the analytics layer for reporting purposes.
        </p>
      </div>
      )}
    </div>
  );
}
