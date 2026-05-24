# BET-29 Crawler SaaS Startup, Accounts, and Keyword Collection Spec

## Context

用户需求：

1. Docker 启动时同步启动 SaaS 页面。
2. 爬虫引擎需要在界面显示当前账号列表，包括平台、账号状态、账号明细，最好有用户名和头像等基础信息。
3. 爬虫不要按照 broad-topic 收集，而是由用户指定关键词并选择平台进行采集。

现有代码边界：

- SaaS API 入口：`apps/api/main.py`。
- API 契约：`docs/openapi/saas-platform.yaml`。
- SaaS 控制台：`apps/web/src/components/ConsoleShell.tsx`。
- Docker Compose 目前只启动 `api` 和 `db`。
- 爬虫任务已有 SaaS 表和接口骨架：`crawler_tasks`、`crawler_platform_configs`、`crawler_strategies`。
- 当前账号相关能力只有 identity allow/block list，不等同于登录账号列表。
- `MindSpider/DeepSentimentCrawling/platform_crawler.py` 已有 `run_multi_platform_crawl_by_keywords(keywords, platforms, ...)`，可以作为关键词+平台采集的后端适配点。

## Product Behavior

### Docker Startup

`docker compose up` 后应同时启动：

- `api`: FastAPI SaaS service, port `8000`。
- `web`: Next.js SaaS console, port `3000`。
- `db`: Postgres, 保持现状。

浏览器访问 `http://localhost:3000` 应能看到 SaaS 控制台，并通过 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1` 调用本机 API。

### Crawler Accounts

控制台新增账号列表视图，展示所有已登记/已发现的爬虫登录账号：

- 平台：`xhs | dy | ks | bili | wb | tieba | zhihu`。
- 账号标识：平台用户 ID 或登录账号 ID。
- 展示信息：用户名、昵称、头像 URL、主页 URL。
- 状态：`active | login_required | expired | disabled | error | unknown`。
- 运行信息：登录方式、最近登录时间、最近校验时间、错误信息。
- 明细：平台原始字段或运行时状态以 `details` 形式保存，但不能保存 cookie、token、密码等敏感值。

账号列表是“爬虫登录账号”的运行资产，不是 allow/block identity rules。现有 identity rules 保留，用于内容筛选或用户名单控制。

### Keyword And Platform Collection

控制台创建爬虫任务时必须显式提供：

- 关键词列表，至少 1 个，去重并 trim。
- 平台列表，至少 1 个。
- 可选参数：每关键词最大笔记数、每笔记最大评论数、登录方式、headless。

SaaS UI 创建的采集任务不再先运行 BroadTopicExtraction，也不依赖 `daily_topics`。BroadTopicExtraction 可以作为 legacy CLI/运维能力保留，但不应是 SaaS 创建爬虫任务的默认路径。

## API Contract Changes

以 `docs/openapi/saas-platform.yaml` 为唯一契约源，前端先更新契约，后端按契约实现。

### New Schemas

`CrawlerAccountStatus`:

```yaml
type: string
enum: [active, login_required, expired, disabled, error, unknown]
```

`CrawlerAccount`:

```yaml
type: object
required: [id, workspaceId, platformId, accountId, status, createdAt, updatedAt]
properties:
  id: { type: string }
  workspaceId: { type: string }
  platformId:
    $ref: "#/components/schemas/PlatformId"
  accountId: { type: string }
  username: { type: string }
  displayName: { type: string }
  avatarUrl: { type: string, format: uri }
  profileUrl: { type: string, format: uri }
  status:
    $ref: "#/components/schemas/CrawlerAccountStatus"
  loginType:
    type: string
    enum: [qrcode, phone, cookie]
  lastLoginAt: { type: string, format: date-time }
  lastCheckedAt: { type: string, format: date-time }
  details:
    type: object
    additionalProperties: true
  error:
    $ref: "#/components/schemas/ErrorObject"
  createdAt: { type: string, format: date-time }
  updatedAt: { type: string, format: date-time }
```

`CrawlerAccountListResponse`:

```yaml
type: object
required: [success, accounts]
properties:
  success: { type: boolean }
  accounts:
    type: array
    items:
      $ref: "#/components/schemas/CrawlerAccount"
