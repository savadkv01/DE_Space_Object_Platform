-- dbt/space_objects/macros/util.sql

{% macro is_hazardous_flag(col_name) %}
    case when {{ col_name }} then 1 else 0 end
{% endmacro %}
