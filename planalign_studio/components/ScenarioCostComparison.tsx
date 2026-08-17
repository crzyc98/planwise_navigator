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
  Eye, Copy, Check, ArrowUp, ArrowDown
} from 'lucide-react';
import { useCopyToClipboard } from '../hooks/useCopyToClipboard';
import { useChartTheme } from '../hooks/useChartTheme';
import { PlanDesignModal, formatMatchMode } from './PlanDesignModal';
import { LayoutContextType } from './Layout';
import {
  listScenarios,
  compareDCPlanAnalytics,
  getScenarioConfig,
  Scenario,
  DCPlanComparisonResponse,
  DCPlanAnalytics,
  ContributionYearSummary,
  DCPlanCohort,
} from '../services/api';
import { MAX_SCENARIO_SELECTION } from '../constants';

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

// 134-new-hire-cohort: short segmented-control labels vs. the fuller badge/
// methodology text (ui-contract.md) — kept separate per the contract's note
// that the toggle label stays short.
const COHORT_TOGGLE_LABELS: Record<DCPlanCohort, string> = {
  all: 'All employees',
  new_hires: 'New hires',
  baseline: 'Starting census',
};

function cohortBadgeLabel(cohort: DCPlanCohort, resolvedFirstSimulationYear?: number): string {
  if (cohort === 'new_hires') {
    return `Hired during the simulation (${resolvedFirstSimulationYear ?? '?'}+)`;
  }
  if (cohort === 'baseline') {
    return 'Starting census';
  }
  return '';
}

const VALID_COHORTS: DCPlanCohort[] = ['all', 'new_hires', 'baseline'];

function isValidCohort(value: unknown): value is DCPlanCohort {
  return typeof value === 'string' && (VALID_COHORTS as string[]).includes(value);
}

// ============================================================================
// LocalStorage Helpers for Persisting Comparison Preferences
// ============================================================================

const STORAGE_KEY_PREFIX = 'planalign_comparison_';

function saveComparisonPrefs(
  workspaceId: string,
  prefs: { selectedIds: string[]; anchorId: string; cohort: DCPlanCohort }
) {
  try {
    localStorage.setItem(`${STORAGE_KEY_PREFIX}${workspaceId}`, JSON.stringify(prefs));
  } catch (e) {
    console.warn('Failed to save comparison preferences:', e);
  }
}

function loadComparisonPrefs(
  workspaceId: string
): { selectedIds: string[]; anchorId: string; cohort?: unknown } | null {
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

/**
 * One-line summaries of the anchor scenario's actual employer-contribution
 * design, read from the config the page already fetches. Returns null when the
 * config has not loaded — the caller says so rather than showing a default,
 * because a wrong plan design here reads as fact.
 */
const derivePlanSummary = (config: Record<string, any> | null) => {
  const dc = config?.dc_plan;
  if (!dc) return null;

  // Rates are stored as fractions; the naive ×100 renders 0.035 as 3.5000000000000004.
  const pct = (fraction: number | null | undefined) => +((fraction ?? 0) * 100).toFixed(2);

  const rateRange = (schedule: any[]) => {
    const rates = schedule.map(t => t.contribution_rate).filter((r): r is number => r != null);
    if (rates.length === 0) return '--';
    return `${pct(Math.min(...rates))}%–${pct(Math.max(...rates))}%`;
  };

  let core: string;
  if (dc.core_enabled === false) {
    core = 'Disabled — this scenario pays no employer core contribution.';
  } else if (dc.core_status === 'graded_by_service') {
    core = `Graded by service, ${rateRange(dc.core_graded_schedule ?? [])} of eligible compensation.`;
  } else if (dc.core_status === 'points_based') {
    core = `Points-based, ${rateRange(dc.core_points_schedule ?? [])} of eligible compensation.`;
  } else if (dc.core_status === 'age_banded') {
    core = `Age-banded, ${rateRange(dc.core_age_schedule ?? [])} of eligible compensation.`;
  } else {
    core = `Flat ${dc.core_contribution_rate_percent ?? '--'}% of eligible compensation.`;
  }

  const rawIntegration = config?.employer_core_contribution?.integration;
  const integration = dc.core_integration_enabled !== undefined
    ? {
        enabled: dc.core_integration_enabled,
        levelMode: dc.core_integration_level_mode,
        levelValue: dc.core_integration_level_value,
        disparityRate: dc.core_integration_disparity_rate,
        disparityRatePercent: dc.core_integration_disparity_rate_percent,
      }
    : rawIntegration && {
        enabled: rawIntegration.enabled,
        levelMode: rawIntegration.level_mode,
        levelValue: rawIntegration.level_value,
        disparityRate: rawIntegration.disparity_rate,
        disparityRatePercent: undefined,
      };
  if (dc.core_enabled !== false && integration?.enabled) {
    const disparityRate = integration.disparityRatePercent ?? pct(integration.disparityRate);
    let integrationLevel = 'the Social Security wage base';
    if (integration.levelMode === 'percent_of_ss_wage_base') {
      integrationLevel = `${integration.levelValue}% of the Social Security wage base`;
    } else if (integration.levelMode === 'fixed_dollar') {
      integrationLevel = `$${Number(integration.levelValue).toLocaleString()}`;
    }
    core = `${core.slice(0, -1)}, plus ${disparityRate}% above ${integrationLevel}.`;
  }

  let match: string;
  const tiers: any[] = dc.match_tiers ?? [];
  if (dc.match_enabled === false) {
    match = 'Disabled — this scenario pays no employer match.';
  } else if (dc.match_status === 'deferral_based' && tiers.length === 1) {
    const tier = tiers[0];
    match = `${pct(tier.match_rate)}% on the first ${pct(tier.employee_max)}% deferred.`;
  } else if (dc.match_status === 'deferral_based' && tiers.length > 1) {
    match = `${tiers.length} deferral tiers, capped at ${pct(dc.match_cap_percent)}% of pay.`;
  } else {
    match = `${formatMatchMode(dc.match_status)}, capped at ${pct(dc.match_cap_percent)}% of pay.`;
  }

  return { core, match };
};

// Custom legend that respects the order of items passed to it
interface CustomLegendProps {
  items: Array<{ name: string; color: string }>;
}

const CustomLegend: React.FC<CustomLegendProps> = ({ items }) => {
  const chartTheme = useChartTheme();
  return (
    <div className="flex flex-wrap justify-center gap-4 mt-2">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: item.color }}
          />
          <span className="text-xs" style={{ color: chartTheme.legendText }}>{item.name}</span>
        </div>
      ))}
    </div>
  );
};

