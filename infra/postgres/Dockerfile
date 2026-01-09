FROM postgres:15

ENV POSTGRES_USER=${POSTGRES_USER}
ENV POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
ENV POSTGRES_DB=${POSTGRES_DB}

# Initialization scripts (e.g., create schemas bronze/silver/gold)
COPY init.sql /docker-entrypoint-initdb.d/init.sql