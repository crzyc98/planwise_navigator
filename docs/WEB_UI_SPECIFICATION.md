# PlanAlign Engine - Web UI Specification

**Document Version**: 1.0
**Created**: 2025-11-24
**Target Platform**: Google AI Studio Gemini 3.0 Build Function
**Status**: Design Specification

---

## Executive Summary

This document provides a comprehensive specification for building a modern, React-based web UI for PlanAlign Engine, Fidelity's workforce simulation and financial modeling platform. The web UI will complement the existing CLI by providing interactive visualizations, real-time monitoring, collaborative features, and intuitive configuration management.

### Project Goals

1. **Accessibility**: Enable non-technical users to run workforce simulations without CLI expertise
2. **Visualization**: Provide interactive charts and dashboards for workforce trends and financial projections
3. **Real-Time Monitoring**: Stream live progress updates during multi-year simulations
4. **Collaboration**: Support multi-user environments with shared configurations and results
5. **Enterprise Integration**: Deploy on-premises with enterprise authentication and security

### Technical Approach

- **Frontend**: React 18+ with TypeScript, Material-UI, Plotly.js
- **Backend**: FastAPI (Python) wrapping existing orchestrator
- **Real-Time**: WebSocket streaming for live progress updates
- **Database**: Existing DuckDB for analytics + PostgreSQL for user management
- **Deployment**: Docker containers for on-premises deployment

---

## 1. Current System Analysis

### 1.1 CLI Capabilities

PlanAlign Engine currently provides a Rich-based CLI with the following commands:

| Command | Description | Key Features |
|---------|-------------|--------------|
| `planalign simulate` | Multi-year workforce simulation | Year ranges, checkpoints, Polars engine (375× faster), dry-run mode |
| `planalign batch` | Multi-scenario processing | Parallel execution, Excel/CSV export, comparison reports |
| `planalign status` | System health monitoring | Database connectivity, config validation, performance metrics |
| `planalign analyze` | Post-simulation analysis | Workforce trends, event patterns, scenario comparison |
| `planalign checkpoints` | Recovery management | List/restore/cleanup checkpoints, integrity validation |
| `planalign validate` | Configuration validation | Pre-flight checks, schema validation |

### 1.2 Existing Streamlit Dashboard

Current dashboard includes:
- **Main Dashboard**: System status, navigation hub
- **Compensation Tuning**: Real-time parameter adjustment with simulation execution
- **Optimization Progress**: SciPy-based optimization monitoring
- **Deferral Escalation Analytics**: Multi-year progression analysis with KPI tracking
- **Debug Dashboard**: Configuration validation and event debugging

### 1.3 Core Data Models

**Fact Tables** (reporting/analytics):
- `fct_workforce_snapshot` - Point-in-time workforce state by year
- `fct_yearly_events` - All workforce events (hire, termination, promotion, raise)
- `fct_compensation_growth` - Compensation trend analysis
- `fct_payroll_ledger` - Payroll event tracking
- `fct_employer_match_events` - DC plan matching

**Event Schema** (Pydantic v2):
- **Workforce Events**: HirePayload, PromotionPayload, TerminationPayload, MeritPayload
- **DC Plan Events**: EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload

### 1.4 Key Workflows

1. **Configuration Management**: Load/edit YAML configs, set parameters, validate
2. **Simulation Execution**: 6-stage pipeline (INITIALIZATION → FOUNDATION → EVENT_GENERATION → STATE_ACCUMULATION → VALIDATION → REPORTING)
3. **Batch Processing**: Multi-scenario parallel execution with comparison reports
4. **Results Analysis**: Workforce trends, compensation growth, event statistics
5. **Recovery**: Checkpoint-based resume capability

---

## 2. Web UI Architecture

### 2.1 Frontend Stack

```json
{
  "framework": "React 18.2+",
  "language": "TypeScript 5.0+",
  "ui_library": "Material-UI (MUI) 5.14+",
  "charts": "Plotly.js 2.26+ (interactive) + Recharts 2.8+ (simple)",
  "state_management": "React Query 5.0+ (server state) + Zustand 4.4+ (client state)",
  "routing": "React Router 6.16+",
  "forms": "React Hook Form 7.47+ + Zod validation",
  "websockets": "Socket.IO Client 4.7+",
  "date_handling": "date-fns 2.30+",
  "tables": "TanStack Table 8.10+",
  "file_upload": "react-dropzone 14.2+",
  "notifications": "notistack 3.0+"
}
```

### 2.2 Backend API Stack

```json
{
  "framework": "FastAPI 0.104+",
  "websockets": "python-socketio 5.10+",
  "database_orm": "SQLAlchemy 2.0+ (user management)",
  "analytics_db": "DuckDB 1.0.0 (existing)",
  "authentication": "FastAPI-Users 12.1+ (JWT + cookie-based)",
  "validation": "Pydantic 2.7.4 (existing)",
  "async": "asyncio + aiofiles",
  "background_jobs": "Celery 5.3+ + Redis 5.0+",
  "file_export": "openpyxl 3.1+ (Excel) + pandas 2.1+ (CSV)"
}
```

### 2.3 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Browser (Client)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ React App    │  │ Plotly.js    │  │ Socket.IO    │      │
│  │ (TypeScript) │  │ Charts       │  │ Client       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTPS/WSS
┌─────────────────────────────────────────────────────────────┐
│                    Nginx Reverse Proxy                       │
│           (SSL Termination, Load Balancing)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   FastAPI Application    │  │   Socket.IO Server       │
│   (REST Endpoints)       │  │   (Real-Time Updates)    │
└──────────────────────────┘  └──────────────────────────┘
                 │                         │
                 ▼                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Celery Workers (Background Jobs)                │
│  ┌──────────────────┐  ┌──────────────────────────────┐    │
│  │ Simulation       │  │ Batch Processing             │    │
│  │ Executor         │  │ Executor                     │    │
│  └──────────────────┘  └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  PipelineOrchestrator    │  │  PostgreSQL Database     │
│  (Existing Python)       │  │  (Users, Sessions)       │
└──────────────────────────┘  └──────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│ DuckDB  │ │ Redis   │ │ File    │
│ (OLAP)  │ │ (Cache) │ │ System  │
└─────────┘ └─────────┘ └─────────┘
```

### 2.4 Deployment Architecture

**Docker Compose Services**:
```yaml
services:
  web:
    image: planwise-ui:latest
    # React production build served by Nginx

  api:
    image: planwise-api:latest
    # FastAPI + Socket.IO server

  worker:
    image: planwise-worker:latest
    # Celery workers for background simulations

  postgres:
    image: postgres:16
    # User management, session storage

  redis:
    image: redis:7
    # Celery broker + caching layer

  nginx:
    image: nginx:latest
    # Reverse proxy, SSL termination
```

---

## 3. Core Features & User Flows

### 3.1 Configuration Studio

**Purpose**: Visual editor for simulation configuration files (YAML)

**UI Components**:

```typescript
interface ConfigurationStudioProps {
  configId?: string;  // Optional: load existing config
  mode: 'create' | 'edit' | 'clone';
}

// Main sections
const ConfigSections = [
  'Simulation Settings',      // Years, seed, growth targets
  'Compensation Parameters',  // COLA, merit, promotion increases
  'New Hire Strategy',        // Percentile-based or fixed compensation
  'Turnover Assumptions',     // Termination hazard rates
  'Hiring Plan',              // Growth targets by department/year
  'DC Plan Configuration',    // Eligibility, matching, vesting
  'Advanced Settings'         // Optimization, threading, Polars engine
];
```

**Layout**:
```
┌────────────────────────────────────────────────────────────────┐
│ Configuration Studio                           [Save] [Validate]│
├──────────────┬─────────────────────────────────────────────────┤
│              │  Simulation Settings                            │
│ Sections:    │  ┌─────────────────────────────────────┐        │
│              │  │ Scenario Name: [Baseline 2025-2027] │        │
│ ☑ Simulation │  │ Start Year:    [2025]      ▼        │        │
│ ☑ Compensat. │  │ End Year:      [2027]      ▼        │        │
│ ☐ New Hire   │  │ Random Seed:   [42]                 │        │
│ ☐ Turnover   │  │ Growth Target: [3.0]% per year      │        │
│ ☐ Hiring     │  │ Growth Tolerance: [±0.5]%           │        │
│ ☐ DC Plan    │  └─────────────────────────────────────┘        │
│ ☐ Advanced   │                                                 │
│              │  Impact Preview                                 │
│              │  ┌─────────────────────────────────────┐        │
│              │  │ Estimated Headcount Growth:         │        │
│              │  │ 2025: 1,000 → 2027: 1,061 (+6.1%)   │        │
│              │  │                                      │        │
│              │  │ Estimated Annual Cost:              │        │
│              │  │ 2025: $125M → 2027: $142M (+13.6%)  │        │
│              │  └─────────────────────────────────────┘        │
├──────────────┴─────────────────────────────────────────────────┤
│ Validation: ✓ All checks passed (last checked: 2 min ago)     │
└────────────────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Real-Time Validation**: Validate as user types, show errors inline
2. **Impact Preview**: Calculate estimated headcount/cost based on parameters
3. **Template Library**: Pre-built configs (Conservative, Baseline, High Growth)
4. **Version History**: Track config changes with diff viewer
5. **Import/Export**: Upload YAML or download current config
6. **Collaboration**: Share configs via URL, comment on parameters

**API Endpoints**:
```typescript
POST   /api/config/create          // Create new configuration
GET    /api/config/{id}            // Load existing configuration
PUT    /api/config/{id}            // Update configuration
POST   /api/config/validate        // Validate without saving
GET    /api/config/templates       // List template configurations
POST   /api/config/{id}/clone      // Clone existing config
GET    /api/config/{id}/history    // Get version history
POST   /api/config/{id}/preview    // Generate impact preview
```

