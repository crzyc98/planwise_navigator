import { useState } from 'react';
import { Save, AlertTriangle, FileText, Settings, TrendingUp, Users, DollarSign, PieChart, Database, Check, ArrowLeft, Play, Copy, Layers, Share2, Gauge } from 'lucide-react';
import { useOutletContext, useParams } from 'react-router-dom';
import { LayoutContextType } from './Layout';
import { listTemplates, Template, listScenarios, Scenario } from '../services/api';
import { ConfigProvider, useConfigContext } from './config/ConfigContext';
import { WorkforceParametersSection } from './config/WorkforceParametersSection';
import { SimulationSection } from './config/SimulationSection';
import { DataSourcesSection } from './config/DataSourcesSection';
import { CompensationSection } from './config/CompensationSection';
import { NewHireSection } from './config/NewHireSection';
import { SegmentationSection } from './config/SegmentationSection';
import { TurnoverSection } from './config/TurnoverSection';
import { DCPlanSection } from './config/DCPlanSection';
import { AdvancedSection } from './config/AdvancedSection';
import { TemplateModal } from './config/TemplateModal';
import { CopyScenarioModal } from './config/CopyScenarioModal';
import { ApplyWorkforceParamsModal } from './config/ApplyWorkforceParamsModal';
import { useWorkspaceNavigate } from '../hooks/useWorkspaceNavigation';

// Primary nav: the curated essentials path (#358) plus the self-contained DC Plan.
const PRIMARY_NAV = [
  { id: 'workforce', label: 'Workforce Parameters', icon: Gauge },
  { id: 'dcplan', label: 'DC Plan', icon: PieChart },
];

// Advanced nav: full detail for every area, one click away under "Advanced".
const ADVANCED_NAV = [
  { id: 'simulation', label: 'Simulation Settings', icon: TrendingUp },
  { id: 'datasources', label: 'Data Sources', icon: Database },
  { id: 'compensation', label: 'Compensation', icon: DollarSign },
  { id: 'newhire', label: 'New Hire Strategy', icon: Users },
  { id: 'segmentation', label: 'Workforce Segmentation', icon: Layers },
  { id: 'turnover', label: 'Workforce & Turnover', icon: AlertTriangle },
  { id: 'advanced', label: 'Advanced Settings', icon: Settings },
];

