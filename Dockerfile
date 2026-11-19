# Image for the AI Ticket Triage API (and the batch / evaluation commands).
FROM python:3.12-slim

# Print logs immediately, and don't write .pyc files into the image
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Dependencies first: this layer is cached and only rebuilt when requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Then the code and the sample data (changes often, cheap to rebuild)
COPY app/ app/
COPY data/ data/

# 3. Run as a normal user, not root, and keep the database in its own folder (mounted as a volume)
RUN useradd --create-home appuser \
    && mkdir -p /app/storage \
    && chown appuser /app/storage
USER appuser
ENV DATABASE_PATH=/app/storage/tickets.db

EXPOSE 8000

# Docker marks the container "unhealthy" if /health stops answering
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]