FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS backend-builder

WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim AS production

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 ffmpeg && rm -rf /var/lib/apt/lists/*

COPY --from=backend-builder /root/.local /root/.local
COPY backend/ ./
COPY --from=frontend-builder /app/frontend/dist /app/frontend-dist

ENV PATH=/root/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    FRONTEND_DIST_DIR=/app/frontend-dist

RUN mkdir -p /app/uploads && chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
