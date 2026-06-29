FROM apache/airflow:2.10.4

# dbt-duckdb + proje bağımlılıkları; airflow kullanıcısı olarak kur
USER airflow

RUN pip install --no-cache-dir \
    "dbt-duckdb==1.10.1" \
    "duckdb==1.5.4" \
    "pandas>=2.0" \
    "pyarrow>=10.0" \
    "requests>=2.28"
