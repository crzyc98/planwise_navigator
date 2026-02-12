import { useState, useRef } from 'react';
import { Database, Upload, Check, HelpCircle } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { uploadCensusFile, validateFilePath, updateScenario } from '../../services/api';

export function DataSourcesSection() {
  const { formData, setFormData, handleChange, activeWorkspace, currentScenario, scenarioId } = useConfigContext();

  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  const [uploadMessage, setUploadMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Data Sources</h2>
        <p className="text-sm text-gray-500">Configure your workforce census data and other input files.</p>
      </div>

      {/* Census Data Section */}
      <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            <Database className="w-5 h-5 text-fidelity-green mr-3" />
            <h3 className="font-semibold text-gray-900">Census Data (Parquet)</h3>
          </div>
          {formData.censusDataStatus === 'loaded' && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
              <Check size={12} className="mr-1" />
              Loaded
            </span>
          )}
        </div>

        {/* Current File Info */}
        {formData.censusDataStatus === 'loaded' && (
          <div className="bg-white rounded-lg p-4 border border-gray-200 mb-4">
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-500 block">File Path</span>
                <span className="font-mono text-gray-900 text-xs">{formData.censusDataPath}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Rows</span>
                <span className="font-semibold text-gray-900">{formData.censusRowCount.toLocaleString()}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Last Modified</span>
                <span className="text-gray-900">{formData.censusLastModified}</span>
              </div>
            </div>
          </div>
        )}

        {/* Upload Section */}
        <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-fidelity-green transition-colors">
          <input
            type="file"
            ref={fileInputRef}
            accept=".parquet,.csv"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file || !activeWorkspace?.id) return;

              setUploadStatus('uploading');
              setUploadMessage(`Uploading ${file.name}...`);

              try {
                const result = await uploadCensusFile(activeWorkspace.id, file);

                setFormData(prev => ({
                  ...prev,
                  censusDataPath: result.file_path,
                  censusDataStatus: 'loaded',
                  censusRowCount: result.row_count,
                  censusLastModified: result.upload_timestamp.split('T')[0]
                }));

                // E089: Auto-save census path to prevent data loss
                let autoSaved = false;
                if (currentScenario && activeWorkspace) {
                  try {
                    await updateScenario(activeWorkspace.id, currentScenario.id, {
                      config_overrides: {
                        data_sources: {
                          census_parquet_path: result.file_path,
                        },
                      },
                    });
                    autoSaved = true;
                  } catch (saveError) {
                    console.error('E089: Auto-save census path failed:', saveError);
                  }
                }

                if (result.validation_warnings.length > 0) {
                  setUploadStatus('success');
                  setUploadMessage(`Uploaded with warnings: ${result.validation_warnings.join(', ')}`);
                } else {
                  setUploadStatus('success');
                  const savedMsg = autoSaved ? ' and saved' : '';
                  setUploadMessage(`File uploaded${savedMsg}! ${result.row_count.toLocaleString()} rows, ${result.columns.length} columns`);
                }
              } catch (error) {
                setUploadStatus('error');
                setUploadMessage(error instanceof Error ? error.message : 'Upload failed');
              }
            }}
          />
          <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
          <p className="text-sm text-gray-600 mb-2">
            Drag and drop your census file here, or{' '}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="text-fidelity-green font-medium hover:underline"
            >
              browse
            </button>
          </p>
          <p className="text-xs text-gray-400">Supports Parquet (.parquet) or CSV (.csv) files</p>

          {uploadStatus === 'uploading' && (
            <div className="mt-4 flex items-center justify-center text-sm text-gray-600">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-fidelity-green mr-2"></div>
              {uploadMessage}
            </div>
          )}
          {uploadStatus === 'success' && (
            <div className="mt-4 flex items-center justify-center text-sm text-green-600">
              <Check size={16} className="mr-2" />
              {uploadMessage}
            </div>
          )}
        </div>

        {/* Manual Path Input */}
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Or specify file path manually
          </label>
          <div className="flex space-x-2">
            <input
              type="text"
              name="censusDataPath"
              value={formData.censusDataPath}
              onChange={handleChange}
              placeholder="data/census_preprocessed.parquet"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green font-mono"
            />
            <button
              type="button"
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors"
              onClick={async () => {
                if (!formData.censusDataPath.trim() || !activeWorkspace?.id) {
                  setUploadStatus('error');
                  setUploadMessage('Please enter a file path');
                  return;
                }

                setUploadStatus('uploading');
                setUploadMessage('Validating path...');

                try {
                  const result = await validateFilePath(
                    activeWorkspace.id,
                    formData.censusDataPath
                  );

                  if (result.valid) {
                    setFormData(prev => ({
                      ...prev,
                      censusDataStatus: 'loaded',
                      censusRowCount: result.row_count || 0,
                      censusLastModified: result.last_modified?.split('T')[0] || 'Unknown'
                    }));
                    setUploadStatus('success');
                    setUploadMessage(`Valid: ${result.row_count?.toLocaleString()} rows, ${result.columns?.length} columns`);
                  } else {
                    setUploadStatus('error');
                    setUploadMessage(result.error_message || 'Invalid path');
                    setFormData(prev => ({ ...prev, censusDataStatus: 'error' }));
                  }
                } catch (error) {
                  setUploadStatus('error');
                  setUploadMessage(error instanceof Error ? error.message : 'Validation failed');
                }
              }}
            >
              Validate
            </button>
          </div>
        </div>
      </div>

      {/* Required Columns Info */}
      <div className="bg-blue-50 rounded-xl p-6 border border-blue-100">
        <div className="flex items-start">
          <HelpCircle className="w-5 h-5 text-blue-500 mr-3 mt-0.5" />
          <div>
            <h4 className="font-semibold text-blue-900 mb-2">Required Census Columns</h4>
            <p className="text-sm text-blue-700 mb-3">
              Your census file must contain the following columns for the simulation to run correctly:
            </p>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              {['employee_id', 'hire_date', 'department', 'job_level', 'annual_salary', 'birth_date', 'termination_date', 'status'].map(col => (
                <div key={col} className="bg-white px-2 py-1 rounded border border-blue-200 text-blue-800">
                  {col}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
