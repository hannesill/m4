# syntax=docker/dockerfile:1

# Build stage: create wheel
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir build && \
    python -m build --wheel

# Base runtime: install m4 and baked SQLite DB
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    M4_BACKEND=duckdb \
    M4_DB_PATH=/root/m4_data/databases/mimic_iv_demo.db

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Download and initialize demo DB using m4 init
RUN m4 init mimic-iv-demo

# Lite: SQLite only
FROM base AS lite
CMD ["python", "-m", "m4.mcp_server"]

# BigQuery: add GCP client
FROM base AS bigquery
RUN pip install --no-cache-dir google-cloud-bigquery
CMD ["python", "-m", "m4.mcp_server"]
