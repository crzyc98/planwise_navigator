{% macro duckdb__alter_column_type(relation, column_name, new_column_type) %}
  {% if config.get('materialized') == 'incremental' %}
    {# DuckDB 1.5 rejects dbt's add/update/drop/rename emulation at COMMIT.
       Native ALTER runs before any incremental strategy modifies rows. #}
    {% call statement('alter_column_type') %}
      ALTER TABLE {{ relation }} ALTER COLUMN {{ adapter.quote(column_name) }}
      TYPE {{ new_column_type }};
    {% endcall %}
  {% else %}
    {{ return(dbt.default__alter_column_type(relation, column_name, new_column_type)) }}
  {% endif %}
{% endmacro %}


{% macro get_incremental_replace_simulation_year_sql(arg_dict) %}
  {# dbt has finished schema synchronization before calling this strategy.
     Keep deletion and insertion in the same transaction, including empty years. #}
  {% set scope = config.get('year_partition_scope', 'scenario') %}
  {% if scope not in ['scenario', 'year'] %}
    {{ exceptions.raise_compiler_error('Unsupported year_partition_scope: ' ~ scope) }}
  {% endif %}
  {% set simulation_year = var('simulation_year') %}
  DELETE FROM {{ arg_dict['target_relation'] }}
  WHERE simulation_year = {{ simulation_year }}
  {% if scope == 'scenario' %}
    AND scenario_id = '{{ var("scenario_id", "default") | replace("'", "''") }}'
  {% endif %};

  {{ get_insert_into_sql(arg_dict['target_relation'], arg_dict['temp_relation'], arg_dict['dest_columns']) }}
{% endmacro %}
