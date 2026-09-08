FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY run.py .
ENV FLASK_ENV=production FLASK_DEBUG=false PORT=8080
RUN useradd --create-home appuser && mkdir -p /app/.runtime && chown appuser:appuser /app/.runtime
USER appuser
EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 300 run:app"]
