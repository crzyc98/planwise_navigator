import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LabelList
} from 'recharts';
import {
  Users, DollarSign, TrendingUp, PieChart as PieChartIcon,
  RefreshCw, AlertCircle, ChevronDown, Database, Loader2, ArrowUpRight, Copy, Check
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import {
  listScenarios,
  getDCPlanAnalytics,
  compareDCPlanAnalytics,
  Scenario,
  DCPlanAnalytics as DCPlanAnalyticsData,
  DCPlanComparisonResponse,
  ContributionYearSummary,
  DCPlanCohort,
  DCPlanPopulation,
} from '../services/api';

// 134-new-hire-cohort (FR-006): same segmented control as ScenarioCostComparison.
const COHORT_TOGGLE_LABELS: Record<DCPlanCohort, string> = {
  all: 'All employees',
  new_hires: 'New hires',
  baseline: 'Starting census',
};
const VALID_COHORTS: DCPlanCohort[] = ['all', 'new_hires', 'baseline'];
const POPULATION_TOGGLE_LABELS: Record<DCPlanPopulation, string> = {
  all_eligible: 'All eligible',
  active_eligible: 'Actives only',
  terminated_eligible: 'Terms only',
};
const VALID_POPULATIONS: DCPlanPopulation[] = [
  'all_eligible',
  'active_eligible',
  'terminated_eligible',
];
import { MAX_SCENARIO_SELECTION } from '../constants';
import { useChartTheme } from '../hooks/useChartTheme';
import { useCopyToClipboard } from '../hooks/useCopyToClipboard';

const formatCurrency = (value: number): string => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
};

const KPI_ICON_STYLES: Record<string, string> = {
  blue: 'bg-info-surface text-info-ink',
  green: 'bg-success-surface text-success-ink',
  red: 'bg-danger-surface text-danger-ink',
  gray: 'bg-surface-subtle text-ink-muted',
  purple: 'bg-info-surface text-info-ink',
  orange: 'bg-warning-surface text-warning-ink',
};

const KPICard = ({ title, value, subtext, icon: Icon, color, loading }: any) => (
  <div className="bg-surface-raised p-5 rounded-xl shadow-sm border border-border flex items-start justify-between">
    <div>
      <p className="text-sm font-medium text-ink-muted">{title}</p>
      {loading ? (
        <div className="h-8 w-20 bg-surface-disabled rounded animate-pulse mt-1" />
      ) : (
        <>
          <h3 className="text-2xl font-bold text-ink mt-1">{value}</h3>
          {subtext && (
            <div className="flex items-center mt-1">
              <span className="text-xs font-medium text-ink-muted">{subtext}</span>
            </div>
          )}
        </>
      )}
    </div>
    <div className={`p-2 rounded-lg ${KPI_ICON_STYLES[color] ?? KPI_ICON_STYLES.gray}`}>
      <Icon size={20} />
    </div>
  </div>
);

const EmptyState = ({ onRefresh }: { onRefresh: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-ink-subtle">
    <Database size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-ink-muted mb-2">No Simulation Selected</h3>
    <p className="text-sm text-ink-muted mb-4 text-center max-w-md">
      Select a completed simulation from the dropdown above to view DC Plan analytics.
    </p>
    <button
      onClick={onRefresh}
      className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Refresh Data
    </button>
  </div>
);

const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-danger-ink">
    <AlertCircle size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-danger-ink mb-2">Failed to Load Analytics</h3>
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

const DeferralTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const { count, percentage } = payload[0].payload;
  return (
    <div className="bg-surface-raised border border-border rounded-lg shadow-lg px-4 py-3 min-w-[160px]">
      <p className="font-semibold text-ink mb-2 text-sm">{label} deferral</p>
      <div className="space-y-1">
        <p className="text-sm text-ink-muted">
          <span className="font-semibold text-ink">{count.toLocaleString()}</span>{' '}
          employees
        </p>
        <p className="text-sm text-ink-muted">
          <span className="font-semibold text-fidelity-green">{percentage.toFixed(1)}%</span>{' '}
          of participants
        </p>
      </div>
    </div>
  );
};

const ParticipationTrendTooltip = ({
  active,
  payload,
  label,
  populationLabel,
}: any) => {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="bg-surface-raised border border-border rounded-lg shadow-lg px-4 py-3 min-w-[210px]">
      <p className="font-semibold text-ink text-sm">{label} · {populationLabel}</p>
      <p className="text-sm text-ink-muted mt-1">
        Participation: <span className="font-semibold text-ink">{row.participationRate.toFixed(1)}%</span>
      </p>
      <p className="text-xs text-ink-muted mt-1">
        {row.participantCount.toLocaleString()} enrolled / {row.eligibleCount.toLocaleString()} eligible
      </p>
    </div>
  );
};

