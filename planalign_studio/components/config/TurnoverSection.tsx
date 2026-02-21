import { useState } from 'react';
import { HelpCircle, BarChart3, AlertTriangle, CheckCircle } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { InputField } from './InputField';
import { analyzeTurnoverRates, TurnoverAnalysisResult } from '../../services/api';

export function TurnoverSection() {
  const { formData, setFormData, inputProps, activeWorkspace } = useConfigContext();

  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<TurnoverAnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const handleMatchCensus = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) {
      setAnalysisError('Please upload a census file first');
      return;
    }
    setAnalyzing(true);
    setAnalysis(null);
    setAnalysisError(null);
    try {
      const result = await analyzeTurnoverRates(activeWorkspace.id, formData.censusDataPath);
      setAnalysis(result);
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : 'Failed to analyze census for turnover rates');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleApplySuggestions = () => {
    if (!analysis) return;
    setFormData(prev => ({
      ...prev,
      ...(analysis.experienced_rate ? { totalTerminationRate: parseFloat((analysis.experienced_rate.rate * 100).toFixed(1)) } : {}),
      ...(analysis.new_hire_rate ? { newHireTerminationRate: parseFloat((analysis.new_hire_rate.rate * 100).toFixed(1)) } : {}),
    }));
    setAnalysis(null);
  };

  const confidenceBadge = (confidence: string) => {
    const colors = {
      high: 'bg-green-100 text-green-800',
      moderate: 'bg-yellow-100 text-yellow-800',
      low: 'bg-red-100 text-red-800',
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
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Workforce & Turnover</h2>
        <p className="text-sm text-gray-500">Model employee attrition rates and retention risks.</p>
      </div>

      {/* Core Workforce Parameters */}
      <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold text-orange-900 uppercase tracking-wider">Core Termination Rates</h4>
          <button
            onClick={handleMatchCensus}
            disabled={analyzing || !formData.censusDataPath}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title={!formData.censusDataPath ? 'Upload a census file first' : 'Analyze census to suggest termination rates'}
          >
            <BarChart3 size={14} />
            {analyzing ? 'Analyzing...' : 'Match Census'}
          </button>
        </div>

        {/* Error message */}
        {analysisError && (
          <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-700">{analysisError}</p>
            <button onClick={() => setAnalysisError(null)} className="mt-1 text-xs text-red-500 hover:text-red-700 underline">
              Dismiss
            </button>
          </div>
        )}

        {/* Suggestion panel */}
        {analysis && (
          <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h4 className="text-blue-800 font-medium">Suggested Termination Rates</h4>
                <p className="text-sm text-blue-600 mt-1">
                  Based on {analysis.total_employees.toLocaleString()} employees ({analysis.total_terminated.toLocaleString()} terminated)
                </p>
              </div>
              <div className="flex gap-2 ml-4">
                <button onClick={() => setAnalysis(null)}
                  className="px-3 py-1.5 text-sm text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
                  Cancel
                </button>
                {(analysis.experienced_rate || analysis.new_hire_rate) && (
                  <button onClick={handleApplySuggestions}
                    className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                    Apply Suggestions
                  </button>
                )}
              </div>
            </div>

            {/* Info message when no rates could be derived */}
            {analysis.message && !analysis.experienced_rate && !analysis.new_hire_rate && (
              <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">{analysis.message}</p>
              </div>
            )}

            {/* Rate suggestions table */}
            {(analysis.experienced_rate || analysis.new_hire_rate) && (
              <div className="mt-3">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-blue-200">
                      <th className="text-left py-2 text-blue-700 font-medium">Rate</th>
                      <th className="text-right py-2 text-blue-700 font-medium">Suggested</th>
                      <th className="text-right py-2 text-blue-700 font-medium">Current</th>
                      <th className="text-right py-2 text-blue-700 font-medium">Sample</th>
                      <th className="text-left py-2 pl-3 text-blue-700 font-medium">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.experienced_rate && (
                      <tr className="border-b border-blue-100">
                        <td className="py-2 text-blue-900">Experienced</td>
                        <td className="py-2 text-right font-semibold text-blue-900">
                          {(analysis.experienced_rate.rate * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-gray-500">
                          {Number(formData.totalTerminationRate).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-blue-700">
                          {analysis.experienced_rate.terminated_count} / {analysis.experienced_rate.sample_size}
                        </td>
                        <td className="py-2 pl-3">
                          {confidenceBadge(analysis.experienced_rate.confidence)}
                        </td>
                      </tr>
                    )}
                    {analysis.new_hire_rate && (
                      <tr>
                        <td className="py-2 text-blue-900">New Hire</td>
                        <td className="py-2 text-right font-semibold text-blue-900">
                          {(analysis.new_hire_rate.rate * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-gray-500">
                          {Number(formData.newHireTerminationRate).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-blue-700">
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
                  <p className="mt-2 text-xs text-blue-600 italic">{analysis.message}</p>
                )}

                {/* Low confidence warning */}
                {((analysis.experienced_rate?.confidence === 'low') || (analysis.new_hire_rate?.confidence === 'low')) && (
                  <div className="mt-2 flex items-start gap-1.5 text-xs text-yellow-700 bg-yellow-50 rounded p-2">
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
