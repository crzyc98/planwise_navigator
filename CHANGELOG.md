# Changelog

All notable changes to Fidelity PlanAlign Engine will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Version Numbering

Fidelity PlanAlign Engine follows **Semantic Versioning 2.0.0** (MAJOR.MINOR.PATCH):

- **MAJOR** version: Incompatible API changes or major architectural changes
- **MINOR** version: New features in a backwards-compatible manner (e.g., completed epics)
- **PATCH** version: Backwards-compatible bug fixes

### When to Increment Versions

**MAJOR (X.0.0):**
- Breaking changes to configuration schema
- Incompatible changes to database schema requiring migration
- Removal of deprecated features
- Major architectural overhauls

**MINOR (x.Y.0):**
- New epic features (E068, E069, E072, etc.)
- New CLI commands
- New dbt models or transformations
- New configuration options (backwards-compatible)
- Performance improvements without breaking changes

**PATCH (x.y.Z):**
- Bug fixes
- Documentation updates
- Internal code refactoring without API changes
- Test improvements

### Version Update Process

1. **Update `_version.py`** in the project root:
   ```python
   __version__ = "1.1.0"  # Update version number
   __version_info__ = tuple(int(x) for x in __version__.split("."))
   __release_date__ = "2025-01-24"  # Update release date
   __release_name__ = "Performance"  # Optional release name
   ```

2. **Update `CHANGELOG.md`** with changes:
   - Add new version section under "## [Unreleased]"
   - Document all changes under appropriate categories
   - Move changes from [Unreleased] to new version section

3. **Update `pyproject.toml`** (line 3):
   ```toml
   version = "1.1.0"
   ```

4. **Commit changes**:
   ```bash
   git add _version.py CHANGELOG.md pyproject.toml
   git commit -m "chore: Bump version to 1.1.0"
   ```

5. **Create git tag**:
   ```bash
   git tag -a v1.1.0 -m "Release version 1.1.0: Performance improvements"
   git push origin v1.1.0
   ```

## [Unreleased]

### Added
### Changed
### Fixed
### Deprecated
### Removed
### Security

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

- **1.0.0** (2025-01-15): Foundation - Initial production release with event sourcing, pipeline modularization, and comprehensive testing

---

## Links

- [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
- [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- [Fidelity PlanAlign Engine Documentation](./docs/)
- [Project Status](./CLAUDE.md#12-project-status)
