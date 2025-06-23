# Dependency Update Plan - June 22, 2024

## Current Dependencies (requirements.txt)
```
duckdb==0.9.2
dbt-core==1.7.4
dbt-duckdb==1.7.0
dagster==1.6.0
dagster-webserver==1.6.0
dagster-dbt==0.22.0
streamlit==1.39.0
pydantic==2.7.4
python-dotenv>=1.0.0
pyyaml>=6.0.0
pandas>=2.0.0
numpy>=1.24.0
```

## Proposed Updates
```
duckdb==1.0.0
dbt-core==1.8.8
dbt-duckdb==1.8.1
dagster==1.8.12
dagster-webserver==1.8.12  # Ensure webserver matches core Dagster version
dagster-dbt==1.8.12  # Ensure dagster-dbt matches core Dagster version for compatibility
streamlit==1.39.0
pydantic==2.7.4
python-dotenv>=1.0.0
pyyaml>=6.0.0
pandas>=2.0.0
numpy>=1.24.0
```

## Key Changes
- Upgraded DuckDB from 0.9.2 to 1.0.0
- Upgraded dbt-core from 1.7.4 to 1.8.8
- Upgraded dbt-duckdb from 1.7.0 to 1.8.1
- Major upgrade for Dagster from 1.6.0 to 1.8.12
- Aligned all Dagster-related packages to version 1.8.12
- Kept streamlit and other dependencies at current versions

## Action Items
1. Update requirements.txt with new versions
2. Test the application thoroughly after updates
3. Check for any breaking changes in the major version updates
4. Update any deprecated API usage in the codebase