---

### 3.2 Simulation Control Center

**Purpose**: Launch and monitor real-time simulation execution

**UI Components**:

```typescript
interface SimulationControlProps {
  configId: string;
  onComplete: (simulationId: string) => void;
}

// Real-time status from WebSocket
interface SimulationStatus {
  simulation_id: string;
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed';
  current_year: number;
  total_years: number;
  current_stage: WorkflowStage;
  progress_percent: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number;
  events_generated: number;
  last_event: string;
  performance_metrics: {
    events_per_second: number;
    memory_usage_mb: number;
    cpu_percent: number;
  };
}

type WorkflowStage =
  | 'INITIALIZATION'
  | 'FOUNDATION'
  | 'EVENT_GENERATION'
  | 'STATE_ACCUMULATION'
  | 'VALIDATION'
  | 'REPORTING';
```

**Layout**:
```
┌────────────────────────────────────────────────────────────────┐
│ Simulation: Baseline 2025-2027            [Pause] [Stop] [Log] │
├────────────────────────────────────────────────────────────────┤
│ Year 2 of 3 (2026)                             ████████░░ 67%  │
│ Stage: EVENT_GENERATION                     Elapsed: 00:04:32  │
│                                           Remaining: 00:02:18  │
├────────────────────────────────────────────────────────────────┤
│ Stage Progress                                                 │
│ ✓ INITIALIZATION          [██████████████████████] 100%  23s  │
│ ✓ FOUNDATION              [██████████████████████] 100%  45s  │
│ ▶ EVENT_GENERATION        [████████████░░░░░░░░░░]  65% 112s  │
│   STATE_ACCUMULATION      [░░░░░░░░░░░░░░░░░░░░░░]   0%   -   │
│   VALIDATION              [░░░░░░░░░░░░░░░░░░░░░░]   0%   -   │
│   REPORTING               [░░░░░░░░░░░░░░░░░░░░░░]   0%   -   │
├────────────────────────────────────────────────────────────────┤
│ Live Metrics                                                   │
│ Events Generated: 12,847    Events/sec: 114    Memory: 523 MB │
│                                                                │
│ Latest Events:                                                 │
│ 14:32:45 - HIRE: EMP_2026_0847 → Engineering L3               │
│ 14:32:44 - PROMOTION: EMP_2023_0234 → L4 ($142K → $168K)      │
│ 14:32:44 - TERMINATION: EMP_2019_1023 (voluntary)             │
├────────────────────────────────────────────────────────────────┤
│ Performance Graph                    [1min] [5min] [All]      │
│                                                                │
│  Events/sec                                                    │
│  150 ┤     ╭──╮                                                │
│  100 ┤   ╭─╯  ╰─╮  ╭──╮                                        │
│   50 ┤ ──╯      ╰──╯  ╰────                                    │
│    0 └────────────────────────────────────────                │
│      0s      60s     120s    180s    240s                      │
└────────────────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Real-Time WebSocket Updates**: Live progress bars, event counts, performance metrics
2. **Stage Breakdown**: Visual progress through 6 workflow stages
3. **Event Stream**: Live tail of recent events (HIRE, TERMINATION, PROMOTION)
4. **Performance Monitoring**: Events/sec, memory usage, CPU utilization
5. **Pause/Resume**: Checkpoint-based pause/resume capability
6. **Detailed Logs**: Expandable log viewer with filtering
7. **Multi-Simulation Queue**: Monitor multiple concurrent simulations

**API Endpoints**:
```typescript
POST   /api/simulations/start                   // Start new simulation
GET    /api/simulations/{id}/status             // Get current status
WS     /api/simulations/{id}/progress           // WebSocket for live updates
POST   /api/simulations/{id}/pause              // Pause execution
POST   /api/simulations/{id}/resume             // Resume from checkpoint
POST   /api/simulations/{id}/cancel             // Cancel simulation
GET    /api/simulations/{id}/logs               // Get execution logs
GET    /api/simulations/queue                   // List queued simulations
```

**WebSocket Event Schema**:
```typescript
// Events sent from server to client
type WebSocketEvent =
  | { type: 'status_update', data: SimulationStatus }
  | { type: 'stage_complete', data: { stage: WorkflowStage, duration: number } }
  | { type: 'year_complete', data: { year: number, event_count: number } }
  | { type: 'event_generated', data: { event_type: string, details: string } }
  | { type: 'error', data: { message: string, stage: string } }
  | { type: 'complete', data: { total_duration: number, total_events: number } };
```

---

### 3.3 Interactive Analytics Dashboard

**Purpose**: Visualize simulation results with interactive charts and filters

**UI Components**:

```typescript
interface AnalyticsDashboardProps {
  simulationId: string;
  comparisonIds?: string[];  // Optional: compare multiple simulations
}

// Available chart types
type ChartType =
  | 'workforce_growth'       // Line chart: headcount over time
  | 'compensation_trends'    // Multi-line: avg/median/total comp
  | 'event_distribution'     // Stacked bar: hires/terms/promos by year
  | 'department_breakdown'   // Treemap: headcount by department
  | 'tenure_distribution'    // Histogram: employee tenure bands
  | 'age_pyramid'            // Population pyramid: age distribution
  | 'compensation_bands'     // Box plot: compensation by job level
  | 'turnover_analysis'      // Line + bar: turnover rate + volume
  | 'enrollment_rates'       // Area chart: DC plan participation
  | 'sankey_flow'            // Sankey: hire → promotion → termination flow
```

**Layout**:
```
┌────────────────────────────────────────────────────────────────┐
│ Analytics: Baseline 2025-2027            [Export] [Compare]    │
├────────────────────────────────────────────────────────────────┤
│ Filters:                                                       │
│ Year: [2025 ▼] [2026 ✓] [2027 ✓]   Department: [All ▼]       │
│ Job Level: [All ▼]   Event Type: [All ▼]                      │
├─────────────────────────────┬──────────────────────────────────┤
│ Workforce Growth            │ Key Metrics                      │
│                             │ ┌──────────────────────────────┐ │
│  Headcount                  │ │ Total Headcount              │ │
│  1,100 ┤        ╭────       │ │ 2027: 1,061 (+6.1%)          │ │
│  1,050 ┤     ╭──╯           │ │                              │ │
│  1,000 ┤ ────╯              │ │ Avg Compensation             │ │
│    950 └────────────        │ │ 2027: $134K (+8.2%)          │ │
│        2025  2026  2027     │ │                              │ │
│                             │ │ Turnover Rate                │ │
│ [Download Chart]            │ │ 2027: 12.3% (±0.5% target)   │ │
│                             │ └──────────────────────────────┘ │
├─────────────────────────────┴──────────────────────────────────┤
│ Event Distribution by Year                                     │
│                                                                │
│  Count                                                         │
│  500 ┤ ███         ███         ███                             │
│  400 ┤ ███         ███         ███                             │
│  300 ┤ ███  ▓▓▓    ███  ▓▓▓    ███  ▓▓▓                        │
│  200 ┤ ███  ▓▓▓    ███  ▓▓▓    ███  ▓▓▓                        │
│  100 ┤ ███  ▓▓▓░░░ ███  ▓▓▓░░░ ███  ▓▓▓░░░                     │
│    0 └─────────────────────────────────                        │
│       2025        2026        2027                             │
│       ███ Hires  ▓▓▓ Terminations  ░░░ Promotions              │
├────────────────────────────────────────────────────────────────┤
│ Department Breakdown (Treemap)        Compensation by Level   │
│ ┌──────────────────────────┐          (Box Plot)              │
│ │ Engineering     Sales    │                                  │
│ │ (450)          (180)     │   $250K ┤      •                 │
│ │                          │   $200K ┤    ┌─┴─┐    •          │
│ │ Finance  HR    Ops       │   $150K ┤  ┌─┴─┬─┴─┐  ┌─┴─┐      │
│ │ (120)   (80)  (231)      │   $100K ┤┌─┴─┬─┴─┬─┴─┬─┴─┬─┐     │
│ └──────────────────────────┘    $50K └┴───┴───┴───┴───┴─┘     │
│                                      L1  L2  L3  L4  L5       │
└────────────────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Interactive Filters**: Year, department, job level, event type - all charts update
2. **Drill-Down**: Click chart elements to filter (e.g., click "Engineering" → filter all charts)
3. **Tooltip Details**: Hover for exact values, percentages, comparisons
4. **Chart Customization**: Toggle series, change axes, adjust time ranges
5. **Export Options**: Download as PNG, SVG, CSV, or Excel
6. **Comparison Mode**: Overlay multiple simulations (baseline vs. high growth)
7. **Cohort Analysis**: Track specific employee cohorts over time
8. **Predictive Trends**: Show trend lines with confidence intervals

**Chart Library Details**:

```typescript
// Plotly.js configuration for interactive charts
import Plotly from 'plotly.js-dist-min';

const plotlyConfig = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  toImageButtonOptions: {
    format: 'png',
    filename: 'planwise_chart',
    height: 800,
    width: 1200,
    scale: 2
  }
};

// Example: Workforce Growth Chart
const workforceGrowthTrace = {
  x: years,
  y: headcounts,
  type: 'scatter',
  mode: 'lines+markers',
  name: 'Baseline',
  line: { color: '#1976d2', width: 3 },
  marker: { size: 8 }
};

// Example: Event Distribution Stacked Bar
const eventDistributionTraces = [
  {
    x: years,
    y: hires,
    name: 'Hires',
    type: 'bar',
    marker: { color: '#4caf50' }
  },
  {
    x: years,
    y: terminations,
    name: 'Terminations',
    type: 'bar',
    marker: { color: '#f44336' }
  },
  {
    x: years,
    y: promotions,
    name: 'Promotions',
    type: 'bar',
    marker: { color: '#ff9800' }
  }
];
```

