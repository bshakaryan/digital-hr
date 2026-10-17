# Single web-container demo with an external PostgreSQL database.
# The existing compose.yaml continues to run separate services with PostgreSQL.
FROM node:22-bookworm-slim AS frontend-dependencies
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM frontend-dependencies AS frontend-build
ENV NEXT_TELEMETRY_DISABLED=1 API_INTERNAL_URL=http://127.0.0.1:8000 DOCUMENTOLOG_PROXY_ORIGIN=http://127.0.0.1:8400
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=10000 DATA_DIR=/var/data PYTHONPATH=/app/backend
WORKDIR /app/backend
COPY backend/requirements.lock ./requirements.lock
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.lock \
    && useradd --uid 1000 --create-home jana \
    && mkdir -p /var/data /app/web \
    && chown jana:jana /var/data /app/web
COPY --from=frontend-dependencies /usr/local/bin/node /usr/local/bin/node
COPY backend/ ./
COPY --from=frontend-build --chown=jana:jana /web/.next/standalone /app/web/
COPY --from=frontend-build --chown=jana:jana /web/.next/static /app/web/.next/static/
COPY --from=frontend-build --chown=jana:jana /web/public /app/web/public/
COPY scripts/start-web.py /app/start-web.py
EXPOSE 10000
CMD ["python", "/app/start-web.py"]
