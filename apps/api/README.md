# BettaFish SaaS API

This FastAPI service implements the backend boundary described in
`docs/openapi/saas-platform.yaml`.

## Local start

```bash
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

The versioned API base URL is `http://localhost:8000/api/v1`. Every SaaS
request must include `X-Workspace-Id`, for example:

```bash
curl -H "X-Workspace-Id: workspace_demo" \
  http://localhost:8000/api/v1/health
```

By default task workers are not executed, so report and crawler creation only
persists queued tasks. This keeps local development and tests independent from
LLM keys, browser crawlers, and database crawlers. Set
`BETTAFISH_API_RUN_WORKERS=true` to run the deterministic stub workers that
produce placeholder artifacts and status events.

## Persistence

SQLite is used for the first service-layer migration. Override paths with:

```bash
export BETTAFISH_API_DB_PATH=./data/saas_api.sqlite3
export BETTAFISH_API_ARTIFACT_DIR=./data/saas_api_artifacts
```

The migration plan is mirrored in `apps/api/migrations/001_init.sql` and creates
the required SaaS tables:

- `report_tasks`
- `crawler_tasks`
- `crawler_platform_configs`
- `crawler_identity_rules`
- `crawler_strategies`
- `app_configs`
- `task_events`
- `search_runs`

## Frontend and database

The BET-3 frontend calls this service through `NEXT_PUBLIC_API_BASE_URL`, for
example `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`. The repo-level
`python app.py` launcher now starts the same FastAPI service.

For local database-backed crawler work, start the Postgres service from the
repo-level `docker-compose.yml`. The SaaS service itself only needs SQLite for
task/config metadata unless a crawler or engine adapter is enabled.
