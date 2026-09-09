FROM python:3.12-slim
WORKDIR /opt/apps/inventarios-uno-a-uno
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY wsgi.py .
ENV APP_ENV=production AUTH_ENABLED=true SESSION_COOKIE_SECURE=true FLASK_ENV=production FLASK_DEBUG=false
RUN useradd --create-home appuser && mkdir -p .runtime && chown appuser:appuser .runtime
USER appuser
# Alternative only with host networking on Linux; the manual deployment uses systemd.
CMD ["gunicorn", "--bind", "127.0.0.1:8000", "--workers", "1", "--threads", "4", "--timeout", "300", "wsgi:app"]
