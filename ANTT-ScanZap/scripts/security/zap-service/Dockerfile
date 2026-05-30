# ─────────────────────────────────────────────────────────────────────────────
# ZAP DAST Service — Dockerfile
# Base image: python:3.11-slim
#
# Runtime cần thiết:
#   - bash, curl, python3        → để chạy zap_pipeline.sh
#   - docker CLI                 → để chạy ZAP container từ bên trong service
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        curl \
        ca-certificates \
        gnupg \
        lsb-release \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/debian \
        $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY app/ ./app/

# ── ZAP Scripts (mount lúc runtime hoặc COPY vào đây) ────────────────────────
# Thư mục này sẽ chứa: zap_pipeline.sh, zap_utils.py, automation.yaml.tpl,
#                       postman_collection.json, zap_logger.js
# Mặc định sẽ được mount từ host qua docker-compose volume.
RUN mkdir -p /app/zap-scripts /app/workspace

# ── Port ──────────────────────────────────────────────────────────────────────
EXPOSE 8080

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# ── Start ─────────────────────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