const SavingsTrendTooltip = ({
  active,
  payload,
  label,
  populationLabel,
}: any) => {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const metrics: Record<string, { label: string; numerator: number }> = {
    employeeRate: { label: 'Employee deferral', numerator: row.employeeContributions },
    matchRate: { label: 'Employer match', numerator: row.employerMatch },
    coreRate: { label: 'Employer non-elective/core', numerator: row.employerCore },
  };

  return (
    <div className="bg-surface-raised border border-border rounded-lg shadow-lg px-4 py-3 min-w-[260px]">
      <p className="font-semibold text-ink text-sm">{label} · {populationLabel}</p>
      <p className="text-xs text-ink-muted mt-1 mb-2">
        Denominator: {formatCurrency(row.totalCompensation)} prorated eligible compensation
      </p>
      <div className="space-y-1">
        {payload.map((entry: any) => {
          const metric = metrics[String(entry.dataKey)];
          if (!metric || entry.value === null) return null;
          return (
            <p key={entry.dataKey} className="text-sm text-ink-muted">
              <span className="font-semibold" style={{ color: entry.color }}>{metric.label}</span>
              {`: ${Number(entry.value).toFixed(2)}% (${formatCurrency(metric.numerator)})`}
            </p>
          );
        })}
      </div>
    </div>
  );
};

