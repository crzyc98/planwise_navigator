import React, { useState } from 'react';
import { Upload, Map, Eye, CheckCircle2, ArrowLeft } from 'lucide-react';
import { Link, useOutletContext } from 'react-router-dom';
import { LayoutContextType } from './Layout';
import { ImportSession, FieldMapping, ParquetFile, SuggestionsResponse } from '../services/importService';
import { FileUploadResponse } from '../services/api';
import FileUploadStep from './imports/FileUploadStep';
import FieldMappingStep from './imports/FieldMappingStep';
import PreviewStep from './imports/PreviewStep';
import ImportedFilesList from './imports/ImportedFilesList';

type WizardStep = 'upload' | 'mapping' | 'preview' | 'done';

const STEPS: { id: WizardStep; label: string; icon: React.ReactNode }[] = [
  { id: 'upload', label: 'Upload', icon: <Upload size={16} /> },
  { id: 'mapping', label: 'Map Fields', icon: <Map size={16} /> },
  { id: 'preview', label: 'Preview', icon: <Eye size={16} /> },
  { id: 'done', label: 'Done', icon: <CheckCircle2 size={16} /> },
];

function StepIndicator({ current }: { current: WizardStep }) {
  const stepOrder: WizardStep[] = ['upload', 'mapping', 'preview', 'done'];
  const currentIdx = stepOrder.indexOf(current);
  return (
    <div className="flex items-center gap-0">
      {STEPS.map((step, i) => {
        const isDone = i < currentIdx;
        const isActive = step.id === current;
        return (
          <React.Fragment key={step.id}>
            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors
              ${isActive ? 'bg-fidelity-green text-white' : isDone ? 'text-fidelity-green' : 'text-gray-400'}`}>
              {step.icon}
              <span className="hidden sm:inline">{step.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-0.5 w-6 ${isDone ? 'bg-fidelity-green' : 'bg-gray-200'}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

export default function DataImportWizard() {
  const { activeWorkspace, refreshActiveWorkspace } = useOutletContext<LayoutContextType>();
  const [step, setStep] = useState<WizardStep>('upload');
  const [session, setSession] = useState<ImportSession | null>(null);
  const [mappings, setMappings] = useState<FieldMapping[]>([]);
  const [suggestionsData, setSuggestionsData] = useState<SuggestionsResponse | null>(null);
  const [generatedFile, setGeneratedFile] = useState<ParquetFile | null>(null);
  const [parquetResult, setParquetResult] = useState<FileUploadResponse | null>(null);
  const [mappingDirty, setMappingDirty] = useState(false);
  const [showLeaveWarning, setShowLeaveWarning] = useState(false);
  const [showFilesView, setShowFilesView] = useState(false);

  const workspaceId = activeWorkspace?.id;

  if (!workspaceId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400">
        <p>Select a workspace to import data.</p>
      </div>
    );
  }

  const handleUploadDone = (s: ImportSession) => {
    setSession(s);
    setStep('mapping');
  };

  const handleMappingSaved = (m: FieldMapping[], sd: SuggestionsResponse | null) => {
    setMappings(m);
    setSuggestionsData(sd);
    setMappingDirty(false);
    setStep('preview');
  };

  const handleGenerated = (file: ParquetFile) => {
    setGeneratedFile(file);
    setStep('done');
    // The generate/upload endpoints set this file as the workspace census in
    // base_config server-side; refresh shared state so Configure sees it immediately.
    void refreshActiveWorkspace();
  };

  const handleParquetDone = (result: FileUploadResponse) => {
    setParquetResult(result);
    setStep('done');
    void refreshActiveWorkspace();
  };

  const handleStartNew = () => {
    setStep('upload');
    setSession(null);
    setMappings([]);
    setGeneratedFile(null);
    setParquetResult(null);
    setMappingDirty(false);
  };

  if (showFilesView) {
    return (
      <div className="p-6 space-y-4">
        <button
          onClick={() => setShowFilesView(false)}
          className="flex items-center gap-1 text-sm text-fidelity-green hover:underline"
        >
          <ArrowLeft size={14} /> Back to Import Wizard
        </button>
        <ImportedFilesList workspaceId={workspaceId} />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-800">Import Data</h1>
          <p className="text-sm text-gray-500 mt-0.5">Import census data from CSV, Excel, or Parquet</p>
        </div>
        <button
          onClick={() => setShowFilesView(true)}
          className="text-sm text-fidelity-green hover:underline"
        >
          View Imported Files
        </button>
      </div>

      <StepIndicator current={step} />

      <div className="border border-gray-200 rounded-xl p-6 bg-white shadow-sm">
        {step === 'upload' && (
          <FileUploadStep workspaceId={workspaceId} onDone={handleUploadDone} onParquetDone={handleParquetDone} />
        )}
        {step === 'mapping' && session && (
          <FieldMappingStep
            workspaceId={workspaceId}
            session={session}
            onSaved={handleMappingSaved}
          />
        )}
        {step === 'preview' && session && (
          <PreviewStep
            workspaceId={workspaceId}
            session={session}
            onGenerated={handleGenerated}
            dataQuality={suggestionsData?.data_quality ?? null}
          />
        )}
        {step === 'done' && parquetResult && (
          <div className="text-center space-y-4 py-6">
            <CheckCircle2 size={48} className="mx-auto text-fidelity-green" />
            <h2 className="text-lg font-semibold text-gray-800">Census Data Ready</h2>
            <p className="text-sm text-gray-500">
              <span className="font-mono">{parquetResult.file_name}</span> — {parquetResult.row_count.toLocaleString()} rows
            </p>
            <p className="text-xs text-gray-400">Your workspace census has been updated.</p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={handleStartNew}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                Import Another File
              </button>
              <Link
                to="/config"
                className="px-4 py-2 text-sm bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark"
              >
                View in Configure
              </Link>
            </div>
          </div>
        )}
        {step === 'done' && generatedFile && (
          <div className="text-center space-y-4 py-6">
            <CheckCircle2 size={48} className="mx-auto text-fidelity-green" />
            <h2 className="text-lg font-semibold text-gray-800">Parquet File Generated!</h2>
            <p className="text-sm text-gray-500">
              <span className="font-mono">{generatedFile.filename}</span> — {generatedFile.row_count.toLocaleString()} rows
            </p>
            <p className="text-xs text-gray-400">
              This file is now set as the workspace census and will be used by your scenarios.
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={handleStartNew}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                Import Another File
              </button>
              <button
                onClick={() => setShowFilesView(true)}
                className="px-4 py-2 text-sm bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark"
              >
                View All Files
              </button>
            </div>
          </div>
        )}
      </div>

      {step !== 'upload' && step !== 'done' && (
        <button
          onClick={() => {
            if (mappingDirty) {
              setShowLeaveWarning(true);
            } else {
              setStep(step === 'preview' ? 'mapping' : 'upload');
            }
          }}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600"
        >
          <ArrowLeft size={14} /> Back
        </button>
      )}

      {showLeaveWarning && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm space-y-4">
            <h3 className="font-semibold text-gray-800">Unsaved mapping changes</h3>
            <p className="text-sm text-gray-500">You have unsaved mapping changes. Navigating away will discard them.</p>
            <div className="flex gap-3">
              <button
                onClick={() => { setShowLeaveWarning(false); setStep('upload'); setMappingDirty(false); }}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg"
              >
                Discard & Leave
              </button>
              <button
                onClick={() => setShowLeaveWarning(false)}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg"
              >
                Stay
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
