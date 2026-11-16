# AGRI-SENSE API (Phase 20). Build from the backend/ directory: docker build -t agri-sense-api backend
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
# Model files present in the build context are used as-is (the two disease models are converted locally and
# are not downloadable). The produce model is fetched and checksum-verified if it is missing.
COPY ml_models ./ml_models
RUN python -m app.cli.fetch_models

RUN useradd --create-home --uid 10001 agrisense && mkdir -p /app/uploads && chown -R agrisense /app/uploads
USER agrisense

ENV APP_ENV=production PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/v1/health', timeout=4)"
# Apply migrations, then serve. --proxy-headers so rate limiting sees the real client IP behind a load balancer.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --workers 1"]
