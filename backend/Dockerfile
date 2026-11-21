# syntax=docker/dockerfile:1
#
# Two targets:
#   dev   what docker-compose.yml builds: dev tooling installed, source bind-mounted.
#   prod  what .github/workflows/cd.yml publishes: runtime deps only, non-root, build
#         identity baked in so GET /api/v1/version can prove which commit is serving.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# ---------------------------------------------------------------------------------------
FROM base AS dev

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "wsgi:app"]

# ---------------------------------------------------------------------------------------
FROM base AS prod

ARG APP_VERSION=dev
ARG BUILD_SHA=unknown
ARG BUILD_TIME=
ENV APP_VERSION=${APP_VERSION} \
    BUILD_SHA=${BUILD_SHA} \
    BUILD_TIME=${BUILD_TIME} \
    FLASK_ENV=production

RUN useradd --create-home --uid 10001 app

# psycopg[binary] bundles libpq, so no compiler or system libraries are needed here.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY --chown=app:app . .
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status != 200)"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--graceful-timeout", "30", "wsgi:app"]