const EmptyState = ({ message, onRefresh }: { message: string; onRefresh?: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-ink-subtle">
    <AlertCircle size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-ink-muted mb-2">No Data Available</h3>
    <p className="text-sm text-ink-muted mb-4 text-center max-w-md">{message}</p>
    {onRefresh && (
      <button
        onClick={onRefresh}
        className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors"
      >
        <RefreshCw size={16} className="mr-2" />
        Refresh Data
      </button>
    )}
  </div>
);

const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-danger-ink">
    <AlertCircle size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-danger-ink mb-2">Failed to Load Data</h3>
    <p className="text-sm text-ink-muted mb-4 text-center max-w-md">{message}</p>
    <button
      onClick={onRetry}
      className="flex items-center px-4 py-2 bg-danger-solid text-ink-inverse rounded-lg text-sm font-medium hover:bg-danger-solid-hover transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Retry
    </button>
  </div>
);

// 134-new-hire-cohort (FR-009, ui-contract.md): visually distinct from the
// existing anchor/plan chips so it reads as a filter indicator, not a title.
const CohortBadge = ({ cohort, resolvedFirstSimulationYear }: {
  cohort: DCPlanCohort;
  resolvedFirstSimulationYear?: number;
}) => {
  if (cohort === 'all') return null;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide bg-info-surface text-info-ink border border-info-border">
      {cohortBadgeLabel(cohort, resolvedFirstSimulationYear)}
    </span>
  );
};

const LoadingState = () => (
  <div className="flex flex-col items-center justify-center h-96 text-ink-subtle">
    <Loader2 size={48} className="mb-4 animate-spin" />
    <h3 className="text-lg font-semibold text-ink-muted">Loading comparison data...</h3>
  </div>
);

// ============================================================================
// Main Component
// ============================================================================

