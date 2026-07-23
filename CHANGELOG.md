# Changelog

All notable changes to Fidelity PlanAlign Engine will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Process

This changelog is **generated at release time, not hand-curated per PR**. Commit messages follow conventional commits (`feat:`/`fix:`/`chore:` with PR numbers), so a release section is drafted from git history and then lightly grouped/condensed:

```bash
# Draft the next release section from commits since the last release tag
git log --no-merges --format='- %s' v2.1.0..HEAD

# Then: bump _version.py + pyproject.toml, fold the draft into a new
# ## [X.Y.Z] section below, commit, and tag:
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

Versioning semantics (SemVer) and the full bump procedure live in [docs/VERSIONING_GUIDE.md](docs/VERSIONING_GUIDE.md).

## Unreleased

### Changed

- **Feature 122 — state pipeline redesign:** managed API/Studio attempts now use
  immutable run-specific databases and atomically retain the latest successful result
  while a new run is active. Scenario reads expose result/active run consistency
  headers, and Studio shows one global in-progress warning.
- Normalized the SQL/dbt event and workforce-state DAG: current-year events publish
  once, workforce state has one authoritative accumulator, benefit calculations use
  separated workforce/enrollment/deferral state, and the workforce snapshot is a
  composition. Removed the two redundant legacy state relations after exact parity.
- STATE_ACCUMULATION now uses one command per year with no state full-refresh. In the
  three-run 60,040-employee warm matrix, median peak RSS was 86.2% of baseline for the
  reference workload and 81.4% for Studio; exact public mart compatibility was
  preserved. The observed whole-run invocation total is evidence, not a fixed target.
- This feature targets the active SQL pipeline only; deprecated Polars compatibility
  remnants remain out of scope and Polars support was not restored.

## [2.2.0] - 2026-07-11 "Calibration"

_Consolidates all work since 2.1.0 (March–July 2026, ~258 commits), reconstructed from git history._

### Added

**Fast Compensation Calibration (Feature 105, #280)**
- `planalign calibrate <year-range>` — rebuilds only the compensation/workforce dbt subgraph per year; per-year avg comp and YoY growth are exact vs. a full simulation, ~3–5× faster
- Interactive re-tune loop (`--interactive`), COLA/merit overrides, isolated calibration databases by default
- Target-seeking auto-calibration against real production levers: workforce growth, COLA/merit, new-hire age distribution, per-level comp ranges via Match Census × scale
- Termination-rate tuning with Match Census; population and total-compensation growth in output
- Studio "Calibration" panel (`/calibrate`) reworked into guided steps, backed by `POST /api/calibration/run` (shared `CalibrationRunner` with the CLI); calibration runs as background jobs with polling (#380)

**Simulation Engine & DC Plan Modeling**
- **Feature 103** (#357): configurable new-hire DC-plan ineligibility — `eligibility.new_hire_ineligible_pct`, optional `eligibility_override` census column, and census-calibrated mode; resolved in the new `int_plan_eligibility_override` temporal accumulator and enforced across enrollment/contribution/match models. Defaults leave behavior byte-for-byte unchanged
- **Feature 102** (#328, #335): match-magnet dial exposed in Studio; fixed match-ceiling not driving deferral selection; `points_based` DMR corrected
- **Feature 101** (#307, #332): contributions and employer match prorated for same-year enroll→opt-out windows
- **Feature 099** (#317): tenure-graded multi-tier employer match formulas (`employer_match_status: 'tenure_graded'`)
- **Feature 093**: `scheduled_hours_per_week` census field with part-time eligibility hours handling
- **Feature 086**: DC plan eligibility audit trail with prerequisite chain enforcement
- **Feature 085**: opt-out rate configuration with census analysis
- Per-employee auto-escalation opt-out census flag (#316)

**Studio & Data Import**
- **Features 087–091**: census data import overhaul — CSV/Excel → Parquet wizard with schema-aware predictive field mapping, sheet re-selection, soft-validated field mappings (#350), and stg_census_data contract fixes
- **Feature 094**: live simulation run dashboard — structured telemetry protocol, milestone activity feed, live trend chart, WebSocket resync with REST snapshot fallback
- **Feature 088** (#291): per-run simulation log capture for analyst access
- Curated "Workforce Parameters" tab with advanced settings tucked away (#358); sidebar nav grouped into Setup/Run/Analyze
- Year selector on DC plan comparison summary and contribution mix (#322); deferral distribution toggle and year filter on analytics pages (#312, #315)

### Changed
- **Feature 092**: consolidated dbt invocations per stage for simulation performance; multi-threading and checkpointing disabled by default
- Runtime outputs consolidated under `var/` with run-artifact retention (#391)
- Python domain code moved from `config/` into the `planalign_core` package (#390)
- **Feature 104** (#365, #367): removed dead eligibility-events join in `fct_workforce_snapshot` (returned zero rows in every configuration); verified byte-identical output
- Lint debt driven to zero: ruff 387→0 (#331), mypy clean across all packages with pydantic plugin (#333), black formatting enforced via pre-commit hooks (#330)
- Docs: pruned ~430 stale epic/story/session docs (#392); documentation rewritten from the current codebase

### Fixed
- **Feature 108** (#419): purge stale prior-run state before each simulated year
- **Feature 107** (#418): preserve census enrollment state across simulation years
- **Feature 106** (#406): stop the simulation when a workflow stage reports failure
- Duplicate simulation starts rejected for queued scenarios (#417); cancel now stops the real subprocess across service instances (#416)
- `event_sequence` ordered chronologically with priority as same-day tiebreaker (#412)
- Year-cleanup deletes scoped to scenario and plan design (#410)
- Studio scenario seed overrides no longer leak into global dbt seeds (#413); per-scenario seeds persist across batch runs
- dbt correctness: merit raises no longer granted to already-terminated employees; zero-mean new-hire comp variance with seeded stable event RNGs; new-hire-termination contribution proration (#334); 414(s) testing compensation capped at IRS limit in ACP/401(a)(4) tests
- **Feature 095**: voluntary enrollees missing from snapshot participation/deferral/match
- WebSocket telemetry reliability (reconnect backoff, missed updates, stuck "running" states); failed/cancelled runs persist `run_metadata.json` and appear in run history
- Census handling: placeholder default no longer shadows workspace census; relative `census_parquet_path` resolved against workspace dir; wizard-generated census wired into workspace config
- Batch: failure exit codes propagate; unknown scenario names rejected
- `ExecutionMutex` acquired atomically (O_EXCL); `int_effective_parameters` built before hazard cache rebuild

### Security
- API authentication boundary and safe network defaults (#414): loopback bind by default, optional shared-token auth via `PLANALIGN_API_TOKEN` (constant-time comparison), wildcard-CORS-on-non-loopback rejected at startup
- Path traversal prevented in the artifact download route (#407)
- API defaults to multi-tenant DB resolution; legacy project-DB fallback gated behind a dev-mode flag (#409)
- New `SECURITY.md` documenting the deployment security model, hardening checklist, and vulnerability reporting

### Removed
- Orphaned auto-enrollment decision-matrix model chain (#319); 5 duplicate dbt models (v2 models renamed to canonical)
- Stale `dq_employee_contributions_validation` references (#408)
- Dead frontend mock telemetry service and unused dev helpers

---

## [2.1.0] - 2026-03-03 "Studio & Compliance"

### Added

**PlanAlign Studio (Web Interface)**
- **E081**: FastAPI backend + React/Vite frontend for scenario management, batch processing, and real-time simulation telemetry via WebSocket
- **E085**: DC Plan Contribution Analytics Dashboard with per-year metrics and export
- **E093**: Compensation analytics broken out by detailed status code
- **E104**: Scenario cost comparison page with multi-scenario charting
- **E013**: Employer cost ratio metrics (employer cost per $1 of employee comp) on comparison page
- **E014/E018**: Redesigned comparison page with sidebar layout, year-by-year breakdown tables, and variance rows
- **E015**: Copy-to-clipboard for comparison tables with Excel-compatible variance formatting
- **033**: Multi-year compensation matrix on Compare Cost page
- **046**: Tenure-based and points-based employer match contribution modes with gap/overlap validation
- **048**: DC plan metrics (participation rate, avg deferral, employer cost) in scenario comparison API
- **049**: Refactored ConfigStudio into modular section components
- **050**: NDT ACP (Actual Contribution Percentage) non-discrimination testing
- **051**: NDT 401(a)(4) general test and 415 annual additions limit test
- **052**: NDT ADP (Actual Deferral Percentage) nondiscrimination test with scenario comparison mode
- **053**: Core contribution tier validation and points-based contribution mode
- **055**: Structured census field validation warnings with tiered severity UI
- **056**: Row-level data quality warnings for census uploads
- **057**: DC plan comparison charts on scenario comparison page
- **059**: Deferral rate distribution comparison across scenarios
- **060**: Average/total compensation toggle with CAGR display on charts
- Unsaved changes tracking in ConfigStudio with beforeunload guard
- Automatic workspace repair on startup
- Delete database option in Advanced Settings tab
- Scenario reorder controls with anchor-first ordering and localStorage persistence
- SECURE 2.0 super catch-up contribution limits for ages 60-63

**Event Sourcing & Simulation Engine**
- **E001**: Centralized age/tenure band definitions in dbt seeds with `assign_age_band`/`assign_tenure_band` macros
- **E003**: Band configuration management UI in PlanAlign Studio
- **E004**: Event type abstraction layer (`EventGenerator`, `EventRegistry`) for extensible event generation
- **E005**: Unified `DatabasePathResolver` for API services (workspace, scenario, project-level databases)
- **E006**: Self-healing dbt initialization with automatic seed/dependency install
- **E007**: State accumulator contract with type-safe Pydantic validation
- **E008**: Hardened IRS 402(g) contribution limit enforcement
- **E010**: Service-based employer match contribution tiers
- **E025/E026**: Vesting analysis page + IRS 401(a)(17) compensation limit compliance
- **E058**: Match-responsive deferral adjustment events
- **E082**: Configurable new hire demographics (age/level distribution via seeds + UI) and promotion rate multiplier
- **E084**: Configurable DC Plan match formulas with editable tiers and graded core by service
- **039**: Per-scenario seed configuration with unified save and workspace fallback chain
- **040**: Vesting year selector on analysis page
- Level discount factor in termination hazard model (higher-level employees get lower termination rates)

**Infrastructure & Architecture**
- **E073**: Split 1,471-line config.py into 7 focused modules
- **E076**: Polars state accumulation pipeline with 1000x+ performance benchmarking
- **E083**: Workspace cloud synchronization via Git (`planalign sync` commands)
- **E011**: Auto-install sqlparse token limit fix on first import (with sitecustomize.py Windows fallback)
- **031**: Workspace export/import via 7z archives
- **034**: Extracted setup and validation concerns from PipelineOrchestrator
- **035**: Modularized config/events.py into domain-specific submodules
- **027**: Split large monolith files into focused packages
- Schema tests for hazard termination model (not_null, monotonicity)

### Changed
- Scenario comparison limit increased from 3 to 6 scenarios
- Tenure calculation now uses day-based precision instead of year-only subtraction
- Terminated employee tenure calculated to termination date (not year-end)
- Census compensation uses correct annualization logic
- Participation rate computed using active employees only per year
- Deferral rate IRS 402(g) cap simplified to guard on compensation > 0 upfront
- Dynamic band macros now use `run_query` to read from seed tables at compile time
- `age_multipliers` and `tenure_multipliers` are now required config fields
- Seed writes use atomic temp file + `os.replace()` to prevent partial files
- Windows compatibility: ProactorEventLoop, cross-platform subprocess, UTF-8 encoding

### Fixed
- **E009**: Service-based core contribution tier support
- **E022**: Hire-termination date ordering and type mismatches
- **E025**: Proportional minimum tenure for new hire terminations
- **E028**: O(n^2) scalar subqueries in fct_workforce_snapshot (performance regression)
- **E036**: Deferral rate escalation now generates events for eligible employees
- **E037/E043**: Census compensation annualization logic corrected
- **E041**: Consistent per-year participation rate
- **E044**: Salary range input UX and default scale factor
- **E047**: Tenure eligibility enforcement for employer contributions; Add Tier defaulting fix
- **E054**: Shared workspace context in DC Plan analytics page
- **E086**: Removed unused turnover parameters from UI
- **E087**: Analytics Dashboard export and storage path display
- **E088**: Removed hardcoded Impact Preview section from Config Studio
- **E089**: Census file upload persistence and metadata display
- **E090**: Census file upload now used in simulations
- **E091**: Use prorated_annual_compensation for analytics
- **E092**: DC Plan analytics page database fallback and case sensitivity
- **E094**: Analytics page remembers workspace and simulation after run
- **E095**: Wired eligibility_months UI field to dbt vars
- **E096**: Participation bug (event type mismatch in deferral accumulator) — 5 bugs fixed
- **E097**: Polars schema mismatch and year range cleanup
- **E098**: Extended seed data through 2035 to fix 2030 contribution bug
- **E099**: Copy scenario now includes all DC Plan and New Hire settings
- **E100**: Copy scenario now includes data sources (census file path)
- **E101**: UI auto-escalation settings now override legacy YAML config
- **E102**: Escalation delay years variable name mismatch; hire date cutoff clearing; Polars var passthrough
- **E103**: Analytics page dropdowns correctly select workspace/scenario from URL
- Auto-escalation hire date filter uses inclusive comparison (>=)
- DuckDB ORDER BY in UNION ALL subquery error
- Cast level_id to INTEGER in snapshot and state models
- Polars: empty parquet files for years with no events, workspace database path priority
- Studio: chart colors, legend ordering, TypeScript errors, stale data overwrite, workspace switching
- Event priority inconsistency, error handler fragility, SQL safety, and warning filter gaps
- Resolved 8 failing unit tests and 5 flaky/environment-specific tests

### Removed
- **E024**: Removed Polars pipeline — simplified to SQL-only mode (~4,400 LOC removed)
- Removed deprecated Streamlit dashboard
- Removed Makefile and Make references
- Removed 179 lines of redundant content from CLAUDE.md and README.md

---

## [2.0.0] - 2025-11-24 "PlanAlign Engine"

### BREAKING CHANGES
- **Project Renamed**: PlanWise Navigator → Fidelity PlanAlign Engine
- **CLI Command Renamed**: `planwise` → `planalign`
- **Package Renamed**: `navigator_orchestrator` → `planalign_orchestrator`
- **Package Renamed**: `planwise_cli` → `planalign_cli`
- **dbt Project Name**: `planwise_navigator` → `fidelity_planalign_engine`

### Migration Guide
1. Update all imports:
   - `from navigator_orchestrator` → `from planalign_orchestrator`
   - `from planwise_cli` → `from planalign_cli`
2. Update CLI commands:
   - `planwise simulate` → `planalign simulate`
   - `planwise batch` → `planalign batch`
   - `planwise status` → `planalign status`
3. Update dbt profiles to reference `fidelity_planalign_engine` profile
4. Reinstall package: `uv pip install -e ".[dev]"`

---

## [1.0.0] - 2025-01-15 "Foundation"

### Added
- **E068**: Performance Optimization (2× improvement, 285s → 150s)
  - Multi-threaded dbt execution with configurable thread pools
  - Optimized incremental model strategies
  - Memory-efficient query patterns
  - 375× performance with Polars mode option

- **E069**: Batch Scenario Processing
  - Isolated database instances per scenario
  - Excel export with metadata (git SHA, seed, configuration)
  - Timestamped batch directories for reproducibility
  - Scenario comparison reports

- **E072**: Pipeline Modularization
  - 51% code reduction (2,478 → 1,220 lines)
  - 6 focused modules: WorkflowBuilder, StateManager, YearExecutor, EventGenerationExecutor, HookManager, DataCleanupManager
  - Extensible callback system for custom workflows
  - Improved testability and maintainability

- **E074**: Enhanced Error Handling
  - Context-rich exception hierarchy (NavigatorError, DatabaseError, PipelineError, etc.)
  - Pattern-based error recognition with ErrorCatalog
  - Correlation IDs for distributed tracing
  - Resolution hints for common issues
  - <5min bug diagnosis capability

- **E075**: Testing Infrastructure
  - 256 comprehensive tests (87 fast unit tests, integration suite)
  - Centralized fixture library (database, config, mock_dbt, workforce_data)
  - In-memory database fixtures for fast testing
  - 90%+ code coverage for core components
  - pytest markers for targeted test execution

- **E023**: Enrollment Architecture Fix
  - Temporal state accumulator pattern
  - `int_enrollment_state_accumulator` model
  - `int_deferral_rate_state_accumulator` model
  - Fixed circular dependencies in enrollment tracking
  - Validation model for enrollment architecture integrity

- **E078**: Cohort Pipeline Integration
  - Polars-based event factory (375× faster than dbt)
  - Multi-year termination fixes
  - Cohort-based workforce modeling
  - Hybrid SQL/Polars execution strategy

- **E080**: Validation Model to Test Conversion
  - Converted 30 validation SQL models to dbt tests
  - 90 passing data quality tests
  - Removed legacy validation code
  - Integrated with dbt build workflow
  - Improved CI/CD validation speed

- **PlanAlign CLI**: Rich-based terminal interface
  - `planalign simulate` - Multi-year simulation with progress tracking
  - `planalign batch` - Batch scenario processing
  - `planalign status` - Comprehensive system diagnostics
  - `planalign health` - Quick health check
  - `planalign checkpoints` - Checkpoint management
  - `planalign analyze` - Results analysis with terminal visualizations
  - `planalign validate` - Configuration validation

- **Versioning System**: Centralized version management
  - Semantic Versioning 2.0.0 compliance
  - Version displayed in CLI and status commands
  - Release metadata tracking

### Changed
- Database location standardized to `dbt/simulation.duckdb`
- dbt commands always run from `/dbt` directory
- Improved error messages with actionable resolution hints
- Enhanced logging with correlation IDs

### Fixed
- Enrollment event duplication across years
- Missing enrollment dates in temporal tracking
- Database lock conflicts with IDE connections
- Configuration validation edge cases
- Multi-year simulation state accumulation issues

### Technical Details
- Python 3.11+ required
- DuckDB 1.0.0 (columnar OLAP engine)
- dbt-core 1.8.8 with dbt-duckdb 1.8.1
- Pydantic v2 for configuration validation
- Rich + Typer for CLI interface
- pytest with comprehensive fixture library

---

## Version History

- **2.2.0** (2026-07-11): Calibration - Fast compensation calibration, new-hire eligibility modeling, tenure-graded match, census import wizard, API security hardening
- **2.1.0** (2026-03-03): Studio & Compliance - PlanAlign Studio, NDT testing, DC plan modeling, SQL-only mode, 60+ features/fixes
- **2.0.0** (2025-11-24): PlanAlign Engine - Project rename from PlanWise Navigator
- **1.0.0** (2025-01-15): Foundation - Initial production release with event sourcing, pipeline modularization, and comprehensive testing

---

## Links

- [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
- [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- [Fidelity PlanAlign Engine Documentation](./docs/)
- [Project Status](./CLAUDE.md#12-project-status)
