FROM python:3.12-slim

# Install core runtime dependencies, including CA Certificates for SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    curl \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Prevent Python from writing .pyc artifacts and enable real-time log printing
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cache and build dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bind full application source files
COPY . .

# EXPOSE is kept for documentation of the API port
EXPOSE 4455

# Set entrypoint to run your celery worker
CMD ["celery", "-A", "app.celery_app.celery_app", "worker", "--loglevel=info", "--concurrency=2"]