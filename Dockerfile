# Agent Reach — Production Dockerfile (Milestone 8)
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# copy backend
COPY backend/agent\ reach\ core/ /app/backend/
COPY backend/agent-reach-core/ /app/agent-reach-core/

WORKDIR /app/backend/agent_reach

RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install gunicorn

ENV AGENT_REACH_PLUGINS_DIR=/app/plugins \
    PYTHONPATH=/app/backend/agent_reach:/app/agent-reach-core:$PYTHONPATH \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
