import React from 'react';
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

const Placeholder = ({ title }: { title: string }) => (
  <div className="flex flex-col items-center justify-center h-full text-gray-400">
    <h2 className="text-xl font-semibold mb-2">{title}</h2>
    <p>This module is currently under development.</p>
  </div>
);

export default function App() {
  return (
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
          <Route path="batch" element={<BatchProcessing />} />
          <Route path="workspaces" element={<WorkspaceManager />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