export default function DCPlanAnalytics() {
  const chartTheme = useChartTheme();
  // Workspace context from Layout (shared across all pages)
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  // State for scenario selection (page-local)
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);

  // State for results
  const [analytics, setAnalytics] = useState<DCPlanAnalyticsData | null>(null);
  const [comparisonData, setComparisonData] = useState<DCPlanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Comparison mode toggle
  const [comparisonMode, setComparisonMode] = useState(false);

  // Explicit status population for participation and savings-rate analytics.
  const [population, setPopulation] = useState<DCPlanPopulation>('all_eligible');

  // 134-new-hire-cohort (FR-006): population filter, same three values as
  // ScenarioCostComparison's Cost Comparison view.
  const [cohort, setCohort] = useState<DCPlanCohort>('all');

  // Deferral distribution view: effective rate for the year vs year-end snapshot
  const [deferralView, setDeferralView] = useState<'effective' | 'yearend'>('yearend');

  // Year filter: null = "All Years" aggregate
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  const {
    copy: copyParticipationTrend,
    copied: participationTrendCopied,
  } = useCopyToClipboard();
  const {
    copy: copySavingsTrend,
    copied: savingsTrendCopied,
  } = useCopyToClipboard();

  // Derived: years available for the year picker
  const availableYears = useMemo<number[]>(() => {
    if (analytics) {
      return analytics.contribution_by_year.map((y) => y.year);
    }
    if (comparisonData && comparisonData.analytics.length > 0) {
      const sets = comparisonData.analytics.map(
        (a) => new Set(a.contribution_by_year.map((y) => y.year))
      );
      return [...sets[0]]
        .filter((yr) => sets.every((s) => s.has(yr)))
        .sort((a, b) => a - b);
    }
    return [];
  }, [analytics, comparisonData]);

  // Derived: single-scenario data for the selected year
  const activeYearData = useMemo<ContributionYearSummary | null>(() => {
    if (!analytics || selectedYear === null) return null;
    return analytics.contribution_by_year.find((y) => y.year === selectedYear) ?? null;
  }, [analytics, selectedYear]);

  // Derived: deferral distribution for selected year (or final-year aggregate)
  const activeDeferralDistribution = useMemo(() => {
    if (!analytics) return [];
    if (selectedYear !== null) {
      return (
        analytics.deferral_distribution_by_year.find((y) => y.year === selectedYear)
          ?.distribution ?? []
      );
    }
    return analytics.deferral_rate_distribution;
  }, [analytics, selectedYear]);

  // Fetch scenarios when workspace changes
  useEffect(() => {
    if (activeWorkspace?.id) {
      fetchScenarios(activeWorkspace.id);
      setSelectedScenarioIds([]);
      setAnalytics(null);
      setComparisonData(null);
      setError(null);
      setSelectedYear(null);
    } else {
      setScenarios([]);
      setSelectedScenarioIds([]);
      setAnalytics(null);
      setComparisonData(null);
      setSelectedYear(null);
    }
  }, [activeWorkspace?.id]);

  // Fetch analytics when scenario, population, cohort, or deferral view changes
  useEffect(() => {
    if (!activeWorkspace?.id) return;
    if (selectedScenarioIds.length === 1 && !comparisonMode) {
      fetchAnalytics(selectedScenarioIds[0]);
    } else if (selectedScenarioIds.length >= 2 && comparisonMode) {
      fetchComparison(selectedScenarioIds);
    } else {
      setAnalytics(null);
      setComparisonData(null);
    }
  }, [selectedScenarioIds, comparisonMode, activeWorkspace?.id, population, deferralView, cohort]);

  const fetchScenarios = async (workspaceId: string) => {
    setLoadingScenarios(true);
    try {
      const data = await listScenarios(workspaceId);
      setScenarios(data);
      const completedScenarios = data.filter(s => s.status === 'completed');
      if (completedScenarios.length > 0 && selectedScenarioIds.length === 0) {
        setSelectedScenarioIds([completedScenarios[0].id]);
      }
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const fetchAnalytics = async (scenarioId: string) => {
    if (!activeWorkspace?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getDCPlanAnalytics(
        activeWorkspace.id,
        scenarioId,
        false,
        deferralView === 'effective',
        cohort,
        population
      );
      setAnalytics(data);
      setComparisonData(null);
      if (data.contribution_by_year.length > 0) {
        const years = data.contribution_by_year.map((y) => y.year);
        setSelectedYear((prev) => (prev === null || !years.includes(prev) ? years[0] : prev));
      }
    } catch (err: any) {
      console.error('Failed to fetch analytics:', err);
      setError(err.message || 'Failed to load DC plan analytics');
      setAnalytics(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchComparison = async (scenarioIds: string[]) => {
    if (!activeWorkspace?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await compareDCPlanAnalytics(
        activeWorkspace.id,
        scenarioIds,
        false,
        deferralView === 'effective',
        cohort,
        population
      );
      setComparisonData(data);
      setAnalytics(null);
    } catch (err: any) {
      console.error('Failed to fetch comparison:', err);
      setError(err.message || 'Failed to load comparison data');
      setComparisonData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleScenarioToggle = (scenarioId: string) => {
    if (comparisonMode) {
      if (selectedScenarioIds.includes(scenarioId)) {
        setSelectedScenarioIds(selectedScenarioIds.filter(id => id !== scenarioId));
      } else if (selectedScenarioIds.length < MAX_SCENARIO_SELECTION) {
        setSelectedScenarioIds([...selectedScenarioIds, scenarioId]);
      }
    } else {
      setSelectedScenarioIds([scenarioId]);
    }
  };

  const handleRefresh = () => {
    if (activeWorkspace?.id) {
      fetchScenarios(activeWorkspace.id);
    }
  };

  const completedScenarios = scenarios.filter(s => s.status === 'completed');

  // Prepare chart data
  const contributionChartData = analytics?.contribution_by_year.map(year => ({
    year: year.year,
    Employee: year.total_employee_contributions,
    Match: year.total_employer_match,
    Core: year.total_employer_core,
  })) || [];

  const trendData = analytics?.contribution_by_year.map(year => {
    const hasEligiblePopulation = year.total_eligible_count > 0;
    const hasCompensation = hasEligiblePopulation && year.total_compensation > 0;
    return {
      year: year.year,
      participationRate: hasEligiblePopulation ? year.participation_rate : null,
      employeeRate: hasCompensation ? year.employee_contribution_rate : null,
      matchRate: hasCompensation ? year.match_contribution_rate : null,
      coreRate: hasCompensation ? year.core_contribution_rate : null,
      participantCount: year.participant_count,
      eligibleCount: year.total_eligible_count,
      totalCompensation: year.total_compensation,
      employeeContributions: year.total_employee_contributions,
      employerMatch: year.total_employer_match,
      employerCore: year.total_employer_core,
    };
  }) || [];

  const hasParticipationTrend = trendData.some(row => row.participationRate !== null);
  const hasSavingsTrend = trendData.some(row => row.employeeRate !== null);
  const populationLabel = POPULATION_TOGGLE_LABELS[population];

  const copyMetadataRows = useCallback(() => [
    ['Scenario', analytics?.scenario_name ?? ''],
    ['Population', populationLabel],
    ['Cohort', COHORT_TOGGLE_LABELS[cohort]],
  ], [analytics?.scenario_name, populationLabel, cohort]);

  const handleCopyParticipationTrend = useCallback(() => {
    if (!analytics || trendData.length === 0) return;
    const rates = trendData
      .map(row => row.participationRate)
      .filter((rate): rate is number => rate !== null);
    const average = rates.length > 0
      ? rates.reduce((sum, rate) => sum + rate, 0) / rates.length
      : null;
    const lines = [
      ...copyMetadataRows().map(row => row.join('\t')),
      ['Year', 'Enrolled employees', 'Eligible employees', 'Participation rate'].join('\t'),
      ...trendData.map(row => [
        row.year,
        row.participantCount,
        row.eligibleCount,
        row.participationRate === null ? 'No eligible population' : `${row.participationRate.toFixed(2)}%`,
      ].join('\t')),
      ['Average', '', '', average === null ? 'No eligible population' : `${average.toFixed(2)}%`].join('\t'),
    ];
    copyParticipationTrend(lines.join('\n'));
  }, [analytics, trendData, copyMetadataRows, copyParticipationTrend]);

  const handleCopySavingsTrend = useCallback(() => {
    if (!analytics || trendData.length === 0) return;
    const populatedRows = trendData.filter(row => row.employeeRate !== null);
    const averageRate = (key: 'employeeRate' | 'matchRate' | 'coreRate') => {
      if (populatedRows.length === 0) return null;
      return populatedRows.reduce((sum, row) => sum + (row[key] ?? 0), 0)
        / populatedRows.length;
    };
    const averageEmployee = averageRate('employeeRate');
    const averageMatch = averageRate('matchRate');
    const averageCore = averageRate('coreRate');
    const formatRate = (rate: number | null) =>
      rate === null ? 'No eligible compensation' : `${rate.toFixed(2)}%`;
    const lines = [
      ...copyMetadataRows().map(row => row.join('\t')),
      [
        'Year',
        'Employee deferral rate',
        'Employer match rate',
        'Employer non-elective/core rate',
        'Total savings rate',
      ].join('\t'),
      ...trendData.map(row => {
        const total = row.employeeRate === null
          ? null
          : row.employeeRate + (row.matchRate ?? 0) + (row.coreRate ?? 0);
        return [
          row.year,
          formatRate(row.employeeRate),
          formatRate(row.matchRate),
          formatRate(row.coreRate),
          formatRate(total),
        ].join('\t');
      }),
      [
        'Average',
        formatRate(averageEmployee),
        formatRate(averageMatch),
        formatRate(averageCore),
        formatRate(
          averageEmployee === null
            ? null
            : averageEmployee + (averageMatch ?? 0) + (averageCore ?? 0)
        ),
      ].join('\t'),
    ];
    copySavingsTrend(lines.join('\n'));
  }, [analytics, trendData, copyMetadataRows, copySavingsTrend]);

  const deferralDistributionData = activeDeferralDistribution.map((bucket) => ({
    bucket: bucket.bucket,
    count: bucket.count,
    percentage: bucket.percentage,
  }));

  const participationPieData = analytics ? [
    { name: 'Auto Enrolled', value: analytics.participation_by_method.auto_enrolled },
    { name: 'Voluntary', value: analytics.participation_by_method.voluntary_enrolled },
    { name: 'Census', value: analytics.participation_by_method.census_enrolled },
  ].filter(d => d.value > 0) : [];

  // Comparison chart data — year-filtered when a year is selected
  const comparisonContributionData = comparisonData?.analytics.map((a) => {
    const yearData = selectedYear !== null
      ? a.contribution_by_year.find((y) => y.year === selectedYear)
      : null;
    return {
      scenario: a.scenario_name,
      Employee: yearData?.total_employee_contributions ?? a.total_employee_contributions,
      Match: yearData?.total_employer_match ?? a.total_employer_match,
      Core: yearData?.total_employer_core ?? a.total_employer_core,
    };
  }) || [];

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">DC Plan Analytics</h1>
          <p className="text-ink-muted mt-1">Analyze retirement plan contributions and participation.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Scenario Selector */}
          <div className="relative">
            <select
              value={comparisonMode ? '' : selectedScenarioIds[0] || ''}
              onChange={(e) => handleScenarioToggle(e.target.value)}
              disabled={!activeWorkspace?.id || loadingScenarios || comparisonMode}
              className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[200px] disabled:bg-surface-subtle disabled:text-ink-subtle"
            >
              <option value="">
                {loadingScenarios ? 'Loading...' : completedScenarios.length === 0 ? 'No completed runs' : 'Select Scenario'}
              </option>
              {completedScenarios.map(scenario => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
          </div>

          {/* Year Picker */}
          {(analytics || comparisonData) && availableYears.length > 1 && (
            <div className="relative">
              <select
                value={selectedYear ?? ''}
                onChange={(e) =>
                  setSelectedYear(e.target.value ? Number(e.target.value) : null)
                }
                className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
              >
                <option value="">All Years</option>
                {availableYears.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
            </div>
          )}

          {/* Comparison Mode Toggle */}
          <button
            onClick={() => {
              setComparisonMode(!comparisonMode);
              if (!comparisonMode) {
                setSelectedScenarioIds([]);
              }
            }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${comparisonMode ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised border border-border-strong text-ink-muted hover:bg-surface-subtle'}`}
          >
            Compare {comparisonMode && `(${selectedScenarioIds.length}/3)`}
          </button>

          {/* Cohort Control (134-new-hire-cohort, FR-006) */}
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

          {/* Eligible Population Control (#641) */}
          <div
            className="flex bg-surface-subtle p-1 rounded-lg"
            role="group"
            aria-label="Eligible employee population"
          >
            {VALID_POPULATIONS.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={population === value}
                onClick={() => setPopulation(value)}
                className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${population === value ? 'bg-surface-raised text-ink shadow-sm' : 'text-ink-muted hover:text-ink'}`}
              >
                {POPULATION_TOGGLE_LABELS[value]}
              </button>
            ))}
          </div>

          <button
            onClick={handleRefresh}
            className="flex items-center px-3 py-2 bg-surface-raised border border-border-strong rounded-lg text-sm font-medium hover:bg-surface-subtle text-ink-muted shadow-sm transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Comparison Mode Scenario Selection */}
      {comparisonMode && (
        <div className="bg-info-surface border border-info-border rounded-lg p-4">
          <p className="text-sm font-medium text-info-ink mb-2">
            Select 2-{MAX_SCENARIO_SELECTION} scenarios to compare (click to select/deselect):
          </p>
          <div className="flex flex-wrap gap-2">
            {completedScenarios.map(scenario => (
              <button
                key={scenario.id}
                onClick={() => handleScenarioToggle(scenario.id)}
                disabled={!selectedScenarioIds.includes(scenario.id) && selectedScenarioIds.length >= MAX_SCENARIO_SELECTION}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedScenarioIds.includes(scenario.id) ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised border border-border-strong text-ink-muted hover:bg-surface-subtle disabled:opacity-50 disabled:cursor-not-allowed'}`}
              >
                {scenario.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Content Area */}
      {loading ? (
        <div className="flex items-center justify-center h-96">
          <Loader2 size={48} className="animate-spin text-fidelity-green" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={handleRefresh} />
      ) : !analytics && !comparisonData ? (
        <EmptyState onRefresh={handleRefresh} />
      ) : comparisonData ? (
        /* Comparison View */
        <>
          <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
            <h3 className="text-lg font-semibold text-ink mb-4">Scenario Comparison</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-4 font-semibold text-ink-muted">Metric</th>
                    {comparisonData.analytics.map(a => (
                      <th key={a.scenario_id} className="text-right py-3 px-4 font-semibold text-ink-muted">
                        {a.scenario_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  <tr>
                    <td className="py-3 px-4 text-ink-muted">Participation Rate</td>
                    {comparisonData.analytics.map((a) => {
                      const yd = selectedYear !== null
                        ? a.contribution_by_year.find((y) => y.year === selectedYear)
                        : null;
                      return (
                        <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                          {(yd?.participation_rate ?? a.participation_rate).toFixed(1)}%
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-ink-muted">Total Employee Contributions</td>
                    {comparisonData.analytics.map((a) => {
                      const yd = selectedYear !== null
                        ? a.contribution_by_year.find((y) => y.year === selectedYear)
                        : null;
                      return (
                        <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                          {formatCurrency(yd?.total_employee_contributions ?? a.total_employee_contributions)}
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-ink-muted">Total Employer Match</td>
                    {comparisonData.analytics.map((a) => {
                      const yd = selectedYear !== null
                        ? a.contribution_by_year.find((y) => y.year === selectedYear)
                        : null;
                      return (
                        <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                          {formatCurrency(yd?.total_employer_match ?? a.total_employer_match)}
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-ink-muted">Total Employer Core</td>
                    {comparisonData.analytics.map((a) => {
                      const yd = selectedYear !== null
                        ? a.contribution_by_year.find((y) => y.year === selectedYear)
                        : null;
                      return (
                        <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                          {formatCurrency(yd?.total_employer_core ?? a.total_employer_core)}
                        </td>
                      );
                    })}
                  </tr>
                  <tr className="bg-surface-subtle">
                    <td className="py-3 px-4 text-ink font-semibold">Total All Contributions</td>
                    {comparisonData.analytics.map((a) => {
                      const yd = selectedYear !== null
                        ? a.contribution_by_year.find((y) => y.year === selectedYear)
                        : null;
                      return (
                        <td key={a.scenario_id} className="py-3 px-4 text-right font-bold text-fidelity-green">
                          {formatCurrency(yd?.total_all_contributions ?? a.total_all_contributions)}
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-ink-muted">
                      Employees at IRS Limit
                      {selectedYear !== null && (
                        <span className="ml-1 text-xs text-ink-subtle">(final year)</span>
                      )}
                    </td>
                    {comparisonData.analytics.map((a) => (
                      <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                        {selectedYear !== null
                          ? '—'
                          : `${a.irs_limit_metrics.employees_at_irs_limit.toLocaleString()} (${a.irs_limit_metrics.irs_limit_rate.toFixed(1)}%)`}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Comparison Bar Chart */}
          <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
            <h3 className="text-lg font-semibold text-ink mb-6">Contribution Totals by Scenario</h3>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={comparisonContributionData} barSize={60}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                  <XAxis dataKey="scenario" stroke={chartTheme.axis.line} />
                  <YAxis stroke={chartTheme.axis.line} tickFormatter={(value) => formatCurrency(value)} />
                  <Tooltip
                    cursor={chartTheme.tooltip.cursorStyle}
                    contentStyle={chartTheme.tooltip.contentStyle}
                    formatter={(value: number) => [formatCurrency(value), '']}
                  />
                  <Legend verticalAlign="top" height={36} formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                  <Bar dataKey="Employee" stackId="a" fill={chartTheme.semantic.contribution.employee} name="Employee" />
                  <Bar dataKey="Match" stackId="a" fill={chartTheme.semantic.contribution.match} name="Employer Match" />
                  <Bar dataKey="Core" stackId="a" fill={chartTheme.semantic.contribution.core} name="Employer Core" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      ) : analytics && (
        /* Single Scenario View */
        <>
          {/* KPI Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <KPICard
              title="Employee Deferrals"
              value={formatCurrency(
                activeYearData?.total_employee_contributions ?? analytics.total_employee_contributions
              )}
              subtext={
                activeYearData
                  ? `${activeYearData.participant_count.toLocaleString()} participants`
                  : `${analytics.total_enrolled.toLocaleString()} participants`
              }
              icon={DollarSign}
              color="blue"
              loading={loading}
            />
            <KPICard
              title="Employer Match"
              value={formatCurrency(
                activeYearData?.total_employer_match ?? analytics.total_employer_match
              )}
              subtext="Total employer match"
              icon={DollarSign}
              color="green"
              loading={loading}
            />
            <KPICard
              title="Employer Core"
              value={formatCurrency(
                activeYearData?.total_employer_core ?? analytics.total_employer_core
              )}
              subtext="Non-elective contributions"
              icon={DollarSign}
              color="orange"
              loading={loading}
            />
            <KPICard
              title="Participation Rate"
              value={`${(activeYearData?.participation_rate ?? analytics.participation_rate).toFixed(1)}%`}
              subtext={
                activeYearData
                  ? `${activeYearData.participant_count.toLocaleString()} of ${activeYearData.total_eligible_count.toLocaleString()} eligible`
                  : `${analytics.total_enrolled.toLocaleString()} of ${analytics.total_eligible.toLocaleString()} ${populationLabel.toLowerCase()}`
              }
              icon={Users}
              color="purple"
              loading={loading}
            />
          </div>

          {/* Scenario Info Banner */}
          <div className="bg-info-surface border border-info-border rounded-lg p-4 flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-info-ink">{analytics.scenario_name}</h3>
              <p className="text-sm text-info-ink">
                Total All Contributions: {formatCurrency(analytics.total_all_contributions)}
              </p>
            </div>
            <div className="text-right text-sm text-info-ink">
              <p>{analytics.contribution_by_year.length} year(s) of data</p>
            </div>
          </div>

          {/* Participation and Savings Rate Trends (#641) */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-ink">Participation Rate Trend</h3>
                <button
                  type="button"
                  onClick={handleCopyParticipationTrend}
                  disabled={!hasParticipationTrend}
                  className={`p-1.5 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${participationTrendCopied ? 'text-success-ink bg-success-surface' : 'text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle'}`}
                  title={participationTrendCopied ? 'Participation trend copied' : 'Copy participation trend'}
                  aria-label={participationTrendCopied ? 'Participation trend copied' : 'Copy participation trend'}
                >
                  {participationTrendCopied ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>
              <p className="text-xs text-ink-muted mt-1 mb-4">
                Enrolled eligible employees divided by the selected eligible population each year.
                Gaps indicate no eligible employees for that year.
              </p>
              <div className="h-80">
                {hasParticipationTrend ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                      <YAxis
                        domain={[0, 100]}
                        stroke={chartTheme.axis.line}
                        tickFormatter={(value) => `${value}%`}
                      />
                      <Tooltip
                        cursor={chartTheme.tooltip.cursorStyle}
                        content={<ParticipationTrendTooltip populationLabel={populationLabel} />}
                      />
                      <Line
                        type="monotone"
                        dataKey="participationRate"
                        name="Participation rate"
                        stroke={chartTheme.semantic.primary}
                        strokeWidth={3}
                        connectNulls={false}
                        dot={{ r: 4 }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle text-center">
                    <p>No eligible employees are available for this population and cohort.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-ink">Average Savings Rate Trend</h3>
                <button
                  type="button"
                  onClick={handleCopySavingsTrend}
                  disabled={!hasSavingsTrend}
                  className={`p-1.5 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${savingsTrendCopied ? 'text-success-ink bg-success-surface' : 'text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle'}`}
                  title={savingsTrendCopied ? 'Savings trend copied' : 'Copy savings trend'}
                  aria-label={savingsTrendCopied ? 'Savings trend copied' : 'Copy savings trend'}
                >
                  {savingsTrendCopied ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>
              <p className="text-xs text-ink-muted mt-1 mb-4">
                Component contributions divided by prorated eligible compensation. Rates are
                compensation-weighted and additive; gaps indicate no eligible compensation.
              </p>
              <div className="h-80">
                {hasSavingsTrend ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                      <YAxis
                        domain={[0, 'auto']}
                        stroke={chartTheme.axis.line}
                        tickFormatter={(value) => `${value}%`}
                      />
                      <Tooltip
                        cursor={chartTheme.tooltip.cursorStyle}
                        content={<SavingsTrendTooltip populationLabel={populationLabel} />}
                      />
                      <Legend
                        verticalAlign="top"
                        height={36}
                        formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>}
                      />
                      <Line
                        type="monotone"
                        dataKey="employeeRate"
                        name="Employee deferral"
                        stroke={chartTheme.semantic.contribution.employee}
                        strokeWidth={2}
                        connectNulls={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="matchRate"
                        name="Employer match"
                        stroke={chartTheme.semantic.contribution.match}
                        strokeWidth={2}
                        connectNulls={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="coreRate"
                        name="Employer non-elective/core"
                        stroke={chartTheme.semantic.contribution.core}
                        strokeWidth={2}
                        connectNulls={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle text-center">
                    <p>No eligible compensation is available for this population and cohort.</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Main Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Contribution Stacked Bar Chart */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <h3 className="text-lg font-semibold text-ink mb-6">Contributions by Year</h3>
              <div className="h-80">
                {contributionChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={contributionChartData} barSize={50}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                      <YAxis stroke={chartTheme.axis.line} tickFormatter={(value) => formatCurrency(value)} />
                      <Tooltip
                        cursor={chartTheme.tooltip.cursorStyle}
                        contentStyle={chartTheme.tooltip.contentStyle}
                        formatter={(value: number) => [formatCurrency(value), '']}
                      />
                      <Legend verticalAlign="top" height={36} formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                      <Bar dataKey="Employee" stackId="a" fill={chartTheme.semantic.contribution.employee} name="Employee" radius={[0, 0, 4, 4]}>
                        {contributionChartData.map((entry) => (
                          <Cell
                            key={`emp-${entry.year}`}
                            fill={chartTheme.semantic.contribution.employee}
                            opacity={selectedYear === null || entry.year === selectedYear ? 1 : 0.35}
                          />
                        ))}
                      </Bar>
                      <Bar dataKey="Match" stackId="a" fill={chartTheme.semantic.contribution.match} name="Employer Match">
                        {contributionChartData.map((entry) => (
                          <Cell
                            key={`match-${entry.year}`}
                            fill={chartTheme.semantic.contribution.match}
                            opacity={selectedYear === null || entry.year === selectedYear ? 1 : 0.35}
                          />
                        ))}
                      </Bar>
                      <Bar dataKey="Core" stackId="a" fill={chartTheme.semantic.contribution.core} name="Employer Core" radius={[4, 4, 0, 0]}>
                        {contributionChartData.map((entry) => (
                          <Cell
                            key={`core-${entry.year}`}
                            fill={chartTheme.semantic.contribution.core}
                            opacity={selectedYear === null || entry.year === selectedYear ? 1 : 0.35}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle">
                    <p>No contribution data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Deferral Rate Distribution */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-ink">Deferral Rate Distribution</h3>
                  <p className="text-xs text-ink-muted mt-0.5">
                    {deferralView === 'effective'
                      ? 'Rate used for contribution calculation — 0% aligns with non-participants'
                      : 'Year-end snapshot — reflects escalations and mid-year opt-outs'}
                  </p>
                </div>
                <div className="flex items-center bg-surface-subtle rounded-lg p-1 shrink-0 ml-4">
                  <button
                    onClick={() => setDeferralView('effective')}
                    className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                      deferralView === 'effective'
                        ? 'bg-surface-raised text-ink shadow-sm'
                        : 'text-ink-muted hover:text-ink-muted'
                    }`}
                  >
                    Effective Rate
                  </button>
                  <button
                    onClick={() => setDeferralView('yearend')}
                    className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                      deferralView === 'yearend'
                        ? 'bg-surface-raised text-ink shadow-sm'
                        : 'text-ink-muted hover:text-ink-muted'
                    }`}
                  >
                    Year-End
                  </button>
                </div>
              </div>
              <div className="h-80">
                {deferralDistributionData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={deferralDistributionData} layout="vertical" barSize={20} margin={{ right: 56 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={chartTheme.grid.line} />
                      <XAxis type="number" stroke={chartTheme.axis.line} />
                      <YAxis dataKey="bucket" type="category" stroke={chartTheme.axis.line} width={50} />
                      <Tooltip
                        cursor={chartTheme.tooltip.cursorStyle}
                        content={<DeferralTooltip />}
                      />
                      <Bar dataKey="count" fill={chartTheme.semantic.primary} name="count" radius={[0, 4, 4, 0]}>
                        <LabelList
                          dataKey="percentage"
                          position="right"
                          formatter={(v: number) => `${v.toFixed(1)}%`}
                          style={{ fill: chartTheme.axis.label, fontSize: 12 }}
                        />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle">
                    <p>No deferral data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Participation Breakdown Pie Chart */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <h3 className="text-lg font-semibold text-ink mb-6">Participation by Enrollment Method</h3>
              <div className="h-80">
                {participationPieData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={participationPieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={5}
                        dataKey="value"
                        label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                        labelLine={false}
                      >
                        {participationPieData.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={chartTheme.colorAt(index)} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={chartTheme.tooltip.contentStyle} formatter={(value: number) => [value.toLocaleString(), 'Employees']} />
                      <Legend layout="vertical" verticalAlign="middle" align="right" formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle">
                    <p>No participation data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Escalation Summary */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <h3 className="text-lg font-semibold text-ink mb-4">Escalation Summary</h3>
              <div className="space-y-4">
                <div className="bg-surface-subtle p-4 rounded-lg">
                  <p className="text-sm text-ink-muted">Employees with Escalations</p>
                  <p className="text-2xl font-bold text-ink">
                    {analytics.escalation_metrics.employees_with_escalations.toLocaleString()}
                    <span className="text-sm font-normal text-ink-muted ml-2">
                      ({((analytics.escalation_metrics.employees_with_escalations / analytics.total_enrolled) * 100).toFixed(1)}% of enrolled)
                    </span>
                  </p>
                </div>
                <div className="bg-surface-subtle p-4 rounded-lg">
                  <p className="text-sm text-ink-muted">Average Escalations per Employee</p>
                  <p className="text-2xl font-bold text-ink">
                    {analytics.escalation_metrics.avg_escalation_count.toFixed(1)}
                  </p>
                </div>
                <div className="bg-surface-subtle p-4 rounded-lg">
                  <p className="text-sm text-ink-muted">Total Rate Increase from Escalations</p>
                  <p className="text-2xl font-bold text-ink">
                    {(analytics.escalation_metrics.total_escalation_amount * 100).toFixed(2)}%
                  </p>
                </div>
                <div className="bg-warning-surface p-4 rounded-lg border border-warning-border">
                  <p className="text-sm text-warning-ink">Employees at IRS 402(g) Limit</p>
                  <p className="text-2xl font-bold text-warning-ink">
                    {analytics.irs_limit_metrics.employees_at_irs_limit.toLocaleString()}
                    <span className="text-sm font-normal text-warning-ink ml-2">
                      ({analytics.irs_limit_metrics.irs_limit_rate.toFixed(1)}% of participants)
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
