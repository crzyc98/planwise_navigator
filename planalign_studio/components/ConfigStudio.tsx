import { useState } from 'react';
import { Save, AlertTriangle, FileText, Settings, TrendingUp, Users, DollarSign, PieChart, Database, Check, ArrowLeft, Play, Copy, Layers } from 'lucide-react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';
import { LayoutContextType } from './Layout';
import { listTemplates, Template, listScenarios, Scenario } from '../services/api';
import { ConfigProvider, useConfigContext } from './config/ConfigContext';
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

const NAV_ITEMS = [
  { id: 'simulation', label: 'Simulation Settings', icon: TrendingUp },
  { id: 'datasources', label: 'Data Sources', icon: Database },
  { id: 'compensation', label: 'Compensation', icon: DollarSign },
  { id: 'newhire', label: 'New Hire Strategy', icon: Users },
  { id: 'segmentation', label: 'Workforce Segmentation', icon: Layers },
  { id: 'turnover', label: 'Workforce & Turnover', icon: AlertTriangle },
  { id: 'dcplan', label: 'DC Plan', icon: PieChart },
  { id: 'advanced', label: 'Advanced Settings', icon: Settings },
];

function ConfigShell() {
  const navigate = useNavigate();
  const {
    currentScenario, scenarioId, scenarioLoading,
    dirtySections, isDirty,
    handleSaveConfig, saveStatus,
    activeWorkspace,
  } = useConfigContext();

  const [activeSection, setActiveSection] = useState('simulation');

  // Template modal state
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  // Copy from scenario modal state
  const [showCopyScenarioModal, setShowCopyScenarioModal] = useState(false);
  const [availableScenarios, setAvailableScenarios] = useState<Scenario[]>([]);
  const [copyingScenariosLoading, setCopyingScenariosLoading] = useState(false);

  if (scenarioLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
          <p className="text-sm text-gray-500">Loading scenario...</p>
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
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                title="Back to Scenarios"
              >
                <ArrowLeft size={20} />
              </button>
            )}
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {currentScenario ? `Configure: ${currentScenario.name}` : 'Base Configuration'}
              </h1>
              <p className="text-gray-500 text-sm">
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
              className="px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 flex items-center font-medium shadow-sm transition-colors"
            >
              {copyingScenariosLoading ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-700 mr-2" />
              ) : (
                <Copy size={18} className="mr-2" />
              )}
              Copy from Scenario
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
            className="px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 flex items-center font-medium shadow-sm transition-colors"
          >
            {templatesLoading ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-700 mr-2" />
            ) : (
              <FileText size={18} className="mr-2" />
            )}
            Load Template
          </button>
          <button
            onClick={handleSaveConfig}
            disabled={saveStatus === 'saving'}
            className={`px-4 py-2 text-white rounded-lg flex items-center font-medium shadow-sm transition-colors ${
              saveStatus === 'saving'
                ? 'bg-gray-400 cursor-not-allowed'
                : saveStatus === 'success'
                ? 'bg-green-600 hover:bg-green-700'
                : isDirty
                ? 'bg-amber-600 hover:bg-amber-700 ring-2 ring-amber-300'
                : 'bg-fidelity-green hover:bg-fidelity-dark'
            }`}
          >
            {saveStatus === 'saving' ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
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
            className={`px-4 py-2 rounded-lg flex items-center font-medium shadow-sm transition-all ${
              saveStatus === 'success'
                ? 'bg-blue-600 hover:bg-blue-700 text-white animate-pulse'
                : 'bg-blue-100 hover:bg-blue-200 text-blue-700 border border-blue-300'
            }`}
          >
            <Play size={18} className="mr-2" />
            Run Simulation
          </button>
        </div>
      </div>

      {/* Content: Sidebar + Form */}
      <div className="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-gray-50 border-r border-gray-200 p-4 flex-shrink-0 overflow-y-auto">
          <nav className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                className={`w-full text-left px-3 py-3 rounded-md text-sm font-medium transition-colors flex items-center justify-between ${
                  activeSection === item.id
                    ? 'bg-white text-fidelity-green shadow-sm border border-gray-200'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                <span className="flex items-center">
                  <item.icon size={16} className={`mr-3 ${activeSection === item.id ? 'text-fidelity-green' : 'text-gray-400'}`} />
                  {item.label}
                </span>
                {dirtySections.has(item.id) && (
                  <span className="w-2 h-2 bg-amber-500 rounded-full" title="Unsaved changes" />
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* Form Area */}
        <div className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-3xl">
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