```

### New Endpoints

`GET /crawler-accounts`

Query params:

- `platform`: optional `PlatformId`
- `status`: optional `CrawlerAccountStatus`
- `pageSize`: default `50`, max `200`

Returns `CrawlerAccountListResponse`.

`PUT /crawler-accounts/{accountId}`

Purpose: backend crawler adapter can upsert the current account profile after login/check. This route may also be used by admin tooling.

Request body:

- `platformId` required
- `username`, `displayName`, `avatarUrl`, `profileUrl`, `status`, `loginType`, `lastLoginAt`, `lastCheckedAt`, `details`, `error`

Do not accept cookie/token/password fields. If such keys appear under `details`, backend must reject or drop them.

### Modified CreateCrawlerTaskRequest

Add explicit keyword input:

```yaml
keywords:
  type: array
  minItems: 1
  maxItems: 500
  items:
    type: string
    minLength: 1
maxNotesPerKeyword:
  type: integer
  minimum: 1
  maximum: 1000
maxCommentsPerNote:
  type: integer
  minimum: 0
  maximum: 5000
loginType:
  type: string
  enum: [qrcode, phone, cookie]
headless:
  type: boolean
```

Rules:

- `keywords` is required for SaaS-created crawler tasks.
- Backend normalizes keywords by trim + dedupe while preserving order.
- `platforms` remains required and must be deduped.
- `runMode=topic_extraction` should not be exposed by the SaaS crawler task form.
- If `runMode=full_workflow` is kept for compatibility, SaaS-created tasks still use provided keywords and must not run BroadTopicExtraction first.
- Store normalized `keywords` on `crawler_tasks` so task history shows what was collected.

### Modified CrawlerTask

Add:

```yaml
keywords:
  type: array
  items:
    type: string
keywordSource:
  type: string
  enum: [manual]
```

The SaaS path should report `keywordSource=manual`.

### Modified Platform

Optional account count summary:

```yaml
accountCounts:
  type: object
  properties:
    active: { type: integer }
    loginRequired: { type: integer }
    expired: { type: integer }
    disabled: { type: integer }
    error: { type: integer }
    unknown: { type: integer }
```

This helps the UI show platform account health without fetching all details on every dashboard refresh. It is optional for first pass if `GET /crawler-accounts` is implemented.

## Backend Design

### Persistence

Add `crawler_accounts` to `apps/api/storage.py` and `apps/api/migrations/001_init.sql`:

```sql
CREATE TABLE IF NOT EXISTS crawler_accounts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    username TEXT,
    display_name TEXT,
    avatar_url TEXT,
    profile_url TEXT,
    status TEXT NOT NULL,
    login_type TEXT,
    last_login_at TEXT,
    last_checked_at TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, platform_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_crawler_accounts_workspace
    ON crawler_accounts(workspace_id, platform_id, status, updated_at DESC);
