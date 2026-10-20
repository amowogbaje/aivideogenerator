# --- build the React UI ---
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- API + UI in one image ---
FROM python:3.12-slim
# ffmpeg renders the video; fonts-dejavu-core is what the burned-in captions use; espeak-ng = offline fallback voice
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=ui /ui/dist frontend/dist
WORKDIR /app/backend
ENV DATA_DIR=/data DATABASE_URL=sqlite+aiosqlite:////data/studio.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
