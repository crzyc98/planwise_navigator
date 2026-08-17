import React, { useEffect, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { PlayCircle, CheckCircle, AlertCircle, Database, TrendingUp, Users, DollarSign, Activity, Briefcase, Loader2 } from 'lucide-react';
import { getSystemStatus, listScenarios, SystemStatus, Scenario } from '../services/api';
import { Workspace } from '../types';

interface LayoutContext {
  activeWorkspace: Workspace;
}

const colorClasses: Record<string, { hoverBorder: string; bg: string; text: string; hoverBg: string }> = {
  green:  { hoverBorder: 'hover:border-success-border',  bg: 'bg-success-surface',  text: 'text-success-ink',  hoverBg: 'group-hover:bg-success-surface' },
  blue:   { hoverBorder: 'hover:border-info-border',   bg: 'bg-info-surface',   text: 'text-info-ink',   hoverBg: 'group-hover:bg-info-surface' },
  purple: { hoverBorder: 'hover:border-info-border', bg: 'bg-info-surface', text: 'text-info-ink', hoverBg: 'group-hover:bg-info-surface' },
  orange: { hoverBorder: 'hover:border-warning-border', bg: 'bg-warning-surface', text: 'text-warning-ink', hoverBg: 'group-hover:bg-warning-surface' },
};

const StatCard = ({ title, value, subtext, icon, color, onClick }: Readonly<{ title: string; value: string | number; subtext: string; icon: React.ReactNode; color: string; onClick?: () => void }>) => {
  const c = colorClasses[color] ?? colorClasses.green;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.(); } }}
      className={`bg-surface-raised rounded-xl shadow-sm border border-border p-6 flex items-start justify-between cursor-pointer transition-all hover:shadow-md ${c.hoverBorder} group`}
    >
      <div>
        <p className="text-sm font-medium text-ink-muted group-hover:text-ink-muted transition-colors">{title}</p>
        <h3 className="text-2xl font-bold text-ink mt-1">{value}</h3>
        <p className={`text-xs mt-2 font-medium ${subtext.includes('+') ? 'text-success-ink' : 'text-ink-muted'}`}>
          {subtext}
        </p>
      </div>
      <div className={`p-3 rounded-lg ${c.bg} ${c.text} ${c.hoverBg} transition-colors`}>
        {icon}
      </div>
    </div>
  );
};

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
        <h1 className="text-2xl font-bold text-ink">Dashboard</h1>
        <p className="text-ink-muted mt-1">System overview and quick actions.</p>
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
          icon={<Users className="text-info-ink" />}
          color="blue"
          onClick={() => navigate('/analytics')}
        />
        <StatCard
          title="Storage Used"
          value={`${systemStatus?.total_storage_mb?.toFixed(1) ?? '0'} MB`}
          subtext={`${systemStatus?.storage_percent?.toFixed(1) ?? '0'}% of limit`}
          icon={<Database className="text-info-ink" />}
          color="purple"
          onClick={() => navigate('/analytics')}
        />
        <StatCard
          title="Thread Count"
          value={systemStatus?.thread_count ?? '-'}
          subtext="Available CPUs"
          icon={<Briefcase className="text-warning-ink" />}
          color="orange"
          onClick={() => navigate('/config')}
        />
      </div>

      {/* Recent Activity Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 bg-surface-raised rounded-xl shadow-sm border border-border overflow-hidden">
          <div className="px-6 py-4 border-b border-border flex justify-between items-center">
            <h2 className="text-lg font-semibold text-ink">Recent Simulations</h2>
            <button
              onClick={() => navigate('/simulate')}
              className="text-sm text-fidelity-green hover:text-fidelity-dark font-medium"
            >
              View All
            </button>
          </div>
          <div className="divide-y divide-border">
            {isLoading ? (
              <div className="p-6 flex items-center justify-center text-ink-muted">
                <Loader2 className="animate-spin mr-2" size={20} />
                Loading scenarios...
              </div>
            ) : scenarios.length === 0 ? (
              <div className="p-6 text-center text-ink-muted">
                No scenarios found. Create one in Configuration.
              </div>
            ) : (
              scenarios.slice(0, 5).map((scenario) => {
                const isRunning = scenario.status === 'running';
                const isCompleted = scenario.status === 'completed';
                return (
                  <div
                    key={scenario.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSimulationClick(scenario)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSimulationClick(scenario); } }}
                    className="p-6 flex items-center justify-between hover:bg-surface-subtle transition-colors cursor-pointer group"
                  >
                    <div className="flex items-center">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${isRunning ? 'bg-info-surface text-info-ink' : isCompleted ? 'bg-success-surface text-success-ink' : 'bg-surface-subtle text-ink-muted'}`}>
                        {isRunning ? <TrendingUp size={20} /> : <CheckCircle size={20} />}
                      </div>
                      <div className="ml-4">
                        <p className="text-sm font-medium text-ink group-hover:text-fidelity-green transition-colors">
                          {scenario.name}
                        </p>
                        <div className="text-xs text-ink-muted flex items-center mt-0.5">
                          <span>{scenario.description || 'No description'}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center">
                      <span className={`px-3 py-1 rounded-full text-xs font-medium border ${isRunning ? 'bg-info-surface text-info-ink border-info-border' : isCompleted ? 'bg-success-surface text-success-ink border-success-border' : scenario.status === 'failed' ? 'bg-danger-surface text-danger-ink border-danger-border' : 'bg-surface-subtle text-ink-muted border-border'}`}>
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
        <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
          <h2 className="text-lg font-semibold text-ink mb-4">Quick Actions</h2>
          <div className="space-y-3">
             <button
               onClick={() => navigate('/simulate')}
               className="w-full flex items-center p-3 bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-dark transition-colors shadow-sm"
             >
                <PlayCircle size={20} className="mr-3" />
                <span className="font-medium">New Simulation</span>
             </button>
             <button
               onClick={() => navigate('/batch')}
               className="w-full flex items-center p-3 bg-surface-raised border border-border text-ink-muted rounded-lg hover:bg-surface-subtle transition-colors"
             >
                <Database size={20} className="mr-3" />
                <span className="font-medium">New Batch Run</span>
             </button>
             <button
               onClick={() => navigate('/analytics')}
               className="w-full flex items-center p-3 bg-surface-raised border border-border text-ink-muted rounded-lg hover:bg-surface-subtle transition-colors"
             >
                <TrendingUp size={20} className="mr-3" />
                <span className="font-medium">Compare Results</span>
             </button>
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
