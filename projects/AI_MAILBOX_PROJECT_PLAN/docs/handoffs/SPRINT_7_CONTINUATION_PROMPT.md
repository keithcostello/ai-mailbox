# AI Mailbox -- Sprint 7 Continuation Prompt

## Project
AI Mailbox: MCP messaging server for inter-AI communication.
Python 3.13 / FastMCP / PostgreSQL / Railway. DaisyUI 4 (corporate theme) + HTMX web UI.

## Current State
- Sprint 6 COMPLETE + post-sprint fixes. 471 tests passing. Deployed to all 3 environments.
- Branch: `mvp-1-staging` (commit `edd97f3`)
- All branches in sync: master = staging = production = mvp-1-staging
- 12 MCP tools registered, all prefixed `mailbox_*` to avoid Claude Desktop name collisions
- GitHub OAuth live on production + staging (separate OAuth apps per environment)
- Invite-only mode active. 3 invited emails: keith@ivenoclue.com, amy@steertrue.ai, amy@ivenoclue.com
- Keith's production account linked to GitHub (email=keith@ivenoclue.com, auth_provider=github)
- Handle picker works: new OAuth users choose their @username on first login
- Change handle works: users can change @username from Settings page
- `list_messages` truncates bodies to 200 chars to prevent token overflow in Claude Desktop
- Version: 0.6.0

## Read These Files (in order)
1. `projects/AI_MAILBOX_PROJECT_PLAN/docs/plans/SPRINT_ROADMAP.md` (Sprint 7 section)
2. `projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_6_SPEC.md` (prior sprint context)
3. `projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md`
4. `projects/AI_MAILBOX_PROJECT_PLAN/docs/runbooks/STAGING_TO_PRODUCTION.md`

## Sprint 7 Scope (from roadmap + identified needs)

### From Roadmap: Webhooks + Notifications + Hardening
- Outbound webhooks (register, deliver, retry with backoff, HMAC signature)
- Email notifications via Resend API
- Dead letter handling for offline agents
- System messages (reserved `system` sender)
- Web UI: notification preferences, webhook management
- Production hardening (connection pooling review, graceful shutdown, health check expansion)

### Identified During Sprint 6 (must-fix for Sprint 7)
- **GitHub OAuth on MCP login page** -- Currently MCP clients (Claude Desktop) can only use password login. New users who only have GitHub cannot connect. Add GitHub OAuth to the `/login` page (the MCP OAuth flow), not just `/web/login`. This is the multi-hop redirect: MCP login -> GitHub -> callback -> create MCP authorization code -> redirect back to Claude Desktop.
- **migrate_003 PostgreSQL boolean fix** -- Production data migration partially failed because `m.read = 1` doesn't work in PostgreSQL (boolean column, not integer). Fix the migration query to use `m.read = TRUE` for PostgreSQL. 24 old messages exist but weren't fully migrated.

### Identified During Deployment (should-fix)
- Production promotion runbook at `docs/runbooks/STAGING_TO_PRODUCTION.md` -- follow this for future deploys
- Railway CLI `-e` flag doesn't work for `railway up` -- must use `railway environment X && railway service Y && railway up -d` instead
- Railway deploys can queue/block if multiple failed deploys exist -- check `railway deployment list` and wait for DEPLOYING -> SUCCESS

## Your First Action
Write the Sprint 7 spec (`SPRINT_7_SPEC.md`) following the same format as Sprint 6. Include: webhook delivery spec, MCP GitHub OAuth flow, notification preferences, dead letter handling, migration fix, acceptance criteria, implementation order. Get human approval before implementing.

## Hard Rules
- TDD required. No exceptions. Write failing test, then implement.
- Modern software practices. Clean architecture. No dead code.
- File and folder hygiene. No orphaned files. No dead imports.
- AI UX UAT required (browser automation).
- Human UAT required after AI testing.
- Group sends require double confirmation. No exceptions.
- Keep responses to 2-3 paragraphs max. No emoji. No celebration.
- Python executable is `py` (Windows), not `python` or `python3`.
- Test command: `py -m pytest tests/ -x -q`
- Design system: DaisyUI 4 corporate theme. Borders not shadows. Bold names. Primary-tinted avatars. Monochrome labels with accent colors only for status indicators.
- MCP tool names MUST be prefixed with `mailbox_` to avoid Claude Desktop collisions.
- `list_messages` body previews max 200 chars. Full content via `get_thread` only.

