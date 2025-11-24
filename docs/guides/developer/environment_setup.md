# Fidelity PlanAlign Engine - Environment Setup Guide

A step-by-step guide for analysts to set up the Fidelity PlanAlign Engine workforce simulation platform on their local development environment.

## Overview

Fidelity PlanAlign Engine is Fidelity's on-premises workforce simulation platform that uses event sourcing to model organizational dynamics. This guide will help you get a fully functional development environment running locally.

## Prerequisites

Before you begin, ensure you have:

- **macOS or Linux** (Windows users should use WSL2)
- **Admin privileges** to install software
- **Git** installed and configured
- **Terminal/Command Line** access
- **Internet connection** for downloading dependencies

## Step 1: Install Python 3.11

Fidelity PlanAlign Engine requires Python 3.11 for long-term support compatibility.

### macOS (using Homebrew)
```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11
brew install python@3.11

# Verify installation
python3.11 --version
```

### Linux (Ubuntu/Debian)
```bash
# Update package list
sudo apt update

# Install Python 3.11
sudo apt install python3.11 python3.11-venv python3.11-pip

# Verify installation
python3.11 --version
```

## Step 2: Clone the Repository

```bash
# Clone the repository
git clone <repository-url> planalign_engine
cd planalign_engine

# Verify you're on the main branch
git branch
```

## Step 3: Create Python Virtual Environment

```bash
# Create virtual environment using Python 3.11
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Verify you're using the correct Python
which python
python --version  # Should show Python 3.11.x

# Upgrade pip to latest version
pip install --upgrade pip
```

## Step 4: Install Dependencies

```bash
# Install all required Python packages
pip install -r requirements.txt

# This will install:
# - dbt-core==1.8.8 (SQL transformation framework)
# - dbt-duckdb==1.8.1 (DuckDB adapter for dbt)
# - dagster==1.8.12 (Pipeline orchestration)
# - streamlit==1.39.0 (Dashboard framework)
# - pydantic==2.7.4 (Configuration management)
# - pytest and other testing tools
```

## Step 5: Set Up Environment Variables

The system requires a specific Dagster home directory configuration.

```bash
# Run the environment setup script
./scripts/set_dagster_home.sh

# Verify the environment variable is set
launchctl getenv DAGSTER_HOME
# Should output: /Users/[your-username]/dagster_home_planwise
```

**Note:** This sets the environment variable system-wide on macOS. If you encounter issues, you may need to restart your terminal or system.

## Step 6: Initialize Database and Configuration

```bash
# Navigate to the dbt directory
cd dbt

# Install dbt dependencies
dbt deps

# Run dbt to set up the database schema
dbt run

# Run tests to verify everything is working
dbt test

# Generate documentation
dbt docs generate
```

## Step 7: Verify Installation

### Test the Complete Pipeline

```bash
# Return to the main directory
cd ..

# Start the Dagster development server
dagster dev
```

This will:
- Start the Dagster web interface at `http://localhost:3000`
- Load all pipeline assets and jobs
- Provide a web UI to monitor and run simulations

### Run a Sample Simulation

1. Open your browser to `http://localhost:3000`
2. Navigate to the "Assets" tab
3. Click "Materialize All" to run a complete simulation
4. Monitor progress in the web interface

### Test the Dashboard

```bash
# In a new terminal (keep Dagster running)
cd planalign_engine
source venv/bin/activate

# Start the Streamlit dashboard
streamlit run streamlit_dashboard/main.py
```

The dashboard will open at `http://localhost:8501` showing simulation results and analytics.

## Step 8: Configuration Management

### Simulation Parameters

Edit the main configuration file:
```bash
# Open the simulation configuration
nano config/simulation_config.yaml
```

Key parameters you can adjust:
```yaml
# Simulation time horizon
start_year: 2023
end_year: 2027

# Growth and turnover rates
target_growth_rate: 0.03        # 3% annual growth
total_termination_rate: 0.12    # 12% annual turnover

# Reproducibility
random_seed: 42                 # For consistent results
```

### Environment-Specific Settings

Create a `.env` file for local overrides:
```bash
# Create environment file
cat > .env << EOF
# Local development settings
DBT_PROFILES_DIR=./dbt
DAGSTER_HOME=~/dagster_home_planwise
LOG_LEVEL=INFO
EOF
```

## Step 9: Development Workflow

### Daily Development Commands

