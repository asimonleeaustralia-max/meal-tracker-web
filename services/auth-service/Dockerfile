# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared lib first so it's cached separately from service code
COPY libs/shared /libs/shared
RUN pip install /libs/shared

# Service-specific deps
COPY services/auth-service/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Service code
COPY services/auth-service/app ./app
COPY services/auth-service/alembic ./alembic
COPY services/auth-service/alembic.ini ./alembic.ini

# Non-root user
RUN useradd --uid 1000 --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8001/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
