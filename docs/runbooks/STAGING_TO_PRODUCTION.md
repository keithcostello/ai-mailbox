# Staging to Production Promotion

## Prerequisites

All three gates must pass before promotion:

| Gate | Command / Evidence | Status |
|------|--------------------|--------|
| Tier 1 | `py -m pytest tests/ -q` -- 0 failures, 589+ tests | |
| Tier 2 | AI UX screenshots from claude.ai | |
| Tier 3 | Human UAT checklist signed (docs/runbooks/UAT_PROCESS.md) | |

## Environment Variables

Production requires all variables from staging plus stricter values:

| Variable | Staging | Production | Notes |
|----------|---------|------------|-------|
| `DATABASE_URL` | Railway Postgres (staging) | Railway Postgres (production) | Separate instances |
| `MAILBOX_JWT_SECRET` | Staging secret | **Different** production secret | Min 32 bytes, unique per env |
| `MAILBOX_KEITH_PASSWORD` | `mvp1-keith-dev` | **Different** production password | |
| `MAILBOX_AMY_PASSWORD` | Set | Set or remove | |
| `GITHUB_CLIENT_ID` | Staging OAuth app | Production OAuth app | Separate GitHub OAuth apps |
| `GITHUB_CLIENT_SECRET` | Staging secret | Production secret | |
| `MAILBOX_INVITE_ONLY` | `true` | `true` | |
| `MAILBOX_INVITED_EMAILS` | Test emails | Production emails | |
| `RAILWAY_PUBLIC_DOMAIN` | Auto-set by Railway | Auto-set by Railway | Used for OAuth issuer URL |

## Promotion Steps

### 1. Final staging verification
```bash
# Verify tests
py -m pytest tests/ -q

# Verify staging health
curl -s https://ai-mailbox-server-mvp-1-staging.up.railway.app/health

# Verify staging MCP tools work (run UAT step 12)
# In claude.ai: "who am I"
```

### 2. Merge to master
```bash
git checkout master
git merge mvp-1-staging --no-ff -m "Promote Sprint 7 to production"
git push origin master
```

### 3. Deploy to production
```bash
# Switch Railway context to production
railway link --environment production

# Verify environment variables are set (do NOT print secrets)
railway variables

# Deploy
railway up --detach

# Switch back to staging context
railway link --environment "MVP 1 Staging"
```

### 4. Post-deploy verification
```bash
# Health check
curl -s https://ai-mailbox-server-production.up.railway.app/health

# Verify migrations ran (user_count should be correct)
# In claude.ai with production MCP: "who am I"
```

### 5. Smoke test in production
Run UAT steps 1, 5, 12 in claude.ai connected to the production MCP server:
- `check my inbox` -- widget renders
- `search my messages for "sprint"` -- search works
- `who am I` -- identity with unread counts

## Rollback

If production breaks after promotion:
```bash
# Revert the merge commit on master
git revert HEAD
git push origin master

# Redeploy
railway link --environment production
railway up --detach
railway link --environment "MVP 1 Staging"
```

## Known Issues at Promotion

- TD-002: Railway auto-deploy from branch push broken (use `railway up` CLI)
- TD-003: Dual Postgres instances on Railway, both 0MB (investigate)
- TD-005: Tailwind CDN in production (no build step yet)
- TD-007: Amy's MCP connector URL needs production update
- GitHub #15: Soft deletes for messages (open, P3)