**API Endpoints**:
```typescript
GET    /api/results/{id}/workforce        // Workforce snapshot data
GET    /api/results/{id}/events           // Event data with filters
GET    /api/results/{id}/compensation     // Compensation trends
GET    /api/results/{id}/departments      // Department breakdown
GET    /api/results/{id}/demographics     // Age/tenure distributions
GET    /api/results/{id}/summary          // KPI summary metrics
POST   /api/results/compare               // Compare multiple simulations
POST   /api/results/{id}/export           // Export to Excel/CSV/PDF
GET    /api/results/{id}/cohort/{year}    // Cohort analysis
```

**Data Response Schema**:
```typescript
interface WorkforceSnapshotResponse {
  simulation_id: string;
  data: {
    year: number;
    total_headcount: number;
    avg_compensation: number;
    median_compensation: number;
    total_payroll: number;
    by_department: Array<{
      department: string;
      headcount: number;
      avg_compensation: number;
    }>;
    by_level: Array<{
      job_level: number;
      headcount: number;
      avg_compensation: number;
      min_compensation: number;
      max_compensation: number;
    }>;
    demographics: {
      avg_age: number;
      avg_tenure_years: number;
      age_distribution: Array<{ age_band: string; count: number }>;
      tenure_distribution: Array<{ tenure_band: string; count: number }>;
    };
  }[];
  metadata: {
    config_name: string;
    execution_date: string;
    random_seed: number;
  };
}
```

---

### 3.4 Batch Processing Interface

**Purpose**: Orchestrate multiple scenario simulations in parallel

**UI Components**:

```typescript
interface BatchProcessingProps {
  onComplete: (batchId: string) => void;
}

interface BatchJob {
  batch_id: string;
  scenarios: Array<{
    scenario_id: string;
    name: string;
    config_path: string;
    status: 'queued' | 'running' | 'completed' | 'failed';
    progress_percent: number;
    start_time?: string;
    end_time?: string;
    error?: string;
  }>;
  export_format: 'excel' | 'csv' | null;
  comparison_report_ready: boolean;
}
```

**Layout**:
```
┌────────────────────────────────────────────────────────────────┐
│ Batch Processing                [New Batch] [Export All]       │
├────────────────────────────────────────────────────────────────┤
│ Batch #1: Q1 2025 Planning Scenarios       Started: 2 min ago │
│ Progress: 2 of 5 completed (40%)               ████████░░░░░░  │
├────────────────────────────────────────────────────────────────┤
│ Scenario Name          Status      Progress  Duration  Actions │
│ ✓ Baseline            Completed   100%      142s      [View]  │
│ ✓ Conservative        Completed   100%      138s      [View]  │
│ ▶ High Growth         Running      67%       94s      [Logs]  │
│   Aggressive Hiring   Queued        0%        -       [—]     │
│   Cost Optimization   Queued        0%        -       [—]     │
├────────────────────────────────────────────────────────────────┤
│ Comparison Report: Not ready (3 scenarios pending)             │
│ Excel Export: Enabled ✓   Optimization Level: Medium           │
├────────────────────────────────────────────────────────────────┤
│ [⊕ Add Scenario] [⊗ Remove Selected] [▶ Start Batch]          │
└────────────────────────────────────────────────────────────────┘

After completion:

┌────────────────────────────────────────────────────────────────┐
│ Comparison Matrix: Q1 2025 Planning Scenarios                  │
├────────────────────────────────────────────────────────────────┤
│ Metric                 Baseline  Conservative  High Growth     │
│ Final Headcount (2027)   1,061       1,023        1,142        │
│ Growth Rate               +6.1%       +2.3%       +14.2%       │
│ Avg Compensation         $134K        $132K        $136K       │
│ Total Payroll (2027)     $142M        $135M        $155M       │
│ Turnover Rate            12.3%        11.8%        13.1%       │
│ DC Plan Enrollment       78.4%        76.2%        79.8%       │
├────────────────────────────────────────────────────────────────┤
│ [Download Comparison Report] [View Side-by-Side Charts]        │
└────────────────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Scenario Builder**: Drag-and-drop configuration files or select from templates
2. **Parallel Execution**: Run up to N scenarios concurrently (configurable)
3. **Live Status Grid**: Real-time progress for each scenario
4. **Comparison Matrix**: Auto-generated comparison table after completion
5. **Bulk Export**: Export all scenarios to Excel with comparison sheets
6. **Failure Recovery**: Retry failed scenarios, view error details
7. **Scheduling**: Schedule batch runs for off-peak hours

**API Endpoints**:
```typescript
POST   /api/batch/create                 // Create new batch job
POST   /api/batch/{id}/scenarios/add     // Add scenario to batch
DELETE /api/batch/{id}/scenarios/{sid}   // Remove scenario
POST   /api/batch/{id}/start             // Start batch execution
GET    /api/batch/{id}/status            // Get batch status
WS     /api/batch/{id}/progress          // WebSocket for live updates
GET    /api/batch/{id}/comparison        // Get comparison matrix
POST   /api/batch/{id}/export            // Export all results
GET    /api/batch/history                // List past batch jobs
```

---

### 3.5 Checkpoint Management UI

**Purpose**: Manage simulation checkpoints for recovery and version control

**UI Components**:

```typescript
interface CheckpointManagerProps {
  simulationId?: string;  // Filter by simulation
}

interface Checkpoint {
  checkpoint_id: string;
  simulation_id: string;
  simulation_name: string;
  year: number;
  stage: WorkflowStage;
  created_at: string;
  size_mb: number;
  config_snapshot: object;
  recovery_compatible: boolean;
  notes?: string;
}
```

**Layout**:
```
┌────────────────────────────────────────────────────────────────┐
│ Checkpoint Manager                  [Cleanup] [Settings]       │
├────────────────────────────────────────────────────────────────┤
│ Storage Usage: 2.4 GB / 10 GB (24%)      ████████████░░░░░░░░  │
│ Total Checkpoints: 47   Retention: Last 30 days                │
├────────────────────────────────────────────────────────────────┤
│ Timeline View                           [List] [Calendar]      │
│                                                                │
│ Nov 24, 2025 ─────●──────●──────●─────────────────────────────│
│                   │      │      │                              │
│                   ▼      ▼      ▼                              │
│              Baseline  High   Conservative                     │
│              2026 Y2   Growth  2025 Y1                         │
│                                                                │
│ Nov 23, 2025 ─────●──────●─────────────────────────────────────│
│                   │      │                                     │
│                   ▼      ▼                                     │
│              Baseline  Baseline                                │
│              2026 Y1   2025 Y3                                 │
├────────────────────────────────────────────────────────────────┤
│ Checkpoint Details                                             │
│ ┌────────────────────────────────────────────────────────────┐ │
│ │ ID: ckpt_baseline_2026_y2_event_gen                        │ │
│ │ Simulation: Baseline 2025-2027                             │ │
│ │ Year: 2026  Stage: EVENT_GENERATION                        │ │
│ │ Created: Nov 24, 2025 14:32:45                             │ │
│ │ Size: 87.3 MB                                              │ │
│ │ Recovery Compatible: Yes ✓                                 │ │
│ │                                                            │ │
│ │ [🔍 View Config] [📊 Preview Data] [♻ Restore] [🗑 Delete] │ │
│ └────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────┤
│ Recovery Wizard                                                │
│ 1. Select checkpoint to restore from                           │
│ 2. Verify configuration compatibility                          │
│ 3. Choose resume year/stage                                    │
│ 4. Execute recovery                                            │
└────────────────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Visual Timeline**: See checkpoints on a timeline with simulation context
2. **Storage Monitoring**: Track disk usage, set retention policies
3. **Quick Restore**: One-click recovery from any checkpoint
4. **Config Diff Viewer**: Compare checkpoint config vs. current config
5. **Data Preview**: Sample data from checkpoint without full restore
6. **Cleanup Wizard**: Bulk delete old checkpoints, free up space
7. **Auto-Retention**: Automatically delete checkpoints older than N days
8. **Notes & Tags**: Add metadata to important checkpoints

**API Endpoints**:
```typescript
GET    /api/checkpoints                        // List all checkpoints
GET    /api/checkpoints/{id}                   // Get checkpoint details
POST   /api/checkpoints/{id}/restore           // Restore from checkpoint
DELETE /api/checkpoints/{id}                   // Delete checkpoint
POST   /api/checkpoints/cleanup                // Bulk cleanup
GET    /api/checkpoints/{id}/config            // Get config snapshot
GET    /api/checkpoints/{id}/preview           // Preview data sample
PUT    /api/checkpoints/{id}/notes             // Update notes/tags
GET    /api/checkpoints/storage                // Storage usage stats
```

---

## 4. API Specification

### 4.1 REST API Endpoints (Complete List)

**Authentication**:
```typescript
POST   /api/auth/login                  // Login with email/password
POST   /api/auth/logout                 // Logout current session
POST   /api/auth/refresh                // Refresh JWT token
GET    /api/auth/user                   // Get current user info
POST   /api/auth/register               // Register new user (admin only)
```

**Configuration Management**:
```typescript
GET    /api/config/templates            // List template configurations
GET    /api/config/{id}                 // Get configuration by ID
POST   /api/config/create               // Create new configuration
PUT    /api/config/{id}                 // Update configuration
DELETE /api/config/{id}                 // Delete configuration
POST   /api/config/validate             // Validate configuration
POST   /api/config/{id}/clone           // Clone configuration
GET    /api/config/{id}/history         // Get version history
POST   /api/config/{id}/preview         // Generate impact preview
POST   /api/config/upload               // Upload YAML file
GET    /api/config/{id}/download        // Download as YAML
```

