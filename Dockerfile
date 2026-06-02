FROM python:3.12-slim

# Install core runtime dependencies, including PostgreSQL libraries and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    curl \
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

EXPOSE 4455