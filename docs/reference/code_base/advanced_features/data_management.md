# Data Management - Advanced Data Handling Utilities

## Purpose

The data management utilities provide sophisticated tools for handling complex data operations in Fidelity PlanAlign Engine, including data migration, schema management, performance optimization, and advanced data processing workflows.

## Architecture

The data management framework implements enterprise-grade capabilities for:
- **Schema Management**: Database schema evolution and migration
- **Data Pipeline Optimization**: Performance tuning and data flow optimization
- **Data Quality Management**: Comprehensive data validation and cleansing
- **Archive and Retention**: Data lifecycle management and storage optimization

## Key Data Management Components

### 1. dbt Macros - Reusable SQL Functions

**Purpose**: Centralized SQL utilities and business logic for consistent data processing across all models.

#### `dbt/macros/get_random_seed.sql` - Random Seed Management

```sql
{#
  Macro to get random seed for reproducible simulations

  Usage:
    {{ get_random_seed() }}
    {{ get_random_seed(default_seed=42) }}
#}

{% macro get_random_seed(default_seed=null) %}
  {% if var('random_seed', none) is not none %}
    {{ var('random_seed') }}
  {% elif default_seed is not none %}
    {{ default_seed }}
  {% else %}
    {# Generate seed based on current timestamp for randomness #}
    {% set current_timestamp = modules.datetime.datetime.now().timestamp() | int %}
    {{ current_timestamp % 2147483647 }}  {# Ensure within int32 range #}
  {% endif %}
{% endmacro %}

{#
  Set random seed for consistent results within a model

  Usage:
    {{ set_random_seed() }}
    {{ set_random_seed(42) }}
#}

{% macro set_random_seed(seed=null) %}
  {% set seed_value = get_random_seed(seed) %}

  {# DuckDB random seed setting #}
  {% if target.type == 'duckdb' %}
    SELECT setseed({{ seed_value }} / 2147483647.0);
  {% elif target.type == 'postgres' %}
    SELECT setseed({{ seed_value }} / 2147483647.0);
  {% elif target.type == 'snowflake' %}
    {# Snowflake uses different approach #}
    ALTER SESSION SET RANDOM_SEED = {{ seed_value }};
  {% endif %}
{% endmacro %}

{#
  Generate reproducible random number between 0 and 1

  Usage:
    {{ random_uniform() }}
    {{ random_uniform(seed=123) }}
#}

{% macro random_uniform(seed=null) %}
  {% if seed is not none %}
    {{ set_random_seed(seed) }}
  {% endif %}

  {% if target.type == 'duckdb' %}
    RANDOM()
  {% elif target.type == 'postgres' %}
    RANDOM()
  {% elif target.type == 'snowflake' %}
    UNIFORM(0, 1, RANDOM())
  {% else %}
    RAND()
  {% endif %}
{% endmacro %}

{#
  Generate random integer within specified range

  Usage:
    {{ random_int(1, 100) }}
    {{ random_int(min_val=0, max_val=10, seed=42) }}
#}

{% macro random_int(min_val, max_val, seed=null) %}
  {% if seed is not none %}
    {{ set_random_seed(seed) }}
  {% endif %}

  FLOOR({{ random_uniform() }} * ({{ max_val }} - {{ min_val }} + 1)) + {{ min_val }}
{% endmacro %}

{#
  Generate random date within range

  Usage:
    {{ random_date('2023-01-01', '2023-12-31') }}
#}

{% macro random_date(start_date, end_date, seed=null) %}
  {% if seed is not none %}
    {{ set_random_seed(seed) }}
  {% endif %}

  {% set start_epoch = "EXTRACT(EPOCH FROM '" ~ start_date ~ "'::DATE)" %}
  {% set end_epoch = "EXTRACT(EPOCH FROM '" ~ end_date ~ "'::DATE)" %}

  ({{ start_epoch }} + {{ random_uniform() }} * ({{ end_epoch }} - {{ start_epoch }}))::INT::DATE
{% endmacro %}
```

#### `dbt/macros/assert_var.sql` - Configuration Validation

