# syntax=docker/dockerfile:1

# ---------- ступень 1: base — общий фундамент ----------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Сначала только список зависимостей: слой с pip install переиспользуется
# из кэша, пока requirements.txt не изменится.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt


# ---------- ступень 2: test — образ для прогона тестов ----------
FROM base AS test

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .
RUN mkdir -p /app/reports
ENV APP_ENV=test

CMD ["pytest", "-v", \
     "--junitxml=/app/reports/junit.xml", \
     "--cov=app", "--cov-report=xml:/app/reports/coverage.xml", \
     "--cov-report=term"]


# ---------- ступень 3: runtime — развёртываемый артефакт ----------
FROM base AS runtime

ARG APP_VERSION=1.0.0
ARG BUILD_NUMBER=0
ARG GIT_COMMIT=unknown

# ARG живёт только во время сборки; ENV закрепляет значение в образе,
# чтобы приложение прочитало его через os.environ во время работы.
ENV APP_VERSION=${APP_VERSION} \
    BUILD_NUMBER=${BUILD_NUMBER} \
    GIT_COMMIT=${GIT_COMMIT} \
    APP_ENV=local \
    APP_PORT=8000

LABEL project="pract4" \
      org.opencontainers.image.title="flask-cicd-demo" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser app.py ./
COPY --chown=appuser:appuser templates ./templates

USER appuser

EXPOSE 8000

# В python:slim нет curl, поэтому проверка написана на стандартной библиотеке.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# exec form: gunicorn становится PID 1 и получает SIGTERM при docker stop.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", \
     "--access-logfile", "-", "--error-logfile", "-", "app:app"]
