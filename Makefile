.PHONY: dev test lint build run

dev:
	cd api && uv run uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload

test:
	cd api && uv run pytest
	cd web && npm test

lint:
	cd api && uv run ruff check . && uv run mypy app
	cd web && npm run check

build:
	docker build -t dwellings:local .

run: build
	docker compose up
