import { useState } from 'react';
import { AlertTriangle, Sparkles } from 'lucide-react';
import {
  DEFERRAL_AGE_SEGMENTS,
  DEFERRAL_INCOME_SEGMENTS,
  type DeferralSegmentKey,
  type VoluntaryDeferralBaseRates,
} from './types';
import {
  analyzeDeferralSegments,
  type DeferralSegmentAnalysisResult,
} from '../../services/api';

/**
 * Editor for the starting deferral rate assigned to each age x income segment of
 * voluntary enrollees.
 *
 * Census employees keep their own deferral rate for the life of a simulation, so
 * these rates only ever apply to new enrollees. When they sit below what the census
 * shows, turnover drags the plan-wide average down over the horizon — which is what
 * Match Census exists to diagnose.
 */

interface VoluntaryDeferralRatesEditorProps {
  rates: VoluntaryDeferralBaseRates;
  onChange: (rates: VoluntaryDeferralBaseRates) => void;
  workspaceId: string | undefined;
  censusDataPath: string;
}

const formatPercent = (decimal: number) => `${(decimal * 100).toFixed(1)}%`;

export function VoluntaryDeferralRatesEditor({
  rates,
  onChange,
  workspaceId,
  censusDataPath,
}: VoluntaryDeferralRatesEditorProps) {
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<DeferralSegmentAnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const suggestions = new Map(
    (analysis?.segments ?? []).map((segment) => [segment.segment, segment])
  );

  const handleMatchCensus = async () => {
    if (!workspaceId || !censusDataPath) return;
    setAnalyzing(true);
    setAnalysis(null);
    setAnalysisError(null);
    try {
      setAnalysis(await analyzeDeferralSegments(workspaceId, { file_path: censusDataPath }));
    } catch (err) {
      setAnalysisError(
        err instanceof Error ? err.message : 'Failed to analyze census for deferral rates'
      );
    } finally {
      setAnalyzing(false);
    }
  };

  // Segments the census cannot speak to keep their configured value rather than
  // being zeroed out by an absent suggestion.
  const handleApply = () => {
    if (!analysis) return;
    const updated = { ...rates };
    for (const segment of analysis.segments) {
      if (segment.average_deferral_rate === null) continue;
      updated[segment.segment as DeferralSegmentKey] = parseFloat(
        (segment.average_deferral_rate * 100).toFixed(1)
      );
    }
    onChange(updated);
    setAnalysis(null);
  };

  const handleRateChange = (segment: DeferralSegmentKey, value: string) => {
    onChange({ ...rates, [segment]: value === '' ? 0 : Number(value) });
  };

  const outOfRange = Object.values(rates).some((rate) => rate < 0 || rate > 100);
  const applicableCount = (analysis?.segments ?? []).filter(
    (segment) => segment.average_deferral_rate !== null
  ).length;

  return (
    <div className="sm:col-span-6 mt-4">
      <div className="flex items-center justify-between mb-1">
        <h4 className="text-sm font-semibold text-ink">Starting Deferral Rates by Segment</h4>
        <button
          type="button"
          onClick={handleMatchCensus}
          disabled={analyzing || !censusDataPath || !workspaceId}
          title={censusDataPath ? undefined : 'Upload a census file first to use Match Census'}
          className="flex items-center px-3 py-1.5 text-sm bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-green-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {analyzing ? (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border mr-2" />
          ) : (
            <Sparkles size={16} className="mr-2" />
          )}
          Match Census
        </button>
      </div>
      <p className="text-xs text-ink-muted mb-3">
        Deferral rate assigned to a new hire who enrolls voluntarily, by age and income.
        Applies only to employees who enroll during the simulation — census employees keep
        their own rate. Match Census fills these from the average rate of participants in
        each segment of your census file.
      </p>

      {!censusDataPath && (
        <p className="text-xs text-ink-muted mb-3">
          Upload a census file to enable Match Census.
        </p>
      )}

      {analysisError && (
        <div className="mb-3 bg-danger-surface border border-danger-border rounded-lg p-3">
          <div className="flex items-center">
            <AlertTriangle className="w-4 h-4 text-danger-ink mr-2" />
            <span className="text-sm text-danger-ink">{analysisError}</span>
          </div>
        </div>
      )}

      {analysis && (
        <div className="mb-4 bg-info-surface border border-info-border rounded-lg p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h5 className="text-info-ink font-medium">Census Deferral Rates</h5>
              <p className="text-sm text-info-ink mt-1">
                {analysis.total_participants.toLocaleString()} participants of{' '}
                {analysis.total_employees_analyzed.toLocaleString()} employees analyzed, ages
                as of {analysis.as_of_date} ({analysis.as_of_date_source}).
                {analysis.overall_average_deferral_rate !== null && (
                  <>
                    {' '}
                    Overall average{' '}
                    <span className="font-semibold">
                      {formatPercent(analysis.overall_average_deferral_rate)}
                    </span>
                    .
                  </>
                )}
              </p>
              {analysis.excluded_count > 0 && (
                <p className="mt-1 text-xs text-info-ink">
                  {analysis.excluded_count.toLocaleString()} employee(s) excluded for a missing
                  or unusable age, compensation, or deferral value.
                </p>
              )}
              {analysis.message && (
                <p className="mt-2 text-xs text-warning-ink">{analysis.message}</p>
              )}
              <p className="mt-2 text-xs text-info-ink">
                Suggestions appear under each field below. Nothing is saved until you apply.
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setAnalysis(null)}
                className="px-3 py-1.5 text-sm text-ink-muted bg-surface-raised border border-border-strong rounded-lg hover:bg-surface-subtle"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleApply}
                disabled={applicableCount === 0}
                className="px-3 py-1.5 text-sm bg-info-solid text-ink-inverse rounded-lg hover:bg-info-solid-hover disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Apply {applicableCount} segment{applicableCount === 1 ? '' : 's'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-3 font-medium text-ink-muted">Age</th>
              {DEFERRAL_INCOME_SEGMENTS.map((income) => (
                <th key={income.key} className="text-left py-2 px-3 font-medium text-ink-muted">
                  {income.label}
                  <span className="block text-xs font-normal">{income.range}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DEFERRAL_AGE_SEGMENTS.map((age) => (
              <tr key={age.key} className="border-b border-border">
                <td className="py-2 px-3 text-ink-muted whitespace-nowrap">
                  {age.label}
                  <span className="block text-xs">{age.range}</span>
                </td>
                {DEFERRAL_INCOME_SEGMENTS.map((income) => {
                  const segment = `${age.key}_${income.key}` as DeferralSegmentKey;
                  const rate = rates[segment];
                  const suggestion = suggestions.get(segment);
                  const invalid = rate < 0 || rate > 100;
                  return (
                    <td key={income.key} className="py-2 px-3">
                      <div className="flex items-center">
                        <input
                          type="number"
                          aria-label={`${age.label} ${income.label} deferral rate`}
                          value={rate}
                          onChange={(e) => handleRateChange(segment, e.target.value)}
                          step="0.5"
                          min={0}
                          max={100}
                          className={`w-20 px-2 py-1 border rounded text-sm ${
                            invalid ? 'border-danger-border' : 'border-border-strong'
                          }`}
                        />
                        <span className="ml-1 text-xs text-ink-muted">%</span>
                      </div>
                      {analysis && (
                        <span className="block mt-1 text-xs text-ink-muted">
                          {suggestion && suggestion.average_deferral_rate !== null ? (
                            <>
                              Census {formatPercent(suggestion.average_deferral_rate)}
                              {suggestion.low_confidence && (
                                <span
                                  className="text-warning-ink"
                                  title={`Only ${suggestion.participant_count} participant(s) in this segment`}
                                >
                                  {' '}
                                  (n={suggestion.participant_count})
                                </span>
                              )}
                            </>
                          ) : (
                            'No census data'
                          )}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {outOfRange && (
        <p className="mt-2 text-xs text-danger-ink">
          Deferral rates must be between 0% and 100%.
        </p>
      )}
    </div>
  );
}
