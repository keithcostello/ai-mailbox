# Railway Environment Documentation

**Project:** ai-mailbox
**Project ID:** 3befc06d-8779-4eba-9a3d-d0ec4a2dfb0f
**Workspace:** keithcostello's Projects

## Environment Map

| | Production | Staging |
|---|---|---|
| **Env ID** | `8eaeb984-dff6-43be-afa7-dfa75cdababa` | `fd379a87-9121-4fbf-a9d0-495c46c7bf21` |
| **Server URL** | `ai-mailbox-server-production.up.railway.app` | `ai-mailbox-server-staging.up.railway.app` |
| **Server service ID** | `40dc3999-91d7-42d1-b307-3a516aa5252f` | same (env-scoped) |
| **Postgres services** | `Postgres` (414b8ce0) + `Postgres-bbLI` (ba25011b) | `Postgres-hjlK` (c681ec22) |
| **Postgres storage** | Both 0MB | 1.1GB |
| **Postgres image** | ghcr.io/railwayapp-templates/postgres-ssl:18 | same |
| **Region** | us-east4-eqdc4a | us-east4-eqdc4a |
| **Replicas** | 1 | 1 |
| **Resource limits** | 4 CPU, 4GB RAM | 4 CPU, 4GB RAM |
| **Health check** | `/health` (300s timeout) | `/health` (300s timeout) |
| **Restart policy** | ON_FAILURE (max 10 retries) | ON_FAILURE (max 10 retries) |
| **Last deploy** | 2026-04-05T22:03Z | 2026-04-05T22:06Z |
| **Status** | SUCCESS | SUCCESS |

## Open Question

Production has two Postgres instances (`Postgres` and `Postgres-bbLI`), both at 0MB storage. Need to confirm:
- Which one does `DATABASE_URL` point to?
- Should the unused one be removed?

## Development Workflow

All development and testing happens against **staging**. Production data (messages, mailboxes) is never touched during development.

### Working Against Staging

```bash
# Link CLI to staging
railway link -p 3befc06d-8779-4eba-9a3d-d0ec4a2dfb0f -e staging

# View staging logs
railway logs

# Check staging status
railway status --json
```

### Working Against Production (verification only)

```bash
# Link CLI to production
railway link -p 3befc06d-8779-4eba-9a3d-d0ec4a2dfb0f -e production

# Verify health
curl https://ai-mailbox-server-production.up.railway.app/health
```

## Staging-to-Production Promotion Rules

### Rule 1: Schema Migrations Only
Production keeps its own data. No data transfer between environments. Migrations propagate schema changes; production messages and mailboxes remain intact.

### Rule 2: Backward-Compatible Migrations
Migrations must be additive:
- `ALTER TABLE ADD COLUMN` -- OK
- `CREATE TABLE` -- OK
- `DROP TABLE` -- requires deprecation cycle
- `DROP COLUMN` -- make nullable first, then drop in later release

### Rule 3: Code Deploys via Railway
Railway deploys from the same GitHub repo, scoped by environment. Pushing to `master` triggers both environments (verify Railway's branch mapping).

### Pre-Promotion Checklist

- [ ] All tests pass locally (`pytest`)
- [ ] Staging `/health` returns 200
- [ ] Staging MCP tools verified (manual or automated UAT)
- [ ] Schema migration ran successfully on staging Postgres
- [ ] No pending schema changes that break backward compatibility

### Post-Promotion Verification

- [ ] Production `/health` returns 200
- [ ] Production messages and mailboxes are intact (spot-check via MCP tools)
- [ ] MCP tools functional on production (send, check, reply, thread, whoami)

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string (auto-set by Railway Postgres plugin) |
| `PORT` | No | Server port (default: 8000, Railway sets automatically) |
| `MAILBOX_JWT_SECRET` | Yes | Secret for JWT signing (min 32 bytes) |
| `MAILBOX_KEITH_PASSWORD` | Yes | Keith's login password |
| `MAILBOX_AMY_PASSWORD` | Yes | Amy's login password |
| `LOG_LEVEL` | No | Python logging level (default: INFO) |

Each environment has its own set of env vars. Staging and production use different JWT secrets and may use different passwords.
