FROM python:3.12-slim-bookworm
ARG VCS_REF=local
LABEL org.opencontainers.image.revision=$VCS_REF
WORKDIR /opt/apps/inventarios-uno-a-uno
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production AUTH_ENABLED=true SESSION_COOKIE_SECURE=true FLASK_ENV=production FLASK_DEBUG=false
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --no-create-home appuser \
    && mkdir -p /var/lock/inventarios-uno-a-uno .runtime \
    && chown 10001:10001 /var/lock/inventarios-uno-a-uno .runtime
COPY app ./app
COPY scripts/*.py ./scripts/
COPY wsgi.py ./
USER 10001:10001
# Linux host networking. One worker is required by the in-memory SSO replay cache.
CMD ["gunicorn", "--bind", "127.0.0.1:8000", "--workers", "1", "--threads", "4", "--timeout", "300", "--graceful-timeout", "300", "--access-logfile", "-", "--access-logformat", "%(h)s %(m)s %(U)s %(s)s", "--error-logfile", "-", "wsgi:app"]
