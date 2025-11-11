# syntax=docker/dockerfile:1.4
FROM python:3.11-slim as builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/app
COPY worker/requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim as runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --shell /bin/bash appuser

WORKDIR /srv/app
ENV PATH="/home/appuser/.local/bin:${PATH}" \
    PYTHONPATH=/srv/app

COPY --from=builder /wheels /wheels
COPY --from=builder /tmp/app/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --find-links=/wheels -r /tmp/requirements.txt

COPY backend/app ./app
COPY worker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chown -R appuser:appuser /srv/app /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=40s CMD celery -A app.tasks inspect ping | grep -qi 'OK'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info"]
