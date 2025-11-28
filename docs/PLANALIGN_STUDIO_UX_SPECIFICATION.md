# PlanAlign Studio - UI/UX Specification

**Version**: 1.0.0
**Status**: Implementation Complete (E081)
**Last Updated**: 2025-11-25

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Vision & Goals](#2-product-vision--goals)
3. [User Personas](#3-user-personas)
4. [Information Architecture](#4-information-architecture)
5. [User Flows & Journeys](#5-user-flows--journeys)
6. [Screen-by-Screen Specifications](#6-screen-by-screen-specifications)
7. [Component Library](#7-component-library)
8. [Visual Design System](#8-visual-design-system)
9. [Interaction Patterns](#9-interaction-patterns)
10. [Technical Implementation](#10-technical-implementation)
11. [API Integration](#11-api-integration)
12. [Future Roadmap](#12-future-roadmap)

---

## 1. Executive Summary

**PlanAlign Studio** is a modern React-based web application that provides a graphical user interface for Fidelity's workforce simulation and benefits modeling engine. It replaces command-line workflows with an intuitive visual interface for HR analysts, benefits administrators, and financial planners.

### Key Capabilities

- **Workspace Management**: Organize simulation projects into isolated workspaces
- **Scenario Configuration**: Visual editors for simulation parameters
- **Real-time Simulation**: Execute simulations with live progress tracking
- **Analytics Dashboard**: Interactive charts and KPI visualization
- **Batch Processing**: Run multiple scenarios in parallel with comparison tools
- **Export & Reporting**: Generate Excel/CSV reports for stakeholder review

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | React 18 + TypeScript | Component-based UI |
| Styling | TailwindCSS | Utility-first CSS framework |
| Charts | Recharts | Data visualization |
| Routing | React Router v6 | SPA navigation |
| State | React Context + Hooks | Local state management |
| Real-time | WebSockets | Live simulation telemetry |
| Backend | FastAPI (Python) | REST API + WebSocket server |
| Build | Vite | Fast development server |

---

## 2. Product Vision & Goals

### Vision Statement

> Enable Fidelity's workforce planning teams to model complex benefit scenarios through an intuitive, visual interface that abstracts technical complexity while maintaining enterprise-grade accuracy and auditability.

### Primary Goals

1. **Reduce Time-to-Insight**: Cut simulation setup time from hours (CLI) to minutes (GUI)
2. **Democratize Access**: Enable non-technical users to run simulations
3. **Improve Collaboration**: Shareable workspaces and exportable reports
4. **Maintain Accuracy**: Same underlying engine with full audit trail
5. **Enterprise Ready**: Scalable architecture supporting concurrent users

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Task Completion Rate | >95% | Users complete simulation without errors |
| Time to First Simulation | <5 min | New user to results |
| Configuration Accuracy | 100% | GUI config matches CLI config |
| User Satisfaction | >4.5/5 | Post-task survey |

---

## 3. User Personas

### Persona 1: Sarah - HR Benefits Analyst

**Demographics**: 35, 8 years experience, intermediate Excel skills

**Goals**:
- Model different 401(k) match formulas
- Compare participation rates across scenarios
- Generate reports for executive review

**Pain Points**:
- CLI commands are intimidating
- Needs help interpreting simulation outputs
- Wants side-by-side scenario comparison

**Usage Pattern**: Weekly batch runs, monthly deep-dives

---

### Persona 2: Michael - Financial Planner

**Demographics**: 42, CFA, advanced analytics skills

**Goals**:
- Project workforce costs over 5-year horizons
- Model acquisition/growth scenarios
- Validate budget assumptions

**Pain Points**:
- Needs granular control over parameters
- Wants raw data export for custom analysis
- Performance matters for large simulations

**Usage Pattern**: Daily iterations during planning cycles

---

### Persona 3: Jennifer - HR Technology Lead

**Demographics**: 38, technical background, manages team

**Goals**:
- Ensure system reliability and performance
- Train team members on the tool
- Troubleshoot failed simulations

**Pain Points**:
- Needs visibility into system health
- Wants detailed error messages
- Requires audit logs for compliance

**Usage Pattern**: Administrative, troubleshooting

---

## 4. Information Architecture

### Site Map

```
PlanAlign Studio
├── Dashboard (/)
│   ├── System Status Cards
│   ├── Recent Simulations
│   └── Quick Actions
├── Configuration (/config)
│   ├── Scenarios Tab
│   ├── Data Sources Tab
│   ├── Simulation Settings Tab
│   ├── Compensation Tab
│   ├── New Hire Strategy Tab
│   ├── Workforce & Turnover Tab
│   ├── Hiring Plan Tab
│   ├── DC Plan Tab
│   └── Advanced Settings Tab
├── Simulate (/simulate)
│   ├── Simulation Control
│   ├── Performance Telemetry
│   ├── Event Stream
│   └── Simulation History
├── Analytics (/analytics)
│   ├── KPI Summary
│   ├── Workforce Charts
│   ├── Event Distribution
│   └── Compensation Trends
├── Batch Processing (/batch)
│   ├── Batch List View
│   ├── Create New Batch
│   ├── Batch Details/Monitor
│   └── Comparison Matrix
└── Workspace Manager (/workspaces)
    ├── Workspace Grid
    ├── Create/Edit Modal
    └── Search/Filter
```

### Navigation Model

**Primary Navigation** (Left Sidebar - Always Visible):
- Dashboard
- Configuration
- Simulate
- Analytics
- Batch Processing

**Secondary Navigation** (Top Header):
- Workspace Selector (Global Context)
- Notifications
- Settings
- Help

**Contextual Navigation**:
- Breadcrumbs within Configuration tabs
- Back arrows in detail views

---

## 5. User Flows & Journeys

### Journey 1: First-Time User Setup

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Landing   │────▶│  Create First    │────▶│    Dashboard    │
│   (Empty)   │     │    Workspace     │     │   (Populated)   │
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │
                    Modal: Name + Description
```

**Steps**:
1. User arrives at empty state (no workspaces)
2. System prompts to create first workspace
3. User enters name and description
4. Workspace created via API
5. Redirect to Dashboard with new workspace active

**Error States**:
- API unavailable → "Failed to load workspaces" + Retry button
- Creation fails → Inline error message in modal

---

### Journey 2: Create and Run Simulation

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌────────────┐
│Dashboard │───▶│Configuration │───▶│   Simulate    │───▶│  Analytics │
│          │    │  (Scenarios) │    │  (Run + Wait) │    │ (Results)  │
└──────────┘    └──────────────┘    └───────────────┘    └────────────┘
                      │
               Create Scenario
               Configure Params
               Save Config
```

**Steps**:
1. From Dashboard, click "New Simulation" or navigate to Configuration
2. Create a new scenario (name + description)
3. Configure simulation parameters across tabs:
   - Simulation Settings (years, seed, growth rate)
   - Compensation (merit, COLA, promotions)
   - Workforce & Turnover (termination rates)
   - DC Plan (401k settings)
   - Advanced (engine, threading)
4. Save configuration
5. Navigate to Simulate page
6. Select scenario from dropdown
7. Click "Start Simulation"
8. Monitor real-time progress via WebSocket
9. On completion, navigate to Analytics
10. View results, export report

**Happy Path Duration**: 5-10 minutes

---

### Journey 3: Batch Comparison Analysis

```
┌────────────┐    ┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│   Config   │───▶│ Batch Processing│───▶│   Monitor    │───▶│  Compare    │
│(3 Scenarios)│   │  (Create Batch) │    │   Progress   │    │   Matrix    │
└────────────┘    └─────────────────┘    └──────────────┘    └─────────────┘
```

**Steps**:
1. Create 3+ scenarios in Configuration
2. Navigate to Batch Processing
3. Click "Create New Batch"
4. Enter batch name
5. Select execution mode (Parallel/Sequential)
6. Select export format (Excel/CSV)
7. Check scenarios to include
8. Click "Launch Batch Execution"
9. Monitor individual scenario progress
10. On completion, view Comparison Matrix
11. Export combined report

---

### Journey 4: Troubleshooting Failed Simulation

```
┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌─────────────┐
│  Simulate    │───▶│ Error Display │───▶│   Config     │───▶│   Re-run    │
│ (Fails)      │    │  (Details)    │    │  (Adjust)    │    │ (Success)   │
└──────────────┘    └───────────────┘    └──────────────┘    └─────────────┘
```

**Steps**:
1. Simulation fails during execution
2. Error message displayed with details
3. User navigates to Configuration
4. Adjusts problematic parameters (e.g., memory limit)
5. Saves updated config
6. Returns to Simulate
7. Re-runs simulation successfully

---

## 6. Screen-by-Screen Specifications

### 6.1 Dashboard

**Purpose**: System overview, quick access to common actions, recent activity

**Layout**: Grid-based responsive layout

```
┌────────────────────────────────────────────────────────────────────┐
│ [Sidebar]                          [Header: Workspace + Actions]   │
├────────────┬───────────────────────────────────────────────────────┤
│            │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│ Dashboard  │  │ Active   │ │  Total   │ │ Storage  │ │  Thread  │ │
│ Config     │  │  Sims    │ │Workspaces│ │   Used   │ │  Count   │ │
│ Simulate   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│ Analytics  │                                                       │
│ Batch      │  ┌─────────────────────────────┐ ┌─────────────────┐ │
│            │  │    Recent Simulations       │ │  Quick Actions  │ │
│            │  │    - Scenario Name          │ │  [New Sim]      │ │
│            │  │    - Status Badge           │ │  [Batch Run]    │ │
│            │  │    - Click to navigate      │ │  [Compare]      │ │
│            │  └─────────────────────────────┘ └─────────────────┘ │
└────────────┴───────────────────────────────────────────────────────┘
```

**Components**:
- **StatCard** (x4): Displays KPI with icon, value, trend indicator
- **Recent Simulations List**: Clickable rows showing scenario name, status, description
- **Quick Actions Panel**: Primary CTA buttons for common tasks
- **Alert Banner**: System maintenance or warning notices

**Data Sources**:
- `GET /api/system/status` → Stats cards
- `GET /api/workspaces/{id}/scenarios` → Recent list

---

### 6.2 Configuration Studio

**Purpose**: Visual parameter editor for simulation scenarios

**Layout**: Two-column with sidebar navigation

```
┌────────────────────────────────────────────────────────────────────┐
│                    [Save Config]  [Load Template]                  │
├────────────┬───────────────────────────────────────────────────────┤
│ Scenarios  │  ┌─────────────────────────────────────────────────┐ │
│ Data Source│  │  Section Title + Description                    │ │
│ Simulation │  │                                                 │ │
│ Compens... │  │  ┌─────────────┐  ┌─────────────┐              │ │
│ New Hire   │  │  │ Input Field │  │ Input Field │              │ │
│ Turnover   │  │  │  + Label    │  │  + Label    │              │ │
│ Hiring     │  │  │  + Helper   │  │  + Helper   │              │ │
│ DC Plan    │  │  └─────────────┘  └─────────────┘              │ │
│ Advanced   │  │                                                 │ │
│            │  │  [Validation Warning Box]                       │ │
├────────────┤  │                                                 │ │
│ Impact     │  └─────────────────────────────────────────────────┘ │
│ Preview    │                                                       │
│ (Sidebar)  │                                                       │
└────────────┴───────────────────────────────────────────────────────┘
```

**Tabs/Sections**:

1. **Scenarios**: Create/delete scenarios, list existing
2. **Data Sources**: Census file upload, path configuration
3. **Simulation Settings**: Name, years, seed, growth rate
4. **Compensation**: Merit budget, COLA, promotion increases
5. **New Hire Strategy**: Percentile vs fixed, variance, bonuses
6. **Workforce & Turnover**: Termination rates, tenure bands
7. **Hiring Plan**: Department-level growth targets table
8. **DC Plan**: 401(k) eligibility, match formula, vesting
9. **Advanced**: Engine selection, threading, logging

**Interaction Patterns**:
- Tab navigation persists scroll position
- Unsaved changes prompt on navigation
- Real-time validation with inline errors
- Impact Preview sidebar updates on change

---

### 6.3 Simulation Control

**Purpose**: Execute simulations with real-time monitoring

**Layout**: Two-column with event stream

```
┌────────────────────────────────────────────────────────────────────┐
│ Simulation Control Center           [Start/Pause/Stop Buttons]    │
├───────────────────────────────────────────┬────────────────────────┤
│  Workspace: Q1 2025 Planning              │                        │
│                                           │   Event Stream         │
│  [Scenario Dropdown]                      │   ┌──────────────────┐ │
│                                           │   │ [HIRE] EMP_001   │ │
│  ┌─────────────────────────────────────┐  │   │ [TERM] EMP_042   │ │
│  │ Progress Bar: 67%                   │  │   │ [PROMO] EMP_108  │ │
│  │ Year 2 of 3                         │  │   │ ...              │ │
│  └─────────────────────────────────────┘  │   └──────────────────┘ │
│                                           │                        │
│  [INIT][FOUND][EVENT][STATE][VAL][RPT]   │                        │
│                                           │                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐  │                        │
│  │Throughput│ │  Memory  │ │ Pressure │  │                        │
│  │ 125/s    │ │  512 MB  │ │   LOW    │  │                        │
│  └──────────┘ └──────────┘ └──────────┘  │                        │
├───────────────────────────────────────────┴────────────────────────┤
│                     Simulation History Table                       │
│  Scenario | Status | Last Run | Run ID | Actions                  │
└────────────────────────────────────────────────────────────────────┘
```

**Components**:
- **Control Header**: Scenario selector, action buttons
- **Progress Section**: Overall progress bar, year indicator
- **Stage Indicators**: Six workflow stages with current highlight
- **Telemetry Cards**: Throughput, memory, pressure, elapsed time
- **Event Stream**: Real-time log of generated events (WebSocket)
- **History Table**: Past runs with status, timestamps, re-run actions

**WebSocket Integration**:
- Connect to `WS /ws/simulation/{run_id}`
- Receive `SimulationTelemetry` messages every ~1 second
- Update progress, metrics, event stream in real-time

---

### 6.4 Analytics Dashboard

**Purpose**: Visualize simulation results with interactive charts

**Layout**: KPI cards + chart grid

```
┌────────────────────────────────────────────────────────────────────┐
│ Analytics & Insights      [Workspace] [Scenario] [Refresh] [Export]│
├────────────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│ │Final HC  │ │  CAGR    │ │ Period   │ │  401k    │               │
│ │  1,061   │ │   3.1%   │ │ 3 Years  │ │   78%    │               │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
│                                                                    │
│ [Scenario Info Banner]                                             │
│                                                                    │
│ ┌─────────────────────────────┐ ┌─────────────────────────────┐   │
│ │ Workforce Headcount         │ │ Event Distribution          │   │
│ │ [LINE CHART]                │ │ [STACKED BAR CHART]         │   │
│ │                             │ │                             │   │
│ └─────────────────────────────┘ └─────────────────────────────┘   │
│                                                                    │
│ ┌─────────────────────────────┐ ┌─────────────────────────────┐   │
│ │ Avg Compensation            │ │ Event Types (Total)         │   │
│ │ [LINE CHART]                │ │ [DONUT CHART]               │   │
│ │                             │ │                             │   │
│ └─────────────────────────────┘ └─────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

**Components**:
- **KPICard** (x4): Final headcount, CAGR, period, participation rate
- **Scenario Banner**: Name, description, last run date
- **Line Charts**: Headcount over time, avg compensation trend
- **Bar Chart**: Stacked event distribution by year
- **Pie/Donut Chart**: Event type breakdown

**Data Sources**:
- `GET /api/scenarios/{id}/results` → All chart data

---

### 6.5 Batch Processing

**Purpose**: Run multiple scenarios, compare results

**Layout**: List/Create/Details views

**List View**:
```
┌────────────────────────────────────────────────────────────────────┐
│ Batch Processing                              [Create New Batch]   │
├────────────────────────────────────────────────────────────────────┤
│ Active Execution (if running)                                      │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ Batch Name: Q1 Planning     [Monitor]                          │ │
│ │ ✓ Baseline (100%)  ◉ High Growth (67%)  ○ Conservative (0%)   │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
│ Batch History [All | Running | Completed]                          │
│ ┌──────────────────────────────────────────────────────────────┐   │
│ │ Name       | Status    | Scenarios | Submitted | Duration    │   │
│ │ Q1 Set A   | Completed |     3     | Nov 24    | 12m 34s     │   │
│ │ Q1 Set B   | Completed |     2     | Nov 23    | 8m 12s      │   │
│ └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

**Create View**:
```
┌────────────────────────────────────────────────────────────────────┐
│ ← Back                     Create New Batch                        │
├────────────────────────────────────────────────────────────────────┤
│ Batch Name: [________________________]                             │
│                                                                    │
│ Execution Mode: [Parallel] [Sequential]                            │
│ Export Format:  [Excel]    [CSV]                                   │
│                                                                    │
│ Select Configurations:                                             │
│ ┌──────────────────┐ ┌──────────────────┐                         │
│ │ ☑ Baseline       │ │ ☑ High Growth    │                         │
│ │   2025-2027      │ │   2025-2028      │                         │
│ └──────────────────┘ └──────────────────┘                         │
│                                                                    │
│                                    [Launch Batch Execution]        │
└────────────────────────────────────────────────────────────────────┘
```

**Details/Comparison View**:
```
┌────────────────────────────────────────────────────────────────────┐
│ ← Back                    Q1 Planning Scenarios      [Export]      │
├────────────────────────────────────────────────────────────────────┤
│ Status: COMPLETED          Progress: [████████████████████] 100%   │
│                                                                    │
│ Scenario Execution Status:                                         │
│ ┌──────────────────────────────────────────────────────────────┐   │
│ │ █ Baseline        Processing Complete                    ✓   │   │
│ │ █ High Growth     Processing Complete                    ✓   │   │
│ │ █ Conservative    Processing Complete                    ✓   │   │
│ └──────────────────────────────────────────────────────────────┘   │
│                                                                    │
│ Comparison Matrix:                                                 │
│ ┌───────────────────────────────────────────────────────────────┐  │
│ │ Metric              │ Baseline │ High Growth │ Conservative  │  │
│ │ Final Headcount     │   1,061  │    1,320    │     1,015     │  │
│ │ CAGR                │    3.1%  │    12.5%    │      0.8%     │  │
│ │ Total Payroll       │ $142.5M  │   $178.2M   │    $135.0M    │  │
│ └───────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

### 6.6 Workspace Manager

**Purpose**: CRUD operations for workspaces

**Layout**: Searchable card grid

```
┌────────────────────────────────────────────────────────────────────┐
│ Manage Workspaces                         [Create New Workspace]   │
├────────────────────────────────────────────────────────────────────┤
│ [🔍 Search workspaces...]                                          │
│                                                                    │
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐    │
│ │ Q1 2025 Planning │ │ Tech Restructure │ │    + Create      │    │
│ │ [Active Badge]   │ │                  │ │    Workspace     │    │
│ │                  │ │                  │ │                  │    │
│ │ 2 Scenarios      │ │ 1 Scenario       │ │                  │    │
│ │ Last: 2 days ago │ │ Last: 1 week ago │ │                  │    │
│ │                  │ │                  │ │                  │    │
│ │ [Edit] [Delete]  │ │ [Edit] [Switch→] │ │                  │    │
│ └──────────────────┘ └──────────────────┘ └──────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

**Components**:
- **Search Bar**: Filter by name or description
- **Workspace Card**: Name, description, scenario count, last run, actions
- **Active Badge**: Indicates currently selected workspace
- **Create Modal**: Name + description form

---

## 7. Component Library

### Core Components

| Component | Purpose | Props |
|-----------|---------|-------|
| `NavItem` | Sidebar navigation link | `to`, `icon`, `label` |
| `StatCard` | KPI display card | `title`, `value`, `subtext`, `trend`, `icon`, `color` |
| `KPICard` | Analytics metric card | `title`, `value`, `subtext`, `trend`, `icon`, `color`, `loading` |
| `InputField` | Form input with label | `label`, `name`, `type`, `width`, `suffix`, `helper`, `step`, `min` |

### Layout Components

| Component | Purpose | Usage |
|-----------|---------|-------|
| `Layout` | Main app shell | Wraps all routes, provides workspace context |
| `Outlet` | React Router outlet | Renders child routes |

### Feedback Components

| Component | Purpose | Usage |
|-----------|---------|-------|
| `Loader2` | Spinning loader | Loading states |
| `AlertCircle` | Error indicator | Error messages |
| `CheckCircle` | Success indicator | Completion states |

### Chart Components (Recharts)

| Component | Purpose | Data Shape |
|-----------|---------|------------|
| `LineChart` | Time series | `[{year, value}]` |
| `BarChart` | Categorical comparison | `[{year, category1, category2}]` |
| `PieChart` | Distribution | `[{name, value}]` |

---

## 8. Visual Design System

### Color Palette

| Name | Hex | Usage |
|------|-----|-------|
| Fidelity Green (Primary) | `#00853F` | Primary buttons, active states, success |
| Fidelity Dark | `#006B32` | Hover states |
| Secondary Green | `#4CAF50` | Secondary actions |
| Accent Orange | `#FF9800` | Warnings, highlights |
| Danger Red | `#F44336` | Errors, destructive actions |
| Gray 50 | `#F9FAFB` | Background |
| Gray 100 | `#F3F4F6` | Card backgrounds |
| Gray 200 | `#E5E7EB` | Borders |
| Gray 500 | `#6B7280` | Secondary text |
| Gray 900 | `#111827` | Primary text |

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| H1 | System Sans | 24px | Bold (700) |
| H2 | System Sans | 20px | Bold (700) |
| H3 | System Sans | 18px | Semibold (600) |
| Body | System Sans | 14px | Regular (400) |
| Small | System Sans | 12px | Regular (400) |
| Caption | System Sans | 10px | Medium (500) |
| Mono | System Mono | 12px | Regular (400) |

### Spacing Scale

```
4px  (space-1)  - Tight spacing
8px  (space-2)  - Component internal
12px (space-3)  - Between elements
16px (space-4)  - Section padding
24px (space-6)  - Card padding
32px (space-8)  - Major sections
```

### Border Radius

| Size | Value | Usage |
|------|-------|-------|
| sm | 4px | Buttons, inputs |
| md | 8px | Cards, modals |
| lg | 12px | Large panels |
| full | 9999px | Pills, badges |

### Shadows

```css
shadow-sm: 0 1px 2px rgba(0,0,0,0.05)
shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)
shadow-md: 0 4px 6px rgba(0,0,0,0.1)
shadow-lg: 0 10px 15px rgba(0,0,0,0.1)
```

---

## 9. Interaction Patterns

### Navigation

- **Sidebar**: Always visible, fixed width (256px)
- **Active State**: Green background, white text
- **Hover State**: Gray background, green text
- **Workspace Switcher**: Dropdown in header, persists selection

### Forms

- **Validation**: Real-time inline validation
- **Save**: Explicit save button, no auto-save
- **Unsaved Changes**: Prompt on navigation away
- **Loading State**: Button shows spinner, disabled state

### Modals

- **Backdrop**: Semi-transparent black with blur
- **Animation**: Fade in (150ms)
- **Close**: Click backdrop, X button, Escape key
- **Focus Trap**: Tab cycles within modal

### Tables

- **Hover**: Row highlight on hover
- **Actions**: Right-aligned action buttons
- **Sorting**: Click column header (not yet implemented)
- **Pagination**: Not yet implemented

### Real-time Updates

- **WebSocket**: Auto-reconnect on disconnect
- **Progress**: Smooth transitions (500ms)
- **Event Stream**: Auto-scroll, max 100 items

### Loading States

- **Initial Load**: Full-page spinner
- **Data Fetch**: Skeleton placeholders
- **Actions**: Button spinner, disabled state

### Error Handling

- **API Errors**: Toast notification + inline message
- **Form Errors**: Inline below field
- **System Errors**: Full-page error state with retry

---

## 10. Technical Implementation

### Project Structure

```
planalign_studio/
├── index.html              # HTML entry point
├── index.tsx               # React entry point
├── App.tsx                 # Router configuration
├── types.ts                # TypeScript interfaces
├── constants.ts            # Mock data, colors, app name
├── vite.config.ts          # Build configuration
├── .env.local              # Environment variables
├── components/
│   ├── Layout.tsx          # Main shell + workspace context
│   ├── Dashboard.tsx       # Home page
│   ├── ConfigStudio.tsx    # Configuration editor
│   ├── SimulationControl.tsx # Run simulations
│   ├── AnalyticsDashboard.tsx # Results visualization
│   ├── BatchProcessing.tsx # Batch management
│   └── WorkspaceManager.tsx # Workspace CRUD
└── services/
    ├── api.ts              # REST API client
    ├── websocket.ts        # WebSocket hooks
    ├── mockService.ts      # Mock data (deprecated)
    └── index.ts            # Barrel exports
```

### State Management

**Workspace Context** (Layout.tsx):
```typescript
interface LayoutContextType {
  activeWorkspace: Workspace;
  setActiveWorkspace: (ws: Workspace) => void;
  workspaces: Workspace[];
  addWorkspace: (ws: Workspace) => void;
  updateWorkspace: (id: string, updates: Partial<Workspace>) => void;
  deleteWorkspace: (id: string) => void;
}
```

**Passed via React Router Outlet Context**:
```typescript
const { activeWorkspace } = useOutletContext<LayoutContext>();
```

### WebSocket Integration

```typescript
// services/websocket.ts
export function useSimulationSocket(runId: string | null) {
  const [telemetry, setTelemetry] = useState<SimulationTelemetry | null>(null);
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([]);

  useEffect(() => {
    if (!runId) return;

    const ws = new WebSocket(`${WS_URL}/ws/simulation/${runId}`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setTelemetry(data);
      setRecentEvents(data.recent_events);
    };

    return () => ws.close();
  }, [runId]);

  return { telemetry, recentEvents };
}
```

### Build & Development

```bash
# Development server (hot reload)
cd planalign_studio
npm run dev
# → http://localhost:5173

# Production build
npm run build
# → dist/

# Type checking
npm run typecheck
```

### Environment Variables

```env
# .env.local
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

---

## 11. API Integration

### Backend Architecture

```
planalign_api/
├── main.py                 # FastAPI app
├── config.py               # APISettings
├── routers/
│   ├── system.py           # /api/health, /api/system/status
│   ├── workspaces.py       # /api/workspaces CRUD
│   ├── scenarios.py        # /api/workspaces/{id}/scenarios CRUD
│   ├── simulations.py      # /api/scenarios/{id}/run
│   ├── batch.py            # /api/workspaces/{id}/run-all
│   └── comparison.py       # /api/workspaces/{id}/comparison
├── services/
│   ├── simulation_service.py
│   ├── comparison_service.py
│   └── telemetry_service.py
├── storage/
│   └── workspace_storage.py # Filesystem operations
└── websocket/
    ├── manager.py          # ConnectionManager
    └── handlers.py         # WebSocket endpoints
```

### API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/system/status` | System metrics |
| GET | `/api/config/defaults` | Default configuration |
| GET/POST | `/api/workspaces` | List/Create workspaces |
| GET/PUT/DELETE | `/api/workspaces/{id}` | Workspace CRUD |
| GET/POST | `/api/workspaces/{id}/scenarios` | Scenario list/create |
| POST | `/api/scenarios/{id}/run` | Start simulation |
| GET | `/api/scenarios/{id}/results` | Get results |
| WS | `/ws/simulation/{run_id}` | Real-time telemetry |

### Storage Format

```
~/.planalign/workspaces/
├── {workspace-uuid}/
│   ├── workspace.json          # Metadata
│   ├── base_config.yaml        # Base configuration
│   └── scenarios/
│       ├── {scenario-uuid}/
│       │   ├── scenario.json   # Metadata
│       │   ├── config.yaml     # Overrides
│       │   ├── simulation.duckdb  # Results
│       │   └── results/
│       │       ├── results.xlsx
│       │       └── results.csv
```

---

## 12. Future Roadmap

### Phase 2: Enhanced Analytics (Planned)

- [ ] Custom chart builder
- [ ] Dashboard templates
- [ ] Saved views/filters
- [ ] PDF report generation
- [ ] Drill-down capabilities

### Phase 3: Collaboration (Planned)

- [ ] User authentication (JWT/OAuth)
- [ ] Role-based access control
- [ ] Workspace sharing
- [ ] Comments/annotations
- [ ] Audit log viewer

### Phase 4: Advanced Configuration (Planned)

- [ ] Visual drag-drop scenario builder
- [ ] Parameter sensitivity analysis
- [ ] Monte Carlo simulation support
- [ ] Custom event type definitions
- [ ] Import/export configuration templates

### Phase 5: Enterprise Features (Planned)

- [ ] Redis-backed session storage
- [ ] Celery background workers
- [ ] PostgreSQL metadata storage
- [ ] API rate limiting
- [ ] Multi-tenant architecture
- [ ] SSO integration

### Known Limitations (Current)

1. **No Authentication**: Single-user mode only
2. **In-Memory State**: Simulation state lost on server restart
3. **Local Storage**: Filesystem-based, not scalable
4. **No Dark Mode**: Light theme only (toggle exists but non-functional)
5. **Limited Mobile**: Not optimized for small screens
6. **No Undo**: Configuration changes are immediate

---

## Appendix A: Mockup Wireframes

### Dashboard Wireframe

```
┌─────────────────────────────────────────────────────────────┐
│ [Logo] PlanAlign Engine                     [🔔] [⚙]       │
├────────────┬────────────────────────────────────────────────┤
│            │  Dashboard                                     │
│ ○ Dash     │  System overview and quick actions.            │
│ ○ Config   │                                                │
│ ○ Simulate │  [====] [====] [====] [====]  ← Stat Cards    │
│ ○ Analyt   │                                                │
│ ○ Batch    │  ┌────────────────────┐ ┌──────────────────┐  │
│            │  │ Recent Simulations │ │ Quick Actions    │  │
│            │  │ ░░░░░░░░░░░░░░░░░░ │ │ [▶ New Sim]      │  │
│            │  │ ░░░░░░░░░░░░░░░░░░ │ │ [▶ Batch Run]    │  │
│            │  │ ░░░░░░░░░░░░░░░░░░ │ │ [▶ Compare]      │  │
│            │  └────────────────────┘ └──────────────────┘  │
└────────────┴────────────────────────────────────────────────┘
```

### Configuration Wireframe

```
┌─────────────────────────────────────────────────────────────┐
│ Configuration Studio           [Load Template] [Save Config]│
├────────────┬────────────────────────────────────────────────┤
│            │                                                │
│ Scenarios  │  Simulation Parameters                         │
│ Data Source│  ─────────────────────                         │
│ Simulation │  Define the temporal scope and settings.       │
│ Compens... │                                                │
│ New Hire   │  Scenario Name     [___________________]       │
│ Turnover   │                                                │
│ Hiring     │  Start Year  [2025]    End Year  [2027]        │
│ DC Plan    │                                                │
│ Advanced   │  Random Seed [42]                              │
│            │                                                │
│ ┌────────┐ │  ⚠ End year must be greater than Start year.  │
│ │Impact  │ │                                                │
│ │Preview │ │                                                │
│ └────────┘ │                                                │
└────────────┴────────────────────────────────────────────────┘
```

---

## Appendix B: Accessibility Considerations

### Current Implementation

- Semantic HTML elements
- Focusable interactive elements
- Color contrast meets WCAG AA
- Keyboard navigation (partial)

### Planned Improvements

- [ ] ARIA labels for complex widgets
- [ ] Screen reader testing
- [ ] Focus management in modals
- [ ] Skip navigation links
- [ ] High contrast mode

---

## Appendix C: Performance Considerations

### Current Optimizations

- Vite for fast dev server and optimized builds
- React.memo for expensive components (planned)
- Lazy loading of routes (planned)
- WebSocket for efficient real-time updates

### Monitoring

- Browser DevTools Performance tab
- React DevTools Profiler
- Backend: FastAPI /api/system/status

---

*Document maintained by the PlanAlign Engine team. For questions, contact the development team.*
