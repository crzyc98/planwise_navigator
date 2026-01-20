import { ChartDataPoint, SimulationConfig, BatchJob, ComparisonMetric, Workspace, Notification } from './types';

export const APP_NAME = "PlanAlign Engine";
export const APP_VERSION = "1.0.0";

// Maximum number of scenarios that can be selected for comparison
export const MAX_SCENARIO_SELECTION = 6;

export const MOCK_WORKSPACES: Workspace[] = [
  {
    id: 'ws_001',
    name: 'Q1 2025 Planning',
    description: 'Strategic workforce planning for upcoming fiscal year.',
    scenarios: ['cfg_001', 'cfg_002'],
    lastRun: '2 days ago'
  },
  {
    id: 'ws_002',
    name: 'Tech Org Restructure',
    description: 'Analysis of engineering department scaling scenarios.',
    scenarios: ['cfg_003'],
    lastRun: '1 week ago'
  }
];

export const MOCK_NOTIFICATIONS: Notification[] = [
  {
    id: '1',
    title: 'Simulation Completed',
    message: 'Baseline 2025-2027 finished successfully',
    timestamp: '2 mins ago',
    type: 'success',
    read: false
  },
  {
    id: '2',
    title: 'Storage Warning',
    message: 'System storage at 80% capacity',
    timestamp: '1 hour ago',
    type: 'warning',
    read: false
  },
  {
    id: '3',
    title: 'Maintenance Alert',
    message: 'Scheduled maintenance tonight at 02:00 EST',
    timestamp: '5 hours ago',
    type: 'info',
    read: true
  },
  {
    id: '4',
    title: 'Simulation Failed',
    message: 'High Growth scenario failed - memory limit exceeded',
    timestamp: 'Yesterday',
    type: 'error',
    read: true
  }
];

export const MOCK_CONFIGS: SimulationConfig[] = [
  {
    id: 'cfg_001',
    workspaceId: 'ws_001',
    name: 'Baseline 2025-2027',
    startYear: 2025,
    endYear: 2027,
    seed: 42,
    growthTarget: 3.0,
    growthTolerance: 0.5,
    description: 'Standard growth scenario based on historical hiring trends.',
    meritBudget: 3.0,
    colaRate: 2.0,
    promoIncrease: 10.0,
    promoBudget: 1.0,
    newHireStrategy: 'percentile',
    targetPercentile: 50,
    baseTurnoverRate: 10.0,
    regrettableFactor: 0.5,
    advanced: {
        engine: 'polars',
        enableMultithreading: true,
        checkpointFrequency: 'year',
        logLevel: 'INFO',
        strictValidation: true
    }
  },
  {
    id: 'cfg_002',
    workspaceId: 'ws_001',
    name: 'High Growth Q1',
    startYear: 2025,
    endYear: 2028,
    seed: 101,
    growthTarget: 12.0,
    growthTolerance: 1.0,
    description: 'Aggressive expansion plan targeting engineering and sales.',
    meritBudget: 4.0,
    colaRate: 2.5,
    promoIncrease: 15.0,
    promoBudget: 2.0,
    newHireStrategy: 'percentile',
    targetPercentile: 75,
    baseTurnoverRate: 15.0,
    advanced: {
        engine: 'polars',
        enableMultithreading: true,
        checkpointFrequency: 'year',
        logLevel: 'DEBUG',
        strictValidation: true
    }
  },
  {
    id: 'cfg_003',
    workspaceId: 'ws_002',
    name: 'Cost Optimization',
    startYear: 2025,
    endYear: 2026,
    seed: 99,
    growthTarget: 0.0,
    growthTolerance: 0.2,
    description: 'Flat headcount growth with focus on internal mobility.',
    meritBudget: 2.0,
    colaRate: 2.0,
    promoIncrease: 8.0,
    promoBudget: 0.8,
    newHireStrategy: 'fixed',
    baseTurnoverRate: 8.0,
    advanced: {
        engine: 'pandas',
        enableMultithreading: false,
        checkpointFrequency: 'none',
        logLevel: 'INFO',
        strictValidation: true
    }
  }
];