**Simulation Execution**:
```typescript
POST   /api/simulations/start           // Start new simulation
GET    /api/simulations/{id}            // Get simulation details
GET    /api/simulations/{id}/status     // Get current status
POST   /api/simulations/{id}/pause      // Pause execution
POST   /api/simulations/{id}/resume     // Resume from checkpoint
POST   /api/simulations/{id}/cancel     // Cancel simulation
GET    /api/simulations/{id}/logs       // Get execution logs (paginated)
GET    /api/simulations/queue           // List queued simulations
GET    /api/simulations/history         // List completed simulations
DELETE /api/simulations/{id}            // Delete simulation results
```

**Results & Analytics**:
```typescript
GET    /api/results/{id}/workforce           // Workforce snapshot data
GET    /api/results/{id}/events              // Event data with filters
GET    /api/results/{id}/compensation        // Compensation trends
GET    /api/results/{id}/departments         // Department breakdown
GET    /api/results/{id}/demographics        // Age/tenure distributions
GET    /api/results/{id}/dc-plan             // DC plan metrics
GET    /api/results/{id}/summary             // KPI summary metrics
POST   /api/results/compare                  // Compare multiple simulations
POST   /api/results/{id}/export              // Export to Excel/CSV/PDF
GET    /api/results/{id}/cohort/{year}       // Cohort analysis
GET    /api/results/{id}/metadata            // Execution metadata
```

**Batch Processing**:
```typescript
POST   /api/batch/create                     // Create new batch job
GET    /api/batch/{id}                       // Get batch details
POST   /api/batch/{id}/scenarios/add         // Add scenario to batch
DELETE /api/batch/{id}/scenarios/{sid}       // Remove scenario
POST   /api/batch/{id}/start                 // Start batch execution
GET    /api/batch/{id}/status                // Get batch status
GET    /api/batch/{id}/comparison            // Get comparison matrix
POST   /api/batch/{id}/export                // Export all results
GET    /api/batch/history                    // List past batch jobs
DELETE /api/batch/{id}                       // Delete batch job
```

**Checkpoint Management**:
```typescript
GET    /api/checkpoints                      // List all checkpoints
GET    /api/checkpoints/{id}                 // Get checkpoint details
POST   /api/checkpoints/{id}/restore         // Restore from checkpoint
DELETE /api/checkpoints/{id}                 // Delete checkpoint
POST   /api/checkpoints/cleanup              // Bulk cleanup
GET    /api/checkpoints/{id}/config          // Get config snapshot
GET    /api/checkpoints/{id}/preview         // Preview data sample
PUT    /api/checkpoints/{id}/notes           // Update notes/tags
GET    /api/checkpoints/storage              // Storage usage stats
```

**System Health**:
```typescript
GET    /api/health                           // System health check
GET    /api/health/database                  // Database connectivity
GET    /api/health/workers                   // Worker status
GET    /api/metrics                          // System metrics
GET    /api/version                          // API version info
```

### 4.2 WebSocket Events

**Connection**:
```typescript
// Client connects to WebSocket
const socket = io('wss://planwise.example.com', {
  auth: { token: jwtToken }
});

// Subscribe to specific simulation
socket.emit('subscribe', { simulation_id: 'sim_123' });
```

**Server → Client Events**:
```typescript
// Simulation progress update (every 1-2 seconds)
socket.on('status_update', (data: SimulationStatus) => {
  // Update UI with current progress
});

// Stage completion
socket.on('stage_complete', (data: {
  stage: WorkflowStage;
  duration_seconds: number;
  events_generated: number;
}) => {
  // Show stage completion notification
});

// Year completion
socket.on('year_complete', (data: {
  year: number;
  total_events: number;
  duration_seconds: number;
}) => {
  // Update year progress
});

// Individual event generated (throttled to ~10/sec)
socket.on('event_generated', (data: {
  event_type: string;
  employee_id: string;
  details: string;
}) => {
  // Add to event stream log
});

// Error occurred
socket.on('error', (data: {
  message: string;
  stage: string;
  severity: 'warning' | 'error' | 'critical';
}) => {
  // Show error notification
});

// Simulation complete
socket.on('complete', (data: {
  total_duration_seconds: number;
  total_events: number;
  final_headcount: number;
}) => {
  // Show completion dialog, redirect to results
});
```

**Client → Server Events**:
```typescript
// Request detailed logs
socket.emit('get_logs', {
  simulation_id: 'sim_123',
  level: 'DEBUG',
  stage: 'EVENT_GENERATION'
});

// Acknowledge status update (backpressure control)
socket.emit('ack_status', { simulation_id: 'sim_123' });
```

### 4.3 Request/Response Schemas

**Configuration Create/Update**:
```typescript
// POST /api/config/create
interface ConfigCreateRequest {
  name: string;
  description?: string;
  template_id?: string;  // Optional: start from template
  config: {
    simulation: {
      start_year: number;
      end_year: number;
      random_seed: number;
      target_growth_rate: number;
      growth_tolerance: number;
    };
    compensation: {
      cola_rate: number;
      merit_budget: number;
      promotion_compensation: {
        base_increase_pct: number;
        distribution_range: number;
      };
    };
    new_hire_compensation: {
      strategy: 'percentile_based' | 'fixed';
      percentile_strategy?: {
        default_percentile: number;
        level_overrides: Record<number, number>;
      };
    };
    dc_plan?: {
      eligibility_months: number;
      auto_enrollment: boolean;
      default_deferral_rate: number;
      employer_match_formula: string;
    };
  };
}

// Response
interface ConfigCreateResponse {
  config_id: string;
  name: string;
  created_at: string;
  validation_status: 'valid' | 'invalid';
  validation_errors?: string[];
}
```

**Simulation Start**:
```typescript
// POST /api/simulations/start
interface SimulationStartRequest {
  config_id: string;
  options?: {
    dry_run?: boolean;
    use_polars_engine?: boolean;
    fail_on_validation_error?: boolean;
    checkpoint_frequency?: 'year' | 'stage';
  };
}

// Response
interface SimulationStartResponse {
  simulation_id: string;
  status: 'queued' | 'running';
  estimated_duration_seconds: number;
  websocket_url: string;
  queue_position?: number;
}
```

**Results Query**:
```typescript
// GET /api/results/{id}/workforce?year=2026&department=Engineering
interface WorkforceQueryParams {
  year?: number;                // Filter by year
  department?: string;          // Filter by department
  job_level?: number;           // Filter by job level
  include_demographics?: boolean; // Include age/tenure data
}

// Response (already defined above in WorkforceSnapshotResponse)
```

**Batch Comparison**:
```typescript
// GET /api/batch/{id}/comparison
interface BatchComparisonResponse {
  batch_id: string;
  scenarios: Array<{
    scenario_id: string;
    name: string;
  }>;
  comparison_matrix: {
    metrics: Array<{
      name: string;
      unit: string;
      values: Record<string, number>;  // scenario_id → value
      delta_from_baseline?: Record<string, number>;
    }>;
  };
  charts: {
    workforce_growth: Array<{
      scenario_id: string;
      data: Array<{ year: number; headcount: number }>;
    }>;
    compensation_trends: Array<{
      scenario_id: string;
      data: Array<{ year: number; avg_comp: number }>;
    }>;
  };
}
```

---

## 5. Component Architecture

### 5.1 React Component Hierarchy

```
App
├── AuthProvider (Context: user, login, logout)
├── ThemeProvider (Material-UI theme)
├── NotificationProvider (notistack for toasts)
└── Router
    ├── Layout (AppBar, Drawer, Footer)
    │   ├── Header
    │   │   ├── UserMenu
    │   │   └── NotificationBell
    │   ├── Sidebar
    │   │   └── NavigationMenu
    │   └── Main
    │       └── [Page Routes]
    │
    ├── /dashboard (DashboardPage)
    │   ├── SystemHealthCard
    │   ├── RecentSimulationsTable
    │   ├── QuickActionButtons
    │   └── PerformanceChart
    │
    ├── /config/studio (ConfigurationStudio)
    │   ├── SectionList
    │   ├── ConfigForm
    │   │   ├── SimulationSettingsForm
    │   │   ├── CompensationForm
    │   │   ├── NewHireStrategyForm
    │   │   └── DCPlanForm
    │   ├── ImpactPreview
    │   └── ValidationPanel
    │
    ├── /simulate (SimulationControl)
    │   ├── ConfigSelector
    │   ├── OptionsPanel
    │   ├── ProgressDashboard
    │   │   ├── YearProgress
    │   │   ├── StageProgressList
    │   │   ├── LiveMetrics
    │   │   ├── EventStream
    │   │   └── PerformanceGraph
    │   └── ControlButtons
    │
    ├── /analytics/:id (AnalyticsDashboard)
    │   ├── FilterBar
    │   ├── MetricCards
    │   ├── ChartGrid
    │   │   ├── WorkforceGrowthChart (Plotly)
    │   │   ├── EventDistributionChart (Plotly)
    │   │   ├── DepartmentTreemap (Plotly)
    │   │   ├── CompensationBoxPlot (Plotly)
    │   │   └── SankeyFlowDiagram (Plotly)
    │   └── ExportMenu
    │
    ├── /batch (BatchProcessing)
    │   ├── ScenarioBuilder
    │   ├── StatusGrid
    │   ├── ComparisonMatrix
    │   └── ExportPanel
    │
    ├── /checkpoints (CheckpointManager)
    │   ├── TimelineView
    │   ├── StorageMonitor
    │   ├── CheckpointDetails
    │   └── RecoveryWizard
    │
    └── /admin (AdminPanel)
        ├── UserManagement
        ├── SystemSettings
        └── AuditLog
```

### 5.2 State Management Strategy

