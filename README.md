# Dwellings

Multi-tenant listing hunts. One image serves the UI, API, and SQLite database. The architecture lives in [PLAN.md](PLAN.md). This tree currently implements the skeleton (phase 1): the image builds, and `GET /api/v1/health` reports database, disk, and job lag.

## Develop

```bash
cp .env.example .env
# For a checkout on the host, point SQLite at ./data instead of /data:
#   DATA_DIR=./data
#   DATABASE_URL=sqlite:///./data/dwellings.db

cd api && uv sync --group dev
cd ../web && npm ci
make dev
```

API: [http://127.0.0.1:8080/api/v1/health](http://127.0.0.1:8080/api/v1/health). The SvelteKit app is served from `web/build` when that directory exists (`npm run build` in `web/`).

## Checks

```bash
make lint
make test
make build
```

`make build` produces the image. Run it with Compose, which mounts a volume at `/data`:

```bash
docker compose up --build
```

Passkeys and the `__Host-dwl` session cookie require HTTPS on `dwellings.rtech.cloud`. Local HTTP is enough for `/api/v1/health`.

On an empty database, open `/setup?token=…` with `ADMIN_EMAIL` and `ADMIN_BOOTSTRAP_TOKEN` from the environment. After that, new people join by invite. A password reset link is printed inside the container:

```bash
python -m app.cli admin reset-link you@example.com
```
