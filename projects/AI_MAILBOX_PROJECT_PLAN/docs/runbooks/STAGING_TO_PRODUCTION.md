# Runbook: Staging to Production Promotion

**Last validated:** 2026-04-06 (staging promotion from mvp-1-staging)
**Railway project:** `3befc06d-8779-4eba-9a3d-d0ec4a2dfb0f`

---

## Pre-flight Checklist

- [ ] All tests pass locally (`py -m pytest tests/ -x -q` -- expect 471+)
- [ ] Staging environment validated (health, login page, settings, GitHub OAuth)
- [ ] No open blockers in WAITING_ON.md
- [ ] User (Amy) notified of upcoming downtime / URL change

## Environments

| Environment | URL | Branch | DB |
|-------------|-----|--------|----|
| MVP 1 Staging | ai-mailbox-server-mvp-1-staging.up.railway.app | mvp-1-staging | Postgres (thc2) |
| Staging | ai-mailbox-server-staging.up.railway.app | staging | Postgres (staging) |
| Production | ai-mailbox-server-production.up.railway.app | production | Postgres (production) |

## Step 1: Back Up Production Database

```bash
# Get the production DATABASE_URL
railway variables -e "production" | grep DATABASE_URL

# pg_dump from the production connection string
pg_dump "postgresql://postgres:PASSWORD@junction.proxy.rlwy.net:PORT/railway" > backup_production_$(date +%Y%m%d).sql
```

Alternative: Use Railway's Postgres plugin UI to create a snapshot.

**Do not proceed without a backup.**

## Step 2: Merge staging -> production branch

```bash
git fetch origin
git checkout production
git merge origin/staging --no-edit
git push origin production
```

## Step 3: Set New Environment Variables on Production

Production currently has old POC env vars (`MAILBOX_KEITH_API_KEY`, `MAILBOX_AMY_API_KEY`) that are no longer used. The new code needs:

```bash
# GitHub OAuth (same app, same callback domain? See Step 3a)
railway variables set "GITHUB_CLIENT_ID=Ov23lim5zrIBkhLQQyIW" -e "production"
railway variables set "GITHUB_CLIENT_SECRET=<secret>" -e "production"

# Invite mode
railway variables set "MAILBOX_INVITE_ONLY=true" -e "production"
railway variables set "MAILBOX_INVITED_EMAILS=keith@ivenoclue.com,amy@steertrue.ai,amy@ivenoclue.com" -e "production"

# Optional: remove obsolete vars
railway variables set "MAILBOX_KEITH_API_KEY=" -e "production"
railway variables set "MAILBOX_AMY_API_KEY=" -e "production"
```

### Step 3a: GitHub OAuth App Callback URL

The GitHub OAuth app's callback URL is currently set to the MVP 1 Staging domain. For production, you need to **either**:

**Option A:** Update the existing GitHub OAuth app's callback URL to the production domain:
`https://ai-mailbox-server-production.up.railway.app/web/oauth/callback`

**Option B:** Create a second GitHub OAuth app for production with the production callback URL, and use different `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` values.

Option A is simpler for now. You can only have one callback URL per OAuth app, so MVP 1 Staging GitHub login will stop working after this change (acceptable -- staging uses password fallback).

## Step 4: Deploy to Production

```bash
railway up -d -e "production"
```

Or if Railway auto-deploy is configured for the `production` branch, the push from Step 2 may trigger it automatically.

## Step 5: Validate Production

```bash
# Health check
curl -s https://ai-mailbox-server-production.up.railway.app/health
# Expected: {"status":"healthy","version":"0.6.0","user_count":2,"auth":"oauth2.1"}

# Login page has GitHub button
curl -s https://ai-mailbox-server-production.up.railway.app/web/login | grep -i "github"

# Settings route exists (302 = redirect to login, correct)
curl -s -o /dev/null -w "%{http_code}" https://ai-mailbox-server-production.up.railway.app/web/settings

# Deploy logs clean
railway logs -d -e "production" | head -15
# Should show: migrations complete, users seeded, no errors
```

## Step 6: Validate Database Migration

The migrations (003-006) run automatically on startup. Check logs for:
- `PostgreSQL schema migrations complete` (all DDL ran)
- `Migration 003: ...` (data migration for old messages)
- `Seeded 2 users` (keith + amy)
- No error lines

If the production DB has existing messages from the POC, `migrate_003` will convert them to the new conversation model. This is a one-time operation.

## Step 7: Update Amy's MCP Connector

Amy's Claude Desktop is configured to connect to the production URL. The MCP endpoint path hasn't changed (`/mcp`), so her connector should still work **but she will need to re-authenticate** because:
- The JWT secret is different per environment
- The OAuth client registration is per-environment

Tell Amy to:
1. Remove and re-add the MCP connector in Claude Desktop settings
2. Log in with username `amy` and password (from `MAILBOX_AMY_PASSWORD` env var on production)

## Step 8: Test MCP Connection

Have Amy (or Keith) verify MCP tools work:
- `whoami` -- returns user info with version 0.6.0
- `list_messages` -- returns messages (may be empty if DB was fresh)
- `send_message` -- send a test message

## Step 9: Smoke Test Web UI

1. Visit `https://ai-mailbox-server-production.up.railway.app/web/login`
2. Log in with password
3. Verify inbox loads
4. Click Settings, verify profile
5. Click Users, verify directory
6. Send a message via compose

## Rollback Plan

If something breaks after production deploy:

```bash
# Revert the production branch to previous commit
git checkout production
git reset --hard HEAD~1
git push --force origin production

# Redeploy old code
railway up -d -e "production"
```

If the database migration caused issues:
```bash
# Restore from backup
psql "postgresql://postgres:PASSWORD@junction.proxy.rlwy.net:PORT/railway" < backup_production_YYYYMMDD.sql
```

## Known Risks

1. **Migration 003 converts old message format** -- one-time, tested on staging. If production has messages with unusual data, the migration might partially fail. Check logs.
2. **GitHub OAuth callback URL** -- must match the production domain exactly. Mismatch = "redirect_uri not associated" error.
3. **Amy's MCP session** -- will break on first request after deploy. She needs to re-authenticate. Warn her before deploying.
4. **Existing sessions** -- all web sessions invalidate when the server restarts (expected, users re-login).
