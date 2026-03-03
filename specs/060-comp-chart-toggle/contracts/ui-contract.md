# UI Contract: Compensation Chart Toggle

**Feature**: 060-comp-chart-toggle
**Date**: 2026-03-03

## Component: Compensation Chart Card

### Toggle Control

**Location**: Inline with chart title, right-aligned or immediately after title text

**Behavior**:
| State | Label | Visual |
|-------|-------|--------|
| Active (selected) | Filled background (fidelity-green), white text |
| Inactive | White/transparent background, gray text, border |

**Options**:
| Value | Label | Tooltip |
|-------|-------|---------|
| `average` | "Average" | "Show average compensation per employee" |
| `total` | "Total" | "Show total compensation across all employees" |

### Chart Title Format

**Template**: `{Metric Label} - All Employees ({Unit}) — CAGR: {cagr_pct}%`

| Toggle | Title Example |
|--------|--------------|
| Average | "Average Compensation - All Employees ($K) — CAGR: 3.21%" |
| Total | "Total Compensation - All Employees ($M) — CAGR: 5.14%" |
| Average (1 year) | "Average Compensation - All Employees ($K)" |
| Total (1 year) | "Total Compensation - All Employees ($M)" |

### Y-Axis Formatting

| Toggle | Scale | Tick Format | Example |
|--------|-------|-------------|---------|
| Average | Thousands | `$XXK` | "$125K" |
| Total (< $1M max) | Thousands | `$XXK` | "$850K" |
| Total (>= $1M max) | Millions | `$X.XM` | "$125.3M" |

### Tooltip Formatting

| Toggle | Format | Example |
|--------|--------|---------|
| Average | `$XXK` | "$125K" |
| Total (< $1M) | `$XXK` | "$850K" |
| Total (>= $1M) | `$X.XM` | "$125.3M" |

### Legend

| Toggle | Legend Label |
|--------|------------|
| Average | "Avg Compensation" |
| Total | "Total Compensation" |

## API Contract (No Changes)

The existing `GET /api/scenarios/{scenarioId}/results` endpoint already returns all required data. No backend changes needed.

**Required fields from `workforce_progression[]`**:
- `avg_compensation` (number, dollars)
- `total_compensation` (number, dollars)

**Required fields from `cagr_metrics[]`**:
- Entry with `metric === "Average Compensation"` → `cagr_pct`
- Entry with `metric === "Total Compensation"` → `cagr_pct`
