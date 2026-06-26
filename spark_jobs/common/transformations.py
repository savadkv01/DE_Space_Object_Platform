from pyspark.sql.functions import col, lower, trim, from_json
from pyspark.sql.types import DoubleType


def normalize_string(col_name):
    return lower(trim(col(col_name)))


def extract_json_double(json_col, json_path):
    return col(json_col).getItem(json_path).cast(DoubleType())


def assert_not_null(df, column):
    if df.filter(col(column).isNull()).count() > 0:
        raise ValueError(f"Null values detected in {column}")