```sql
{#
  Macro to assert that required variables are defined and valid

  Usage:
    {{ assert_var('current_simulation_year') }}
    {{ assert_var('target_growth_rate', min_value=0, max_value=1) }}
#}

{% macro assert_var(var_name, min_value=none, max_value=none, allowed_values=none, error_message=none) %}

  {# Check if variable exists #}
  {% if var(var_name, none) is none %}
    {% set default_message = "Required variable '" ~ var_name ~ "' is not defined" %}
    {{ log(error_message or default_message, info=false) }}
    {{ exceptions.raise_compiler_error(error_message or default_message) }}
  {% endif %}

  {% set var_value = var(var_name) %}

  {# Validate numeric ranges #}
  {% if min_value is not none and var_value < min_value %}
    {% set range_message = "Variable '" ~ var_name ~ "' value " ~ var_value ~ " is below minimum " ~ min_value %}
    {{ log(error_message or range_message, info=false) }}
    {{ exceptions.raise_compiler_error(error_message or range_message) }}
  {% endif %}

  {% if max_value is not none and var_value > max_value %}
    {% set range_message = "Variable '" ~ var_name ~ "' value " ~ var_value ~ " is above maximum " ~ max_value %}
    {{ log(error_message or range_message, info=false) }}
    {{ exceptions.raise_compiler_error(error_message or range_message) }}
  {% endif %}

  {# Validate allowed values #}
  {% if allowed_values is not none and var_value not in allowed_values %}
    {% set values_message = "Variable '" ~ var_name ~ "' value '" ~ var_value ~ "' not in allowed values: " ~ allowed_values %}
    {{ log(error_message or values_message, info=false) }}
    {{ exceptions.raise_compiler_error(error_message or values_message) }}
  {% endif %}

  {# Return the validated value #}
  {{ return(var_value) }}
{% endmacro %}

{#
  Macro to validate simulation year progression

  Usage:
    {{ validate_simulation_year() }}
    {{ validate_simulation_year(year=2025) }}
#}

{% macro validate_simulation_year(year=none) %}
  {% set current_year = year or var('current_simulation_year') %}
  {% set start_year = var('simulation_start_year', 2024) %}
  {% set max_years = var('max_simulation_years', 20) %}

  {# Validate year is not in the past relative to start #}
  {% if current_year < start_year %}
    {% set message = "Simulation year " ~ current_year ~ " cannot be before start year " ~ start_year %}
    {{ exceptions.raise_compiler_error(message) }}
  {% endif %}

  {# Validate year is within reasonable range #}
  {% if current_year > start_year + max_years %}
    {% set message = "Simulation year " ~ current_year ~ " exceeds maximum range (" ~ max_years ~ " years from " ~ start_year ~ ")" %}
    {{ exceptions.raise_compiler_error(message) }}
  {% endif %}

  {{ return(current_year) }}
{% endmacro %}

{#
  Macro to validate configuration consistency

  Usage:
    {{ validate_config_consistency() }}
#}

{% macro validate_config_consistency() %}

  {# Validate growth and termination rates make sense together #}
  {% set growth_rate = var('target_growth_rate', 0.03) %}
  {% set termination_rate = var('total_termination_rate', 0.12) %}
  {% set new_hire_term_rate = var('new_hire_termination_rate', 0.25) %}

  {# Growth rate should be reasonable #}
  {% if growth_rate < -0.50 or growth_rate > 1.0 %}
    {{ exceptions.raise_compiler_error("Growth rate " ~ growth_rate ~ " is outside reasonable range (-50% to 100%)") }}
  {% endif %}

  {# Termination rate should be reasonable #}
  {% if termination_rate < 0.01 or termination_rate > 0.80 %}
    {{ exceptions.raise_compiler_error("Termination rate " ~ termination_rate ~ " is outside reasonable range (1% to 80%)") }}
  {% endif %}

  {# New hire termination should be higher than general termination #}
  {% if new_hire_term_rate < termination_rate %}
    {{ log("Warning: New hire termination rate (" ~ new_hire_term_rate ~ ") is lower than general rate (" ~ termination_rate ~ ")", info=true) }}
  {% endif %}

  {# Growth + termination should require reasonable hiring rates #}
  {% set required_hiring_rate = growth_rate + termination_rate %}
  {% if required_hiring_rate > 0.50 %}
    {{ log("Warning: Required hiring rate (" ~ required_hiring_rate ~ ") is very high. Consider adjusting growth or termination rates.", info=true) }}
  {% endif %}

{% endmacro %}
```

#### `dbt/macros/simulation_helpers.sql` - Business Logic Utilities

