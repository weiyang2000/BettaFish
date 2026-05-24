# BettaFish SaaS Frontend Integration Notes

This note is the handoff between the Next.js console and the backend migration.
The canonical API contract is `docs/openapi/saas-platform.yaml`; this file
summarizes how the service-layer adapter maps existing engine capabilities into
that contract and where mock data is used by `apps/web`.

## Runtime Model

- Frontend base URL: `NEXT_PUBLIC_API_BASE_URL`.
- Local mock mode: leave `NEXT_PUBLIC_API_BASE_URL` empty or set
  `NEXT_PUBLIC_USE_MOCKS=true`.
- Workspace scope: every backend request must accept `X-Workspace-Id`.
- User scope: request bodies include an `owner` or `updatedBy` placeholder so
  SaaS identity can be added without changing the frontend shape later.

## Legacy to SaaS API Mapping

| SaaS path | Legacy source today | Backend note |
| --- | --- | --- |
| `GET /api/v1/system/components` | Engine facade runtime state | Normalize `insight`, `media`, `query`, `forum`, `report`, `mindspider`, and `database` into `SystemComponent[]`; component ports are optional infrastructure metadata, not page routes. |
| `POST /api/v1/system/components/{id}:start` | Engine facade runtime action | Prefer POST. Component-level and full-system starts can share the same handler. |
| `POST /api/v1/system/components/{id}:stop` | Engine facade runtime action | Return `202` once stop is requested; do not block on long process cleanup. |
| `GET /api/v1/system/config` | `GET /api/config` | Return config as field metadata and mask sensitive fields. |
| `PATCH /api/v1/system/config` | `POST /api/config` | Ignore masked placeholders like `********`; never persist masked values as real secrets. |
| `GET /api/v1/logs` | `GET /api/output/{app}`, `GET /api/forum/log`, `GET /api/report/log` | Add `source`, `level`, `tail`, and cursor support. |
| `POST /api/v1/search` | `POST /api/search` | Return an accepted search run and track ownership/workspace. |
| `POST /api/v1/report-tasks` | `POST /api/report/generate` | Convert `topic` to legacy `query`; keep `templateId` for the new engine. |
| `GET /api/v1/report-tasks/{id}` | `GET /api/report/progress/{task_id}` | Map legacy `completed` to SaaS `succeeded`, `error` to `failed`. |
| `GET /api/v1/report-tasks/{id}/events` | `GET /api/report/stream/{task_id}` | Keep SSE payloads JSON. Preserve `Last-Event-ID` resume behavior. |
| `GET /api/v1/report-tasks/{id}/result` | `GET /api/report/result/{task_id}/json` | Prefer metadata plus preview URL; inline HTML is optional. |
| `GET /api/v1/report-tasks/{id}/exports/{format}` | `GET /api/report/download/{id}`, `/export/md/{id}`, `/export/pdf/{id}` | Use `html`, `md`, and `pdf` format path values. |
| `POST /api/v1/report-tasks/{id}:cancel` | `POST /api/report/cancel/{task_id}` | Return the updated task. |
| `POST /api/v1/crawler-tasks` | `MindSpider.run_*` methods | New backend task wrapper needed; current crawler is synchronous library/CLI code. |
| `GET/PUT /api/v1/platforms/{id}/policy` | `PlatformCrawler.create_base_config` and config files | Store SaaS policy separately; render MediaCrawler config at execution time. |
| `GET/POST/DELETE /api/v1/platforms/{id}/identity-lists` | Not present | New persistence needed for user ID allow/block rules. |

## Status Enums

Frontend task chips expect these values:

- Reports: `queued`, `pending`, `running`, `succeeded`, `failed`, `cancelled`.
- Crawlers: `queued`, `pending`, `running`, `succeeded`, `failed`, `stopping`,
  `stopped`, `cancelled`.
- Components: `unknown`, `stopped`, `starting`, `running`, `degraded`,
  `failed`, `stopping`.

Legacy adapter mapping:

- `completed` -> `succeeded`
- `error` -> `failed`
- missing or cleaned report task -> backend should return `NOT_FOUND` unless a
  durable task table can prove it succeeded.

## Error Codes

Use the `ErrorResponse` shape from the OpenAPI document. High-value codes for
the first backend pass:

- `ENGINE_NOT_READY`: required input files or engine components are missing.
- `TASK_ALREADY_RUNNING`: current single-task ReportEngine limit is hit.
- `TASK_NOT_CANCELLABLE`: task is terminal or not owned by the workspace.
- `EXPORT_UNAVAILABLE`: requested artifact cannot be produced.
- `DEPENDENCY_MISSING`: PDF export dependencies such as Pango are unavailable.
- `VALIDATION_ERROR`: invalid policy, config key, or task payload.

## SSE Event Format

The stream endpoint is `GET /api/v1/report-tasks/{taskId}/events`.

```text
id: 17
event: progress
data: {"id":"17","type":"progress","taskId":"report_001","timestamp":"2026-05-22T10:10:00Z","payload":{"status":"running","progress":52,"stage":"agent_running","message":"Generating chapter 3"}}
```

Supported `type` values are `status`, `progress`, `stage`, `log`, `warning`,
`html_ready`, `completed`, `error`, `cancelled`, and `heartbeat`.

## Sensitive Config Handling

Sensitive keys include any key ending with `API_KEY`, `PASSWORD`, `SECRET`, or
`TOKEN`. Backend responses must return masked values only, for example
`********`. The frontend does not print submitted secret values to logs or page
state. If a config update body omits a sensitive field, the backend should keep
the current value. If the body contains the mask placeholder, the backend should
also keep the current value.

## Mock Boundary

`apps/web/src/lib/openapi-client.ts` is the only integration boundary used by
the frontend components. It calls real OpenAPI paths when
`NEXT_PUBLIC_API_BASE_URL` is set and mock mode is not enabled. Otherwise it
returns deterministic mock data from `apps/web/src/lib/mock-data.ts`. The mock
adapter exists only to make the console reviewable before the backend task API
and platform identity persistence are implemented.
