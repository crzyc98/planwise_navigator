/**
 * E018: Scenario Cost Comparison Redesign
 *
 * Multi-scenario comparison page with:
 * - Sidebar-based scenario selection with search
 * - Anchor/baseline designation for variance calculations
 * - Annual/Cumulative view toggle
 * - Employer Cost Trends chart (BarChart/AreaChart)
 * - Incremental Costs variance chart
 * - Multi-Year Cost Matrix table
 * - Methodology panels
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area, ComposedChart, Line
} from 'recharts';
import {
  CheckSquare, Square, Search, Filter,
  Anchor, Calendar, DollarSign, Download,
  RefreshCw, AlertCircle, Loader2,
  TrendingUp, TrendingDown, Info, Calculator,
  ShieldCheck, Zap, Copy, Check, ArrowUp, ArrowDown
} from 'lucide-react';
import { useCopyToClipboard } from '../hooks/useCopyToClipboard';
import { LayoutContextType } from './Layout';
import {
  listScenarios,
  compareDCPlanAnalytics,
  getScenarioConfig,
  Scenario,
  DCPlanComparisonResponse,
  DCPlanAnalytics,
  ContributionYearSummary,
} from '../services/api';
import { COLORS, MAX_SCENARIO_SELECTION } from '../constants';

// ============================================================================
// Utility Functions
// ============================================================================

const formatCurrency = (value: number): string => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
};

const formatPercent = (value: number, decimals: number = 1): string => {
  return `${value.toFixed(decimals)}%`;
};

// ============================================================================
// LocalStorage Helpers for Persisting Comparison Preferences
// ============================================================================

const STORAGE_KEY_PREFIX = 'planalign_comparison_';

function saveComparisonPrefs(workspaceId: string, prefs: { selectedIds: string[]; anchorId: string }) {
  try {
    localStorage.setItem(`${STORAGE_KEY_PREFIX}${workspaceId}`, JSON.stringify(prefs));
  } catch (e) {
    console.warn('Failed to save comparison preferences:', e);
  }
}

function loadComparisonPrefs(workspaceId: string): { selectedIds: string[]; anchorId: string } | null {
  try {
    const stored = localStorage.getItem(`${STORAGE_KEY_PREFIX}${workspaceId}`);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch (e) {
    console.warn('Failed to load comparison preferences:', e);
  }
  return null;
}

// ============================================================================
// Sub-Components
// ============================================================================

// Custom legend that respects the order of items passed to it
interface CustomLegendProps {
  items: Array<{ name: string; color: string }>;
}

const CustomLegend: React.FC<CustomLegendProps> = ({ items }) => {
  return (
    <div className="flex flex-wrap justify-center gap-4 mt-2">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: item.color }}
          />
          <span className="text-xs text-gray-600">{item.name}</span>
        </div>
      ))}
    </div>
  );
};

const EmptyState = ({ message, onRefresh }: { message: string; onRefresh?: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-gray-400">
    <AlertCircle size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-gray-600 mb-2">No Data Available</h3>
    <p className="text-sm text-gray-500 mb-4 text-center max-w-md">{message}</p>
    {onRefresh && (
      <button
        onClick={onRefresh}
        className="flex items-center px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors"
      >
        <RefreshCw size={16} className="mr-2" />
        Refresh Data
      </button>
    )}
  </div>
);

const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-red-400">
    <AlertCircle size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-red-600 mb-2">Failed to Load Data</h3>
    <p className="text-sm text-gray-500 mb-4 text-center max-w-md">{message}</p>
    <button
      onClick={onRetry}
      className="flex items-center px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Retry
    </button>
  </div>
);

const LoadingState = () => (
  <div className="flex flex-col items-center justify-center h-96 text-gray-400">
    <Loader2 size={48} className="mb-4 animate-spin" />
    <h3 className="text-lg font-semibold text-gray-600">Loading comparison data...</h3>
  </div>
);

// ============================================================================
// Main Component
// ============================================================================

export default function ScenarioCostComparison() {
  // -------------------------------------------------------------------------
  // Context: Active Workspace from Layout
  // -------------------------------------------------------------------------
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  // -------------------------------------------------------------------------
  // State: Scenario Selection
  // -------------------------------------------------------------------------
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [anchorScenarioId, setAnchorScenarioId] = useState<string>('');

  // -------------------------------------------------------------------------
  // State: View Configuration
  // -------------------------------------------------------------------------
  const [viewMode, setViewMode] = useState<'annual' | 'cumulative'>('annual');
  const [searchQuery, setSearchQuery] = useState('');

  // -------------------------------------------------------------------------
  // State: API Data & UI State
  // -------------------------------------------------------------------------
  const [comparisonData, setComparisonData] = useState<DCPlanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anchorConfig, setAnchorConfig] = useState<Record<string, any> | null>(null);

  // -------------------------------------------------------------------------
  // Copy to Clipboard Hook
  // -------------------------------------------------------------------------
  const { copy, copied, error: copyError } = useCopyToClipboard();

  // -------------------------------------------------------------------------
  // Derived Data: Completed Scenarios
  // -------------------------------------------------------------------------
  const completedScenarios = useMemo(() =>
    scenarios.filter(s => s.status === 'completed'),
    [scenarios]
  );

  // -------------------------------------------------------------------------
  // Derived Data: Filtered Scenarios (search)
  // -------------------------------------------------------------------------
  const filteredScenarios = useMemo(() =>
    completedScenarios.filter(s =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase())
    ),
    [completedScenarios, searchQuery]
  );

  // -------------------------------------------------------------------------
  // Derived Data: Anchor Analytics
  // -------------------------------------------------------------------------
  const anchorAnalytics = useMemo(() =>
    comparisonData?.analytics.find(a => a.scenario_id === anchorScenarioId),
    [comparisonData, anchorScenarioId]
  );

  // -------------------------------------------------------------------------
  // Derived Data: Years from comparison data
  // -------------------------------------------------------------------------
  const years = useMemo(() => {
    if (!comparisonData || comparisonData.analytics.length === 0) return [];
    const allYears = new Set<number>();
    comparisonData.analytics.forEach(a => {
      a.contribution_by_year.forEach(y => allYears.add(y.year));
    });
    return Array.from(allYears).sort((a, b) => a - b);
  }, [comparisonData]);

  // -------------------------------------------------------------------------
  // Derived Data: Processed Chart Data
  // -------------------------------------------------------------------------
  const processedData = useMemo(() => {
    if (!comparisonData || years.length === 0) return [];

    // Build year -> scenario -> cost map
    const yearDataMap = new Map<number, Map<string, number>>();
    years.forEach(year => yearDataMap.set(year, new Map()));

    comparisonData.analytics.forEach(analytics => {
      const scenarioId = analytics.scenario_id;
      analytics.contribution_by_year.forEach(yearData => {
        const yearMap = yearDataMap.get(yearData.year);
        if (yearMap) {
          yearMap.set(scenarioId, yearData.total_employer_cost);
        }
      });
    });

    // Transform to chart data
    let data = years.map(year => {
      const yearMap = yearDataMap.get(year) || new Map();
      const row: Record<string, number> = { year };

      selectedScenarioIds.forEach(id => {
        row[id] = yearMap.get(id) || 0;
        // Calculate delta from anchor
        if (anchorScenarioId && id !== anchorScenarioId) {
          const anchorValue = yearMap.get(anchorScenarioId) || 0;
          row[`${id}_delta`] = (row[id] || 0) - anchorValue;
        }
      });

      return row;
    });

    // Apply cumulative transformation if needed
    if (viewMode === 'cumulative') {
      const runningTotals: Record<string, number> = {};
      selectedScenarioIds.forEach(id => {
        runningTotals[id] = 0;
      });

      data = data.map(yearRow => {
        const newRow: Record<string, number> = { year: yearRow.year };

        selectedScenarioIds.forEach(id => {
          runningTotals[id] += yearRow[id] || 0;
          newRow[id] = runningTotals[id];

          if (anchorScenarioId && id !== anchorScenarioId) {
            newRow[`${id}_delta`] = runningTotals[id] - runningTotals[anchorScenarioId];
          }
        });

        return newRow;
      });
    }

    return data;
  }, [comparisonData, selectedScenarioIds, anchorScenarioId, viewMode, years]);

  // -------------------------------------------------------------------------
  // Derived Data: Anchor Summary
  // -------------------------------------------------------------------------
  const anchorSummary = useMemo(() => {
    if (!anchorAnalytics) return null;
    const totalCost = anchorAnalytics.contribution_by_year.reduce(
      (sum, y) => sum + y.total_employer_cost, 0
    );
    return {
      name: anchorAnalytics.scenario_name,
      yearCount: anchorAnalytics.contribution_by_year.length,
      totalCost,
      avgAnnualCost: totalCost / anchorAnalytics.contribution_by_year.length,
    };
  }, [anchorAnalytics]);

  // -------------------------------------------------------------------------
  // Derived Data: Ordered Scenario IDs (anchor first, then rest in user order)
  // -------------------------------------------------------------------------
  const orderedScenarioIds = useMemo(() => {
    if (!anchorScenarioId) return selectedScenarioIds;
    const nonAnchor = selectedScenarioIds.filter(id => id !== anchorScenarioId);
    return [anchorScenarioId, ...nonAnchor];
  }, [selectedScenarioIds, anchorScenarioId]);

  // -------------------------------------------------------------------------
  // Derived Data: Consistent Color Map for Scenarios
  // -------------------------------------------------------------------------
  const scenarioColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    let colorIdx = 0;
    // Use orderedScenarioIds so colors are stable relative to display order
    orderedScenarioIds.forEach(id => {
      if (id !== anchorScenarioId) {
        map[id] = COLORS.charts[colorIdx % COLORS.charts.length];
        colorIdx++;
      }
    });
    return map;
  }, [orderedScenarioIds, anchorScenarioId]);

  // -------------------------------------------------------------------------
  // Derived Data: Plan Design from Anchor Config
  // -------------------------------------------------------------------------
  const coreDesign = useMemo(() => {
    if (!anchorConfig?.employer_core_contribution) {
      return { title: 'Core Contribution', subtitle: 'Not configured' };
    }
    const core = anchorConfig.employer_core_contribution;
    if (!core.enabled) {
      return { title: 'Core Contribution', subtitle: 'Disabled' };
    }
    if (core.status === 'graded_by_service') {
      const schedule = core.graded_schedule || [];
      const rates = schedule.map((t: any) => `${(t.contribution_rate * 100).toFixed(0)}%`).join(' / ');
      return { title: 'Graded by Service', subtitle: rates || 'See schedule' };
    }
    const rate = (core.contribution_rate * 100).toFixed(1);
    return { title: 'Fixed Non-Elective', subtitle: `${rate}% Automatic Contribution` };
  }, [anchorConfig]);

  const matchDesign = useMemo(() => {
    if (!anchorConfig?.employer_match) {
      return { title: 'Employer Match', subtitle: 'Not configured' };
    }
    const match = anchorConfig.employer_match;
    const activeFormula = match.active_formula;
    const formulas = match.formulas || {};
    const formula = formulas[activeFormula];

    if (!formula) {
      return { title: activeFormula || 'Match Formula', subtitle: 'See configuration' };
    }

    if (formula.type === 'simple') {
      const matchRate = ((formula.match_rate || 0) * 100).toFixed(0);
      const maxMatch = ((formula.max_match_percentage || 0) * 100).toFixed(0);
      return { title: `${matchRate}% Match`, subtitle: `Up to ${maxMatch}% of pay` };
    }

    if (formula.type === 'tiered' && formula.tiers) {
      const firstTier = formula.tiers[0];
      if (firstTier) {
        const matchRate = ((firstTier.match_rate || 0) * 100).toFixed(0);
        const tierMax = ((firstTier.employee_max || 0) * 100).toFixed(0);
        return { title: `${matchRate}% on first ${tierMax}%`, subtitle: formula.name || 'Tiered Match' };
      }
    }

    return { title: formula.name || activeFormula, subtitle: 'See configuration' };
  }, [anchorConfig]);

  // -------------------------------------------------------------------------
  // API Functions
  // -------------------------------------------------------------------------
  const fetchScenarios = useCallback(async (workspaceId: string) => {
    setLoadingScenarios(true);
    try {
      const data = await listScenarios(workspaceId);
      setScenarios(data);

      const completed = data.filter(s => s.status === 'completed');
      const completedIds = new Set(completed.map(s => s.id));

      // Try to restore saved preferences
      const savedPrefs = loadComparisonPrefs(workspaceId);
      if (savedPrefs) {
        // Filter to only include scenarios that still exist and are completed
        const validSelectedIds = savedPrefs.selectedIds.filter(id => completedIds.has(id));
        const validAnchorId = completedIds.has(savedPrefs.anchorId) ? savedPrefs.anchorId : '';

        if (validSelectedIds.length > 0) {
          // Restore saved selection
          setSelectedScenarioIds(validSelectedIds);
          setAnchorScenarioId(validAnchorId || validSelectedIds[0]);
          return;
        }
      }

      // Fall back to auto-selection: find "baseline" scenario
      if (completed.length >= 1) {
        const baselineScenario = completed.find(
          s => s.name.toLowerCase() === 'baseline'
        );

        if (baselineScenario) {
          // Use "baseline" as anchor, select first other scenario too
          const others = completed.filter(s => s.id !== baselineScenario.id);
          const initialSelection = others.length > 0
            ? [baselineScenario.id, others[0].id]
            : [baselineScenario.id];
          setSelectedScenarioIds(initialSelection);
          setAnchorScenarioId(baselineScenario.id);
        } else if (completed.length >= 2) {
          // No "baseline", select first two
          setSelectedScenarioIds([completed[0].id, completed[1].id]);
          setAnchorScenarioId(completed[0].id);
        } else {
          // Only one completed scenario
          setSelectedScenarioIds([completed[0].id]);
          setAnchorScenarioId(completed[0].id);
        }
      } else {
        setSelectedScenarioIds([]);
        setAnchorScenarioId('');
      }
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  }, []);

  const fetchComparison = useCallback(async () => {
    if (!activeWorkspace?.id || selectedScenarioIds.length === 0) {
      setComparisonData(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await compareDCPlanAnalytics(activeWorkspace.id, selectedScenarioIds);
      setComparisonData(data);
    } catch (err) {
      console.error('Failed to fetch comparison:', err);
      setError(err instanceof Error ? err.message : 'Failed to load comparison data');
      setComparisonData(null);
    } finally {
      setLoading(false);
    }
  }, [activeWorkspace?.id, selectedScenarioIds]);

  // -------------------------------------------------------------------------
  // Effects
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (activeWorkspace?.id) {
      fetchScenarios(activeWorkspace.id);
    } else {
      setScenarios([]);
      setSelectedScenarioIds([]);
      setAnchorScenarioId('');
    }
  }, [activeWorkspace?.id, fetchScenarios]);

  useEffect(() => {
    if (selectedScenarioIds.length > 0) {
      fetchComparison();
    } else {
      setComparisonData(null);
    }
  }, [selectedScenarioIds, fetchComparison]);

  // Fetch anchor scenario config for plan design display
  useEffect(() => {
    if (activeWorkspace?.id && anchorScenarioId) {
      getScenarioConfig(activeWorkspace.id, anchorScenarioId)
        .then(setAnchorConfig)
        .catch(err => {
          console.error('Failed to fetch anchor config:', err);
          setAnchorConfig(null);
        });
    } else {
      setAnchorConfig(null);
    }
  }, [activeWorkspace?.id, anchorScenarioId]);

  // Save comparison preferences when selection or anchor changes
  useEffect(() => {
    if (activeWorkspace?.id && selectedScenarioIds.length > 0) {
      saveComparisonPrefs(activeWorkspace.id, {
        selectedIds: selectedScenarioIds,
        anchorId: anchorScenarioId,
      });
    }
  }, [activeWorkspace?.id, selectedScenarioIds, anchorScenarioId]);

  // -------------------------------------------------------------------------
  // Event Handlers
  // -------------------------------------------------------------------------
  const toggleSelection = useCallback((id: string) => {
    setSelectedScenarioIds(prev => {
      if (prev.includes(id)) {
        // Deselecting - ensure at least 1 remains
        if (prev.length > 1) {
          const newSelection = prev.filter(i => i !== id);
          // If anchor was deselected, reassign to first remaining
          if (id === anchorScenarioId) {
            setAnchorScenarioId(newSelection[0]);
          }
          return newSelection;
        }
        return prev; // Can't deselect the last one
      } else {
        // Selecting - max scenarios based on constant
        if (prev.length < MAX_SCENARIO_SELECTION) {
          return [...prev, id];
        }
        return prev;
      }
    });
  }, [anchorScenarioId]);

  const handleSetAnchor = useCallback((id: string) => {
    if (selectedScenarioIds.includes(id)) {
      setAnchorScenarioId(id);
    }
  }, [selectedScenarioIds]);

  const moveScenarioUp = useCallback((id: string) => {
    setSelectedScenarioIds(prev => {
      const idx = prev.indexOf(id);
      if (idx <= 0) return prev; // Already at top or not found
      const newArr = [...prev];
      [newArr[idx - 1], newArr[idx]] = [newArr[idx], newArr[idx - 1]];
      return newArr;
    });
  }, []);

  const moveScenarioDown = useCallback((id: string) => {
    setSelectedScenarioIds(prev => {
      const idx = prev.indexOf(id);
      if (idx < 0 || idx >= prev.length - 1) return prev; // At bottom or not found
      const newArr = [...prev];
      [newArr[idx], newArr[idx + 1]] = [newArr[idx + 1], newArr[idx]];
      return newArr;
    });
  }, []);

  // -------------------------------------------------------------------------
  // Table Data for Copy
  // -------------------------------------------------------------------------
  const tableToTSV = useCallback(() => {
    if (!comparisonData || years.length === 0) return '';

    const lines: string[] = [];

    // Header row
    lines.push(['Scenario', ...years.map(String), 'Total', 'Variance'].join('\t'));

    // Data rows
    selectedScenarioIds.forEach(id => {
      const analytics = comparisonData.analytics.find(a => a.scenario_id === id);
      if (!analytics) return;

      const yearValues = years.map(year => {
        const yearData = analytics.contribution_by_year.find(y => y.year === year);
        return yearData ? formatCurrency(yearData.total_employer_cost) : '-';
      });

      const total = analytics.contribution_by_year.reduce(
        (sum, y) => sum + y.total_employer_cost, 0
      );

      let variance = '--';
      if (id !== anchorScenarioId && anchorAnalytics) {
        const anchorTotal = anchorAnalytics.contribution_by_year.reduce(
          (sum, y) => sum + y.total_employer_cost, 0
        );
        const delta = total - anchorTotal;
        variance = `${delta >= 0 ? '+' : ''}${formatCurrency(delta)}`;
      }

      const name = comparisonData.scenario_names[id] || id;
      lines.push([name, ...yearValues, formatCurrency(total), variance].join('\t'));
    });

    return lines.join('\n');
  }, [comparisonData, years, selectedScenarioIds, anchorScenarioId, anchorAnalytics]);

  const handleCopy = useCallback(() => {
    const tsv = tableToTSV();
    if (tsv) copy(tsv);
  }, [tableToTSV, copy]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="flex h-full gap-6 animate-fadeIn">
      {/* ===== Sidebar Selector ===== */}
      <aside className="w-80 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col overflow-hidden flex-shrink-0">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-gray-100 bg-gray-50">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-gray-800 flex items-center">
              <Filter size={18} className="mr-2 text-gray-500" />
              Scenarios
            </h3>
            <span className="text-[10px] font-bold bg-fidelity-green text-white px-1.5 py-0.5 rounded">
              {selectedScenarioIds.length} SELECTED
            </span>
          </div>

          {/* Search Input */}
          <div className="mt-3 relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search scenarios..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-white border border-gray-200 rounded-md focus:ring-1 focus:ring-fidelity-green outline-none"
            />
          </div>
        </div>

        {/* Scenario List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingScenarios ? (
            <div className="flex items-center justify-center py-8 text-gray-400">
              <Loader2 size={20} className="animate-spin mr-2" />
              <span className="text-xs">Loading scenarios...</span>
            </div>
          ) : filteredScenarios.length === 0 ? (
            <div className="text-center py-8 text-gray-400 text-xs">
              {completedScenarios.length === 0
                ? 'No completed scenarios in this workspace'
                : 'No scenarios match your search'
              }
            </div>
          ) : (
            <>
              {/* Selected scenarios - anchor first, then rest in order */}
              {orderedScenarioIds.length > 0 && (
                <>
                  <div className="px-2 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                    Selected ({orderedScenarioIds.length})
                  </div>
                  {orderedScenarioIds.map((id, index) => {
                    const scenario = filteredScenarios.find(s => s.id === id);
                    if (!scenario) return null;
                    const isAnchor = anchorScenarioId === id;
                    // For reorder: anchor is always index 0, non-anchor items can move
                    const canMoveUp = !isAnchor && index > 1; // Can't move above anchor (index 0)
                    const canMoveDown = !isAnchor && index < orderedScenarioIds.length - 1;

                    return (
                      <div
                        key={id}
                        className={`group w-full text-left px-3 py-2 rounded-lg flex items-center justify-between transition-all border ${
                          isAnchor
                            ? 'bg-blue-50 border-blue-200 shadow-sm'
                            : 'bg-fidelity-green/5 border-fidelity-green/20'
                        }`}
                      >
                        <button
                          onClick={() => toggleSelection(id)}
                          className="flex items-start flex-1 min-w-0"
                        >
                          <div className="mt-1 mr-3 flex-shrink-0">
                            <CheckSquare size={16} className={isAnchor ? 'text-blue-600' : 'text-fidelity-green'} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className={`text-xs font-semibold block truncate ${
                              isAnchor ? 'text-blue-700' : 'text-fidelity-green'
                            }`}>
                              {scenario.name}
                            </span>
                            <p className="text-[9px] text-gray-500 uppercase tracking-tight">
                              {isAnchor ? 'Baseline Anchor' : 'Scenario'}
                            </p>
                          </div>
                        </button>

                        <div className="flex items-center ml-2 space-x-1">
                          {/* Reorder buttons - only for non-anchor items */}
                          {!isAnchor && (
                            <div className="flex flex-col">
                              <button
                                onClick={() => moveScenarioUp(id)}
                                disabled={!canMoveUp}
                                className="p-0.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                title="Move up"
                              >
                                <ArrowUp size={12} />
                              </button>
                              <button
                                onClick={() => moveScenarioDown(id)}
                                disabled={!canMoveDown}
                                className="p-0.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                title="Move down"
                              >
                                <ArrowDown size={12} />
                              </button>
                            </div>
                          )}
                          {/* Anchor button */}
                          <button
                            onClick={() => handleSetAnchor(id)}
                            className={`p-1 rounded-md transition-colors ${
                              isAnchor
                                ? 'bg-blue-600 text-white'
                                : 'text-gray-400 hover:text-blue-600 hover:bg-blue-50'
                            }`}
                            title={isAnchor ? 'Current Anchor' : 'Set as Anchor'}
                          >
                            <Anchor size={14} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}

              {/* Unselected scenarios */}
              {filteredScenarios.filter(s => !selectedScenarioIds.includes(s.id)).length > 0 && (
                <>
                  <div className="px-2 py-1 mt-2 text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                    Available
                  </div>
                  {filteredScenarios.filter(s => !selectedScenarioIds.includes(s.id)).map((scenario) => {
                    const isAtLimit = selectedScenarioIds.length >= MAX_SCENARIO_SELECTION;

                    return (
                      <div
                        key={scenario.id}
                        className={`group w-full text-left px-3 py-2 rounded-lg flex items-center justify-between transition-all border ${
                          isAtLimit
                            ? 'bg-gray-50 border-transparent'
                            : 'hover:bg-gray-50 border-transparent'
                        }`}
                      >
                        <button
                          onClick={() => toggleSelection(scenario.id)}
                          disabled={isAtLimit}
                          title={isAtLimit ? `Maximum of ${MAX_SCENARIO_SELECTION} scenarios selected` : undefined}
                          className={`flex items-start flex-1 min-w-0 ${isAtLimit ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          <div className="mt-1 mr-3 flex-shrink-0">
                            <Square size={16} className={isAtLimit ? 'text-gray-200' : 'text-gray-300'} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-xs font-semibold block truncate text-gray-700">
                              {scenario.name}
                            </span>
                            <p className="text-[9px] text-gray-500 uppercase tracking-tight">
                              Scenario
                            </p>
                          </div>
                        </button>
                      </div>
                    );
                  })}
                </>
              )}
            </>
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="p-4 border-t border-gray-100 bg-gray-50 space-y-2">
          <div className="bg-white p-3 rounded-lg border border-gray-200">
            <div className="flex items-center text-[10px] font-bold text-gray-400 uppercase mb-2">
              <Anchor size={10} className="mr-1" /> Active Anchor
            </div>
            <div className="text-xs font-bold text-gray-800 truncate">
              {anchorAnalytics?.scenario_name || 'None selected'}
            </div>
          </div>
          <button className="w-full py-2 bg-white border border-gray-300 rounded-lg text-xs font-bold text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors">
            <Download size={14} className="mr-2" /> Download Report
          </button>
        </div>
      </aside>

      {/* ===== Main Content Area ===== */}
      <div className="flex-1 space-y-6 overflow-y-auto pr-2 pb-8">
        {/* Error State */}
        {error && <ErrorState message={error} onRetry={fetchComparison} />}

        {/* Loading State */}
        {loading && !error && <LoadingState />}

        {/* Empty State */}
        {!loading && !error && selectedScenarioIds.length === 0 && (
          <EmptyState
            message="Select at least one scenario from the sidebar to view cost comparison."
          />
        )}

        {/* Single Scenario Warning */}
        {!loading && !error && selectedScenarioIds.length === 1 && completedScenarios.length === 1 && (
          <EmptyState
            message="Only one completed scenario exists. Run more simulations to enable comparison."
          />
        )}

        {/* Main Content */}
        {!loading && !error && comparisonData && selectedScenarioIds.length > 0 && (
          <>
            {/* Anchor Header Panel */}
            {anchorSummary && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex flex-col md:flex-row gap-8 items-start md:items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-2 text-blue-600 font-bold text-[10px] uppercase tracking-widest mb-1.5">
                    <Anchor size={12} />
                    <span>Anchored Baseline Context</span>
                  </div>
                  <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">{anchorSummary.name}</h2>
                  <div className="flex items-center mt-3 space-x-3">
                    <span className="flex items-center text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded">
                      <Calendar size={12} className="mr-1.5" /> {anchorSummary.yearCount}-Year Plan
                    </span>
                    <span className="flex items-center text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded">
                      <DollarSign size={12} className="mr-1.5" /> {formatCurrency(anchorSummary.totalCost)} Total
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
                    <p className="text-sm font-bold text-blue-900">{coreDesign.title}</p>
                    <p className="text-[10px] text-blue-700 mt-1">{coreDesign.subtitle}</p>
                  </div>

                  {/* Match Design Pill */}
                  <div className="bg-green-50 border border-green-100 rounded-xl p-4 min-w-[180px]">
                    <div className="flex items-center space-x-2 text-fidelity-green font-bold text-[9px] uppercase tracking-wider mb-2">
                      <Zap size={12} />
                      <span>Match Design</span>
                    </div>
                    <p className="text-sm font-bold text-green-900">{matchDesign.title}</p>
                    <p className="text-[10px] text-green-700 mt-1">{matchDesign.subtitle}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Primary Chart: Employer Cost Trends */}
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
                    <BarChart key={selectedScenarioIds.join(',')} data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                      <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={v => formatCurrency(v)} />
                      <Tooltip
                        cursor={{ fill: '#f8fafc' }}
                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                        formatter={(value: number) => formatCurrency(value)}
                      />
                      <Legend
                        content={() => (
                          <CustomLegend
                            items={orderedScenarioIds.map(id => ({
                              name: comparisonData.scenario_names[id] || id,
                              color: id === anchorScenarioId ? '#1e293b' : scenarioColorMap[id],
                            }))}
                          />
                        )}
                      />
                      {orderedScenarioIds.map((id) => (
                        <Bar
                          key={id}
                          dataKey={id}
                          name={comparisonData.scenario_names[id] || id}
                          fill={id === anchorScenarioId ? '#1e293b' : scenarioColorMap[id]}
                          radius={[4, 4, 0, 0]}
                          barSize={selectedScenarioIds.length > 4 ? 12 : 30}
                        />
                      ))}
                    </BarChart>
                  ) : (
                    <AreaChart key={selectedScenarioIds.join(',')} data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                      <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={v => formatCurrency(v)} />
                      <Tooltip
                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                        formatter={(value: number) => formatCurrency(value)}
                      />
                      <Legend
                        content={() => (
                          <CustomLegend
                            items={orderedScenarioIds.map(id => ({
                              name: comparisonData.scenario_names[id] || id,
                              color: id === anchorScenarioId ? '#1e293b' : scenarioColorMap[id],
                            }))}
                          />
                        )}
                      />
                      {orderedScenarioIds.map((id) => (
                        <Area
                          key={id}
                          type="monotone"
                          dataKey={id}
                          name={comparisonData.scenario_names[id] || id}
                          stroke={id === anchorScenarioId ? '#1e293b' : scenarioColorMap[id]}
                          fill={id === anchorScenarioId ? '#1e293b' : scenarioColorMap[id]}
                          fillOpacity={0.1}
                          strokeWidth={id === anchorScenarioId ? 3 : 2}
                        />
                      ))}
                    </AreaChart>
                  )}
                </ResponsiveContainer>
              </div>
            </div>

            {/* Secondary Chart: Incremental Costs */}
            {selectedScenarioIds.length > 1 && (
              <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-lg font-bold text-gray-900 flex items-center">
                    <Calculator size={18} className="mr-2 text-blue-600" />
                    Incremental Costs vs. {anchorAnalytics?.scenario_name}
                  </h3>
                  <div className="px-3 py-1 bg-blue-50 text-blue-700 text-[10px] font-bold rounded-md uppercase tracking-wide">
                    Values represent cost delta
                  </div>
                </div>

                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart key={selectedScenarioIds.join(',')} data={processedData} margin={{ bottom: 30 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                      <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={v => formatCurrency(v)} />
                      <Tooltip
                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                        formatter={(value: number) => formatCurrency(value)}
                      />
                      <Legend
                        content={() => (
                          <CustomLegend
                            items={[
                              ...orderedScenarioIds
                                .filter(id => id !== anchorScenarioId)
                                .map(id => ({
                                  name: `Delta: ${comparisonData.scenario_names[id]}`,
                                  color: scenarioColorMap[id],
                                })),
                              { name: 'Baseline Zero', color: '#1e293b' },
                            ]}
                          />
                        )}
                      />
                      {orderedScenarioIds.filter(id => id !== anchorScenarioId).map((id) => (
                        <Line
                          key={`${id}_delta`}
                          type="monotone"
                          dataKey={`${id}_delta`}
                          name={`Delta: ${comparisonData.scenario_names[id]}`}
                          stroke={scenarioColorMap[id]}
                          strokeWidth={2}
                          dot={{ r: 4 }}
                        />
                      ))}
                      <Line
                        dataKey={() => 0}
                        name="Baseline Zero"
                        stroke="#1e293b"
                        strokeDasharray="5 5"
                        dot={false}
                        strokeWidth={2}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-4 text-xs text-gray-500 italic text-center">
                  Highlights additional costs relative to the {viewMode} values of the anchored baseline.
                </p>
              </div>
            )}

            {/* Multi-Year Cost Matrix Table */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
                <h3 className="text-sm font-bold text-gray-800 uppercase tracking-wider">Multi-Year Cost Matrix</h3>
                <div className="flex items-center space-x-2">
                  <span className="text-[10px] bg-white border border-gray-200 text-gray-600 px-2 py-0.5 rounded font-bold flex items-center">
                    <DollarSign size={8} className="mr-0.5" /> VALUES IN $
                  </span>
                  <button
                    onClick={handleCopy}
                    className={`p-1.5 rounded-md transition-colors ${
                      copied
                        ? 'text-green-600 bg-green-50'
                        : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
                    }`}
                    title={copied ? 'Copied!' : 'Copy to clipboard'}
                  >
                    {copied ? <Check size={16} /> : <Copy size={16} />}
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50 font-bold">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs text-gray-500 uppercase tracking-wider border-r border-gray-200">
                        Scenario Name
                      </th>
                      {years.map(y => (
                        <th key={y} className="px-6 py-2 text-center text-[10px] text-gray-400 uppercase">
                          {y}
                        </th>
                      ))}
                      <th className="px-6 py-4 text-right text-xs text-gray-900 uppercase tracking-wider bg-gray-100 border-l border-gray-200">
                        Total
                      </th>
                      <th className="px-6 py-4 text-right text-xs text-gray-900 uppercase tracking-wider bg-gray-50">
                        Variance
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {orderedScenarioIds.map((id) => {
                      const analytics = comparisonData.analytics.find(a => a.scenario_id === id);
                      if (!analytics) return null;

                      const isAnchor = id === anchorScenarioId;
                      const total = analytics.contribution_by_year.reduce(
                        (sum, y) => sum + y.total_employer_cost, 0
                      );

                      let delta = 0;
                      if (!isAnchor && anchorAnalytics) {
                        const anchorTotal = anchorAnalytics.contribution_by_year.reduce(
                          (sum, y) => sum + y.total_employer_cost, 0
                        );
                        delta = total - anchorTotal;
                      }

                      return (
                        <tr key={id} className={`hover:bg-gray-50 transition-colors ${isAnchor ? 'bg-blue-50/30' : ''}`}>
                          <td className="px-6 py-4 whitespace-nowrap border-r border-gray-100">
                            <div className="flex items-center">
                              <div className={`w-2 h-2 rounded-full mr-2 ${isAnchor ? 'bg-blue-600' : 'bg-fidelity-green'}`} />
                              <span className={`text-sm font-bold ${isAnchor ? 'text-blue-700' : 'text-gray-900'}`}>
                                {comparisonData.scenario_names[id]}
                                {isAnchor && (
                                  <span className="ml-2 text-[8px] font-bold bg-blue-100 text-blue-600 px-1 py-0.5 rounded uppercase">
                                    Anchor
                                  </span>
                                )}
                              </span>
                            </div>
                          </td>
                          {years.map((year) => {
                            const yearData = analytics.contribution_by_year.find(y => y.year === year);
                            return (
                              <td key={year} className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-600 font-mono">
                                {yearData ? formatCurrency(yearData.total_employer_cost) : '-'}
                              </td>
                            );
                          })}
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-900 font-bold font-mono bg-gray-50/50 border-l border-gray-100">
                            {formatCurrency(total)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right">
                            {isAnchor ? (
                              <span className="text-xs text-gray-400 italic">--</span>
                            ) : (
                              <span className={`px-2 py-1 text-xs font-bold rounded ${
                                delta >= 0 ? 'bg-orange-50 text-orange-700' : 'bg-green-50 text-green-700'
                              }`}>
                                {delta >= 0 ? '+' : ''}{formatCurrency(delta)}
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
                    Plan costs are primarily sensitive to <strong>enrollment velocity</strong> and{' '}
                    <strong>merit compounding</strong>. High-growth scenarios compound these effects,
                    creating significant multi-year divergence.
                  </p>
                  <p>
                    The <span className="text-white font-bold">Incremental Variance</span> metric
                    captures the added financial burden of non-baseline policy logic, such as
                    higher matching percentages or lower eligibility periods.
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
          </>
        )}
      </div>
    </div>
  );
}
