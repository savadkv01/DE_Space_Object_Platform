from pyspark.sql import SparkSession


def main():
    spark = (
        SparkSession.builder
        .appName("spark-connectivity-test")
        .master("spark://spark-master:7077")
        .config("spark.jars.packages", "org.postgresql:postgresql:42.7.3")
        .getOrCreate()
    )

    url = "jdbc:postgresql://postgres:5432/space_warehouse"
    props = {
        "user": "space_user",
        "password": "space_password",
        "driver": "org.postgresql.Driver",
    }

    df = spark.createDataFrame([(1, "test"), (2, "spark")], ["id", "value"])

    df.write.mode("overwrite").jdbc(
        url=url,
        table="meta.spark_connectivity_test",
        properties=props,
    )

    df_read = spark.read.jdbc(url=url, table="meta.spark_connectivity_test", properties=props)
    df_read.show()

    spark.stop()


if __name__ == "__main__":
    main()