## Do Not Redo
- Sprint 1-6 implementation (complete, tested, deployed to production)
- UI redesign (corporate theme, flat messages -- done, deployed)
- Three-table conversation model (established, working)
- GitHub OAuth web login (working on all environments)
- Handle picker + change handle (working)
- Settings page (working)
- Rate limiting, group confirmation, JWT/CORS, token cleanup (all working)
- Search, JSON payloads, HTMX polling, ACK protocol, archiving, agent identity (all working)
- Tool name prefix (mailbox_*) -- done, deployed
- Body truncation in list_messages -- done, deployed
- Generic README -- done

## Architecture Quick Reference
- Backend: Python 3.13 / FastMCP / Starlette / Jinja2
- Database: PostgreSQL (staging/production), SQLite (tests) -- dual-path queries
- Frontend: DaisyUI 4 corporate theme + Tailwind CSS CDN + HTMX 2.0.4 (server-rendered)
- Auth: OAuth 2.1 + PKCE / JWT sessions (web uses httpOnly cookie) / GitHub OAuth (web only, MCP is password-only)
- Infrastructure: Railway (3 environments: MVP 1 Staging, Staging, Production)
- Tests: pytest (471 tests passing)
- Deploy: `railway environment X && railway service ai-mailbox-server && railway up -d`

## Key Files
- `src/ai_mailbox/server.py` -- MCP tool registration (mailbox_* prefix), app factory, _seed_users
- `src/ai_mailbox/web.py` -- web routes, settings page, change handle, Jinja2 env
- `src/ai_mailbox/web_oauth.py` -- GitHub OAuth routes, handle picker, user creation
- `src/ai_mailbox/oauth.py` -- MCP OAuth provider (password-based login for Claude Desktop)
- `src/ai_mailbox/db/queries.py` -- all database queries
- `src/ai_mailbox/db/connection.py` -- DBConnection protocol, SQLiteDB, PostgresDB
- `src/ai_mailbox/db/schema.py` -- migration runner (handles $$ blocks, PG-only set)
- `src/ai_mailbox/config.py` -- Config.from_env(), GitHub OAuth vars, invite_only
- `src/ai_mailbox/templates/` -- Jinja2 templates (login, settings, pick_handle, inbox, etc.)
- `tests/conftest.py` -- test fixtures, SQLite DB with schema
- `tests/test_web.py` -- web UI tests (has its own schema copy -- must stay in sync)

## Railway Environments
| Environment | URL | Branch |
|---|---|---|
| MVP 1 Staging | ai-mailbox-server-mvp-1-staging.up.railway.app | mvp-1-staging |
| Staging | ai-mailbox-server-staging.up.railway.app | staging |
| Production | ai-mailbox-server-production.up.railway.app | production |

GitHub OAuth Apps: separate app per environment (different client_id/secret). Callback URL must match exactly.

## Open Tech Debt
- TD-001: Staging DB legacy columns (to_user, read, project on messages)
- TD-002: Railway auto-deploy not triggering from push
- TD-003: Dual Postgres instances in Railway (both at 0MB)
- TD-005: Tailwind CDN -- add build step for production
- TD-007: Amy's MCP connector URL needs updating for production
- TD-008: migrate_003 boolean fix for PostgreSQL production data

## GitHub Issues
- #15 OPEN: Add soft deletes for messages
- All others closed (#1-#14, #16)

## Success Criteria
- Sprint 7 spec written and approved
- All Sprint 7 features implemented with TDD
- 520+ tests, 100% pass rate
- GitHub OAuth works on MCP login page (Claude Desktop can use GitHub to authenticate)
- Deployed to all 3 environments
- AI UX UAT passed
- Human UAT passed
- Old production messages migrated correctly
