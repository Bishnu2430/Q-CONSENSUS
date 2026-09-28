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

# Run as a non-root user. Only /app/data (bind-mounted from ./data) needs to
# be writable; the code stays root-owned and read-only.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" appuser \
    && useradd -m -u "${APP_UID}" -g appuser appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data
USER appuser

# Pre-fetch the Solidity compiler used by scripts/deploy_contract.py, so the
# launcher can deploy the anchor contract from this image (no Python needed
# on the host, and no download at deploy time).
RUN python -c "import solcx; solcx.install_solc('0.8.17')"

COPY scripts/deploy_contract.py ./scripts/
COPY src ./src
COPY config ./config
COPY --from=frontend-build /frontend/dist ./frontend-dist

ENV PYTHONPATH=/app
ENV FRONTEND_DIST_DIR=/app/frontend-dist

EXPOSE 8000

CMD ["uvicorn", "src.qconsensus.web:app", "--host", "0.0.0.0", "--port", "8000"]
