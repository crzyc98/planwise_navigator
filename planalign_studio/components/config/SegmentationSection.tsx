import { useState } from 'react';
import { AlertTriangle, Users, TrendingUp, Sparkles, Check } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { Band, BandValidationError, BandAnalysisResult, analyzeAgeBands, analyzeTenureBands } from '../../services/api';

export function SegmentationSection() {
  const { formData, bandConfig, setBandConfig, saveStatus, activeWorkspace } = useConfigContext();

  const [bandConfigLoading] = useState(false);
  const [bandConfigError, setBandConfigError] = useState<string | null>(null);
  const [bandValidationErrors, setBandValidationErrors] = useState<BandValidationError[]>([]);
  const [ageBandAnalysis, setAgeBandAnalysis] = useState<BandAnalysisResult | null>(null);
  const [ageBandAnalyzing, setAgeBandAnalyzing] = useState(false);
  const [tenureBandAnalysis, setTenureBandAnalysis] = useState<BandAnalysisResult | null>(null);
  const [tenureBandAnalyzing, setTenureBandAnalyzing] = useState(false);

  const handleBandChange = (
    bandType: 'age' | 'tenure',
    bandId: number,
    field: keyof Band,
    value: string | number
  ) => {
    if (!bandConfig) return;
    const bandsKey = bandType === 'age' ? 'age_bands' : 'tenure_bands';
    const updatedBands = bandConfig[bandsKey].map(band =>
      band.band_id === bandId
        ? { ...band, [field]: typeof value === 'string' && field !== 'band_label' ? parseInt(value) || 0 : value }
        : band
    );
    setBandConfig({ ...bandConfig, [bandsKey]: updatedBands });
    setBandValidationErrors([]);
  };

  const handleMatchCensusAgeBands = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) {
      setBandConfigError('Please upload a census file first');
      return;
    }
    setAgeBandAnalyzing(true);
    setAgeBandAnalysis(null);
    try {
      const result = await analyzeAgeBands(activeWorkspace.id, formData.censusDataPath);
      setAgeBandAnalysis(result);
    } catch (error) {
      console.error('Failed to analyze age bands:', error);
      setBandConfigError(error instanceof Error ? error.message : 'Failed to analyze census for age bands');
    } finally {
      setAgeBandAnalyzing(false);
    }
  };

  const handleApplyAgeBandSuggestions = () => {
    if (!ageBandAnalysis || !bandConfig) return;
    setBandConfig({ ...bandConfig, age_bands: ageBandAnalysis.suggested_bands });
    setAgeBandAnalysis(null);
    setBandValidationErrors([]);
  };

  const handleMatchCensusTenureBands = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) {
      setBandConfigError('Please upload a census file first');
      return;
    }
    setTenureBandAnalyzing(true);
    setTenureBandAnalysis(null);
    try {
      const result = await analyzeTenureBands(activeWorkspace.id, formData.censusDataPath);
      setTenureBandAnalysis(result);
    } catch (error) {
      console.error('Failed to analyze tenure bands:', error);
      setBandConfigError(error instanceof Error ? error.message : 'Failed to analyze census for tenure bands');
    } finally {
      setTenureBandAnalyzing(false);
    }
  };

  const handleApplyTenureBandSuggestions = () => {
    if (!tenureBandAnalysis || !bandConfig) return;
    setBandConfig({ ...bandConfig, tenure_bands: tenureBandAnalysis.suggested_bands });
    setTenureBandAnalysis(null);
    setBandValidationErrors([]);
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Workforce Segmentation</h2>
        <p className="text-sm text-gray-500">Configure age and tenure band definitions used for workforce analytics and simulations.</p>
      </div>

      {bandConfigLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green"></div>
          <span className="ml-3 text-gray-600">Loading band configurations...</span>
        </div>
      )}

      {bandConfigError && !bandConfigLoading && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center">
            <AlertTriangle className="w-5 h-5 text-red-600 mr-2" />
            <span className="text-red-800">{bandConfigError}</span>
          </div>
        </div>
      )}

      {bandConfig && !bandConfigLoading && (
        <>
          {bandValidationErrors.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-start">
                <AlertTriangle className="w-5 h-5 text-red-600 mr-2 mt-0.5" />
                <div>
                  <h4 className="text-red-800 font-medium">Validation Errors</h4>
                  <ul className="mt-2 space-y-1">
                    {bandValidationErrors.map((error, idx) => (
                      <li key={idx} className="text-sm text-red-700">
                        <span className="font-medium capitalize">{error.band_type} bands:</span> {error.message}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {saveStatus === 'success' && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center">
                <Check className="w-5 h-5 text-green-600 mr-2" />
                <span className="text-green-800">Configuration saved successfully.</span>
              </div>
            </div>
          )}

          {/* Age Bands Section */}
          <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center">
                <Users className="w-5 h-5 text-fidelity-green mr-3" />
                <h3 className="font-semibold text-gray-900">Age Bands</h3>
              </div>
              <button
                onClick={handleMatchCensusAgeBands}
                disabled={ageBandAnalyzing || !formData.censusDataPath}
                className="flex items-center px-3 py-1.5 text-sm bg-fidelity-green text-white rounded-lg hover:bg-fidelity-green-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {ageBandAnalyzing ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                ) : (
                  <Sparkles size={16} className="mr-2" />
                )}
                Match Census
              </button>
            </div>

            {ageBandAnalysis && (
              <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="text-blue-800 font-medium">Suggested Age Bands</h4>
                    <p className="text-sm text-blue-600 mt-1">
                      Based on {ageBandAnalysis.distribution_stats.total_employees} employees ({ageBandAnalysis.analysis_type})
                    </p>
                    <div className="mt-2 text-xs text-blue-700">
                      <span>Age range: {ageBandAnalysis.distribution_stats.min_value} - {ageBandAnalysis.distribution_stats.max_value}</span>
                      <span className="mx-2">|</span>
                      <span>Median: {ageBandAnalysis.distribution_stats.median_value.toFixed(1)}</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => setAgeBandAnalysis(null)} className="px-3 py-1.5 text-sm text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
                    <button onClick={handleApplyAgeBandSuggestions} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">Apply</button>
                  </div>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 px-3 font-medium text-gray-700">ID</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Label</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Min (inclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Max (exclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Order</th>
                  </tr>
                </thead>
                <tbody>
                  {[...bandConfig.age_bands].sort((a, b) => a.display_order - b.display_order).map((band) => {
                    const hasError = bandValidationErrors.some(e => e.band_type === 'age' && e.band_ids.includes(band.band_id));
                    return (
                      <tr key={band.band_id} className={`border-b border-gray-100 ${hasError ? 'bg-red-50' : ''}`}>
                        <td className="py-2 px-3 text-gray-600">{band.band_id}</td>
                        <td className="py-2 px-3">
                          <input type="text" value={band.band_label} onChange={(e) => handleBandChange('age', band.band_id, 'band_label', e.target.value)} className={`w-full px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} />
                        </td>
                        <td className="py-2 px-3">
                          <input type="number" value={band.min_value} onChange={(e) => handleBandChange('age', band.band_id, 'min_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} min="0" />
                        </td>
                        <td className="py-2 px-3">
                          <input type="number" value={band.max_value} onChange={(e) => handleBandChange('age', band.band_id, 'max_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} min="1" />
                        </td>
                        <td className="py-2 px-3">
                          <input type="number" value={band.display_order} onChange={(e) => handleBandChange('age', band.band_id, 'display_order', e.target.value)} className={`w-16 px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} min="1" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Bands use [min, max) interval convention: min_value is inclusive, max_value is exclusive.
            </p>
          </div>

          {/* Tenure Bands Section */}
          <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center">
                <TrendingUp className="w-5 h-5 text-fidelity-green mr-3" />
                <h3 className="font-semibold text-gray-900">Tenure Bands</h3>
              </div>
              <button
                onClick={handleMatchCensusTenureBands}
                disabled={tenureBandAnalyzing || !formData.censusDataPath}
                className="flex items-center px-3 py-1.5 text-sm bg-fidelity-green text-white rounded-lg hover:bg-fidelity-green-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {tenureBandAnalyzing ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                ) : (
                  <Sparkles size={16} className="mr-2" />
                )}
                Match Census
              </button>
            </div>

            {tenureBandAnalysis && (
              <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="text-blue-800 font-medium">Suggested Tenure Bands</h4>
                    <p className="text-sm text-blue-600 mt-1">
                      Based on {tenureBandAnalysis.distribution_stats.total_employees} employees ({tenureBandAnalysis.analysis_type})
                    </p>
                    <div className="mt-2 text-xs text-blue-700">
                      <span>Tenure range: {tenureBandAnalysis.distribution_stats.min_value} - {tenureBandAnalysis.distribution_stats.max_value} years</span>
                      <span className="mx-2">|</span>
                      <span>Median: {tenureBandAnalysis.distribution_stats.median_value.toFixed(1)} years</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => setTenureBandAnalysis(null)} className="px-3 py-1.5 text-sm text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
                    <button onClick={handleApplyTenureBandSuggestions} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">Apply</button>
                  </div>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 px-3 font-medium text-gray-700">ID</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Label</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Min Years (inclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Max Years (exclusive)</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-700">Order</th>
                  </tr>
                </thead>
                <tbody>
                  {[...bandConfig.tenure_bands].sort((a, b) => a.display_order - b.display_order).map((band) => {
                    const hasError = bandValidationErrors.some(e => e.band_type === 'tenure' && e.band_ids.includes(band.band_id));
                    return (
                      <tr key={band.band_id} className={`border-b border-gray-100 ${hasError ? 'bg-red-50' : ''}`}>
                        <td className="py-2 px-3 text-gray-600">{band.band_id}</td>
                        <td className="py-2 px-3">
                          <input type="text" value={band.band_label} onChange={(e) => handleBandChange('tenure', band.band_id, 'band_label', e.target.value)} className={`w-full px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} />
                        </td>
                        <td className="py-2 px-3">
                          <input type="number" value={band.min_value} onChange={(e) => handleBandChange('tenure', band.band_id, 'min_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} min="0" />
                        </td>
                        <td className="py-2 px-3">
                          <input type="number" value={band.max_value} onChange={(e) => handleBandChange('tenure', band.band_id, 'max_value', e.target.value)} className={`w-20 px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} min="1" />
                        </td>
                        <td className="py-2 px-3">
                          <input type="number" value={band.display_order} onChange={(e) => handleBandChange('tenure', band.band_id, 'display_order', e.target.value)} className={`w-16 px-2 py-1 border rounded text-sm ${hasError ? 'border-red-300' : 'border-gray-300'}`} min="1" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Bands use [min, max) interval convention: min_value is inclusive, max_value is exclusive.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
