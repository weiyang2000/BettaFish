# BettaFish SaaS Console

Contract-first Next.js console for the SaaS migration work. The UI calls
`src/lib/openapi-client.ts`, which targets `docs/openapi/saas-platform.yaml`.

## Run

```bash
npm install
npm run dev
```

The console runs with deterministic mock data when `NEXT_PUBLIC_API_BASE_URL`
is empty or `NEXT_PUBLIC_USE_MOCKS=true`.

To point at a backend:

```bash
cp .env.example .env.local
npm run dev
```

Sensitive config fields are rendered as masked/blank client inputs. The client
does not log secret values and only sends fields the operator edits.

## Tests

```bash
npm run typecheck
npm run test:e2e
```

The Playwright suite starts the console in deterministic mock mode and covers
navigation, report and crawler task forms, identity-list validation, and masked
system configuration fields.
