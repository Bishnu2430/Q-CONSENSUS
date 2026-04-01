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
COPY data ./data
COPY --from=frontend-build /frontend/dist ./frontend-dist

ENV PYTHONPATH=/app
ENV FRONTEND_DIST_DIR=/app/frontend-dist

EXPOSE 8000

CMD ["uvicorn", "src.qconsensus.web:app", "--host", "0.0.0.0", "--port", "8000"]
