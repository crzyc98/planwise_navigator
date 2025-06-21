# PlanWise Navigator - Code Base Documentation

This directory contains comprehensive documentation for the most critical components of the PlanWise Navigator workforce simulation platform.

## Organization

The documentation is organized by functional area to mirror the system architecture:

### 📍 Entry Points & Core Infrastructure
- **[definitions.py](entry_points/definitions.md)** - Main Dagster workspace entry point
- **[simulation_pipeline.py](entry_points/simulation_pipeline.md)** - Core simulation orchestration
- **[Dashboard.py](entry_points/dashboard.md)** - Streamlit dashboard entry point

### ⚙️ Configuration & Settings  
- **[simulation_config.yaml](configuration/simulation_config.md)** - Primary simulation configuration
- **[dbt_project.yml](configuration/dbt_project.md)** - dbt project configuration
- **[profiles.yml](configuration/profiles.md)** - Database connection profiles

### 🎯 Core Business Logic (dbt Models)
- **[Staging Models](business_logic/staging_models.md)** - Data ingestion and standardization
- **[Event Generation](business_logic/event_generation.md)** - Core workforce event models
- **[Hazard Models](business_logic/hazard_models.md)** - Risk and probability calculations
- **[Mart Models](business_logic/mart_models.md)** - Final analytical outputs

### 🔍 Data Quality & Monitoring
- **[Schema Tests](data_quality/schema_tests.md)** - Data validation and quality tests
- **[Monitoring Models](data_quality/monitoring_models.md)** - Pipeline and data quality monitoring

### 📊 Analytics & Reporting
- **[Dashboard Pages](analytics/dashboard_pages.md)** - Interactive visualization components
- **[Data Utilities](analytics/data_utilities.md)** - Data access and processing utilities

### 🔧 Operations & Scripts
- **[Core Scripts](operations/core_scripts.md)** - Primary operational utilities
- **[Environment Scripts](operations/environment_scripts.md)** - Setup and deployment scripts

### 🚀 Advanced Features
- **[Optimization Tools](advanced_features/optimization_tools.md)** - Parameter tuning and analysis
- **[Data Management](advanced_features/data_management.md)** - Advanced data handling utilities

## Priority Documentation Status

### Tier 1 (Critical) - ⭐⭐⭐
- [ ] definitions.py
- [ ] simulation_pipeline.py
- [ ] simulation_config.yaml
- [ ] Event generation models
- [ ] fct_workforce_snapshot.sql

### Tier 2 (High Priority) - ⭐⭐
- [ ] Dashboard components
- [ ] Hazard calculation models
- [ ] Data quality models
- [ ] Core operational scripts

### Tier 3 (Important) - ⭐
- [ ] Utility scripts
- [ ] Advanced analytics
- [ ] Environment setup
- [ ] Supporting components

## Usage Guidelines

Each documentation file follows a consistent structure:
1. **Purpose** - What the file does and why it exists
2. **Architecture** - How it fits into the overall system
3. **Key Components** - Major functions/classes/models
4. **Configuration** - Required settings and parameters
5. **Dependencies** - What it depends on and what depends on it
6. **Usage Examples** - How to use/call/modify the component
7. **Common Issues** - Known problems and solutions
8. **Related Files** - Connected components and references

## Contributing

When documenting new files:
1. Follow the established template structure
2. Include practical examples and use cases
3. Document both happy path and error scenarios
4. Link to related components and dependencies
5. Keep business context and technical details balanced