**Server State (React Query)**:
```typescript
// queries/useSimulation.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export function useSimulation(simulationId: string) {
  return useQuery({
    queryKey: ['simulation', simulationId],
    queryFn: () => api.getSimulation(simulationId),
    refetchInterval: 5000,  // Poll every 5 seconds for status
  });
}

export function useStartSimulation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: SimulationStartRequest) =>
      api.startSimulation(request),
    onSuccess: (data) => {
      // Invalidate simulations list
      queryClient.invalidateQueries({ queryKey: ['simulations'] });
      // Start WebSocket subscription
      subscribeToSimulation(data.simulation_id);
    },
  });
}

export function useWorkforceData(simulationId: string, filters: WorkforceQueryParams) {
  return useQuery({
    queryKey: ['workforce', simulationId, filters],
    queryFn: () => api.getWorkforceData(simulationId, filters),
    staleTime: 60000,  // Cache for 1 minute
  });
}
```

**Client State (Zustand)**:
```typescript
// stores/uiStore.ts
import create from 'zustand';

interface UIStore {
  sidebarOpen: boolean;
  activeFilters: Record<string, any>;
  chartSettings: Record<string, any>;
  setSidebarOpen: (open: boolean) => void;
  setFilter: (key: string, value: any) => void;
  clearFilters: () => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  activeFilters: {},
  chartSettings: {},
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setFilter: (key, value) => set((state) => ({
    activeFilters: { ...state.activeFilters, [key]: value }
  })),
  clearFilters: () => set({ activeFilters: {} }),
}));
```

**WebSocket State**:
```typescript
// hooks/useSimulationProgress.ts
import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';

export function useSimulationProgress(simulationId: string) {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [socket, setSocket] = useState<Socket | null>(null);

  useEffect(() => {
    const newSocket = io(WS_URL, {
      auth: { token: getAuthToken() }
    });

    newSocket.emit('subscribe', { simulation_id: simulationId });

    newSocket.on('status_update', (data: SimulationStatus) => {
      setStatus(data);
    });

    newSocket.on('complete', () => {
      // Invalidate React Query cache to fetch final results
      queryClient.invalidateQueries(['simulation', simulationId]);
    });

    setSocket(newSocket);

    return () => {
      newSocket.close();
    };
  }, [simulationId]);

  return { status, socket };
}
```

### 5.3 Routing Structure

```typescript
// App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" />} />
            <Route path="dashboard" element={<DashboardPage />} />

            <Route path="config">
              <Route path="templates" element={<TemplatesPage />} />
              <Route path="studio" element={<ConfigurationStudio />} />
              <Route path="studio/:id" element={<ConfigurationStudio />} />
            </Route>

            <Route path="simulate">
              <Route index element={<SimulationControl />} />
              <Route path=":id" element={<SimulationMonitor />} />
            </Route>

            <Route path="analytics">
              <Route index element={<AnalyticsListPage />} />
              <Route path=":id" element={<AnalyticsDashboard />} />
              <Route path="compare" element={<ComparisonPage />} />
            </Route>

            <Route path="batch">
              <Route index element={<BatchListPage />} />
              <Route path="new" element={<BatchProcessing />} />
              <Route path=":id" element={<BatchMonitor />} />
            </Route>

            <Route path="checkpoints" element={<CheckpointManager />} />

            <Route path="admin">
              <Route path="users" element={<UserManagement />} />
              <Route path="settings" element={<SystemSettings />} />
              <Route path="audit" element={<AuditLog />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

### 5.4 Reusable Component Library

**Core Components**:

```typescript
// components/common/MetricCard.tsx
interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  trend?: {
    direction: 'up' | 'down' | 'flat';
    percentage: number;
  };
  icon?: React.ReactNode;
  color?: string;
}

