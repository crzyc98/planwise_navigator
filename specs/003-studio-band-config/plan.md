# Implementation Plan: Studio Band Configuration Management

**Branch**: `003-studio-band-config` | **Date**: 2025-12-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-studio-band-config/spec.md`

## Summary

Add band configuration management to PlanAlign Studio, enabling users to view and edit age/tenure band definitions through the web UI with real-time validation and "Match Census" magic buttons. This follows existing UI patterns in ConfigStudio.tsx for age distribution and compensation configuration.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend), React 18 + Vite (frontend), Pydantic v2 (validation)
**Storage**: CSV files (dbt seeds: `config_age_bands.csv`, `config_tenure_bands.csv`), Parquet (census data)
**Testing**: pytest (backend), Vitest (frontend - if needed)
**Target Platform**: Web browser (React SPA) + Linux/macOS server (FastAPI)
**Project Type**: Web application (frontend + backend)
**Performance Goals**: <5 seconds for Match Census analysis on 100K employees
**Constraints**: Must not regress existing simulation functionality, bands must pass dbt validation tests
**Scale/Scope**: Single feature addition to existing 106-model dbt project with React frontend

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Event Sourcing & Immutability** | N/A | Band configuration is seed data, not events. No immutability requirements. |
| **II. Modular Architecture** | PASS | New band_service.py will be <600 lines, single responsibility. |
| **III. Test-First Development** | PASS | Tests not explicitly required in spec, but validation logic will be tested. |
| **IV. Enterprise Transparency** | PASS | Band changes logged via config version control, audit trail in CSV commits. |
| **V. Type-Safe Configuration** | PASS | Pydantic v2 models for band data, explicit validation constraints. |
| **VI. Performance & Scalability** | PASS | <5s goal for 100K employees aligns with constitution requirements. |

**Pre-Phase 0 Status**: PASS - All gates clear, no violations.

## Project Structure

### Documentation (this feature)

```text
specs/003-studio-band-config/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI specs)
├── checklists/          # Requirements checklist
│   └── requirements.md
└── tasks.md             # Phase 2 output (already created)
```

### Source Code (repository root)

```text
# Web application structure (existing)
planalign_api/                  # FastAPI backend
├── models/
│   └── bands.py               # NEW: Pydantic models for band data
├── services/
│   └── band_service.py        # NEW: Band validation and analysis
├── routers/
│   ├── __init__.py            # MODIFY: Register bands router
│   └── bands.py               # NEW: Band configuration endpoints
└── main.py                    # MODIFY: Include bands router

planalign_studio/               # React frontend
├── services/
│   └── api.ts                 # MODIFY: Add band API types and functions
└── components/
    └── ConfigStudio.tsx       # MODIFY: Add band configuration section

dbt/seeds/                      # dbt seed files (source of truth)
├── config_age_bands.csv       # EXISTS: Modified by API
└── config_tenure_bands.csv    # EXISTS: Modified by API

tests/                          # Test files
├── unit/
│   └── test_band_service.py   # NEW: Band validation tests
└── integration/
    └── test_band_api.py       # NEW: API endpoint tests
```

**Structure Decision**: Web application pattern with existing FastAPI backend (`planalign_api/`) and React frontend (`planalign_studio/`). Band configuration is a new feature added to existing ConfigStudio component.

## Complexity Tracking

> No constitution violations detected. Table left empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | - | - |

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    PlanAlign Studio (React)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              ConfigStudio.tsx                         │  │
│  │  ┌────────────────┐  ┌────────────────┐              │  │
│  │  │  Age Bands     │  │  Tenure Bands  │              │  │
│  │  │  Table Editor  │  │  Table Editor  │              │  │
│  │  │  + Validation  │  │  + Validation  │              │  │
│  │  │  + Match Census│  │  + Match Census│              │  │
│  │  └────────────────┘  └────────────────┘              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PlanAlign API (FastAPI)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              routers/bands.py (new)                   │  │
│  │  GET  /config/bands        - Read band configs        │  │
│  │  PUT  /config/bands        - Save band configs        │  │
│  │  POST /analyze-age-bands   - Census analysis          │  │
│  │  POST /analyze-tenure-bands- Census analysis          │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              services/band_service.py (new)           │  │
│  │  - Band validation logic                              │  │
│  │  - CSV read/write operations                          │  │
│  │  - Census analysis algorithms                         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    dbt Seeds (CSV files)                     │
│  config_age_bands.csv    config_tenure_bands.csv            │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 0: Research
- Existing patterns for census analysis (analyzeAgeDistribution, analyzeCompensation)
- Band boundary optimization algorithms (percentile-based vs k-means)

### Phase 1: Design
- Data models for Band, BandConfig, BandAnalysisResult
- API contracts for 4 endpoints
- Validation rules specification

### Phase 2: Tasks (see tasks.md)
- Foundational: Pydantic models, service skeleton, validation logic
- US1 (P1): View bands in UI
- US2 (P2): Edit bands with validation
- US4/US5 (P3): Match Census magic buttons
- US6 (P4): dbt seed reload integration

## Dependencies

- **Feature 001-centralize-band-definitions**: Created the seed files and macros (COMPLETED)
- **Existing**: ConfigStudio.tsx patterns for editable tables and Match Census buttons
- **Existing**: analyzeAgeDistribution and analyzeCompensation API patterns

## Success Criteria

- SC-001: View bands without CSV file access
- SC-002: All validation errors detected before save
- SC-003: 100% pass rate on dbt band validation tests
- SC-004: Match Census completes in <5 seconds for 100K employees
- SC-005: Zero regression in simulation event counts
