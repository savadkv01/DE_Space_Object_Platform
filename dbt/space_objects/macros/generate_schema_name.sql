-- Override dbt's default schema name generation.
-- When a model has a custom +schema config, use it directly (ignore profile base schema).
-- This ensures gold models land in 'gold', silver models in 'silver', etc.

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema | trim }}
    {%- endif -%}
{%- endmacro %}