export default function ScenarioCostComparison() {
  const chartTheme = useChartTheme();
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
  // Track which workspace the current selection belongs to (prevents saving stale data on workspace switch)
  const [selectionWorkspaceId, setSelectionWorkspaceId] = useState<string>('');

  // -------------------------------------------------------------------------
  // State: View Configuration
  // -------------------------------------------------------------------------
  const [viewMode, setViewMode] = useState<'annual' | 'cumulative'>('annual');
  const [searchQuery, setSearchQuery] = useState('');
  const [cohort, setCohort] = useState<DCPlanCohort>('all');

  // -------------------------------------------------------------------------
  // State: API Data & UI State
  // -------------------------------------------------------------------------
  const [comparisonData, setComparisonData] = useState<DCPlanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(true); // Start true since we fetch on mount
  const [error, setError] = useState<string | null>(null);
  const [anchorConfig, setAnchorConfig] = useState<Record<string, any> | null>(null);
  const [showPlanDesign, setShowPlanDesign] = useState(false);

  // -------------------------------------------------------------------------
  // Copy to Clipboard Hooks
  // -------------------------------------------------------------------------
  const { copy, copied } = useCopyToClipboard();
  const { copy: copyCompensation, copied: copiedCompensation } = useCopyToClipboard();

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
        map[id] = chartTheme.colorAt(colorIdx);
        colorIdx++;
      }
    });
    return map;
  }, [orderedScenarioIds, anchorScenarioId]);

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
        // FR-008: an unrecognized/corrupted stored cohort value falls back to 'all'
        // rather than blocking selectedIds/anchorId restoration.
        setCohort(isValidCohort(savedPrefs.cohort) ? savedPrefs.cohort : 'all');

        if (validSelectedIds.length > 0) {
          // Restore saved selection
          setSelectedScenarioIds(validSelectedIds);
          setAnchorScenarioId(validAnchorId || validSelectedIds[0]);
          setSelectionWorkspaceId(workspaceId);
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
        setSelectionWorkspaceId(workspaceId);
      } else {
        setSelectedScenarioIds([]);
        setAnchorScenarioId('');
        setSelectionWorkspaceId(workspaceId);
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
      const data = await compareDCPlanAnalytics(
        activeWorkspace.id,
        selectedScenarioIds,
        false,
        false,
        cohort
      );
      setComparisonData(data);
    } catch (err) {
      console.error('Failed to fetch comparison:', err);
      setError(err instanceof Error ? err.message : 'Failed to load comparison data');
      setComparisonData(null);
    } finally {
      setLoading(false);
    }
  }, [activeWorkspace?.id, selectedScenarioIds, cohort]);

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
    // Don't fetch comparison while scenarios are still loading
    if (loadingScenarios) return;

    if (selectedScenarioIds.length > 0) {
      fetchComparison();
    } else {
      setComparisonData(null);
    }
  }, [selectedScenarioIds, fetchComparison, loadingScenarios]);

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
  // Only save when selections belong to the current workspace (prevents saving stale data on switch)
  useEffect(() => {
    if (activeWorkspace?.id &&
        selectionWorkspaceId === activeWorkspace.id &&
        selectedScenarioIds.length > 0) {
      saveComparisonPrefs(activeWorkspace.id, {
        selectedIds: selectedScenarioIds,
        anchorId: anchorScenarioId,
        cohort,
      });
    }
  }, [activeWorkspace?.id, selectionWorkspaceId, selectedScenarioIds, anchorScenarioId, cohort]);

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

    // 134-new-hire-cohort (FR-011, ui-contract.md): identifies the active
    // cohort out of UI context when the matrix is pasted elsewhere.
    if (cohort !== 'all') {
      lines.push(`# Cohort: ${cohortBadgeLabel(cohort, anchorAnalytics?.resolved_first_simulation_year)}`);
    }

    // Header row
    lines.push(['Scenario', ...years.map(String), 'Total', 'Variance'].join('\t'));

    // Data rows
    orderedScenarioIds.forEach(id => {
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

      const name = comparisonData.scenario_names[id] || analytics.scenario_name || id;
      lines.push([name, ...yearValues, formatCurrency(total), variance].join('\t'));
    });

    return lines.join('\n');
  }, [comparisonData, years, orderedScenarioIds, anchorScenarioId, anchorAnalytics, cohort]);

  const handleCopy = useCallback(() => {
    const tsv = tableToTSV();
    if (tsv) copy(tsv);
  }, [tableToTSV, copy]);

  // -------------------------------------------------------------------------
  // Compensation Table Data for Copy
  // -------------------------------------------------------------------------
  const compensationTableToTSV = useCallback(() => {
    if (!comparisonData || years.length === 0) return '';

    const lines: string[] = [];

    // 134-new-hire-cohort (FR-011)
    if (cohort !== 'all') {
      lines.push(`# Cohort: ${cohortBadgeLabel(cohort, anchorAnalytics?.resolved_first_simulation_year)}`);
    }

    // Header row
    lines.push(['Scenario', ...years.map(String), 'Total', 'Variance'].join('\t'));

    // Data rows
    orderedScenarioIds.forEach(id => {
      const analytics = comparisonData.analytics.find(a => a.scenario_id === id);
      if (!analytics) return;

      const yearValues = years.map(year => {
        const yearData = analytics.contribution_by_year.find(y => y.year === year);
        return yearData ? formatCurrency(yearData.total_compensation) : '-';
      });

      const total = analytics.contribution_by_year.reduce(
        (sum, y) => sum + y.total_compensation, 0
      );

      let variance = '--';
      if (id !== anchorScenarioId && anchorAnalytics) {
        const anchorTotal = anchorAnalytics.contribution_by_year.reduce(
          (sum, y) => sum + y.total_compensation, 0
        );
        const delta = total - anchorTotal;
        variance = `${delta >= 0 ? '+' : ''}${formatCurrency(delta)}`;
      }

      const name = comparisonData.scenario_names[id] || analytics.scenario_name || id;
      lines.push([name, ...yearValues, formatCurrency(total), variance].join('\t'));
    });

    return lines.join('\n');
  }, [comparisonData, years, orderedScenarioIds, anchorScenarioId, anchorAnalytics, cohort]);

  const handleCompensationCopy = useCallback(() => {
    const tsv = compensationTableToTSV();
    if (tsv) copyCompensation(tsv);
  }, [compensationTableToTSV, copyCompensation]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="flex h-full gap-6 animate-fadeIn">
      {/* ===== Sidebar Selector ===== */}
      <aside className="w-80 bg-surface-raised rounded-xl shadow-sm border border-border flex flex-col overflow-hidden flex-shrink-0">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-border bg-surface-subtle">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-ink flex items-center">
              <Filter size={18} className="mr-2 text-ink-muted" />
              Scenarios
            </h3>
            <span className="text-[10px] font-bold bg-fidelity-green text-ink-inverse px-1.5 py-0.5 rounded">
              {selectedScenarioIds.length} SELECTED
            </span>
          </div>

          {/* Search Input */}
          <div className="mt-3 relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-ink-subtle" />
            <input
              type="text"
              placeholder="Search scenarios..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-surface-raised border border-border rounded-md focus:ring-1 focus:ring-fidelity-green outline-none"
            />
          </div>
        </div>

        {/* Scenario List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingScenarios ? (
            <div className="flex items-center justify-center py-8 text-ink-subtle">
              <Loader2 size={20} className="animate-spin mr-2" />
              <span className="text-xs">Loading scenarios...</span>
            </div>
          ) : filteredScenarios.length === 0 ? (
            <div className="text-center py-8 text-ink-subtle text-xs">
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
                  <div className="px-2 py-1 text-[10px] font-bold text-ink-subtle uppercase tracking-widest">
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
                        className={`group w-full text-left px-3 py-2 rounded-lg flex items-center justify-between transition-all border ${isAnchor ? 'bg-info-surface border-info-border shadow-sm' : 'bg-fidelity-green/5 border-fidelity-green/20'}`}
                      >
                        <button
                          onClick={() => toggleSelection(id)}
                          className="flex items-start flex-1 min-w-0"
                        >
                          <div className="mt-1 mr-3 flex-shrink-0">
                            <CheckSquare size={16} className={isAnchor ? 'text-info-ink' : 'text-fidelity-green'} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className={`text-xs font-semibold block truncate ${isAnchor ? 'text-info-ink' : 'text-fidelity-green'}`}>
                              {scenario.name}
                            </span>
                            <p className="text-[9px] text-ink-muted uppercase tracking-tight">
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
                                className="p-0.5 rounded text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                title="Move up"
                              >
                                <ArrowUp size={12} />
                              </button>
                              <button
                                onClick={() => moveScenarioDown(id)}
                                disabled={!canMoveDown}
                                className="p-0.5 rounded text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                title="Move down"
                              >
                                <ArrowDown size={12} />
                              </button>
                            </div>
                          )}
                          {/* Anchor button */}
                          <button
                            onClick={() => handleSetAnchor(id)}
                            className={`p-1 rounded-md transition-colors ${isAnchor ? 'bg-info-solid text-ink-inverse' : 'text-ink-subtle hover:text-info-ink hover:bg-info-surface'}`}
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
                  <div className="px-2 py-1 mt-2 text-[10px] font-bold text-ink-subtle uppercase tracking-widest">
                    Available
                  </div>
                  {filteredScenarios.filter(s => !selectedScenarioIds.includes(s.id)).map((scenario) => {
                    const isAtLimit = selectedScenarioIds.length >= MAX_SCENARIO_SELECTION;

                    return (
                      <div
                        key={scenario.id}
                        className={`group w-full text-left px-3 py-2 rounded-lg flex items-center justify-between transition-all border ${isAtLimit ? 'bg-surface-subtle border-transparent' : 'hover:bg-surface-subtle border-transparent'}`}
                      >
                        <button
                          onClick={() => toggleSelection(scenario.id)}
                          disabled={isAtLimit}
                          title={isAtLimit ? `Maximum of ${MAX_SCENARIO_SELECTION} scenarios selected` : undefined}
                          className={`flex items-start flex-1 min-w-0 ${isAtLimit ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          <div className="mt-1 mr-3 flex-shrink-0">
                            <Square size={16} className={isAtLimit ? 'text-ink-subtle' : 'text-ink-subtle'} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-xs font-semibold block truncate text-ink-muted">
                              {scenario.name}
                            </span>
                            <p className="text-[9px] text-ink-muted uppercase tracking-tight">
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
        <div className="p-4 border-t border-border bg-surface-subtle space-y-2">
          <div className="bg-surface-raised p-3 rounded-lg border border-border">
            <div className="flex items-center text-[10px] font-bold text-ink-subtle uppercase mb-2">
              <Anchor size={10} className="mr-1" /> Active Anchor
            </div>
            <div className="text-xs font-bold text-ink truncate">
              {anchorAnalytics?.scenario_name || 'None selected'}
            </div>
          </div>
          <button className="w-full py-2 bg-surface-raised border border-border-strong rounded-lg text-xs font-bold text-ink-muted hover:bg-surface-subtle flex items-center justify-center transition-colors">
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
              <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6 flex flex-col md:flex-row gap-8 items-start md:items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-2 text-info-ink font-bold text-[10px] uppercase tracking-widest mb-1.5">
                    <Anchor size={12} />
                    <span>Anchored Baseline Context</span>
                  </div>
                  <h2 className="text-2xl font-extrabold text-ink tracking-tight">{anchorSummary.name}</h2>
                  <div className="flex items-center mt-3 space-x-3">
                    <span className="flex items-center text-xs font-medium text-ink-muted bg-surface-subtle px-2 py-1 rounded">
                      <Calendar size={12} className="mr-1.5" /> {anchorSummary.yearCount}-Year Plan
                    </span>
                    <span className="flex items-center text-xs font-medium text-ink-muted bg-surface-subtle px-2 py-1 rounded">
                      <DollarSign size={12} className="mr-1.5" /> {formatCurrency(anchorSummary.totalCost)} Total
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => setShowPlanDesign(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-info-surface border border-info-border rounded-xl text-info-ink hover:bg-info-surface hover:border-info-border transition-colors text-sm font-medium"
                >
                  <Eye size={16} />
                  View Plan Design
                </button>
              </div>
            )}

            {/* Primary Chart: Employer Cost Trends */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <div className="flex items-center justify-between mb-8">
                <div>
                  <h3 className="text-lg font-bold text-ink flex items-center gap-2">
                    Employer Cost Trends
                    <CohortBadge cohort={cohort} resolvedFirstSimulationYear={anchorAnalytics?.resolved_first_simulation_year} />
                  </h3>
                  <p className="text-sm text-ink-muted">Comparing total contributions for the selected horizon.</p>
                </div>

                <div className="flex items-center gap-2">
                  {/* Cohort Control (134-new-hire-cohort, FR-001) */}
                  <div className="flex bg-surface-subtle p-1 rounded-lg">
                    {VALID_COHORTS.map((value) => (
                      <button
                        key={value}
                        onClick={() => setCohort(value)}
                        className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${cohort === value ? 'bg-surface-raised text-ink shadow-sm' : 'text-ink-muted hover:text-ink-muted'}`}
                      >
                        {COHORT_TOGGLE_LABELS[value]}
                      </button>
                    ))}
                  </div>

                  {/* View Mode Toggle */}
                  <div className="flex bg-surface-subtle p-1 rounded-lg">
                    <button
                      onClick={() => setViewMode('annual')}
                      className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${viewMode === 'annual' ? 'bg-surface-raised text-ink shadow-sm' : 'text-ink-muted hover:text-ink-muted'}`}
                    >
                      Annual Spend
                    </button>
                    <button
                      onClick={() => setViewMode('cumulative')}
                      className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${viewMode === 'cumulative' ? 'bg-surface-raised text-ink shadow-sm' : 'text-ink-muted hover:text-ink-muted'}`}
                    >
                      Cumulative Cost
                    </button>
                  </div>
                </div>
              </div>

              <div className="h-96">
                <ResponsiveContainer width="100%" height="100%">
                  {viewMode === 'annual' ? (
                    <BarChart key={selectedScenarioIds.join(',')} data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} fontSize={12} />
                      <YAxis stroke={chartTheme.axis.line} fontSize={12} tickFormatter={v => formatCurrency(v)} />
                      <Tooltip
                        cursor={chartTheme.tooltip.cursorStyle}
                        contentStyle={chartTheme.tooltip.contentStyle}
                        formatter={(value: number) => formatCurrency(value)}
                      />
                      <Legend
                        content={() => (
                          <CustomLegend
                            items={orderedScenarioIds.map(id => ({
                              name: comparisonData.scenario_names[id] || id,
                              color: id === anchorScenarioId ? chartTheme.semantic.anchor : scenarioColorMap[id],
                            }))}
                          />
                        )}
                      />
                      {orderedScenarioIds.map((id) => (
                        <Bar
                          key={id}
                          dataKey={id}
                          name={comparisonData.scenario_names[id] || id}
                          fill={id === anchorScenarioId ? chartTheme.semantic.anchor : scenarioColorMap[id]}
                          radius={[4, 4, 0, 0]}
                          barSize={selectedScenarioIds.length > 4 ? 12 : 30}
                        />
                      ))}
                    </BarChart>
                  ) : (
                    <AreaChart key={selectedScenarioIds.join(',')} data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} fontSize={12} />
                      <YAxis stroke={chartTheme.axis.line} fontSize={12} tickFormatter={v => formatCurrency(v)} />
                      <Tooltip
                        contentStyle={chartTheme.tooltip.contentStyle}
                        formatter={(value: number) => formatCurrency(value)}
                      />
                      <Legend
                        content={() => (
                          <CustomLegend
                            items={orderedScenarioIds.map(id => ({
                              name: comparisonData.scenario_names[id] || id,
                              color: id === anchorScenarioId ? chartTheme.semantic.anchor : scenarioColorMap[id],
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
                          stroke={id === anchorScenarioId ? chartTheme.semantic.anchor : scenarioColorMap[id]}
                          fill={id === anchorScenarioId ? chartTheme.semantic.anchor : scenarioColorMap[id]}
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
              <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-lg font-bold text-ink flex items-center gap-2">
                    <Calculator size={18} className="mr-2 text-info-ink" />
                    Incremental Costs vs. {anchorAnalytics?.scenario_name}
                    <CohortBadge cohort={cohort} resolvedFirstSimulationYear={anchorAnalytics?.resolved_first_simulation_year} />
                  </h3>
                  <div className="px-3 py-1 bg-info-surface text-info-ink text-[10px] font-bold rounded-md uppercase tracking-wide">
                    Values represent cost delta
                  </div>
                </div>

                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart key={selectedScenarioIds.join(',')} data={processedData} margin={{ bottom: 30 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} fontSize={12} />
                      <YAxis stroke={chartTheme.axis.line} fontSize={12} tickFormatter={v => formatCurrency(v)} />
                      <Tooltip
                        contentStyle={chartTheme.tooltip.contentStyle}
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
                              { name: 'Baseline Zero', color: chartTheme.semantic.anchor },
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
                        stroke={chartTheme.semantic.anchor}
                        strokeDasharray="5 5"
                        dot={false}
                        strokeWidth={2}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-4 text-xs text-ink-muted italic text-center">
                  Highlights additional costs relative to the {viewMode} values of the anchored baseline.
                </p>
              </div>
            )}

            {/* Multi-Year Cost Matrix Table */}
            <div className="bg-surface-raised rounded-xl shadow-sm border border-border overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-surface-subtle flex items-center justify-between">
                <h3 className="text-sm font-bold text-ink uppercase tracking-wider flex items-center gap-2">
                  Multi-Year Cost Matrix
                  <CohortBadge cohort={cohort} resolvedFirstSimulationYear={anchorAnalytics?.resolved_first_simulation_year} />
                </h3>
                <div className="flex items-center space-x-2">
                  <span className="text-[10px] bg-surface-raised border border-border text-ink-muted px-2 py-0.5 rounded font-bold flex items-center">
                    <DollarSign size={8} className="mr-0.5" /> VALUES IN $
                  </span>
                  <button
                    onClick={handleCopy}
                    className={`p-1.5 rounded-md transition-colors ${copied ? 'text-success-ink bg-success-surface' : 'text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle'}`}
                    title={copied ? 'Copied!' : 'Copy to clipboard'}
                  >
                    {copied ? <Check size={16} /> : <Copy size={16} />}
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-border">
                  <thead className="bg-surface-subtle font-bold">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs text-ink-muted uppercase tracking-wider border-r border-border">
                        Scenario Name
                      </th>
                      {years.map(y => (
                        <th key={y} className="px-6 py-2 text-center text-[10px] text-ink-subtle uppercase">
                          {y}
                        </th>
                      ))}
                      <th className="px-6 py-4 text-right text-xs text-ink uppercase tracking-wider bg-surface-subtle border-l border-border">
                        Total
                      </th>
                      <th className="px-6 py-4 text-right text-xs text-ink uppercase tracking-wider bg-surface-subtle">
                        Variance
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border bg-surface-raised">
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
                        <tr key={id} className={`hover:bg-surface-subtle transition-colors ${isAnchor ? 'bg-info-surface/30' : ''}`}>
                          <td className="px-6 py-4 whitespace-nowrap border-r border-border">
                            <div className="flex items-center">
                              <div className={`w-2 h-2 rounded-full mr-2 ${isAnchor ? 'bg-info-solid' : 'bg-fidelity-green'}`} />
                              <span className={`text-sm font-bold ${isAnchor ? 'text-info-ink' : 'text-ink'}`}>
                                {comparisonData.scenario_names[id] || analytics.scenario_name || id}
                                {isAnchor && (
                                  <span className="ml-2 text-[8px] font-bold bg-info-surface text-info-ink px-1 py-0.5 rounded uppercase">
                                    Anchor
                                  </span>
                                )}
                              </span>
                            </div>
                          </td>
                          {years.map((year) => {
                            const yearData = analytics.contribution_by_year.find(y => y.year === year);
                            if (!yearData) {
                              // 134-new-hire-cohort (FR-012): a year absent from
                              // contribution_by_year means zero cohort-matching
                              // employees — distinguishable from a computed $0.
                              return (
                                <td key={year} className="px-6 py-4 whitespace-nowrap text-right text-sm text-ink-subtle font-mono italic">
                                  {cohort !== 'all' ? (
                                    <span title="No employees in cohort">—</span>
                                  ) : (
                                    '-'
                                  )}
                                </td>
                              );
                            }
                            return (
                              <td key={year} className="px-6 py-4 whitespace-nowrap text-right text-sm text-ink-muted font-mono">
                                {formatCurrency(yearData.total_employer_cost)}
                              </td>
                            );
                          })}
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-ink font-bold font-mono bg-surface-subtle/50 border-l border-border">
                            {formatCurrency(total)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right">
                            {isAnchor ? (
                              <span className="text-xs text-ink-subtle italic">--</span>
                            ) : (
                              <span className={`px-2 py-1 text-xs font-bold rounded ${delta >= 0 ? 'bg-warning-surface text-warning-ink' : 'bg-success-surface text-success-ink'}`}>
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

            {/* Multi-Year Compensation Matrix Table */}
            <div className="bg-surface-raised rounded-xl shadow-sm border border-border overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-surface-subtle flex items-center justify-between">
                <h3 className="text-sm font-bold text-ink uppercase tracking-wider">Multi-Year Compensation Matrix</h3>
                <div className="flex items-center space-x-2">
                  <span className="text-[10px] bg-surface-raised border border-border text-ink-muted px-2 py-0.5 rounded font-bold flex items-center">
                    <DollarSign size={8} className="mr-0.5" /> VALUES IN $
                  </span>
                  <button
                    onClick={handleCompensationCopy}
                    className={`p-1.5 rounded-md transition-colors ${copiedCompensation ? 'text-success-ink bg-success-surface' : 'text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle'}`}
                    title={copiedCompensation ? 'Copied!' : 'Copy to clipboard'}
                  >
                    {copiedCompensation ? <Check size={16} /> : <Copy size={16} />}
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-border">
                  <thead className="bg-surface-subtle font-bold">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs text-ink-muted uppercase tracking-wider border-r border-border">
                        Scenario Name
                      </th>
                      {years.map(y => (
                        <th key={y} className="px-6 py-2 text-center text-[10px] text-ink-subtle uppercase">
                          {y}
                        </th>
                      ))}
                      <th className="px-6 py-4 text-right text-xs text-ink uppercase tracking-wider bg-surface-subtle border-l border-border">
                        Total
                      </th>
                      <th className="px-6 py-4 text-right text-xs text-ink uppercase tracking-wider bg-surface-subtle">
                        Variance
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border bg-surface-raised">
                    {orderedScenarioIds.map((id) => {
                      const analytics = comparisonData.analytics.find(a => a.scenario_id === id);
                      if (!analytics) return null;

                      const isAnchor = id === anchorScenarioId;
                      const total = analytics.contribution_by_year.reduce(
                        (sum, y) => sum + y.total_compensation, 0
                      );

                      let delta = 0;
                      if (!isAnchor && anchorAnalytics) {
                        const anchorTotal = anchorAnalytics.contribution_by_year.reduce(
                          (sum, y) => sum + y.total_compensation, 0
                        );
                        delta = total - anchorTotal;
                      }

                      return (
                        <tr key={id} className={`hover:bg-surface-subtle transition-colors ${isAnchor ? 'bg-info-surface/30' : ''}`}>
                          <td className="px-6 py-4 whitespace-nowrap border-r border-border">
                            <div className="flex items-center">
                              <div className={`w-2 h-2 rounded-full mr-2 ${isAnchor ? 'bg-info-solid' : 'bg-fidelity-green'}`} />
                              <span className={`text-sm font-bold ${isAnchor ? 'text-info-ink' : 'text-ink'}`}>
                                {comparisonData.scenario_names[id] || analytics.scenario_name || id}
                                {isAnchor && (
                                  <span className="ml-2 text-[8px] font-bold bg-info-surface text-info-ink px-1 py-0.5 rounded uppercase">
                                    Anchor
                                  </span>
                                )}
                              </span>
                            </div>
                          </td>
                          {years.map((year) => {
                            const yearData = analytics.contribution_by_year.find(y => y.year === year);
                            return (
                              <td key={year} className="px-6 py-4 whitespace-nowrap text-right text-sm text-ink-muted font-mono">
                                {yearData ? formatCurrency(yearData.total_compensation) : '-'}
                              </td>
                            );
                          })}
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-ink font-bold font-mono bg-surface-subtle/50 border-l border-border">
                            {formatCurrency(total)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right">
                            {isAnchor ? (
                              <span className="text-xs text-ink-subtle italic">--</span>
                            ) : (
                              <span className={`px-2 py-1 text-xs font-bold rounded ${delta >= 0 ? 'bg-warning-surface text-warning-ink' : 'bg-success-surface text-success-ink'}`}>
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
              <div className="bg-surface-inverse text-ink-subtle p-6 rounded-xl border border-border-strong shadow-lg">
                <div className="flex items-center text-fidelity-light mb-4 font-bold">
                  <TrendingDown size={18} className="mr-2" />
                  How these figures are measured
                </div>
                <div className="space-y-4 text-sm leading-relaxed">
                  <p>
                    <span className="text-ink-inverse font-bold">Employer cost</span> is employer match
                    plus employer core, summed across every employee in the workforce snapshot for
                    each simulation year. Employee deferrals and salary are not included.
                  </p>
                  <p>
                    <span className="text-ink-inverse font-bold">Incremental cost</span> is a scenario's
                    employer cost minus {anchorAnalytics?.scenario_name ?? 'the anchor'}'s, so it
                    reflects <strong>every</strong> difference between the two runs — workforce
                    growth, compensation and census as well as plan design. It does not isolate the
                    effect of a policy change on its own.
                  </p>
                  {cohort !== 'all' && (
                    <p>
                      <span className="text-ink-inverse font-bold">Cohort:</span> figures reflect only
                      the <strong>{cohortBadgeLabel(cohort, anchorAnalytics?.resolved_first_simulation_year)}</strong> cohort
                      {cohort === 'new_hires'
                        ? ` — employees hired on or after ${anchorAnalytics?.resolved_first_simulation_year ?? 'the first simulation year'}.`
                        : ' — everyone else in the workforce snapshot.'}
                    </p>
                  )}
                </div>
              </div>

              <div className="bg-info-surface p-6 rounded-xl border border-info-border">
                <div className="flex items-center text-info-ink mb-4 font-bold">
                  <Info size={18} className="mr-2" />
                  {anchorAnalytics?.scenario_name ?? 'Anchor'} employer contributions
                </div>
                {(() => {
                  const summary = derivePlanSummary(anchorConfig);
                  if (!summary) {
                    return (
                      <p className="text-sm text-info-ink">
                        Plan design unavailable for this scenario.
                      </p>
                    );
                  }
                  return (
                    <>
                      <ul className="space-y-3 text-sm text-info-ink">
                        <li className="flex items-start">
                          <div className="w-1.5 h-1.5 rounded-full bg-info-solid mt-1.5 mr-2 flex-shrink-0" />
                          <span><strong>Employer core:</strong> {summary.core}</span>
                        </li>
                        <li className="flex items-start">
                          <div className="w-1.5 h-1.5 rounded-full bg-info-solid mt-1.5 mr-2 flex-shrink-0" />
                          <span><strong>Employer match:</strong> {summary.match}</span>
                        </li>
                      </ul>
                      <p className="mt-4 text-xs text-info-ink">
                        Eligibility gates, vesting and the full tier schedule are in
                        {' '}<strong>View Plan Design</strong>. Other scenarios in this comparison
                        may use a different design.
                      </p>
                    </>
                  );
                })()}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Plan Design Modal */}
      {showPlanDesign && (
        <PlanDesignModal config={anchorConfig} onClose={() => setShowPlanDesign(false)} />
      )}
    </div>
  );
}