```sql
{#
  Calculate age band from birth year and current year

  Usage:
    {{ get_age_band('birth_year', 2024) }}
#}

{% macro get_age_band(birth_year_col, current_year=none) %}
  {% set year = current_year or var('current_simulation_year', 2024) %}

  CASE
    WHEN {{ year }} - {{ birth_year_col }} < 25 THEN '< 25'
    WHEN {{ year }} - {{ birth_year_col }} < 30 THEN '25-29'
    WHEN {{ year }} - {{ birth_year_col }} < 35 THEN '30-34'
    WHEN {{ year }} - {{ birth_year_col }} < 40 THEN '35-39'
    WHEN {{ year }} - {{ birth_year_col }} < 45 THEN '40-44'
    WHEN {{ year }} - {{ birth_year_col }} < 50 THEN '45-49'
    WHEN {{ year }} - {{ birth_year_col }} < 55 THEN '50-54'
    WHEN {{ year }} - {{ birth_year_col }} < 60 THEN '55-59'
    WHEN {{ year }} - {{ birth_year_col }} < 65 THEN '60-64'
    ELSE '65+'
  END
{% endmacro %}

{#
  Calculate tenure band from hire date and current date

  Usage:
    {{ get_tenure_band('hire_date', '2024-12-31') }}
#}

{% macro get_tenure_band(hire_date_col, current_date=none) %}
  {% set ref_date = current_date or "'" ~ var('current_simulation_year') ~ "-12-31'" %}

  CASE
    WHEN DATEDIFF('month', {{ hire_date_col }}, {{ ref_date }}) < 6 THEN '< 6 months'
    WHEN DATEDIFF('month', {{ hire_date_col }}, {{ ref_date }}) < 12 THEN '6-12 months'
    WHEN DATEDIFF('month', {{ hire_date_col }}, {{ ref_date }}) < 24 THEN '1-2 years'
    WHEN DATEDIFF('month', {{ hire_date_col }}, {{ ref_date }}) < 60 THEN '2-5 years'
    WHEN DATEDIFF('month', {{ hire_date_col }}, {{ ref_date }}) < 120 THEN '5-10 years'
    WHEN DATEDIFF('month', {{ hire_date_col }}, {{ ref_date }}) < 240 THEN '10-20 years'
    ELSE '20+ years'
  END
{% endmacro %}

{#
  Apply cost of living adjustment to salary

  Usage:
    {{ apply_cola('current_salary', 0.025) }}
#}

{% macro apply_cola(salary_col, cola_rate=none) %}
  {% set rate = cola_rate or var('cola_rate', 0.025) %}

  ROUND({{ salary_col }} * (1 + {{ rate }}), 2)
{% endmacro %}

{#
  Calculate promotion salary increase

  Usage:
    {{ calculate_promotion_salary('current_salary', 'from_level', 'to_level') }}
#}

{% macro calculate_promotion_salary(salary_col, from_level_col, to_level_col) %}
  {% set base_increase = var('promotion_base_increase', 0.15) %}

  ROUND(
    {{ salary_col }} * (
      1 + {{ base_increase }} +
      ({{ to_level_col }} - {{ from_level_col }}) * 0.05  -- Additional 5% per level jump
    ), 2
  )
{% endmacro %}

{#
  Generate employee ID with prefix and padding

  Usage:
    {{ generate_employee_id('prefix', 'sequence_number') }}
#}

{% macro generate_employee_id(prefix, sequence_col, padding=6) %}
  CONCAT(
    '{{ prefix }}',
    LPAD(CAST({{ sequence_col }} AS VARCHAR), {{ padding }}, '0')
  )
{% endmacro %}

{#
  Calculate business days between dates (approximate)

  Usage:
    {{ business_days_between('start_date', 'end_date') }}
#}

{% macro business_days_between(start_date_col, end_date_col) %}
  -- Approximate business days (excludes weekends, not holidays)
  CASE
    WHEN {{ start_date_col }} IS NULL OR {{ end_date_col }} IS NULL THEN NULL
    ELSE FLOOR(
      DATEDIFF('day', {{ start_date_col }}, {{ end_date_col }}) * 5.0 / 7.0
    )
  END
{% endmacro %}

{#
  Format currency for display

  Usage:
    {{ format_currency('salary_amount') }}
#}

{% macro format_currency(amount_col, currency_symbol='$') %}
  CONCAT(
    '{{ currency_symbol }}',
    FORMAT(ROUND({{ amount_col }}, 2), '999,999,999.99')
  )
{% endmacro %}

{#
  Calculate percentage change between two values

  Usage:
    {{ percentage_change('old_value', 'new_value') }}
#}

{% macro percentage_change(old_value_col, new_value_col) %}
  CASE
    WHEN {{ old_value_col }} IS NULL OR {{ old_value_col }} = 0 THEN NULL
    ELSE ROUND(
      (({{ new_value_col }} - {{ old_value_col }}) * 100.0 / {{ old_value_col }}), 2
    )
  END
{% endmacro %}

{#
  Create simulation event record structure

  Usage:
    {{ create_event_record('employee_id', 'hire', 'level_id', 'salary') }}
#}

{% macro create_event_record(employee_id_col, event_type, level_col=none, salary_col=none, date_col=none) %}
  SELECT
    {{ employee_id_col }} AS employee_id,
    '{{ event_type }}' AS event_type,
    {{ var('current_simulation_year') }} AS simulation_year,
    {% if level_col %}
      {{ level_col }} AS level_id,
    {% else %}
      NULL AS level_id,
    {% endif %}
    {% if salary_col %}
      {{ salary_col }} AS salary_amount,
    {% else %}
      NULL AS salary_amount,
    {% endif %}
    {% if date_col %}
      {{ date_col }} AS event_date,
    {% else %}
      CURRENT_DATE AS event_date,
    {% endif %}
    CURRENT_TIMESTAMP AS created_at
{% endmacro %}
```

