{% macro duckdb__alter_column_type(relation, column_name, new_column_type) %}
  {% if config.get('incremental_strategy') == 'replace_event_year' %}
    {# DuckDB 1.5 rejects dbt's add/update/drop/rename emulation at COMMIT.
       Native ALTER runs before the replacement strategy modifies any rows. #}
    {% call statement('alter_column_type') %}
      ALTER TABLE {{ relation }} ALTER COLUMN {{ adapter.quote(column_name) }}
      TYPE {{ new_column_type }};
    {% endcall %}
  {% else %}
    {{ return(dbt.default__alter_column_type(relation, column_name, new_column_type)) }}
  {% endif %}
{% endmacro %}


{% macro get_incremental_replace_event_year_sql(arg_dict) %}
  {# dbt has finished schema synchronization before calling this strategy.
     Keep deletion and insertion in the same transaction, including empty years. #}
  DELETE FROM {{ arg_dict['target_relation'] }}
  WHERE scenario_id = '{{ var("scenario_id", "default") | replace("'", "''") }}'
    AND simulation_year = {{ var('simulation_year', 2025) }};

  {{ get_insert_into_sql(arg_dict['target_relation'], arg_dict['temp_relation'], arg_dict['dest_columns']) }}
{% endmacro %}
