import React, { Component, ReactNode, ErrorInfo, useEffect, useState } from 'react';
import { HashRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import SimulationControl from './components/SimulationControl';
import SimulationDetail from './components/SimulationDetail';
import ConfigStudio from './components/ConfigStudio';
import ScenariosPage from './components/ScenariosPage';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import ScenarioComparison from './components/ScenarioComparison';
import ScenarioDiff from './components/ScenarioDiff';
import BatchProcessing from './components/BatchProcessing';
import WorkspaceManager from './components/WorkspaceManager';
import DCPlanAnalytics from './components/DCPlanAnalytics';
import ScenarioCostComparison from './components/ScenarioCostComparison';
import VestingAnalysis from './components/VestingAnalysis';
import NDTTesting from './components/NDTTesting';
import WinnersLosersTab from './components/WinnersLosersTab';
import DataImportWizard from './components/DataImportWizard';
import CalibrationPanel from './components/CalibrationPanel';
import OptimizerPanel from './components/OptimizerPanel';
import RunProvenanceReport from './components/RunProvenanceReport';
import EmployeeTimelinePage from './components/timeline/EmployeeTimelinePage';
import { getWorkspace, listWorkspaces } from './services/api';

// Error boundary to catch and display React errors
interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('React Error Boundary caught:', error, errorInfo);
  }

  render(): ReactNode {
    const { children } = this.props;
    const { hasError, error } = this.state;

    if (hasError) {
      return (
        <div className="p-8 bg-danger-surface min-h-screen">
          <h1 className="text-2xl font-bold text-danger-ink mb-4">Something went wrong</h1>
          <pre className="bg-danger-surface p-4 rounded text-sm overflow-auto">
            {error?.message}
            {'\n\n'}
            {error?.stack}
          </pre>
          <button
            className="mt-4 px-4 py-2 bg-danger-solid text-ink-inverse rounded"
            onClick={() => window.location.reload()}
          >
            Reload Page
          </button>
        </div>
      );
    }
    return children;
  }
}

const Placeholder = ({ title }: { title: string }) => (
  <div className="flex flex-col items-center justify-center h-full text-ink-subtle">
    <h2 className="text-xl font-semibold mb-2">{title}</h2>
    <p>This module is currently under development.</p>
  </div>
);

function LegacyWorkspaceRedirect() {
  const location = useLocation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function resolveWorkspace() {
      let rememberedId: string | null = null;
      try {
        rememberedId = window.localStorage.getItem('planalign.activeWorkspaceId');
      } catch {
        // Browser persistence is best-effort; the deterministic fallback below remains safe.
      }

      let selectedId: string | null = null;
      if (rememberedId) {
        try {
          const remembered = await getWorkspace(rememberedId);
          if (remembered.lifecycle === 'active') selectedId = remembered.id;
        } catch {
          // A deleted or inaccessible remembered workspace falls through explicitly.
        }
      }
      if (!selectedId) {
        const page = await listWorkspaces({ lifecycle: 'active', limit: 1, sort: 'name' });
        selectedId = page.items[0]?.id ?? null;
      }
      if (!selectedId) {
        setError('No active workspace is available. Create or restore one to continue.');
        return;
      }

      const legacyTimeline = location.pathname.match(/^\/timeline\/([^/]+)(\/.*)?$/);
      const target = legacyTimeline
        ? `/w/${legacyTimeline[1]}/timeline${legacyTimeline[2] ?? ''}`
        : `/w/${selectedId}${location.pathname === '/' ? '' : location.pathname}`;
      navigate(target, {
        replace: true,
        state: !rememberedId || rememberedId === selectedId
          ? undefined
          : { workspaceNotice: 'The remembered workspace is unavailable. Opened the first active workspace alphabetically.' },
      });
    }

    void resolveWorkspace().catch(err => {
      setError(err instanceof Error ? err.message : 'Failed to resolve a workspace.');
    });
  }, [location.pathname, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-subtle p-8 text-center text-ink-muted">
      {error ?? 'Opening workspace…'}
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <HashRouter>
        <Routes>
          <Route path="/w/:workspaceId" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="simulate" element={<SimulationControl />} />
            <Route path="simulate/:scenarioId" element={<SimulationDetail />} />
            <Route path="simulate/:scenarioId/runs/:runId/provenance" element={<RunProvenanceReport />} />
            <Route path="scenarios" element={<ScenariosPage />} />
            <Route path="config" element={<ConfigStudio />} />
            <Route path="calibrate" element={<CalibrationPanel />} />
            <Route path="optimize" element={<OptimizerPanel />} />
            <Route path="config/:scenarioId" element={<ConfigStudio />} />
            <Route path="analytics" element={<AnalyticsDashboard />} />
            <Route path="analytics/compare" element={<ScenarioComparison />} />
            <Route path="analytics/diff" element={<ScenarioDiff />} />
            <Route path="analytics/dc-plan" element={<DCPlanAnalytics />} />
            <Route path="analytics/vesting" element={<VestingAnalysis />} />
            <Route path="analytics/ndt" element={<NDTTesting />} />
            <Route path="analytics/winners-losers" element={<WinnersLosersTab />} />
            <Route path="compare" element={<ScenarioCostComparison />} />
            <Route path="batch" element={<BatchProcessing />} />
            <Route path="workspaces" element={<WorkspaceManager />} />
            <Route path="import" element={<DataImportWizard />} />
            <Route path="timeline" element={<EmployeeTimelinePage />} />
            <Route path="timeline/:scenarioId/:employeeId" element={<EmployeeTimelinePage />} />
            <Route path="*" element={<Placeholder title="Page Not Found" />} />
          </Route>
          <Route path="*" element={<LegacyWorkspaceRedirect />} />
        </Routes>
      </HashRouter>
    </ErrorBoundary>
  );
}
