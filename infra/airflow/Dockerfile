FROM apache/airflow:2.8.3-python3.11

USER airflow

# If you don't have any extra deps yet, this file can even be empty.
# For now we just keep it minimal.
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