### 2. Database Schema Management

#### Schema Migration Framework
```python
# orchestrator/utils/schema_manager.py

class SchemaManager:
    """Manage database schema evolution and migrations"""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.migration_history = self._load_migration_history()

    def apply_migrations(self, target_version: str = None):
        """Apply pending schema migrations"""
        pending_migrations = self._get_pending_migrations(target_version)

        for migration in pending_migrations:
            self._apply_migration(migration)

    def validate_schema(self) -> Dict[str, Any]:
        """Validate current schema against expected structure"""
        expected_tables = self._get_expected_schema()
        actual_tables = self._get_current_schema()

        return self._compare_schemas(expected_tables, actual_tables)

    def backup_schema(self, backup_name: str = None):
        """Create schema backup before major changes"""
        if backup_name is None:
            backup_name = f"schema_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Implementation for schema backup
        pass
```

### 3. Data Quality Management

#### Comprehensive Data Validation
```python
# orchestrator/utils/data_quality_manager.py

class DataQualityManager:
    """Advanced data quality management and validation"""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.quality_rules = self._load_quality_rules()

    def run_quality_checks(self, table_name: str = None) -> Dict[str, Any]:
        """Run comprehensive data quality checks"""
        if table_name:
            return self._check_single_table(table_name)
        else:
            return self._check_all_tables()

    def auto_clean_data(self, table_name: str, dry_run: bool = True) -> Dict[str, Any]:
        """Automatically clean data quality issues"""
        issues = self._identify_data_issues(table_name)

        if dry_run:
            return self._simulate_cleaning(issues)
        else:
            return self._apply_cleaning(issues)

    def generate_quality_report(self) -> str:
        """Generate comprehensive data quality report"""
        quality_metrics = self.run_quality_checks()
        return self._format_quality_report(quality_metrics)
```

### 4. Performance Optimization

#### Query Performance Analysis
```python
# orchestrator/utils/performance_optimizer.py

class PerformanceOptimizer:
    """Database and query performance optimization"""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.performance_history = []

    def analyze_query_performance(self, query: str) -> Dict[str, Any]:
        """Analyze query execution performance"""
        explain_plan = self._get_explain_plan(query)
        execution_stats = self._execute_with_timing(query)

        return {
            'execution_time': execution_stats['duration'],
            'rows_processed': execution_stats['row_count'],
            'memory_usage': execution_stats['memory_mb'],
            'explain_plan': explain_plan,
            'optimization_suggestions': self._generate_suggestions(explain_plan)
        }

    def optimize_table_structure(self, table_name: str) -> List[str]:
        """Suggest table structure optimizations"""
        table_stats = self._analyze_table_usage(table_name)
        return self._suggest_optimizations(table_stats)

    def create_recommended_indexes(self, table_name: str, dry_run: bool = True):
        """Create recommended indexes for performance"""
        index_recommendations = self._analyze_index_opportunities(table_name)

        if dry_run:
            return index_recommendations
        else:
            return self._create_indexes(index_recommendations)
```