```

Add `keywords_json` and `keyword_source` to `crawler_tasks`. SQLite startup schema and migration file should match.

### Services

Add `AccountService` under `apps/api/services/accounts.py`:

- `list_accounts(workspace_id, platform=None, status=None, page_size=50)`
- `upsert_account(workspace_id, account_id, payload)`
- details sanitizer that rejects/drops sensitive keys recursively: `cookie`, `cookies`, `token`, `access_token`, `refresh_token`, `password`, `secret`, `authorization`, `auth`.

Update `TaskService`:

- Validate and persist `payload.keywords`.
- For stub worker, calculate `totalKeywords` from task keywords, not default policy.
- For real worker path, call the MindSpider keyword+platform adapter with task keywords and platforms.
- Do not call `run_broad_topic_extraction` for SaaS-created tasks.
- Emit task events that include current platform and keyword progress when available.

### Crawler Adapter

Initial adapter can wrap existing code:

- Use `PlatformCrawler.run_multi_platform_crawl_by_keywords(keywords, platforms, login_type, max_notes_per_keyword)`.
- Map result stats into `CrawlerTask.stats`.
- Account discovery should be best-effort:
  - If MediaCrawler exposes logged-in profile fields, upsert them through `AccountService`.
  - If not available in first pass, allow manual/demo account rows only in mock data and keep real API empty instead of fabricating accounts.

### Security

- Never return or persist cookies/tokens/passwords.
- Do not log account secrets or full raw browser storage.
- Account details should be workspace-scoped on every query/update.
- Avatar/profile URLs should be treated as plain strings; UI should not execute HTML from details.

## Frontend Design

Update `apps/web/src/lib/types.ts` and `apps/web/src/lib/openapi-client.ts` from the OpenAPI contract.

Controls:

- Add `accounts` or `crawler accounts` section in the console navigation, or add a tab/panel under `爬虫`.
- Show platform filter, status filter, refresh button.
- Render avatar, display name/username, platform, status badge, last checked time, login type, and expandable details.
- Empty state should distinguish “no accounts discovered yet” from load error.
- Crawler task creation form replaces strategy/date-first flow with:
  - Keywords textarea or chip input.
  - Platform multi-select.
  - Max notes/comments numeric inputs.
  - Login type select.
  - Headless toggle.
- Hide or demote broad-topic/full workflow mode in the SaaS UI.

Mock data should include representative accounts for visual review. Real API loading should use `GET /crawler-accounts`.

## Docker Design

Add a web container path that does not require developers to run `npm run dev` separately.

Recommended first implementation:

- Add `apps/web/Dockerfile`.
- Add `web` service to root `docker-compose.yml`.
- `web` depends on `api`.
- Expose `${WEB_PORT:-3000}:3000`.
- Set `NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000/api/v1}` and `NEXT_PUBLIC_WORKSPACE_ID=${NEXT_PUBLIC_WORKSPACE_ID:-workspace_demo}`.
- Keep `api` on port `8000`.

Because `NEXT_PUBLIC_*` variables are build-time for static client bundles, the Dockerfile/compose implementation must ensure the intended local API URL is available during build. Runtime-only env is not enough for already-built client code.

## Test Plan

Backend:

- API tests for `GET /crawler-accounts` filter/status/page size.
- API tests for account upsert and sensitive details sanitization.
- API tests for crawler task creation:
  - valid keywords + platforms accepted.
  - empty keywords rejected.
  - duplicate/blank keywords normalized.
  - unsupported platform rejected.
  - persisted task includes `keywords` and `keywordSource=manual`.
- Stub worker uses provided keywords in stats.

Frontend:

- Typecheck.
- Playwright mock-mode test for account list rendering and filters.
- Playwright real-API route mock test for `GET /crawler-accounts`.
- Crawler form test verifies keywords/platform payload.
- Regression test confirms broad-topic mode is not the default SaaS crawler task path.

Docker:

- `docker compose config` should pass.
- `docker compose up --build api web db` should expose:
  - `http://localhost:8000/api/v1/health`
  - `http://localhost:3000`

## Sub-Issue Plan

1. Frontend/OpenAPI/Docker UI task
   - Update OpenAPI contract.
   - Update Next.js types/client/mock data/UI.
   - Add web Dockerfile and compose web service.
   - Produce handoff comment for backend with final contract details.

2. Backend task
   - Implement persistence, schemas, routes, services, and crawler task keyword handling according to the updated OpenAPI contract.
   - Integrate stub worker stats and best-effort MindSpider adapter without BroadTopicExtraction.
   - Add backend tests.

3. Test task
   - Expand API and E2E coverage after contract and backend are ready.
   - Verify Docker startup flow and regression coverage for keyword/platform collection.

## Acceptance Criteria

- `docker compose up --build` starts the API and SaaS page together.
- SaaS page at `localhost:3000` calls the API at `localhost:8000/api/v1`.
- UI shows crawler account list with platform, status, username/display name, avatar when available, and details.
- API exposes workspace-scoped crawler accounts without leaking secrets.
- Creating a crawler task from SaaS UI requires explicit keywords and selected platforms.
- Backend crawler task history stores and returns the normalized keywords.
- SaaS-created crawler tasks do not run BroadTopicExtraction before collection.
- Tests cover API contract, frontend payloads, account list rendering, and Docker config.
