# InSite Signs

InSite Signs is a Flask-based application for creating, purchasing, and managing reusable SmartSigns and property marketing pages.

## What This Repository Includes

- Application code (`app.py`, `routes/`, `services/`, `templates/`, `static/`)
- Database migrations (`migrations/`, `migrate.py`, `alembic.ini`)
- Docker runtime files (`Dockerfile`, `docker-compose.yml`)
- Test suite (`tests/`)
- Release and operational scripts (`scripts/`)

## Quick Start (Docker)

```bash
docker compose up -d --build
```

App URL:

```text
http://localhost:8080
```

## Run Tests (Docker)

```bash
bash scripts/run_tests_in_docker.sh
```

## Build Release Artifact

```bash
python scripts/build_release_zip.py
```

The release zip is written to `releases/` and validated by `scripts/validate_release_zip.py`.
