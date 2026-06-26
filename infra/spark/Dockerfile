FROM apache/spark:3.5.5-scala2.12-java17-python3-ubuntu

USER root

# Python packages needed for Spark job drivers
RUN pip3 install --no-cache-dir psycopg2-binary requests

# PostgreSQL JDBC driver — placed in Spark's jars directory so it's on classpath
RUN curl -L -o /opt/spark/jars/postgresql-42.7.3.jar \
    https://jdbc.postgresql.org/download/postgresql-42.7.3.jar

COPY spark-defaults.conf /opt/spark/conf/spark-defaults.conf

USER spark
