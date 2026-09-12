FROM node:20-alpine AS frontend-build

WORKDIR /frontend

COPY consensus-command-main/package*.json ./
RUN npm ci

COPY consensus-command-main ./
RUN npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY config ./config
COPY --from=frontend-build /frontend/dist ./frontend-dist

ENV PYTHONPATH=/app
ENV FRONTEND_DIST_DIR=/app/frontend-dist

# Run as a non-root user so files written into the bind-mounted ./data
# volume (event logs, etc.) are owned by a normal user on the host instead
# of root. Override APP_UID/APP_GID at build time if they don't match your
# host user (see .env.example).
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" appuser \
    && useradd -m -u "${APP_UID}" -g appuser appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.qconsensus.web:app", "--host", "0.0.0.0", "--port", "8000"]