export function MetricCard({ title, value, unit, trend, icon, color }: MetricCardProps) {
  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="h6" color="textSecondary">{title}</Typography>
          {icon && <Box color={color}>{icon}</Box>}
        </Box>
        <Typography variant="h3" component="div">
          {value}{unit && <Typography variant="h5" component="span" color="textSecondary"> {unit}</Typography>}
        </Typography>
        {trend && (
          <Box display="flex" alignItems="center" mt={1}>
            <TrendIcon direction={trend.direction} />
            <Typography variant="body2" color={trend.direction === 'up' ? 'success.main' : 'error.main'}>
              {trend.percentage}%
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

// components/common/StatusBadge.tsx
type Status = 'queued' | 'running' | 'completed' | 'failed' | 'paused';

export function StatusBadge({ status }: { status: Status }) {
  const config = {
    queued: { color: 'default', icon: <QueueIcon /> },
    running: { color: 'primary', icon: <PlayIcon /> },
    completed: { color: 'success', icon: <CheckIcon /> },
    failed: { color: 'error', icon: <ErrorIcon /> },
    paused: { color: 'warning', icon: <PauseIcon /> },
  };

  return (
    <Chip
      label={status.toUpperCase()}
      color={config[status].color}
      icon={config[status].icon}
      size="small"
    />
  );
}

// components/common/ProgressBar.tsx
interface ProgressBarProps {
  value: number;  // 0-100
  label?: string;
  showPercentage?: boolean;
  color?: 'primary' | 'secondary' | 'success' | 'error';
  height?: number;
}

export function ProgressBar({ value, label, showPercentage, color, height }: ProgressBarProps) {
  return (
    <Box width="100%">
      {label && (
        <Box display="flex" justifyContent="space-between" mb={0.5}>
          <Typography variant="body2">{label}</Typography>
          {showPercentage && <Typography variant="body2">{value}%</Typography>}
        </Box>
      )}
      <LinearProgress
        variant="determinate"
        value={value}
        color={color}
        sx={{ height: height || 8, borderRadius: 4 }}
      />
    </Box>
  );
}

// components/charts/WorkforceGrowthChart.tsx
interface WorkforceGrowthChartProps {
  data: Array<{ year: number; headcount: number; scenario?: string }>;
  height?: number;
  showLegend?: boolean;
}

export function WorkforceGrowthChart({ data, height, showLegend }: WorkforceGrowthChartProps) {
  // Group by scenario if multi-scenario comparison
  const scenarios = Array.from(new Set(data.map(d => d.scenario || 'default')));

  const traces = scenarios.map(scenario => {
    const scenarioData = data.filter(d => (d.scenario || 'default') === scenario);
    return {
      x: scenarioData.map(d => d.year),
      y: scenarioData.map(d => d.headcount),
      type: 'scatter',
      mode: 'lines+markers',
      name: scenario,
      line: { width: 3 },
      marker: { size: 8 }
    };
  });

  return (
    <Plot
      data={traces}
      layout={{
        title: 'Workforce Growth',
        xaxis: { title: 'Year' },
        yaxis: { title: 'Headcount' },
        height: height || 400,
        showlegend: showLegend !== false,
        hovermode: 'x unified'
      }}
      config={{ responsive: true, displayModeBar: true }}
    />
  );
}
```

---

## 6. Data Visualization Requirements

### 6.1 Chart Type Specifications

**1. Workforce Growth (Line Chart)**
- **Purpose**: Show headcount trends over time
- **Axes**: X = Year, Y = Headcount
- **Features**: Multi-line for scenario comparison, markers on data points, trend line
- **Interactions**: Hover for exact values, click to drill down by department

**2. Event Distribution (Stacked Bar Chart)**
- **Purpose**: Visualize hire/termination/promotion volumes by year
- **Axes**: X = Year, Y = Event Count
- **Series**: Hires (green), Terminations (red), Promotions (orange)
- **Features**: Stacked or grouped mode, percentage view option

**3. Department Breakdown (Treemap)**
- **Purpose**: Hierarchical view of headcount by department
- **Hierarchy**: Company → Department → Sub-department
- **Features**: Click to zoom into department, color by headcount or avg compensation

**4. Compensation Distribution (Box Plot)**
- **Purpose**: Show compensation spread by job level
- **Axes**: X = Job Level, Y = Compensation ($)
- **Features**: Quartiles, outliers, mean/median markers

**5. Age Pyramid (Population Pyramid)**
- **Purpose**: Demographic visualization of age distribution
- **Axes**: X = Count (mirrored), Y = Age Bands
- **Features**: Male/Female split (if available), color by tenure

**6. Sankey Flow Diagram**
- **Purpose**: Visualize employee flow (hire → promote → terminate)
- **Nodes**: New Hires, Current Employees (by level), Terminations
- **Links**: Thickness = count of employees flowing through path

**7. Performance Metrics (Real-Time Line Chart)**
- **Purpose**: Live monitoring of events/sec during simulation
- **Axes**: X = Time (seconds), Y = Events/Second
- **Features**: Auto-scroll, max 300-second window, smoothing option

### 6.2 Interactive Features

**All Charts Support**:
1. **Hover Tooltips**: Show exact values, percentages, comparisons
2. **Zoom/Pan**: Zoom into time ranges or specific data regions
3. **Export**: Download as PNG, SVG, or data as CSV
4. **Responsive**: Auto-resize based on container width
5. **Theme Support**: Light/dark mode compatible

**Advanced Interactions**:
1. **Cross-Filtering**: Click on chart element → filter all other charts
2. **Synchronized Tooltips**: Hover on one chart → show values on all charts for that year
3. **Annotation Mode**: Add notes/markers to specific data points
4. **Comparison Overlays**: Toggle baseline scenario overlay on any chart

### 6.3 Real-Time Update Strategy

**During Simulation Execution**:
```typescript
// Update performance chart every 2 seconds
useEffect(() => {
  if (status?.performance_metrics) {
    setPerformanceData(prev => [
      ...prev.slice(-150),  // Keep last 300 seconds (150 points @ 2s interval)
      {
        timestamp: Date.now(),
        events_per_second: status.performance_metrics.events_per_second,
        memory_mb: status.performance_metrics.memory_usage_mb
      }
    ]);
  }
}, [status]);

// Throttle event stream updates to avoid overwhelming UI
const throttledEvents = useThrottle(status?.last_event, 1000);  // Max 1/sec
```

---

## 7. Design System

### 7.1 Color Palette

**Primary Colors**:
```css
/* Fidelity brand-inspired colors (adjust to actual brand guidelines) */
--primary-green: #00853F;      /* Fidelity green */
--primary-dark: #004D25;
--primary-light: #4CAF50;

/* Semantic colors */
--success: #4CAF50;
--warning: #FF9800;
--error: #F44336;
--info: #2196F3;

/* Neutral grays */
--gray-50: #FAFAFA;
--gray-100: #F5F5F5;
--gray-200: #EEEEEE;
--gray-300: #E0E0E0;
--gray-400: #BDBDBD;
--gray-500: #9E9E9E;
--gray-600: #757575;
--gray-700: #616161;
--gray-800: #424242;
--gray-900: #212121;

/* Chart palette (8 distinct colors for multi-series) */
--chart-1: #1976D2;  /* Blue */
--chart-2: #F57C00;  /* Orange */
--chart-3: #7B1FA2;  /* Purple */
--chart-4: #C62828;  /* Red */
--chart-5: #00897B;  /* Teal */
--chart-6: #FBC02D;  /* Yellow */
--chart-7: #5E35B1;  /* Deep Purple */
--chart-8: #0288D1;  /* Light Blue */
```

**Event Type Colors**:
```css
--event-hire: #4CAF50;         /* Green */
--event-termination: #F44336;  /* Red */
--event-promotion: #FF9800;    /* Orange */
--event-raise: #2196F3;        /* Blue */
--event-enrollment: #9C27B0;   /* Purple */
```

### 7.2 Typography Scale

```css
/* Material-UI default typography scale */
h1: 6rem (96px) - Roboto Light
h2: 3.75rem (60px) - Roboto Light
h3: 3rem (48px) - Roboto Regular
h4: 2.125rem (34px) - Roboto Regular
h5: 1.5rem (24px) - Roboto Regular
h6: 1.25rem (20px) - Roboto Medium

body1: 1rem (16px) - Roboto Regular (default paragraph)
body2: 0.875rem (14px) - Roboto Regular (secondary text)

button: 0.875rem (14px) - Roboto Medium, UPPERCASE
caption: 0.75rem (12px) - Roboto Regular (form labels)
```

### 7.3 Component Variants

**Buttons**:
```typescript
<Button variant="contained" color="primary">Primary Action</Button>
<Button variant="outlined" color="primary">Secondary Action</Button>
<Button variant="text" color="primary">Tertiary Action</Button>

// Icon buttons for actions
<IconButton color="primary"><PlayIcon /></IconButton>
<IconButton color="error"><DeleteIcon /></IconButton>
```

**Cards**:
```typescript
<Card elevation={2}>  // Standard shadow
  <CardHeader title="Card Title" />
  <CardContent>Content here</CardContent>
  <CardActions>
    <Button>Action</Button>
  </CardActions>
</Card>

<Paper elevation={0} sx={{ border: '1px solid #E0E0E0' }}>
  // Alternative: Flat card with border
</Paper>
```

**Tables**:
```typescript
// Use TanStack Table for large datasets
import { useReactTable, flexRender } from '@tanstack/react-table';

// Features: sorting, filtering, pagination, row selection
<Table>
  <TableHead>
    {table.getHeaderGroups().map(headerGroup => (
      <TableRow key={headerGroup.id}>
        {headerGroup.headers.map(header => (
          <TableCell key={header.id}>
            {flexRender(header.column.columnDef.header, header.getContext())}
          </TableCell>
        ))}
      </TableRow>
    ))}
  </TableHead>
  <TableBody>
    {/* Rows */}
  </TableBody>
</Table>
```

### 7.4 Responsive Breakpoints

```typescript
// Material-UI breakpoints
const breakpoints = {
  xs: 0,      // Mobile
  sm: 600,    // Tablet portrait
  md: 960,    // Tablet landscape
  lg: 1280,   // Desktop
  xl: 1920    // Large desktop
};

// Responsive layout example
<Grid container spacing={3}>
  <Grid item xs={12} md={6} lg={4}>
    <MetricCard />
  </Grid>
</Grid>

// Mobile: 1 column (xs=12)
// Tablet: 2 columns (md=6)
// Desktop: 3 columns (lg=4)
```

### 7.5 Accessibility (WCAG 2.1 AA)

**Requirements**:
1. **Color Contrast**: 4.5:1 for normal text, 3:1 for large text
2. **Keyboard Navigation**: All interactive elements accessible via Tab/Enter
3. **Screen Reader Support**: Proper ARIA labels, semantic HTML
4. **Focus Indicators**: Visible focus rings on all interactive elements
5. **Alt Text**: All images and charts have descriptive alt text

**Implementation**:
```typescript
// Accessible button
<Button aria-label="Start simulation">
  <PlayIcon aria-hidden="true" />
  Start
</Button>

// Accessible form
<TextField
  id="start-year"
  label="Start Year"
  type="number"
  required
  error={Boolean(errors.startYear)}
  helperText={errors.startYear?.message}
  inputProps={{
    'aria-describedby': 'start-year-help',
    min: 2020,
    max: 2050
  }}
/>
<FormHelperText id="start-year-help">
  Enter the first year of simulation (2020-2050)
</FormHelperText>

// Accessible chart
<Plot
  data={traces}
  layout={layout}
  config={{
    ...plotlyConfig,
    // Add accessible descriptions
    accessible: true,
    description: 'Line chart showing workforce growth from 2025 to 2027'
  }}
/>
```

---

## 8. Integration Points

### 8.1 Python Orchestrator Integration

**Approach**: FastAPI wraps existing `PipelineOrchestrator` and calls it in Celery workers

**Backend Service Structure**:
```python
# api/main.py
from fastapi import FastAPI, WebSocket, Depends
from celery import Celery
from planalign_orchestrator import PipelineOrchestrator, load_simulation_config

app = FastAPI(title="PlanWise API", version="1.0.0")
celery = Celery('planwise', broker='redis://redis:6379/0')

@app.post("/api/simulations/start")
async def start_simulation(request: SimulationStartRequest):
    # Queue simulation task in Celery
    task = run_simulation.delay(
        config_id=request.config_id,
        options=request.options
    )

    return {
        "simulation_id": task.id,
        "status": "queued",
        "websocket_url": f"wss://{DOMAIN}/ws/simulations/{task.id}"
    }

# workers/tasks.py
@celery.task(bind=True)
def run_simulation(self, config_id: str, options: dict):
    """Execute simulation in background worker."""

    # Load configuration
    config = get_config_by_id(config_id)
    config_path = save_temp_config(config)

    # Create orchestrator
    orchestrator = PipelineOrchestrator(load_simulation_config(config_path))

    # Execute with progress callbacks
    def on_progress(status: dict):
        # Send WebSocket update
        send_ws_update(self.request.id, 'status_update', status)

    try:
        result = orchestrator.execute_multi_year_simulation(
            start_year=config['simulation']['start_year'],
            end_year=config['simulation']['end_year'],
            progress_callback=on_progress
        )

        # Store results in database
        store_simulation_results(self.request.id, result)

        send_ws_update(self.request.id, 'complete', {
            'total_duration': result.total_duration,
            'total_events': result.total_events
        })

        return {"status": "completed"}

    except Exception as e:
        send_ws_update(self.request.id, 'error', {
            'message': str(e),
            'stage': orchestrator.current_stage
        })
        raise
```

**Progress Callback Integration**:
```python
# Modify PipelineOrchestrator to accept progress_callback
class PipelineOrchestrator:
    def __init__(self, config: SimulationConfig, progress_callback=None):
        self.config = config
        self.progress_callback = progress_callback

    def execute_year(self, year: int):
        for stage in WORKFLOW_STAGES:
            # Notify progress before each stage
            if self.progress_callback:
                self.progress_callback({
                    'year': year,
                    'stage': stage.name,
                    'progress_percent': self._calculate_progress(),
                    'events_generated': self.event_count
                })

            # Execute stage
            self._execute_stage(stage, year)

            # Notify stage completion
            if self.progress_callback:
                self.progress_callback({
                    'stage_complete': stage.name,
                    'duration': stage.duration
                })
```

### 8.2 DuckDB Connection Management

**Connection Pooling**:
```python
# database/connection.py
import duckdb
from contextlib import contextmanager
from pathlib import Path

class DuckDBConnectionPool:
    def __init__(self, db_path: Path, max_connections: int = 5):
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool = []

    @contextmanager
    def get_connection(self):
        """Get connection from pool or create new one."""
        conn = duckdb.connect(str(self.db_path), read_only=True)
        try:
            yield conn
        finally:
            conn.close()

    def execute_query(self, query: str, params: list = None):
        """Execute query and return DataFrame."""
        with self.get_connection() as conn:
            if params:
                result = conn.execute(query, params).df()
            else:
                result = conn.execute(query).df()
        return result

# API endpoint using connection pool
@app.get("/api/results/{simulation_id}/workforce")
async def get_workforce_data(simulation_id: str, filters: WorkforceQueryParams):
    db_path = get_simulation_db_path(simulation_id)
    pool = DuckDBConnectionPool(db_path)

    query = """
        SELECT *
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
    """
    params = [filters.year] if filters.year else []

    df = pool.execute_query(query, params)

    return df.to_dict(orient='records')
```

**Query Optimization**:
```python
# Use parameterized queries for safety and caching
def get_events_by_type(simulation_id: str, event_type: str, year: int):
    query = """
        SELECT
            event_id,
            employee_id,
            event_type,
            event_date,
            payload
        FROM fct_yearly_events
        WHERE scenario_id = ?
          AND event_type = ?
          AND simulation_year = ?
        ORDER BY event_date
    """
    return pool.execute_query(query, [simulation_id, event_type, year])

# Use materialized aggregations for performance
def get_department_summary(simulation_id: str, year: int):
    query = """
        SELECT
            department,
            COUNT(*) as headcount,
            AVG(annual_compensation) as avg_compensation,
            SUM(annual_compensation) as total_payroll
        FROM fct_workforce_snapshot
        WHERE scenario_id = ?
          AND simulation_year = ?
        GROUP BY department
        ORDER BY headcount DESC
    """
    return pool.execute_query(query, [simulation_id, year])
```

### 8.3 File System Access

**Configuration File Management**:
```python
# storage/config.py
from pathlib import Path
import yaml

CONFIG_DIR = Path("/var/planwise/configs")
RESULTS_DIR = Path("/var/planwise/results")

def save_config(config_id: str, config_data: dict):
    """Save configuration to YAML file."""
    config_path = CONFIG_DIR / f"{config_id}.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, 'w') as f:
        yaml.dump(config_data, f, default_flow_style=False)

    return config_path

def load_config(config_id: str) -> dict:
    """Load configuration from YAML file."""
    config_path = CONFIG_DIR / f"{config_id}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config {config_id} not found")

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_simulation_db_path(simulation_id: str) -> Path:
    """Get path to simulation DuckDB file."""
    return RESULTS_DIR / simulation_id / "simulation.duckdb"
```

**Export File Generation**:
```python
# export/excel.py
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
import pandas as pd

def export_to_excel(simulation_id: str, output_path: Path):
    """Generate Excel workbook with simulation results."""

    # Load data from DuckDB
    workforce_df = get_workforce_data(simulation_id)
    events_df = get_events_data(simulation_id)
    summary_df = get_summary_metrics(simulation_id)

    # Create workbook
    wb = Workbook()

    # Workforce snapshot sheet
    ws1 = wb.active
    ws1.title = "Workforce Snapshot"
    write_dataframe_to_sheet(ws1, workforce_df)

    # Events sheet
    ws2 = wb.create_sheet("Events")
    write_dataframe_to_sheet(ws2, events_df)

    # Summary sheet
    ws3 = wb.create_sheet("Summary")
    write_dataframe_to_sheet(ws3, summary_df)

    # Metadata sheet
    ws4 = wb.create_sheet("Metadata")
    write_metadata(ws4, simulation_id)

    # Save workbook
    wb.save(output_path)

    return output_path

# API endpoint for export
@app.post("/api/results/{simulation_id}/export")
async def export_results(simulation_id: str, format: str = "excel"):
    """Generate export file and return download URL."""

    if format == "excel":
        output_path = EXPORT_DIR / f"{simulation_id}.xlsx"
        export_to_excel(simulation_id, output_path)
    elif format == "csv":
        output_path = EXPORT_DIR / f"{simulation_id}.zip"
        export_to_csv_zip(simulation_id, output_path)

    # Return download URL
    return {
        "download_url": f"/api/downloads/{output_path.name}",
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
    }
```

### 8.4 Background Job Integration

**Celery Task Structure**:
```python
# workers/tasks.py
from celery import Celery, Task
from celery.signals import task_prerun, task_postrun

celery = Celery('planwise')

class SimulationTask(Task):
    """Base task for simulations with progress tracking."""

    def on_success(self, retval, task_id, args, kwargs):
        """Handle successful completion."""
        # Update database status
        update_simulation_status(task_id, 'completed', retval)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle failure."""
        # Update database status with error
        update_simulation_status(task_id, 'failed', {'error': str(exc)})

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle retry."""
        update_simulation_status(task_id, 'retrying', {'attempt': self.request.retries})

@celery.task(base=SimulationTask, bind=True, max_retries=3)
def run_simulation(self, config_id: str, options: dict):
    """Execute simulation in background."""
    # Implementation shown earlier
    pass

@celery.task(base=SimulationTask, bind=True)
def run_batch(self, batch_id: str, scenario_ids: list):
    """Execute batch of scenarios in parallel."""

    # Create group of simulation tasks
    job = group([
        run_simulation.s(scenario_id, {})
        for scenario_id in scenario_ids
    ])

    # Execute group
    result = job.apply_async()

    # Wait for all to complete
    result.get()

    # Generate comparison report
    generate_comparison_report(batch_id, scenario_ids)

    return {"status": "completed", "scenarios": len(scenario_ids)}
```

**Task Monitoring**:
```python
# API endpoint to check task status
@app.get("/api/simulations/{simulation_id}/status")
async def get_simulation_status(simulation_id: str):
    """Get current status of simulation task."""

    # Check Celery task status
    task = celery.AsyncResult(simulation_id)

    if task.state == 'PENDING':
        status = 'queued'
    elif task.state == 'STARTED':
        status = 'running'
    elif task.state == 'SUCCESS':
        status = 'completed'
    elif task.state == 'FAILURE':
        status = 'failed'
    else:
        status = task.state.lower()

    # Get additional info from database
    db_status = get_simulation_status_from_db(simulation_id)

    return {
        "simulation_id": simulation_id,
        "status": status,
        "progress_percent": db_status.get('progress_percent', 0),
        "current_year": db_status.get('current_year'),
        "current_stage": db_status.get('current_stage'),
        "error": task.info if task.state == 'FAILURE' else None
    }
```

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-3)

**Week 1: Backend Setup**
- [ ] Set up FastAPI project structure
- [ ] Implement authentication (FastAPI-Users + JWT)
- [ ] Create PostgreSQL schema for users, simulations, configs
- [ ] Set up Celery workers with Redis broker
- [ ] Implement basic CRUD endpoints for configurations

**Week 2: Core API**
- [ ] Wrap PipelineOrchestrator with Celery tasks
- [ ] Implement simulation start/stop/status endpoints
- [ ] Set up WebSocket server with Socket.IO
- [ ] Implement progress callback integration
- [ ] Create DuckDB connection pool

**Week 3: Frontend Setup**
- [ ] Initialize React + TypeScript project
- [ ] Set up Material-UI theme
- [ ] Implement authentication flow (login/logout)
- [ ] Create basic layout (AppBar, Drawer, routing)
- [ ] Set up React Query for API calls

### Phase 2: Core Features (Weeks 4-7)

**Week 4: Configuration Studio**
- [ ] Build configuration form with validation
- [ ] Implement template library
- [ ] Create impact preview feature
- [ ] Add YAML import/export

**Week 5: Simulation Control**
- [ ] Build simulation launch interface
- [ ] Implement WebSocket connection for live updates
- [ ] Create progress dashboard with stage breakdown
- [ ] Add event stream display
- [ ] Build performance monitoring chart

**Week 6: Basic Analytics**
- [ ] Implement workforce growth chart (Plotly)
- [ ] Create event distribution chart
- [ ] Build metric cards for KPIs
- [ ] Add filter controls
- [ ] Implement Excel/CSV export

**Week 7: Testing & Polish**
- [ ] Write unit tests for API endpoints
- [ ] Add integration tests for simulation flow
- [ ] Implement error handling and notifications
- [ ] Add loading states and skeleton screens
- [ ] Performance optimization

### Phase 3: Advanced Features (Weeks 8-11)

**Week 8: Batch Processing**
- [ ] Build batch scenario builder interface
- [ ] Implement parallel execution monitoring
- [ ] Create comparison matrix component
- [ ] Add bulk export functionality

**Week 9: Advanced Analytics**
- [ ] Implement remaining chart types (treemap, box plot, Sankey)
- [ ] Add drill-down and cross-filtering
- [ ] Create scenario comparison page
- [ ] Build cohort analysis feature

**Week 10: Checkpoint Management**
- [ ] Build checkpoint timeline view
- [ ] Implement restore wizard
- [ ] Add storage monitoring
- [ ] Create config diff viewer

**Week 11: Admin Panel**
- [ ] Build user management interface
- [ ] Implement system settings page
- [ ] Add audit log viewer
- [ ] Create system health dashboard

### Phase 4: Production Readiness (Weeks 12-14)

**Week 12: Security & Performance**
- [ ] Security audit and penetration testing
- [ ] Implement rate limiting
- [ ] Add request caching (Redis)
- [ ] Optimize database queries
- [ ] Load testing and performance tuning

**Week 13: Deployment**
- [ ] Create Docker images for all services
- [ ] Write Docker Compose configuration
- [ ] Set up Nginx reverse proxy
- [ ] Configure SSL/TLS certificates
- [ ] Create deployment documentation

**Week 14: Documentation & Training**
- [ ] Write user documentation
- [ ] Create video tutorials
- [ ] Prepare admin guide
- [ ] Conduct user training sessions
- [ ] Gather feedback and iterate

---

## 10. Technical Requirements

### 10.1 Development Environment

**Prerequisites**:
```bash
# Node.js and npm
node >= 18.0.0
npm >= 9.0.0

# Python
python >= 3.11

# Docker
docker >= 24.0.0
docker-compose >= 2.20.0

# Database
postgresql >= 16.0
redis >= 7.0
```

**Setup Instructions**:
```bash
# Clone repository
git clone https://github.com/fidelity/planwise-web-ui.git
cd planwise-web-ui

# Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install

# Start development servers
docker-compose up -d postgres redis  # Start databases
cd backend && uvicorn main:app --reload  # Start API
cd backend && celery -A workers worker --loglevel=info  # Start worker
cd frontend && npm start  # Start React dev server
```

### 10.2 Dependencies

**Backend (Python)**:
```txt
# requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-socketio==5.10.0
celery[redis]==5.3.4
redis==5.0.1
sqlalchemy==2.0.23
alembic==1.12.1
asyncpg==0.29.0
pydantic==2.7.4
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
fastapi-users==12.1.2
duckdb==1.0.0
pandas==2.1.3
openpyxl==3.1.2
pyyaml==6.0.1
python-multipart==0.0.6
```

**Frontend (JavaScript/TypeScript)**:
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.16.0",
    "@mui/material": "^5.14.0",
    "@mui/icons-material": "^5.14.0",
    "@emotion/react": "^11.11.0",
    "@emotion/styled": "^11.11.0",
    "@tanstack/react-query": "^5.0.0",
    "@tanstack/react-table": "^8.10.0",
    "plotly.js": "^2.26.0",
    "react-plotly.js": "^2.6.0",
    "recharts": "^2.8.0",
    "socket.io-client": "^4.7.0",
    "zustand": "^4.4.0",
    "react-hook-form": "^7.47.0",
    "zod": "^3.22.0",
    "date-fns": "^2.30.0",
    "notistack": "^3.0.0",
    "react-dropzone": "^14.2.0",
    "axios": "^1.5.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@types/node": "^20.8.0",
    "@types/plotly.js": "^2.12.0",
    "typescript": "^5.0.0",
    "vite": "^4.5.0",
    "@vitejs/plugin-react": "^4.1.0",
    "eslint": "^8.51.0",
    "@typescript-eslint/parser": "^6.8.0",
    "prettier": "^3.0.0"
  }
}
```

### 10.3 Environment Configuration

**Backend (.env)**:
```env
# Application
APP_NAME=PlanAlign Engine
APP_VERSION=1.0.0
DEBUG=false

# Database
DATABASE_URL=postgresql://planwise:password@localhost:5432/planwise
DUCKDB_DIR=/var/planwise/duckdb

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Authentication
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
ALLOWED_ORIGINS=http://localhost:3000,https://planwise.example.com

# File Storage
CONFIG_DIR=/var/planwise/configs
RESULTS_DIR=/var/planwise/results
EXPORT_DIR=/var/planwise/exports
MAX_UPLOAD_SIZE=50MB

# Celery
CELERY_WORKER_CONCURRENCY=4
CELERY_TASK_TIMEOUT=7200  # 2 hours

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

**Frontend (.env)**:
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_APP_NAME=PlanAlign Engine
VITE_APP_VERSION=1.0.0
```

### 10.4 Deployment Configuration

**Docker Compose (docker-compose.yml)**:
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: planwise
      POSTGRES_USER: planwise
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql://planwise:${DB_PASSWORD}@postgres:5432/planwise
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY}
    volumes:
      - /var/planwise:/var/planwise
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile.worker
    environment:
      DATABASE_URL: postgresql://planwise:${DB_PASSWORD}@postgres:5432/planwise
      REDIS_URL: redis://redis:6379/0
    volumes:
      - /var/planwise:/var/planwise
    depends_on:
      - postgres
      - redis
    command: celery -A workers worker --concurrency=4 --loglevel=info

  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - api

  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - api
      - web

volumes:
  postgres_data:
  redis_data:
```

---

## 11. Gemini 3.0 Build Instructions

### Input Format for Google AI Studio

**Prompt Template**:
```
Build a modern, enterprise-grade web UI for PlanAlign Engine, a workforce simulation and financial modeling platform.

TECHNICAL STACK:
- Frontend: React 18 + TypeScript + Material-UI 5
- Charts: Plotly.js for interactive visualizations
- State Management: React Query (server) + Zustand (client)
- Real-Time: WebSocket (Socket.IO)

CORE FEATURES TO IMPLEMENT:

1. Configuration Studio
   - Visual YAML editor with real-time validation
   - Template library for common scenarios
   - Impact preview (estimated headcount/cost)
   - Import/export YAML files

2. Simulation Control Center
   - Launch simulations with progress monitoring
   - Real-time WebSocket updates showing:
     - Current year/stage progress bars
     - Live event stream (hires, terminations, promotions)
     - Performance metrics (events/sec, memory usage)
   - Pause/resume capability

3. Interactive Analytics Dashboard
   - Workforce Growth line chart (Plotly)
   - Event Distribution stacked bar chart
   - Department Breakdown treemap
   - Compensation Distribution box plot
   - Filters: year, department, job level
   - Export to Excel/CSV

4. Batch Processing Interface
   - Multi-scenario execution queue
   - Live status grid for parallel simulations
   - Comparison matrix after completion
   - Bulk export functionality

5. Checkpoint Management
   - Timeline view of recovery points
   - One-click restore
   - Storage usage monitoring
   - Config diff viewer

API ENDPOINTS (mock these for frontend-only development):
[Include REST and WebSocket endpoint list from Section 4]

DATA SCHEMAS:
[Include TypeScript interfaces from Section 4]

DESIGN SYSTEM:
- Primary Color: #00853F (Fidelity green)
- Typography: Roboto font family
- Components: Material-UI defaults
- Responsive: Mobile-first, breakpoints at 600/960/1280/1920px

ACCESSIBILITY REQUIREMENTS:
- WCAG 2.1 AA compliant
- Keyboard navigation for all features
- Screen reader support with ARIA labels
- 4.5:1 color contrast minimum

Please generate:
1. Complete React component structure
2. API client with TypeScript interfaces
3. WebSocket integration for real-time updates
4. Plotly.js chart components
5. Material-UI themed layout
6. React Query hooks for data fetching
7. Zustand stores for client state
8. Responsive design for mobile/tablet/desktop

Focus on production-ready code with proper error handling, loading states, and user feedback.
```

### Supporting Documents to Provide

1. **API Specification** (OpenAPI/Swagger YAML)
   - Generate from Section 4.1-4.3
   - Include all endpoints with request/response schemas

2. **Component Hierarchy** (Markdown or diagram)
   - From Section 5.1
   - Show parent-child relationships

3. **Sample Data** (JSON files)
   - Mock simulation status responses
   - Sample workforce data
   - Example configuration objects

4. **Design Tokens** (JSON)
   ```json
   {
     "colors": {
       "primary": "#00853F",
       "success": "#4CAF50",
       "error": "#F44336"
     },
     "typography": {
       "fontFamily": "Roboto, sans-serif",
       "h1": "6rem",
       "body1": "1rem"
     }
   }
   ```

5. **User Stories** (Markdown)
   - For each feature, provide 2-3 user stories
   - Include acceptance criteria

### Expected Output from Gemini 3.0

- **Frontend Application**: Complete React codebase with:
  - All components in Section 5.1
  - API integration with TypeScript
  - WebSocket real-time updates
  - Plotly.js charts
  - Material-UI styling
  - Responsive layout
  - Error handling and loading states

- **API Mock Layer**: For standalone frontend development
  - Mock REST endpoints
  - Mock WebSocket server
  - Sample data generators

- **Documentation**: Generated by Gemini
  - Component documentation
  - Usage examples
  - Setup instructions

---

## Appendix A: Glossary

**Terms**:
- **Simulation**: Multi-year workforce projection with event generation
- **Scenario**: Specific configuration for a simulation (baseline, high growth, etc.)
- **Event**: Discrete workforce action (HIRE, TERMINATION, PROMOTION, RAISE)
- **Checkpoint**: Recovery point saved during simulation execution
- **Batch**: Collection of scenarios executed in parallel
- **Pipeline**: Sequential workflow stages (INITIALIZATION → REPORTING)
- **Orchestrator**: Python service managing simulation execution
- **DuckDB**: Column-oriented OLAP database for analytics
- **dbt**: Data transformation framework (SQL models)

**Acronyms**:
- **OLAP**: Online Analytical Processing
- **CRUD**: Create, Read, Update, Delete
- **JWT**: JSON Web Token
- **CORS**: Cross-Origin Resource Sharing
- **WS/WSS**: WebSocket / WebSocket Secure
- **MUI**: Material-UI
- **API**: Application Programming Interface
- **REST**: Representational State Transfer
- **DC Plan**: Defined Contribution retirement plan
- **KPI**: Key Performance Indicator

---

## Appendix B: Sample Screens (ASCII Mockups)

**Login Screen**:
```
┌────────────────────────────────────────────────┐
│                                                │
│              🏢 PlanAlign Engine              │
│         Workforce Simulation Platform          │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │ Email:    [                          ] │  │
│  │ Password: [                          ] │  │
│  │                                        │  │
│  │        [Login]       [Forgot Password] │  │
│  └──────────────────────────────────────────┘  │
│                                                │
│        Fidelity Internal Use Only              │
│               v1.0.0                           │
└────────────────────────────────────────────────┘
```

**Dashboard**:
```
┌────────────────────────────────────────────────────────────────┐
│ ≡ PlanAlign Engine                   👤 John Doe    🔔 (3)  │
├────────────────────────────────────────────────────────────────┤
│ Dashboard  Configure  Simulate  Analytics  Batch  Checkpoints  │
├────────────────────────────────────────────────────────────────┤
│ System Health: ✓ All systems operational                      │
│                                                                │
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐  │
│ │ Active Sims     │ │ Completed       │ │ Storage         │  │
│ │ 3               │ │ 47 this month   │ │ 24% used        │  │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘  │
│                                                                │
│ Recent Simulations                          [View All]         │
│ ┌────────────────────────────────────────────────────────────┐ │
│ │ Name              Status      Progress   Completed         │ │
│ │ Baseline 2025-27  Running     67%        -                 │ │
│ │ High Growth Q1    Completed   100%       2 hours ago       │ │
│ │ Conservative      Completed   100%       Yesterday         │ │
│ └────────────────────────────────────────────────────────────┘ │
│                                                                │
│ Quick Actions                                                  │
│ [▶ New Simulation] [⚙ Configure] [📊 Analyze Results]         │
└────────────────────────────────────────────────────────────────┘
```

---

## Appendix C: Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-24 | Initial specification document created |

---

**End of Specification Document**

This comprehensive specification provides Google AI Studio's Gemini 3.0 with all necessary information to generate a production-ready web UI for PlanAlign Engine. The document includes detailed functional requirements, API specifications, component architecture, design system, and implementation guidance.

For questions or clarifications, please contact the PlanAlign Engine development team.