function ConfigShell() {
  const navigate = useWorkspaceNavigate();
  const {
    currentScenario, scenarioId, scenarioLoading,
    dirtySections, isDirty,
    handleSaveConfig, saveStatus, saveMessage,
    activeWorkspace,
  } = useConfigContext();

  const [activeSection, setActiveSection] = useState('workforce');

  // Template modal state
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  // Copy from scenario modal state
  const [showCopyScenarioModal, setShowCopyScenarioModal] = useState(false);
  const [availableScenarios, setAvailableScenarios] = useState<Scenario[]>([]);
  const [copyingScenariosLoading, setCopyingScenariosLoading] = useState(false);

  // Apply workforce params modal state
  const [showApplyWorkforceModal, setShowApplyWorkforceModal] = useState(false);
  const [applyWorkforceScenarios, setApplyWorkforceScenarios] = useState<Scenario[]>([]);
  const [applyWorkforceLoading, setApplyWorkforceLoading] = useState(false);

  if (scenarioLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
          <p className="text-sm text-ink-muted">Loading scenario...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center space-x-3">
            {currentScenario && (
              <button
                onClick={() => navigate('/scenarios')}
                className="p-1.5 text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle rounded-lg transition-colors"
                title="Back to Scenarios"
              >
                <ArrowLeft size={20} />
              </button>
            )}
            <div>
              <h1 className="text-2xl font-bold text-ink">
                {currentScenario ? `Configure: ${currentScenario.name}` : 'Base Configuration'}
              </h1>
              <p className="text-ink-muted text-sm">
                {currentScenario
                  ? 'Edit scenario-specific configuration overrides.'
                  : 'Edit workspace default simulation parameters.'}
              </p>
            </div>
          </div>
        </div>
        <div className="flex space-x-3">
          {scenarioId && (
            <button
              onClick={async () => {
                setCopyingScenariosLoading(true);
                try {
                  const scenarios = await listScenarios(activeWorkspace.id);
                  setAvailableScenarios(scenarios.filter(s => s.id !== scenarioId));
                  setShowCopyScenarioModal(true);
                } catch (error) {
                  console.error('Failed to load scenarios:', error);
                } finally {
                  setCopyingScenariosLoading(false);
                }
              }}
              disabled={copyingScenariosLoading}
              className="px-4 py-2 bg-surface-raised border border-border-strong rounded-lg text-ink-muted hover:bg-surface-subtle flex items-center font-medium shadow-sm transition-colors"
            >
              {copyingScenariosLoading ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border-strong mr-2" />
              ) : (
                <Copy size={18} className="mr-2" />
              )}
              Copy from Scenario
            </button>
          )}
          {scenarioId && (
            <button
              onClick={async () => {
                setApplyWorkforceLoading(true);
                try {
                  const scenarios = await listScenarios(activeWorkspace.id);
                  const others = scenarios.filter(s => s.id !== scenarioId);
                  setApplyWorkforceScenarios(others);
                  setShowApplyWorkforceModal(true);
                } catch (error) {
                  console.error('Failed to load scenarios:', error);
                } finally {
                  setApplyWorkforceLoading(false);
                }
              }}
              disabled={applyWorkforceLoading}
              className="px-4 py-2 bg-surface-raised border border-border-strong rounded-lg text-ink-muted hover:bg-surface-subtle flex items-center font-medium shadow-sm transition-colors"
            >
              {applyWorkforceLoading ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border-strong mr-2" />
              ) : (
                <Share2 size={18} className="mr-2" />
              )}
              Apply Workforce Params
            </button>
          )}
          <button
            onClick={async () => {
              setTemplatesLoading(true);
              try {
                const response = await listTemplates();
                setTemplates(response.templates);
                setShowTemplateModal(true);
              } catch (error) {
                console.error('Failed to load templates:', error);
              } finally {
                setTemplatesLoading(false);
              }
            }}
            disabled={templatesLoading}
            className="px-4 py-2 bg-surface-raised border border-border-strong rounded-lg text-ink-muted hover:bg-surface-subtle flex items-center font-medium shadow-sm transition-colors"
          >
            {templatesLoading ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border-strong mr-2" />
            ) : (
              <FileText size={18} className="mr-2" />
            )}
            Load Template
          </button>
          <button
            onClick={handleSaveConfig}
            disabled={saveStatus === 'saving'}
            className={`px-4 py-2 text-ink-inverse rounded-lg flex items-center font-medium shadow-sm transition-colors ${saveStatus === 'saving' ? 'bg-surface-disabled cursor-not-allowed' : saveStatus === 'success' ? 'bg-success-solid hover:bg-success-solid-hover' : isDirty ? 'bg-warning-solid hover:bg-warning-solid-hover ring-2 ring-focus' : 'bg-fidelity-green hover:bg-fidelity-dark'}`}
          >
            {saveStatus === 'saving' ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border mr-2"></div>
                Saving...
              </>
            ) : saveStatus === 'success' ? (
              <>
                <Check size={18} className="mr-2" />
                Saved!
              </>
            ) : isDirty ? (
              <>
                <Save size={18} className="mr-2" />
                Save Changes
              </>
            ) : (
              <>
                <Save size={18} className="mr-2" />
                Save Config
              </>
            )}
          </button>
          <button
            onClick={() => navigate(`/simulate?scenario=${scenarioId}`)}
            className={`px-4 py-2 rounded-lg flex items-center font-medium shadow-sm transition-all ${saveStatus === 'success' ? 'bg-info-solid hover:bg-info-solid-hover text-ink-inverse animate-pulse' : 'bg-info-surface hover:bg-info-surface text-info-ink border border-info-border'}`}
          >
            <Play size={18} className="mr-2" />
            Run Simulation
          </button>
        </div>
      </div>

      {/* Validation error banner */}
      {saveStatus === 'error' && saveMessage && (
        <div className="mb-4 rounded-lg bg-danger-surface border border-danger-border p-4 flex items-start">
          <AlertTriangle className="h-5 w-5 text-danger-ink mt-0.5 flex-shrink-0" />
          <p className="ml-3 text-sm text-danger-ink">{saveMessage}</p>
        </div>
      )}

      {/* Content: Sidebar + Form */}
      <div className="flex-1 bg-surface-raised rounded-xl shadow-sm border border-border flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-surface-subtle border-r border-border p-4 flex-shrink-0 overflow-y-auto">
          <nav className="space-y-1">
            {PRIMARY_NAV.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                className={`w-full text-left px-3 py-3 rounded-md text-sm font-medium transition-colors flex items-center justify-between ${activeSection === item.id ? 'bg-surface-raised text-fidelity-green shadow-sm border border-border' : 'text-ink-muted hover:bg-surface-subtle hover:text-ink'}`}
              >
                <span className="flex items-center">
                  <item.icon size={16} className={`mr-3 ${activeSection === item.id ? 'text-fidelity-green' : 'text-ink-subtle'}`} />
                  {item.label}
                </span>
                {dirtySections.has(item.id) && (
                  <span className="w-2 h-2 bg-warning-solid rounded-full" title="Unsaved changes" />
                )}
              </button>
            ))}

            <div className="px-3 pt-5 pb-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Advanced</span>
            </div>

            {ADVANCED_NAV.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                className={`w-full text-left px-3 py-3 rounded-md text-sm font-medium transition-colors flex items-center justify-between ${activeSection === item.id ? 'bg-surface-raised text-fidelity-green shadow-sm border border-border' : 'text-ink-muted hover:bg-surface-subtle hover:text-ink'}`}
              >
                <span className="flex items-center">
                  <item.icon size={16} className={`mr-3 ${activeSection === item.id ? 'text-fidelity-green' : 'text-ink-subtle'}`} />
                  {item.label}
                </span>
                {dirtySections.has(item.id) && (
                  <span className="w-2 h-2 bg-warning-solid rounded-full" title="Unsaved changes" />
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* Form Area */}
        <div className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-3xl">
            {activeSection === 'workforce' && <WorkforceParametersSection />}
            {activeSection === 'simulation' && <SimulationSection />}
            {activeSection === 'datasources' && <DataSourcesSection />}
            {activeSection === 'compensation' && <CompensationSection />}
            {activeSection === 'newhire' && <NewHireSection />}
            {activeSection === 'segmentation' && <SegmentationSection />}
            {activeSection === 'turnover' && <TurnoverSection />}
            {activeSection === 'dcplan' && <DCPlanSection />}
            {activeSection === 'advanced' && <AdvancedSection />}
          </div>
        </div>
      </div>

      {/* Modals */}
      {showTemplateModal && (
        <TemplateModal
          templates={templates}
          onClose={() => setShowTemplateModal(false)}
        />
      )}
      {showCopyScenarioModal && (
        <CopyScenarioModal
          availableScenarios={availableScenarios}
          onClose={() => setShowCopyScenarioModal(false)}
        />
      )}
      {showApplyWorkforceModal && scenarioId && (
        <ApplyWorkforceParamsModal
          availableScenarios={applyWorkforceScenarios}
          sourceScenarioId={scenarioId}
          workspaceId={activeWorkspace.id}
          onClose={() => setShowApplyWorkforceModal(false)}
        />
      )}
    </div>
  );
}

export default function ConfigStudio() {
  const { scenarioId } = useParams<{ scenarioId?: string }>();
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  return (
    <ConfigProvider activeWorkspace={activeWorkspace} scenarioId={scenarioId}>
      <ConfigShell />
    </ConfigProvider>
  );
}
