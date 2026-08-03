{%- macro subsystem_seed(subsystem) -%}{{ var('random_seed_' ~ subsystem, var('random_seed', 42)) }}{%- endmacro -%}
