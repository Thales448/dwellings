# 1 — build the web app
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# 2 — build Python wheels
FROM python:3.12-slim AS py
WORKDIR /api
RUN pip install --no-cache-dir uv
COPY api/pyproject.toml api/uv.lock ./
RUN uv export --frozen --no-dev --no-hashes > req.txt && pip wheel --no-cache-dir -r req.txt -w /wheels

# 3 — runtime
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libwebp7 tini sqlite3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -r -u 10001 -d /data dwellings \
 && mkdir -p /data && chown dwellings:dwellings /data
COPY --from=py /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /app
COPY api/ /app/
COPY --from=web /web/build /app/static
ENV DATA_DIR=/data DATABASE_URL=sqlite:////data/dwellings.db PORT=8080 PYTHONUNBUFFERED=1
VOLUME ["/data"]
USER dwellings
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health').status==200 else 1)"
ENTRYPOINT ["tini","--"]
CMD ["sh","-c","python -m app.cli migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*' --workers 1"]