### 5. Data Archive and Retention

#### Lifecycle Management
```python
# orchestrator/utils/data_lifecycle_manager.py

class DataLifecycleManager:
    """Manage data retention and archival policies"""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.retention_policies = config['retention_policies']
        self.archive_config = config['archive_config']

    def apply_retention_policies(self, dry_run: bool = True) -> Dict[str, Any]:
        """Apply data retention policies"""
        actions = []

        for table, policy in self.retention_policies.items():
            expired_data = self._identify_expired_data(table, policy)

            if expired_data:
                if policy['action'] == 'archive':
                    actions.append(self._archive_data(table, expired_data, dry_run))
                elif policy['action'] == 'delete':
                    actions.append(self._delete_data(table, expired_data, dry_run))

        return {'actions': actions, 'dry_run': dry_run}

    def archive_simulation_results(self, simulation_id: str,
                                 compression: bool = True) -> str:
        """Archive specific simulation results"""
        archive_path = self._create_archive_path(simulation_id)

        # Export simulation data
        tables_to_archive = [
            'fct_workforce_snapshot',
            'fct_yearly_events',
            'mart_workforce_summary'
        ]

        for table in tables_to_archive:
            self._export_table_data(table, archive_path, simulation_id, compression)

        return archive_path
```

## Configuration Management

### Data Management Configuration
```yaml
# config/data_management_config.yaml
data_quality:
  validation_rules:
    employee_id:
      - not_null
      - unique
      - format: "^[A-Z]{2}\\d{6}$"

    salary:
      - not_null
      - range: [30000, 500000]
      - data_type: "numeric"

    simulation_year:
      - not_null
      - range: [2020, 2040]

retention_policies:
  fct_workforce_snapshot:
    retention_period: "7 years"
    action: "archive"

  fct_yearly_events:
    retention_period: "10 years"
    action: "archive"

  monitoring_logs:
    retention_period: "1 year"
    action: "delete"

performance_optimization:
  auto_index_creation: true
  query_timeout: 300  # seconds
  memory_limit: "8GB"

archive_settings:
  compression: true
  format: "parquet"
  storage_location: "data/archives"
  encryption: false
```

## Usage Examples

### Schema Management
```bash
# Apply pending migrations
python scripts/manage_schema.py --migrate

# Validate current schema
python scripts/manage_schema.py --validate

# Backup schema before changes
python scripts/manage_schema.py --backup --name "pre_v2_upgrade"
```

### Data Quality Management
```bash
# Run quality checks
python scripts/data_quality_check.py --table fct_workforce_snapshot

# Generate quality report
python scripts/data_quality_check.py --report --output quality_report.html

# Auto-clean data issues (dry run)
python scripts/data_quality_check.py --clean --dry-run
```

### Performance Optimization
```bash
# Analyze query performance
python scripts/optimize_performance.py --analyze-query "SELECT * FROM fct_workforce_snapshot"

# Create recommended indexes
python scripts/optimize_performance.py --create-indexes --table fct_workforce_snapshot

# Performance monitoring
python scripts/optimize_performance.py --monitor --duration 1h
```

## Dependencies

### External Libraries
- `alembic` - Database migrations
- `sqlparse` - SQL parsing and analysis
- `psutil` - System performance monitoring
- `pandas` - Data manipulation and analysis

### Internal Dependencies
- Database connection utilities
- Configuration management
- Logging and monitoring systems
- Security and access control

## Related Files

### Core Infrastructure
- Database connection and utilities
- Configuration management system
- Logging and monitoring components

### Schema Definitions
- dbt model definitions
- Database table schemas
- Migration scripts and history

## Implementation Notes

### Best Practices
1. **Version Control**: Track all schema changes and migrations
2. **Testing**: Validate all data operations in staging environments
3. **Performance**: Monitor and optimize query performance regularly
4. **Security**: Implement proper access controls and data encryption
5. **Documentation**: Maintain comprehensive documentation of data structures

### Security Considerations
- Implement row-level security where appropriate
- Use encryption for sensitive data at rest and in transit
- Audit all data access and modifications
- Implement proper backup and disaster recovery procedures

### Maintenance Guidelines
- Regular performance monitoring and optimization
- Scheduled data quality checks and cleanup
- Periodic schema validation and optimization
- Archive old data according to retention policies
- Monitor storage usage and implement cleanup procedures
