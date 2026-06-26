FROM apache/airflow:2.8.3-python3.11

# ---------------------------------------------------------
# System-level deps: Java + curl + Spark client
# ---------------------------------------------------------
USER root

# Install Java (needed for Spark) and curl
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Spark client installation
ENV SPARK_VERSION=3.5.5
ENV HADOOP_VERSION=3
ENV SPARK_HOME=/opt/spark
ENV PATH="${PATH}:${SPARK_HOME}/bin"
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

RUN curl -L -o /tmp/spark.tgz \
      https://dlcdn.apache.org/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz && \
    mkdir -p /opt && \
    tar -xzf /tmp/spark.tgz -C /opt && \
    mv /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} ${SPARK_HOME} && \
    rm /tmp/spark.tgz

# ---------------------------------------------------------
# Python-level deps: project requirements + dbt
# ---------------------------------------------------------
USER airflow

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt && \
    pip install --no-cache-dir \
        dbt-core==1.8.2 \
        dbt-postgres==1.8.2
