FROM bitnami/spark:latest

# Ensure Python and common libs are available
USER root
RUN install_packages python3 python3-pip && \
    pip3 install --no-cache-dir psycopg2-binary requests

# Optional: copy spark-defaults.conf
COPY spark-defaults.conf /opt/bitnami/spark/conf/spark-defaults.conf

USER 1001