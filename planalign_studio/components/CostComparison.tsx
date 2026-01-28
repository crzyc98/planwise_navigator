
import React, { useState, useMemo } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area, ComposedChart, Line
} from 'recharts';
import {
  CheckSquare, Square, Info,
  TrendingUp, Download, Filter, Search,
  Layers, Anchor, Calendar, Calculator, TrendingDown,
  DollarSign, Briefcase, Target, ShieldCheck, Zap
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import { MOCK_CONFIGS, RETIREMENT_COST_DATA, COLORS } from '../constants';

export default function CostComparison() {
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  // Get all configs for the current workspace
  const workspaceConfigs = useMemo(() => {
    return MOCK_CONFIGS.filter(c => activeWorkspace.scenarios.includes(c.id));
  }, [activeWorkspace.scenarios]);

  // UI State
  const [selectedIds, setSelectedIds] = useState<string[]>(
    workspaceConfigs.slice(0, 3).map(c => c.id)
  );
  const [baselineId, setBaselineId] = useState<string>(workspaceConfigs[0]?.id || '');
  const [viewMode, setViewMode] = useState<'annual' | 'cumulative'>('annual');
  const [searchQuery, setSearchQuery] = useState('');

  const toggleSelection = (id: string) => {
    if (selectedIds.includes(id)) {
      if (selectedIds.length > 1) {
        setSelectedIds(prev => prev.filter(i => i !== id));
        if (baselineId === id) {
          const remaining = selectedIds.filter(i => i !== id);
          setBaselineId(remaining[0]);
        }
      }
    } else {
      setSelectedIds(prev => [...prev, id]);
    }
  };

  const filteredConfigs = workspaceConfigs.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Years in the data
  const years = useMemo(() => RETIREMENT_COST_DATA.map(d => d.year), []);
  const yearCount = years.length;

  // Current Baseline Config Object
  const baselineConfig = useMemo(() =>
    MOCK_CONFIGS.find(c => c.id === baselineId),
  [baselineId]);

  // Transformation logic for charts
  const processedData = useMemo(() => {
    const data = RETIREMENT_COST_DATA.map((yearRow: any) => {
      const row: any = { year: yearRow.year };

      selectedIds.forEach(id => {
        row[id] = yearRow[id] || 0;
        if (baselineId && id !== baselineId) {
          row[`${id}_delta`] = (yearRow[id] || 0) - (yearRow[baselineId] || 0);
        }
      });

      return row;
    });

    if (viewMode === 'cumulative') {
      let cumulative: any = [];
      let runningTotals: Record<string, number> = {};
      selectedIds.forEach(id => runningTotals[id] = 0);

      data.forEach(yearRow => {
        const newRow: any = { year: yearRow.year };
        selectedIds.forEach(id => {
          runningTotals[id] += yearRow[id];
          newRow[id] = runningTotals[id];

          if (baselineId && id !== baselineId) {
            newRow[`${id}_delta`] = runningTotals[id] - runningTotals[baselineId];
          }
        });
        cumulative.push(newRow);
      });
      return cumulative;
    }

    return data;
  }, [selectedIds, baselineId, viewMode]);

  // Baseline Summary Calculations
  const baselineSummary = useMemo(() => {
    const annuals = RETIREMENT_COST_DATA.map(d => (d as any)[baselineId] || 0);
    const cumulativeTotal = annuals.reduce((a, b) => a + b, 0);
    return {
      cumulativeTotal,
      avgAnnualCost: cumulativeTotal / yearCount,
    };
  }, [baselineId, yearCount]);

  return (
    <div className="flex h-full gap-6 animate-fadeIn">

      {/* Sidebar Selector */}
      <aside className="w-80 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col overflow-hidden flex-shrink-0">
        <div className="p-4 border-b border-gray-100 bg-gray-50">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-gray-800 flex items-center">
              <Filter size={18} className="mr-2 text-gray-500" />
              Scenarios
            </h3>
            <span className="text-[10px] font-bold bg-fidelity-green text-white px-1.5 py-0.5 rounded">
              {selectedIds.length} SELECTED
            </span>
          </div>

          <div className="mt-3 relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-white border border-gray-200 rounded-md focus:ring-1 focus:ring-fidelity-green outline-none"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <div className="px-2 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-widest">Select & Anchor</div>
          {filteredConfigs.map((config) => {
            const isSelected = selectedIds.includes(config.id);
            const isBaseline = baselineId === config.id;

            return (
              <div
                key={config.id}
                className={`group w-full text-left px-3 py-2 rounded-lg flex items-center justify-between transition-all border ${
                  isSelected
                    ? isBaseline
                        ? 'bg-blue-50 border-blue-200 shadow-sm'
                        : 'bg-fidelity-green/5 border-fidelity-green/20'
                    : 'hover:bg-gray-50 border-transparent'
                }`}
              >
                <button
                  onClick={() => toggleSelection(config.id)}
                  className="flex items-start flex-1 min-w-0"
                >
                  <div className="mt-1 mr-3 flex-shrink-0">
                    {isSelected ? (
                      <CheckSquare size={16} className={isBaseline ? "text-blue-600" : "text-fidelity-green"} />
                    ) : (
                      <Square size={16} className="text-gray-300" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className={`text-xs font-semibold block truncate ${isSelected ? isBaseline ? 'text-blue-700' : 'text-fidelity-green' : 'text-gray-700'}`}>
                      {config.name}
                    </span>
                    <p className="text-[9px] text-gray-500 uppercase tracking-tight">
                      {isBaseline ? 'Baseline Anchor' : 'Scenario Config'}
                    </p>
                  </div>
                </button>

                {isSelected && (
                  <button
                    onClick={() => setBaselineId(config.id)}
                    className={`ml-2 p-1 rounded-md transition-colors ${
                      isBaseline
                        ? 'bg-blue-600 text-white'
                        : 'text-gray-400 hover:text-blue-600 hover:bg-blue-50'
                    }`}
                    title={isBaseline ? "Current Anchor" : "Set as Anchor"}
                  >
                    <Anchor size={14} />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        <div className="p-4 border-t border-gray-100 bg-gray-50 space-y-2">
           <div className="bg-white p-3 rounded-lg border border-gray-200">
             <div className="flex items-center text-[10px] font-bold text-gray-400 uppercase mb-2">
               <Anchor size={10} className="mr-1" /> Active Anchor
             </div>
             <div className="text-xs font-bold text-gray-800 truncate">
                {baselineConfig?.name || 'None'}
             </div>
           </div>
          <button className="w-full py-2 bg-white border border-gray-300 rounded-lg text-xs font-bold text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors">
            <Download size={14} className="mr-2" /> Download Report
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 space-y-6 overflow-y-auto pr-2 pb-8">

        {/* Compact Baseline Anchor Header */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex flex-col md:flex-row gap-8 items-start md:items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center space-x-2 text-blue-600 font-bold text-[10px] uppercase tracking-widest mb-1.5">
              <Anchor size={12} />
              <span>Anchored Baseline Context</span>
            </div>
            <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">{baselineConfig?.name}</h2>
            <div className="flex items-center mt-3 space-x-3">
              <span className="flex items-center text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded">
                <Calendar size={12} className="mr-1.5" /> {yearCount}-Year Plan
              </span>
              <span className="flex items-center text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded">
                <DollarSign size={12} className="mr-1.5" /> ${baselineSummary.cumulativeTotal.toFixed(1)}M Total Costs
              </span>
            </div>
          </div>

          <div className="flex gap-4">
            {/* Core Design Pill */}
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 min-w-[180px]">
              <div className="flex items-center space-x-2 text-blue-600 font-bold text-[9px] uppercase tracking-wider mb-2">
                <ShieldCheck size={12} />
                <span>Core Design</span>
              </div>
              <p className="text-sm font-bold text-blue-900">Fixed Non-Elective</p>
              <p className="text-[10px] text-blue-700 mt-1">3.0% Automatic Contribution</p>
            </div>

            {/* Match Design Pill */}
            <div className="bg-green-50 border border-green-100 rounded-xl p-4 min-w-[180px]">
              <div className="flex items-center space-x-2 text-fidelity-green font-bold text-[9px] uppercase tracking-wider mb-2">
                <Zap size={12} />
                <span>Match Design</span>
              </div>
              <p className="text-sm font-bold text-green-900">{baselineConfig?.dcMatchPercent}% Up To {baselineConfig?.dcMatchLimit}%</p>
              <p className="text-[10px] text-green-700 mt-1">Employee Elective Contribution</p>
            </div>
          </div>
        </div>

        {/* Primary Chart: Cost Trends */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h3 className="text-lg font-bold text-gray-900">Employer Cost Trends</h3>
              <p className="text-sm text-gray-500">Comparing total contributions for the selected horizon.</p>
            </div>

            {/* View Mode Toggle */}
            <div className="flex bg-gray-100 p-1 rounded-lg">
              <button
                onClick={() => setViewMode('annual')}
                className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${
                  viewMode === 'annual' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Annual Spend
              </button>
              <button
                onClick={() => setViewMode('cumulative')}
                className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${
                  viewMode === 'cumulative' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Cumulative Cost
              </button>
            </div>
          </div>

          <div className="h-96">
            <ResponsiveContainer width="100%" height="100%">
              {viewMode === 'annual' ? (
                <BarChart data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={v => `$${v}M`} />
                  <Tooltip
                    cursor={{ fill: '#f8fafc' }}
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                  />
                  <Legend iconType="circle" />
                  {selectedIds.map((id, idx) => (
                    <Bar
                      key={id}
                      dataKey={id}
                      name={workspaceConfigs.find(c => c.id === id)?.name || id}
                      fill={id === baselineId ? '#1e293b' : COLORS.charts[idx % COLORS.charts.length]}
                      radius={[4, 4, 0, 0]}
                      barSize={selectedIds.length > 4 ? 12 : 30}
                    />
                  ))}
                </BarChart>
              ) : (
                <AreaChart data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={v => `$${v}M`} />
                  <Tooltip
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                  />
                  <Legend iconType="circle" />
                  {selectedIds.map((id, idx) => (
                    <Area
                      key={id}
                      type="monotone"
                      dataKey={id}
                      name={workspaceConfigs.find(c => c.id === id)?.name || id}
                      stroke={id === baselineId ? '#1e293b' : COLORS.charts[idx % COLORS.charts.length]}
                      fill={id === baselineId ? '#1e293b' : COLORS.charts[idx % COLORS.charts.length]}
                      fillOpacity={0.1}
                      strokeWidth={id === baselineId ? 3 : 2}
                    />
                  ))}
                </AreaChart>
              )}
            </ResponsiveContainer>
          </div>
        </div>

        {/* Secondary Chart: Incremental Delta */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
           <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-gray-900 flex items-center">
                <Calculator size={18} className="mr-2 text-blue-600" />
                Incremental Costs vs. {baselineConfig?.name}
              </h3>
              <div className="px-3 py-1 bg-blue-50 text-blue-700 text-[10px] font-bold rounded-md uppercase tracking-wide">
                Values represent cost delta ($M)
              </div>
           </div>

           <div className="h-64">
             <ResponsiveContainer width="100%" height="100%">
               <ComposedChart data={processedData}>
                 <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                 <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                 <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={v => `$${v}M`} />
                 <Tooltip
                   contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                 />
                 <Legend />
                 {selectedIds.filter(id => id !== baselineId).map((id, idx) => (
                   <Line
                     key={`${id}_delta`}
                     type="monotone"
                     dataKey={`${id}_delta`}
                     name={`Delta: ${workspaceConfigs.find(c => c.id === id)?.name}`}
                     stroke={COLORS.charts[idx % COLORS.charts.length]}
                     strokeWidth={2}
                     dot={{ r: 4 }}
                   />
                 ))}
                 <Line dataKey={() => 0} name="Baseline Zero" stroke="#1e293b" strokeDasharray="5 5" dot={false} strokeWidth={2} />
               </ComposedChart>
             </ResponsiveContainer>
           </div>
           <p className="mt-4 text-xs text-gray-500 italic text-center">
             Highlights additional matching and core expenses relative to the {viewMode} costs of the anchored baseline.
           </p>
        </div>

        {/* Data Grid: Multi-Year Cost Matrix */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-800 uppercase tracking-wider">Multi-Year Cost Matrix</h3>
            <div className="flex items-center space-x-2">
               <span className="text-[10px] bg-white border border-gray-200 text-gray-600 px-2 py-0.5 rounded font-bold flex items-center">
                 <DollarSign size={8} className="mr-0.5" /> VALUES IN $M
               </span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 font-bold">
                <tr>
                  <th rowSpan={2} className="px-6 py-4 text-left text-xs text-gray-500 uppercase tracking-wider border-r border-gray-200">Scenario Name</th>
                  {years.map(y => (
                    <th key={y} className="px-6 py-2 text-center text-[10px] text-gray-400 uppercase border-b border-gray-200">{y} Costs</th>
                  ))}
                  <th rowSpan={2} className="px-6 py-4 text-right text-xs text-gray-900 uppercase tracking-wider bg-gray-100 border-l border-gray-200">Total {yearCount}-Year Plan</th>
                  <th rowSpan={2} className="px-6 py-4 text-right text-xs text-gray-900 uppercase tracking-wider bg-gray-50">Incremental Variance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {selectedIds.map((id) => {
                  const config = workspaceConfigs.find(c => c.id === id);
                  const isBaseline = id === baselineId;

                  const annuals = RETIREMENT_COST_DATA.map(d => (d as any)[id] || 0);
                  const total = annuals.reduce((a, b) => a + b, 0);
                  const baselineTotal = RETIREMENT_COST_DATA.map(d => (d as any)[baselineId] || 0).reduce((a, b) => a + b, 0);
                  const delta = total - baselineTotal;

                  return (
                    <tr key={id} className={`hover:bg-gray-50 transition-colors ${isBaseline ? 'bg-blue-50/30' : ''}`}>
                      <td className="px-6 py-4 whitespace-nowrap border-r border-gray-100">
                        <div className="flex items-center">
                          <div className={`w-2 h-2 rounded-full mr-2 ${isBaseline ? 'bg-blue-600' : 'bg-fidelity-green'}`} />
                          <span className={`text-sm font-bold ${isBaseline ? 'text-blue-700' : 'text-gray-900'}`}>
                            {config?.name}
                            {isBaseline && <span className="ml-2 text-[8px] font-bold bg-blue-100 text-blue-600 px-1 py-0.5 rounded uppercase">Anchor</span>}
                          </span>
                        </div>
                      </td>
                      {annuals.map((val, i) => (
                        <td key={i} className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-600 font-mono">
                          ${val.toFixed(2)}
                        </td>
                      ))}
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-900 font-bold font-mono bg-gray-50/50 border-l border-gray-100">
                        ${total.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right">
                         {isBaseline ? (
                           <span className="text-xs text-gray-400 italic">--</span>
                         ) : (
                           <span className={`px-2 py-1 text-xs font-bold rounded ${delta >= 0 ? 'bg-orange-50 text-orange-700' : 'bg-green-50 text-green-700'}`}>
                             {delta >= 0 ? '+' : ''}${delta.toFixed(2)}M
                           </span>
                         )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Methodology Footer Section */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
           <div className="bg-gray-900 text-gray-300 p-6 rounded-xl border border-gray-800 shadow-lg">
             <div className="flex items-center text-fidelity-light mb-4 font-bold">
                <TrendingDown size={18} className="mr-2" />
                Cost Sensitivity Drivers
             </div>
             <div className="space-y-4 text-sm leading-relaxed">
                <p>
                  Plan costs are primarily sensitive to <strong>enrollment velocity</strong> and <strong>merit compounding</strong>. High-growth scenarios compound these effects, creating significant multi-year divergence.
                </p>
                <p>
                  The <span className="text-white font-bold">Incremental Variance</span> metric captures the added financial burden of non-baseline policy logic, such as higher matching percentages or lower eligibility periods.
                </p>
             </div>
           </div>

           <div className="bg-blue-50 p-6 rounded-xl border border-blue-100">
             <div className="flex items-center text-blue-700 mb-4 font-bold">
                <Info size={18} className="mr-2" />
                Modeling Assumptions
             </div>
             <ul className="space-y-3 text-sm text-blue-800">
                <li className="flex items-start">
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 mr-2 flex-shrink-0" />
                  <span><strong>Core Design:</strong> Fixed contribution of 3.0% of eligible compensation.</span>
                </li>
                <li className="flex items-start">
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 mr-2 flex-shrink-0" />
                  <span><strong>Match Logic:</strong> Based on configured percentage caps and employer limits.</span>
                </li>
                <li className="flex items-start">
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 mr-2 flex-shrink-0" />
                  <span><strong>Total Cost:</strong> Core + Match + Merit-adjusted salary base overhead.</span>
                </li>
             </ul>
           </div>
        </div>

      </div>
    </div>
  );
}
