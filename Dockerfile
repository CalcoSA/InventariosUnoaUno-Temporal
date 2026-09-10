FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-lock.txt ./

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-lock.txt \
    && python -m pip install gunicorn==23.0.0

COPY . .

RUN mkdir -p /app/.runtime \
    && groupadd --gid 10001 appgroup \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-create-home \
        --shell /usr/sbin/nologin \
        appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD [
    "gunicorn",
    "--bind", "0.0.0.0:8000",
    "--workers", "1",
    "--threads", "4",
    "--timeout", "120",
    "--access-logfile", "-",
    "--error-logfile", "-",
    "wsgi:app"
]