import { NumericInput } from './NumericInput';
import { useState } from 'react';
import { AlertTriangle, Users, TrendingUp, Sparkles, Check } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { useSuggestionPreview } from './useSuggestionPreview';
import { Band, BandValidationError, BandAnalysisResult, analyzeAgeBands, analyzeTenureBands } from '../../services/api';

export function SegmentationSection() {
  const { formData, bandConfig, setBandConfig, saveStatus, activeWorkspace, scenarioId, scenarioLoading } = useConfigContext();
  const [bandValidationErrors, setBandValidationErrors] = useState<BandValidationError[]>([]);
  const [asOfYear, setAsOfYear] = useState('');
  const asOfDate = asOfYear ? `${asOfYear}-12-31` : undefined;
  const inputKey = JSON.stringify([formData, bandConfig, asOfYear, scenarioLoading]);
  const scopeKey = JSON.stringify([activeWorkspace?.id, scenarioId]);
  const agePreview = useSuggestionPreview<BandAnalysisResult>(inputKey, scopeKey);
  const tenurePreview = useSuggestionPreview<BandAnalysisResult>(inputKey, scopeKey);
  const ageBandAnalysis = agePreview.value;
  const tenureBandAnalysis = tenurePreview.value;
  const ageBandAnalyzing = agePreview.pending;
  const tenureBandAnalyzing = tenurePreview.pending;
  const bandConfigError = agePreview.error || tenurePreview.error;

  const handleBandChange = (
    bandType: 'age' | 'tenure',
    bandId: number,
    field: keyof Band,
    value: string | number
  ) => {
    if (!bandConfig) return;
    const bandsKey = bandType === 'age' ? 'age_bands' : 'tenure_bands';
    const updatedBands = bandConfig[bandsKey].map(band => {
      if (band.band_id !== bandId) return band;
      const parsedValue = typeof value === 'string' && field !== 'band_label' ? parseInt(value) || 0 : value;
      return { ...band, [field]: parsedValue };
    });
    setBandConfig({ ...bandConfig, [bandsKey]: updatedBands });
    setBandValidationErrors([]);
  };

  const handleMatchCensusAgeBands = () => agePreview.calculate(() =>
    analyzeAgeBands(activeWorkspace.id, formData.censusDataPath, asOfDate));
  const handleApplyAgeBandSuggestions = () => agePreview.apply(analysis => {
    if (!bandConfig) return;
    setBandConfig({ ...bandConfig, age_bands: analysis.suggested_bands });
    setBandValidationErrors([]);
  });
  const handleMatchCensusTenureBands = () => tenurePreview.calculate(() =>
    analyzeTenureBands(activeWorkspace.id, formData.censusDataPath, asOfDate));
  const handleApplyTenureBandSuggestions = () => tenurePreview.apply(analysis => {
    if (!bandConfig) return;
    setBandConfig({ ...bandConfig, tenure_bands: analysis.suggested_bands });
    setBandValidationErrors([]);
  });

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">Workforce Segmentation</h2>
        <p className="text-sm text-ink-muted">Configure age and tenure band definitions used for workforce analytics and simulations.</p>
      </div>

      {bandConfigError && (
        <div className="bg-danger-surface border border-danger-border rounded-lg p-4">
          <div className="flex items-center">
            <AlertTriangle className="w-5 h-5 text-danger-ink mr-2" />
            <span className="text-danger-ink">{bandConfigError}</span>
          </div>
        </div>
      )}

      {bandConfig && (
        <>
          <label className="block text-sm text-ink-muted">Census year
            <input value={asOfYear} onChange={(event) => setAsOfYear(event.target.value)} placeholder="Inferred from census" inputMode="numeric" className="ml-2 w-32 rounded border border-border-strong px-2 py-1 text-sm" />
          </label>
          {bandValidationErrors.length > 0 && (
            <div className="bg-danger-surface border border-danger-border rounded-lg p-4">
              <div className="flex items-start">
                <AlertTriangle className="w-5 h-5 text-danger-ink mr-2 mt-0.5" />
                <div>
                  <h4 className="text-danger-ink font-medium">Validation Errors</h4>
                  <ul className="mt-2 space-y-1">
                    {bandValidationErrors.map((error, idx) => (
                      <li key={idx} className="text-sm text-danger-ink">
                        <span className="font-medium capitalize">{error.band_type} bands:</span> {error.message}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {saveStatus === 'success' && (
            <div className="bg-success-surface border border-success-border rounded-lg p-4">
              <div className="flex items-center">
                <Check className="w-5 h-5 text-success-ink mr-2" />
                <span className="text-success-ink">Configuration saved successfully.</span>
              </div>
            </div>
          )}

          {/* Age Bands Section */}
          <div className="bg-surface-subtle rounded-xl p-6 border border-border">
            <div className="flex flex-wrap gap-3 items-center justify-between mb-4">
              <div className="flex items-center">
                <Users className="w-5 h-5 text-fidelity-green mr-3" />
                <h3 className="font-semibold text-ink">Age Bands</h3>
              </div>
              <button
                onClick={handleMatchCensusAgeBands}
                disabled={ageBandAnalyzing || !formData.censusDataPath || scenarioLoading}
                className="flex items-center px-3 py-1.5 text-sm bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-green-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {ageBandAnalyzing ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border mr-2" />
                ) : (
                  <Sparkles size={16} className="mr-2" />
                )}
                Suggest from census
              </button>
            </div>

            {ageBandAnalysis && (
              <div className="mb-4 bg-info-surface border border-info-border rounded-lg p-4">
                <div className="flex flex-wrap gap-3 items-start justify-between">
                  <div>
                    <h4 className="text-info-ink font-medium">Suggested Age Bands — not applied</h4>
                    <p className="text-xs text-info-ink mt-2">Source: {formData.censusDataPath}. Current draft: {bandConfig.age_bands.map(band => `${band.band_label} [${band.min_value}, ${band.max_value})`).join('; ')}.</p>
                    {agePreview.stale && <p role="status" className="text-sm text-warning-ink">Needs recalculation: inputs have changed.</p>}
                    <p className="text-sm text-info-ink mt-1">
                      Based on {ageBandAnalysis.distribution_stats.total_employees} employees ({ageBandAnalysis.analysis_type})
                      {' '}as of {ageBandAnalysis.as_of_date} ({ageBandAnalysis.as_of_date_source})
                    </p>
                    <div className="mt-2 text-xs text-info-ink">
                      <span>Age range: {ageBandAnalysis.distribution_stats.min_value} - {ageBandAnalysis.distribution_stats.max_value}</span>
                      <span className="mx-2">|</span>
                      <span>Median: {ageBandAnalysis.distribution_stats.median_value.toFixed(1)}</span>
                    </div>
                    {ageBandAnalysis.fallback_notice && <p className="mt-2 text-xs text-warning-ink">{ageBandAnalysis.fallback_notice}</p>}
                  </div>
                  <div className="flex gap-2">
                    <button onClick={agePreview.cancel} className="px-3 py-1.5 text-sm text-ink-muted bg-surface-raised border border-border-strong rounded-lg hover:bg-surface-subtle">Cancel</button>
                    <button disabled={agePreview.stale} onClick={handleApplyAgeBandSuggestions} className="px-3 py-1.5 text-sm bg-info-solid text-ink-inverse rounded-lg hover:bg-info-solid-hover">Apply</button>
                  </div>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">ID</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Label</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Min (inclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Max (exclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Order</th>
                  </tr>
                </thead>
                <tbody>
                  {[...bandConfig.age_bands].sort((a, b) => a.display_order - b.display_order).map((band) => {
                    const hasError = bandValidationErrors.some(e => e.band_type === 'age' && e.band_ids.includes(band.band_id));
                    return (
                      <tr key={band.band_id} className={`border-b border-border ${hasError ? 'bg-danger-surface' : ''}`}>
                        <td className="py-2 px-3 text-ink-muted">{band.band_id}</td>
                        <td className="py-2 px-3">
                          <input type="text" value={band.band_label} onChange={(e) => handleBandChange('age', band.band_id, 'band_label', e.target.value)} className={`w-full px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} />
                        </td>
                        <td className="py-2 px-3">
                          <NumericInput integer type="number" value={band.min_value} onChange={(e) => handleBandChange('age', band.band_id, 'min_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} min="0" />
                        </td>
                        <td className="py-2 px-3">
                          <NumericInput integer type="number" value={band.max_value} onChange={(e) => handleBandChange('age', band.band_id, 'max_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} min="1" />
                        </td>
                        <td className="py-2 px-3">
                          <NumericInput integer type="number" value={band.display_order} onChange={(e) => handleBandChange('age', band.band_id, 'display_order', e.target.value)} className={`w-16 px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} min="1" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-ink-muted">
              Bands use [min, max) interval convention: min_value is inclusive, max_value is exclusive.
            </p>
          </div>

          {/* Tenure Bands Section */}
          <div className="bg-surface-subtle rounded-xl p-6 border border-border">
            <div className="flex flex-wrap gap-3 items-center justify-between mb-4">
              <div className="flex items-center">
                <TrendingUp className="w-5 h-5 text-fidelity-green mr-3" />
                <h3 className="font-semibold text-ink">Tenure Bands</h3>
              </div>
              <button
                onClick={handleMatchCensusTenureBands}
                disabled={tenureBandAnalyzing || !formData.censusDataPath || scenarioLoading}
                className="flex items-center px-3 py-1.5 text-sm bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-green-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {tenureBandAnalyzing ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border mr-2" />
                ) : (
                  <Sparkles size={16} className="mr-2" />
                )}
                Suggest from census
              </button>
            </div>

            {tenureBandAnalysis && (
              <div className="mb-4 bg-info-surface border border-info-border rounded-lg p-4">
                <div className="flex flex-wrap gap-3 items-start justify-between">
                  <div>
                    <h4 className="text-info-ink font-medium">Suggested Tenure Bands — not applied</h4>
                    <p className="text-xs text-info-ink mt-2">Source: {formData.censusDataPath}. Current draft: {bandConfig.tenure_bands.map(band => `${band.band_label} [${band.min_value}, ${band.max_value})`).join('; ')}.</p>
                    {tenurePreview.stale && <p role="status" className="text-sm text-warning-ink">Needs recalculation: inputs have changed.</p>}
                    <p className="text-sm text-info-ink mt-1">
                      Based on {tenureBandAnalysis.distribution_stats.total_employees} employees ({tenureBandAnalysis.analysis_type})
                      {' '}as of {tenureBandAnalysis.as_of_date} ({tenureBandAnalysis.as_of_date_source})
                    </p>
                    <div className="mt-2 text-xs text-info-ink">
                      <span>Tenure range: {tenureBandAnalysis.distribution_stats.min_value} - {tenureBandAnalysis.distribution_stats.max_value} years</span>
                      <span className="mx-2">|</span>
                      <span>Median: {tenureBandAnalysis.distribution_stats.median_value.toFixed(1)} years</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={tenurePreview.cancel} className="px-3 py-1.5 text-sm text-ink-muted bg-surface-raised border border-border-strong rounded-lg hover:bg-surface-subtle">Cancel</button>
                    <button disabled={tenurePreview.stale} onClick={handleApplyTenureBandSuggestions} className="px-3 py-1.5 text-sm bg-info-solid text-ink-inverse rounded-lg hover:bg-info-solid-hover">Apply</button>
                  </div>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">ID</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Label</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Min Years (inclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Max Years (exclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-ink-muted">Order</th>
                  </tr>
                </thead>
                <tbody>
                  {[...bandConfig.tenure_bands].sort((a, b) => a.display_order - b.display_order).map((band) => {
                    const hasError = bandValidationErrors.some(e => e.band_type === 'tenure' && e.band_ids.includes(band.band_id));
                    return (
                      <tr key={band.band_id} className={`border-b border-border ${hasError ? 'bg-danger-surface' : ''}`}>
                        <td className="py-2 px-3 text-ink-muted">{band.band_id}</td>
                        <td className="py-2 px-3">
                          <input type="text" value={band.band_label} onChange={(e) => handleBandChange('tenure', band.band_id, 'band_label', e.target.value)} className={`w-full px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} />
                        </td>
                        <td className="py-2 px-3">
                          <NumericInput integer type="number" value={band.min_value} onChange={(e) => handleBandChange('tenure', band.band_id, 'min_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} min="0" />
                        </td>
                        <td className="py-2 px-3">
                          <NumericInput integer type="number" value={band.max_value} onChange={(e) => handleBandChange('tenure', band.band_id, 'max_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} min="1" />
                        </td>
                        <td className="py-2 px-3">
                          <NumericInput integer type="number" value={band.display_order} onChange={(e) => handleBandChange('tenure', band.band_id, 'display_order', e.target.value)} className={`w-16 px-2 py-1 border rounded text-sm ${hasError ? 'border-danger-border' : 'border-border-strong'}`} min="1" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-ink-muted">
              Bands use [min, max) interval convention: min_value is inclusive, max_value is exclusive.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