export const WORKFORCE_GROWTH_DATA: ChartDataPoint[] = [
  { year: 2025, baseline: 1000, highGrowth: 1000, conservative: 1000 },
  { year: 2026, baseline: 1030, highGrowth: 1150, conservative: 1010 },
  { year: 2027, baseline: 1061, highGrowth: 1320, conservative: 1015 },
  { year: 2028, baseline: 1092, highGrowth: 1510, conservative: 1020 },
];

export const EVENT_DISTRIBUTION_DATA: ChartDataPoint[] = [
  { year: 2025, Hires: 120, Terminations: 80, Promotions: 45 },
  { year: 2026, Hires: 145, Terminations: 85, Promotions: 50 },
  { year: 2027, Hires: 160, Terminations: 90, Promotions: 55 },
];

export const DEPARTMENT_DATA = [
  { name: 'Engineering', value: 450 },
  { name: 'Sales', value: 180 },
  { name: 'Operations', value: 231 },
  { name: 'Finance', value: 120 },
  { name: 'HR', value: 80 },
];

export const COLORS = {
  primary: '#00853F',
  secondary: '#4CAF50',
  accent: '#FF9800',
  danger: '#F44336',
  charts: ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#E91E63']
};

export const MOCK_BATCH_JOBS: BatchJob[] = [
  {
    id: 'batch_001',
    name: 'Q1 2025 Planning Scenarios',
    status: 'completed',
    submittedAt: '2024-11-24 09:00',
    duration: '12m 34s',
    executionMode: 'parallel',
    exportFormat: 'excel',
    scenarios: [
      { scenario_id: 'sc_01', config_id: 'cfg_001', name: 'Baseline 2025-2027', status: 'completed', progress: 100 },
      { scenario_id: 'sc_02', config_id: 'cfg_002', name: 'High Growth Q1', status: 'completed', progress: 100 },
      { scenario_id: 'sc_03', config_id: 'cfg_003', name: 'Cost Optimization', status: 'completed', progress: 100 },
    ]
  },
  {
    id: 'batch_002',
    name: 'Executive Review Set B',
    status: 'running',
    submittedAt: '2024-11-25 14:30',
    duration: '-',
    executionMode: 'parallel',
    exportFormat: 'excel',
    scenarios: [
      { scenario_id: 'sc_04', config_id: 'cfg_001', name: 'Baseline 2025-2027', status: 'completed', progress: 100 },
      { scenario_id: 'sc_05', config_id: 'cfg_002', name: 'High Growth Q1', status: 'running', progress: 67 },
      { scenario_id: 'sc_06', config_id: 'cfg_003', name: 'Cost Optimization', status: 'queued', progress: 0 },
    ]
  }
];

export const COMPARISON_DATA: ComparisonMetric[] = [
  { metric: 'Final Headcount (2027)', unit: '', 'Baseline 2025-2027': 1061, 'High Growth Q1': 1320, 'Cost Optimization': 1015 },
  { metric: 'CAGR (Growth Rate)', unit: '%', 'Baseline 2025-2027': 3.1, 'High Growth Q1': 12.5, 'Cost Optimization': 0.8 },
  { metric: 'Total Payroll (2027)', unit: '$M', 'Baseline 2025-2027': 142.5, 'High Growth Q1': 178.2, 'Cost Optimization': 135.0 },
  { metric: 'Avg Compensation', unit: '$K', 'Baseline 2025-2027': 134, 'High Growth Q1': 135, 'Cost Optimization': 133 },
  { metric: 'Turnover Rate', unit: '%', 'Baseline 2025-2027': 12.0, 'High Growth Q1': 14.5, 'Cost Optimization': 11.2 },
  { metric: 'DC Plan Enrollment', unit: '%', 'Baseline 2025-2027': 78.4, 'High Growth Q1': 76.2, 'Cost Optimization': 79.8 },
];
