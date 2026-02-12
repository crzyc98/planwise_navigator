# Data Model: ConfigStudio Component Interfaces

**Feature**: 049-refactor-config-studio
**Date**: 2026-02-12

## Overview

This document defines the TypeScript interfaces and state contracts for the refactored ConfigStudio architecture. These interfaces serve as the contracts between the Context provider, section components, and utility functions.

---

## Core Types

### FormData

The central state object holding all configuration fields. Shape is preserved exactly from the current monolith.

**Fields grouped by section**:

| Section | Fields | Types |
|---------|--------|-------|
| datasources | censusDataPath, censusDataStatus, censusRowCount, censusLastModified | string, string literal, number, string |
| simulation | name, startYear, endYear, seed, targetGrowthRate | string, number×4 |
| compensation | meritBudget, colaRate, promoIncrease, promoDistributionRange, promoBudget, promoRateMultiplier | number×6 |
| newhire | newHireStrategy, targetPercentile, newHireCompVariance, newHireAgeDistribution[], levelDistributionMode, newHireLevelDistribution[], jobLevelCompensation[], marketScenario, levelMarketAdjustments[] | mixed |
| turnover | totalTerminationRate, newHireTerminationRate | number×2 |
| dcplan | 30+ fields: eligibility, auto-enroll, match tiers, match eligibility, core contribution, escalation | mixed |
| advanced | engine, enableMultithreading, checkpointFrequency, memoryLimitGB, logLevel, strictValidation | mixed |

**Total fields**: ~65

### MatchTier / MatchTemplate

Interfaces for DC Plan match formula configuration:
- `MatchTier`: { deferralMin, deferralMax, matchRate } (all numbers)
- `MatchTemplate`: { name, tiers: MatchTier[], isSafeHarbor } (used by MATCH_TEMPLATES constant)

---

## Context Contract

### ConfigContextType

The React Context value type. This is the API surface available to all section components.

**State (read-only for sections)**:
- `formData`: FormData — current form values
- `savedFormData`: FormData | null — last-saved snapshot
- `promotionHazardConfig`: PromotionHazardConfig | null
- `savedPromotionHazardConfig`: PromotionHazardConfig | null — last-saved snapshot (for dirty-tracking)
- `bandConfig`: BandConfig | null
- `savedBandConfig`: BandConfig | null — last-saved snapshot (for dirty-tracking)
- `dirtySections`: Set\<string\> — which sections have unsaved changes
- `isDirty`: boolean — any unsaved changes exist
- `saveStatus`: 'idle' | 'saving' | 'success' | 'error'
- `saveMessage`: string
- `activeWorkspace`: Workspace (from Layout context)
- `currentScenario`: Scenario | null
- `scenarioId`: string | undefined (from URL params)

**Setters (write)**:
- `setFormData`: React.Dispatch\<SetStateAction\<FormData\>\>
- `setPromotionHazardConfig`: React.Dispatch\<SetStateAction\<PromotionHazardConfig | null\>\>
- `setBandConfig`: React.Dispatch\<SetStateAction\<BandConfig | null\>\>

**Handlers**:
- `handleChange`: (e: React.ChangeEvent\<HTMLInputElement\>) => void — generic input change
- `handleSaveConfig`: () => Promise\<void\> — save all config to API
- `inputProps`: (name: string) => { name, value, onChange } — convenience helper

---

## Section Component Contracts

Each section component receives shared state via `useConfigContext()` hook and manages its own local UI state.

### Common Pattern

```
SectionComponent
├── Uses: useConfigContext() for formData, setFormData, handleChange
├── Local state: section-specific loading/error/UI states
├── Local handlers: section-specific operations
└── Renders: section-specific JSX
```

### Section State Ownership

| Component | Local State | Context State Modified |
|-----------|-------------|----------------------|
| DataSourcesSection | uploadStatus, uploadMessage, fileInputRef | formData (census fields) |
| SimulationSection | (none) | formData (simulation fields) |
| CompensationSection | targetCompGrowth, solverStatus, solverResult, solverError | formData (compensation fields) |
| NewHireSection | matchCensusLoading/Error/Success, matchCompLoading/Error/Success, compensationAnalysis, compLookbackYears, compScaleFactor, compScaleLocal | formData (newhire fields) |
| PromotionHazardEditor | promotionHazardLoading, promotionHazardError, promotionHazardValidationErrors | promotionHazardConfig |
| SegmentationSection | bandConfigLoading, bandConfigError, bandValidationErrors, ageBandAnalysis, ageBandAnalyzing, tenureBandAnalysis, tenureBandAnalyzing | bandConfig |
| TurnoverSection | (none) | formData (turnover fields) |
| DCPlanSection | (none beyond inline handlers) | formData (dcplan fields) |
| AdvancedSection | dbDeleteStatus, dbDeleteMessage | formData (advanced fields) |

### Modal Contracts

| Component | Props from Shell | Context State Modified |
|-----------|-----------------|----------------------|
| TemplateModal | show, onClose, templates, templatesLoading | formData (all fields) |
| CopyScenarioModal | show, onClose, scenarios, scenariosLoading | formData, promotionHazardConfig, bandConfig |

---

## Utility Function Contracts

### buildConfigPayload

**Input**: `(formData: FormData, promotionHazardConfig: PromotionHazardConfig | null, bandConfig: BandConfig | null)`

**Output**: API-shaped config object with:
- Percentage fields converted to decimals (÷100)
- Frontend field names mapped to API field names
- Nested structure matching API expectations (simulation, workforce, data_sources, compensation, new_hire, dc_plan, advanced, promotion_hazard, age_bands, tenure_bands)

### calculateMatchCap

**Input**: `(tiers: MatchTier[])`
**Output**: `number` — sum of (tier_width × match_rate) across all tiers

---

## State Lifecycle

1. **Initial Load**: ConfigProvider useEffect loads config from workspace `base_config` → populates `formData`
2. **Scenario Load**: If `scenarioId` present, useEffect loads scenario `config_overrides` → overwrites `formData`
3. **Seed Config Load**: useEffect loads band config + promotion hazard from API → populates `bandConfig`, `promotionHazardConfig`
4. **Saved Snapshot**: After initial load, `savedFormData` is set to a deep copy of `formData`
5. **Dirty Detection**: `dirtySections` useMemo compares `formData` vs `savedFormData` field-by-field per section
6. **Save**: `handleSaveConfig` builds payload, validates, calls API, updates `savedFormData` snapshot
