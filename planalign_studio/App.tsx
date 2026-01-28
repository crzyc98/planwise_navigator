import React, { Component, ReactNode, ErrorInfo } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import SimulationControl from './components/SimulationControl';
import SimulationDetail from './components/SimulationDetail';
import ConfigStudio from './components/ConfigStudio';
import ScenariosPage from './components/ScenariosPage';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import ScenarioComparison from './components/ScenarioComparison';
import BatchProcessing from './components/BatchProcessing';
import WorkspaceManager from './components/WorkspaceManager';
import DCPlanAnalytics from './components/DCPlanAnalytics';
import ScenarioCostComparison from './components/ScenarioCostComparison';
import VestingAnalysis from './components/VestingAnalysis';

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
        <div className="p-8 bg-red-50 min-h-screen">
          <h1 className="text-2xl font-bold text-red-700 mb-4">Something went wrong</h1>
          <pre className="bg-red-100 p-4 rounded text-sm overflow-auto">
            {error?.message}
            {'\n\n'}
            {error?.stack}
          </pre>
          <button
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded"
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
  <div className="flex flex-col items-center justify-center h-full text-gray-400">
    <h2 className="text-xl font-semibold mb-2">{title}</h2>
    <p>This module is currently under development.</p>
  </div>
);

export default function App() {
  return (
    <ErrorBoundary>
      <HashRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="simulate" element={<SimulationControl />} />
            <Route path="simulate/:scenarioId" element={<SimulationDetail />} />
            <Route path="scenarios" element={<ScenariosPage />} />
            <Route path="config" element={<ConfigStudio />} />
            <Route path="config/:scenarioId" element={<ConfigStudio />} />
            <Route path="analytics" element={<AnalyticsDashboard />} />
            <Route path="analytics/compare" element={<ScenarioComparison />} />
            <Route path="analytics/dc-plan" element={<DCPlanAnalytics />} />
            <Route path="analytics/vesting" element={<VestingAnalysis />} />
            <Route path="compare" element={<ScenarioCostComparison />} />
            <Route path="batch" element={<BatchProcessing />} />
            <Route path="workspaces" element={<WorkspaceManager />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </ErrorBoundary>
  );
}
