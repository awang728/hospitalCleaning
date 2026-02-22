# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# ── Generate proto stubs if vectorai.proto is present ─────────────────────────
# (run this manually if you have the proto file)
# RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. vectorai.proto

EXPOSE 8080

# Use gunicorn in production (4 workers on a Vultr 4-core instance)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", \
     "--timeout", "120", "--access-logfile", "-", "app:app"]
