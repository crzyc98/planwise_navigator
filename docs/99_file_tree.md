# PlanWise Navigator - Complete File Tree v3.0

Generated on: 2025-06-21
Based on PRD v3.0 (2025-06-21)

This document provides a comprehensive view of the PlanWise Navigator codebase structure, excluding temporary files, build artifacts, and generated content.

## Project Root Structure

```
planwise_navigator/
├── .gitignore
├── CLAUDE.md
├── README.md
├── definitions.py
├── pyproject.toml
├── requirements.txt
├── simulation.duckdb
│
├── config/
│   ├── multi_year_config.yaml
│   ├── simulation_config.yaml
│   └── test_config.yaml
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── analyses/
│   ├── macros/
│   │   ├── get_config_value.sql
│   │   ├── get_current_simulation_year.sql
│   │   ├── get_random_seed.sql
│   │   ├── validate_simulation_year.sql
│   │   └── generate_events.sql
│   ├── models/
│   │   ├── intermediate/
│   │   │   ├── events/
│   │   │   │   ├── int_hiring_events.sql
│   │   │   │   ├── int_merit_events.sql
│   │   │   │   ├── int_new_hire_termination_events.sql
│   │   │   │   ├── int_promotion_events.sql
│   │   │   │   └── int_termination_events.sql
│   │   │   ├── hazards/
│   │   │   │   ├── int_hazard_merit.sql
│   │   │   │   ├── int_hazard_promotion.sql
│   │   │   │   └── int_hazard_termination.sql
│   │   │   ├── int_baseline_workforce.sql
│   │   │   ├── int_previous_year_workforce.sql
│   │   │   └── schema.yml
│   │   ├── marts/
│   │   │   ├── dim_hazard_table.sql
│   │   │   ├── fct_workforce_snapshot.sql
│   │   │   ├── fct_yearly_events.sql
│   │   │   ├── mart_cohort_analysis.sql
│   │   │   ├── mart_financial_impact.sql
│   │   │   ├── mart_workforce_summary.sql
│   │   │   └── schema.yml
│   │   ├── monitoring/
│   │   │   ├── mon_data_quality.sql
│   │   │   └── mon_pipeline_performance.sql
│   │   ├── staging/
│   │   │   └── stg_census_data.sql
│   │   └── test/
│   │       └── test_simulation_data.sql
│   ├── seeds/
│   │   ├── bootstrap_census_data.csv
│   │   ├── config_cola_by_year.csv
│   │   ├── config_job_levels.csv
│   │   ├── config_promotion_hazard_age_multipliers.csv
│   │   ├── config_promotion_hazard_base.csv
│   │   ├── config_promotion_hazard_tenure_multipliers.csv
│   │   ├── config_raises_hazard.csv
│   │   ├── config_termination_hazard_age_multipliers.csv
│   │   ├── config_termination_hazard_base.csv
│   │   └── config_termination_hazard_tenure_multipliers.csv
│   └── tests/
│       ├── epic_11_5_acceptance_criteria.sql
│       └── epic_11_5_new_hire_terminations.sql
│
├── docs/
│   ├── README.md
│   ├── architecture.md
│   ├── events.md
│   ├── migration_guide.md
│   ├── simulation_config.md
│   ├── duckdb_relation_serialization_issue.md
│   └── rebuild/
│       ├── PRD-REBUILD-PLANWISE-NAVIGATOR.md
│       ├── dagster_patterns.md
│       ├── duckdb_dagster_patterns.md
│       ├── rebuild_implementation_addendum.md
│       └── technical_implementation_guide.md
│
├── orchestrator/
│   ├── __init__.py
│   ├── assets/
│   │   ├── __init__.py
│   │   ├── census_data.py
│   │   ├── dbt_assets.py
│   │   ├── simulation_state.py
│   │   └── validation.py
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── multi_year_simulation.py
│   │   └── single_year_simulation.py
│   ├── ops/
│   │   ├── __init__.py
│   │   ├── census_ops.py
│   │   ├── simulation_ops.py
│   │   └── validation_ops.py
│   ├── resources/
│   │   ├── __init__.py
│   │   ├── dbt_resource.py
│   │   └── duckdb_resource.py
│   └── utils/
│       ├── __init__.py
│       ├── config_loader.py
│       ├── database_utils.py
│       └── simulation_utils.py
│
├── scripts/
│   ├── __init__.py
│   ├── analysis_tools.py
│   ├── dashboard_launcher.py
│   ├── data_export.py
│   ├── install_venv.sh
│   ├── lint.py
│   ├── migration_helper.py
│   ├── set_dagster_home.sh
│   ├── setup_unified_pipeline.py
│   ├── start_dashboard.sh
│   ├── test_runner.py
│   └── validation_checks.py
│
├── streamlit_dashboard/
│   ├── __init__.py
│   ├── app.py
│   ├── components/
│   │   ├── __init__.py
│   │   ├── charts.py
│   │   ├── data_explorer.py
│   │   ├── filters.py
│   │   └── metrics.py
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── cohort_analysis.py
│   │   ├── financial_impact.py
│   │   ├── scenario_comparison.py
│   │   └── workforce_overview.py
│   └── utils/
│       ├── __init__.py
│       ├── data_loader.py
│       └── visualization_helpers.py
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_assets/
    │   ├── __init__.py
    │   ├── test_census_data.py
    │   ├── test_dbt_assets.py
    │   ├── test_simulation_state.py
    │   └── test_validation.py
    ├── test_jobs/
    │   ├── __init__.py
    │   ├── test_multi_year_simulation.py
    │   └── test_single_year_simulation.py
    ├── test_ops/
    │   ├── __init__.py
    │   ├── test_census_ops.py
    │   ├── test_simulation_ops.py
    │   └── test_validation_ops.py
    ├── test_resources/
    │   ├── __init__.py
    │   ├── test_dbt_resource.py
    │   └── test_duckdb_resource.py
    ├── test_scripts/
    │   ├── __init__.py
    │   ├── test_analysis_tools.py
    │   ├── test_migration_helper.py
    │   └── test_validation_checks.py
    └── test_utils/
        ├── __init__.py
        ├── test_config_loader.py
        ├── test_database_utils.py
        └── test_simulation_utils.py
```

