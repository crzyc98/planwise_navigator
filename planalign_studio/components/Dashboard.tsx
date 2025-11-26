import React, { useEffect, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { PlayCircle, CheckCircle, AlertCircle, Database, TrendingUp, Users, DollarSign, Activity, Briefcase, Loader2 } from 'lucide-react';
import { getSystemStatus, listScenarios, SystemStatus, Scenario } from '../services/api';
import { Workspace } from '../types';

interface LayoutContext {
  activeWorkspace: Workspace;
}

const StatCard = ({ title, value, subtext, icon, color, onClick }: any) => (
  <div
    onClick={onClick}
    className={`bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex items-start justify-between cursor-pointer transition-all hover:shadow-md hover:border-${color}-200 group`}
  >
    <div>
      <p className="text-sm font-medium text-gray-500 group-hover:text-gray-700 transition-colors">{title}</p>
      <h3 className="text-2xl font-bold text-gray-900 mt-1">{value}</h3>
      <p className={`text-xs mt-2 font-medium ${subtext.includes('+') ? 'text-green-600' : 'text-gray-500'}`}>
        {subtext}
      </p>
    </div>
    <div className={`p-3 rounded-lg bg-${color}-50 text-${color}-600 group-hover:bg-${color}-100 transition-colors`}>
      {icon}
    </div>
  </div>
);

export default function Dashboard() {
  const navigate = useNavigate();
  const { activeWorkspace } = useOutletContext<LayoutContext>();

  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoading(true);
        const [status, scenarioList] = await Promise.all([
          getSystemStatus(),
          listScenarios(activeWorkspace.id),
        ]);
        setSystemStatus(status);
        setScenarios(scenarioList);
      } catch (err) {
        console.error('Failed to load dashboard data:', err);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [activeWorkspace.id]);

  const handleSimulationClick = (scenario: Scenario) => {
    if (scenario.status === 'running') {
      navigate('/simulate');
    } else if (scenario.status === 'completed') {
      navigate('/analytics');
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">System overview and quick actions.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Active Simulations"
          value={systemStatus?.active_simulations ?? '-'}
          subtext={`${systemStatus?.queued_simulations ?? 0} Queued`}
          icon={<ActivityIcon className="text-fidelity-green" />}
          color="green"
          onClick={() => navigate('/simulate')}
        />
        <StatCard
          title="Total Workspaces"
          value={systemStatus?.workspace_count ?? '-'}
          subtext={`${systemStatus?.scenario_count ?? 0} scenarios`}
          icon={<Users className="text-blue-600" />}
          color="blue"
          onClick={() => navigate('/analytics')}
        />
        <StatCard
          title="Storage Used"
          value={`${systemStatus?.total_storage_mb?.toFixed(1) ?? '0'} MB`}
          subtext={`${systemStatus?.storage_percent?.toFixed(1) ?? '0'}% of limit`}
          icon={<Database className="text-purple-600" />}
          color="purple"
          onClick={() => navigate('/analytics')}
        />
        <StatCard
          title="Thread Count"
          value={systemStatus?.thread_count ?? '-'}
          subtext="Available CPUs"
          icon={<Briefcase className="text-orange-600" />}
          color="orange"
          onClick={() => navigate('/config')}
        />
      </div>

      {/* Recent Activity Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-gray-800">Recent Simulations</h2>
            <button
              onClick={() => navigate('/simulate')}
              className="text-sm text-fidelity-green hover:text-fidelity-dark font-medium"
            >
              View All
            </button>
          </div>
          <div className="divide-y divide-gray-100">
            {isLoading ? (
              <div className="p-6 flex items-center justify-center text-gray-500">
                <Loader2 className="animate-spin mr-2" size={20} />
                Loading scenarios...
              </div>
            ) : scenarios.length === 0 ? (
              <div className="p-6 text-center text-gray-500">
                No scenarios found. Create one in Configuration.
              </div>
            ) : (
              scenarios.slice(0, 5).map((scenario) => {
                const isRunning = scenario.status === 'running';
                const isCompleted = scenario.status === 'completed';
                return (
                  <div
                    key={scenario.id}
                    onClick={() => handleSimulationClick(scenario)}
                    className="p-6 flex items-center justify-between hover:bg-gray-50 transition-colors cursor-pointer group"
                  >
                    <div className="flex items-center">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                        isRunning ? 'bg-blue-100 text-blue-600' :
                        isCompleted ? 'bg-green-100 text-green-600' :
                        'bg-gray-100 text-gray-500'
                      }`}>
                        {isRunning ? <TrendingUp size={20} /> : <CheckCircle size={20} />}
                      </div>
                      <div className="ml-4">
                        <p className="text-sm font-medium text-gray-900 group-hover:text-fidelity-green transition-colors">
                          {scenario.name}
                        </p>
                        <div className="text-xs text-gray-500 flex items-center mt-0.5">
                          <span>{scenario.description || 'No description'}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center">
                      <span className={`px-3 py-1 rounded-full text-xs font-medium border ${
                        isRunning ? 'bg-blue-50 text-blue-700 border-blue-100' :
                        isCompleted ? 'bg-green-50 text-green-700 border-green-100' :
                        scenario.status === 'failed' ? 'bg-red-50 text-red-700 border-red-100' :
                        'bg-gray-50 text-gray-700 border-gray-100'
                      }`}>
                        {scenario.status === 'not_run' ? 'Not Run' : scenario.status}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Quick Actions</h2>
          <div className="space-y-3">
             <button
               onClick={() => navigate('/simulate')}
               className="w-full flex items-center p-3 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark transition-colors shadow-sm"
             >
                <PlayCircle size={20} className="mr-3" />
                <span className="font-medium">New Simulation</span>
             </button>
             <button
               onClick={() => navigate('/batch')}
               className="w-full flex items-center p-3 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
             >
                <Database size={20} className="mr-3" />
                <span className="font-medium">New Batch Run</span>
             </button>
             <button
               onClick={() => navigate('/analytics')}
               className="w-full flex items-center p-3 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
             >
                <TrendingUp size={20} className="mr-3" />
                <span className="font-medium">Compare Results</span>
             </button>
          </div>

          <div className="mt-8 p-4 bg-yellow-50 rounded-lg border border-yellow-100">
            <div className="flex items-start">
              <AlertCircle size={20} className="text-yellow-600 mt-0.5" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800">System Maintenance</h3>
                <p className="text-xs text-yellow-700 mt-1">
                  Scheduled for tonight at 02:00 AM EST. Simulations may be paused.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Icon helper
function ActivityIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
    </svg>
  );
}