```bash
# Activate environment (run this in each new terminal)
cd planalign_engine
source venv/bin/activate

# Run specific dbt models
cd dbt
dbt run --select staging    # Run staging models only
dbt run --select marts      # Run final output models
dbt test --select int_termination_events  # Test specific models

# Run Python tests
cd ..
python -m pytest tests/unit/  # Unit tests
python -m pytest tests/integration/  # Integration tests

# Start development servers
dagster dev                 # Pipeline orchestration
streamlit run streamlit_dashboard/main.py  # Analytics dashboard
```

### Running Simulations

```bash
# Single year simulation
dagster asset materialize --select simulation_year_state

# Multi-year simulation
dagster asset materialize --select multi_year_simulation

# Specific simulation components
dagster asset materialize --select dbt_models             # Run dbt models
dagster asset materialize --select workforce_simulation   # Run simulation logic
dagster asset materialize --select dashboard_data        # Prepare dashboard data
```

## Common Troubleshooting

### DuckDB Connection Issues

**Problem:** `DuckDB database is locked` errors
```bash
# Solution: Clear any hanging connections
rm -f simulation.duckdb.wal simulation.duckdb.db
```

**Problem:** Permission errors with database files
```bash
# Solution: Reset database permissions
chmod 664 simulation.duckdb
```

### Python Environment Issues

**Problem:** `Module not found` errors
```bash
# Solution: Reinstall in clean environment
deactivate
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Dagster Environment Issues

**Problem:** Temporary `.tmp_dagster_home_*` directories
```bash
# Solution: Re-run environment setup
./scripts/set_dagster_home.sh
# Restart terminal or system
```

**Problem:** Dagster web interface not loading
```bash
# Check if DAGSTER_HOME is set correctly
launchctl getenv DAGSTER_HOME

# Restart Dagster
pkill -f dagster
dagster dev
```

### dbt Issues

**Problem:** Models not finding dependencies
```bash
# Solution: Re-install dbt packages and run dependencies
cd dbt
dbt clean
dbt deps
dbt run
```

**Problem:** Test failures
```bash
# Check specific test
dbt test --select test_name

# Run with debug info
dbt --debug test
```

## Performance Optimization

### For Large Datasets

```bash
# Use DuckDB performance settings
export DUCKDB_ENABLE_EXTERNAL_ACCESS=1
export DUCKDB_MEMORY_LIMIT=8GB
```

### For Development Speed

```bash
# Run specific model selections
dbt run --select +my_model+     # Run model and all dependencies
dbt run --select my_model+      # Run model and downstream models
dbt run --select +my_model      # Run model and upstream models
```

## Data Sources and Setup

### Census Data

Place your initial workforce census data in:
```bash
data/census_raw.csv
```

Required columns:
- `employee_id`: Unique identifier
- `employee_ssn`: Social security number (will be hashed)
- `employee_birth_date`: Birth date (YYYY-MM-DD)
- `employee_hire_date`: Hire date (YYYY-MM-DD)
- `employee_gross_compensation`: Annual compensation
- `employment_status`: 'active' for current employees

### Configuration Seeds

The system includes reference data in `dbt/seeds/`:
- Job levels and compensation bands
- Termination hazard multipliers
- COLA adjustment rates
- Department mappings

## Security Considerations

### Data Privacy

- Employee SSNs are automatically hashed for privacy
- All data stays local - no external data transmission
- Database files are excluded from Git (`.gitignore`)

### Access Control

```bash
# Set restrictive permissions on data files
chmod 600 data/census_raw.csv
chmod 600 simulation.duckdb
```

## Getting Help

### Documentation

- **Architecture Deep Dive:** `docs/architecture.md`
- **Event Sourcing Guide:** `docs/events.md`
- **API Reference:** `docs/api-reference.md`

### Command Reference

```bash
# View all available dbt models
dbt list

# View Dagster assets
dagster asset list

# Run tests with verbose output
python -m pytest -v

# Generate dbt documentation
dbt docs generate && dbt docs serve
```

### Support Contacts

- **Technical Issues:** Data Engineering Team
- **Business Logic Questions:** Workforce Analytics Team
- **Platform Issues:** Infrastructure Team

## Next Steps

Once your environment is running:

1. **Explore the Dashboard** - Review sample simulation outputs
2. **Run Custom Scenarios** - Modify configuration parameters
3. **Review Documentation** - Understand the event sourcing architecture
4. **Join Team Meetings** - Participate in sprint planning and reviews

---

**🎉 Congratulations!** You now have a fully functional Fidelity PlanAlign Engine development environment. The platform is ready for workforce simulation modeling and analysis.

For questions or issues, refer to the troubleshooting section above or contact the development team.