## Directory Descriptions

### Core Application Files
- **definitions.py**: Main Dagster workspace entry point
- **requirements.txt**: Python dependencies
- **pyproject.toml**: Python project configuration
- **CLAUDE.md**: Development playbook and coding standards
- **simulation.duckdb**: Main DuckDB database file

### Configuration (`config/`)
Central configuration management for different simulation scenarios:
- **simulation_config.yaml**: Default simulation parameters
- **multi_year_config.yaml**: Multi-year simulation configuration
- **test_config.yaml**: Testing configuration

### Data Transformation (`dbt/`)
Complete dbt project for SQL-based data modeling:
- **models/**: SQL models organized by layer (staging, intermediate, marts, monitoring)
- **seeds/**: CSV reference data and configuration tables
- **macros/**: Reusable SQL functions and utilities
- **tests/**: Custom dbt tests for business logic validation

### Orchestration (`orchestrator/`)
Dagster-based pipeline orchestration:
- **assets/**: Asset definitions for data pipeline components
- **jobs/**: Job definitions for complete simulation workflows
- **ops/**: Individual operation definitions
- **resources/**: Shared resources (database connections, dbt)
- **utils/**: Shared utility functions

### Analytics Dashboard (`streamlit_dashboard/`)
Interactive web dashboard for simulation results:
- **components/**: Reusable UI components
- **pages/**: Individual dashboard pages
- **utils/**: Dashboard-specific utilities

### Automation & Utilities (`scripts/`)
Development and operational scripts:
- **setup_unified_pipeline.py**: Migration and setup utilities
- **dashboard_launcher.py**: Dashboard startup automation
- **analysis_tools.py**: Data analysis utilities
- **validation_checks.py**: Data quality checks

### Testing (`tests/`)
Comprehensive test suite matching the application structure:
- **test_assets/**: Tests for Dagster assets
- **test_jobs/**: Tests for simulation jobs
- **test_ops/**: Tests for individual operations
- **test_resources/**: Tests for shared resources
- **test_scripts/**: Tests for utility scripts
- **test_utils/**: Tests for utility functions

### Documentation (`docs/`)
Technical documentation and rebuild guides:
- **architecture.md**: System architecture overview
- **events.md**: Workforce event taxonomy
- **migration_guide.md**: Migration instructions
- **rebuild/**: Comprehensive rebuild documentation

## File Type Summary

| File Type | Count | Purpose |
|-----------|-------|---------|
| Python (.py) | 65 | Application logic, orchestration, testing |
| SQL (.sql) | 30 | Data transformation models and tests |
| YAML (.yml/.yaml) | 8 | Configuration and dbt schemas |
| Markdown (.md) | 60+ | Documentation and specifications |
| CSV (.csv) | 10 | Reference data and configuration seeds |
| Shell (.sh) | 3 | Setup and automation scripts |

## Key Features Represented

1. **Data Pipeline**: Complete dbt models for workforce simulation
2. **Orchestration**: Dagster assets and jobs for pipeline management
3. **Analytics**: Streamlit dashboard for interactive exploration
4. **Configuration**: YAML-based configuration management
5. **Testing**: Comprehensive test coverage across all components
6. **Documentation**: Extensive documentation for development and operations
7. **Automation**: Scripts for setup, migration, and operational tasks

This structure represents a mature, production-ready workforce simulation platform with clear separation of concerns and comprehensive tooling for development and operations.
