# AI Mailbox -- Sprint 6 Implementation Prompt

## Project
AI Mailbox: MCP messaging server for inter-AI communication.
Python 3.13 / FastMCP / PostgreSQL / Railway. DaisyUI 4 (corporate theme) + HTMX web UI.

## Current State
- Sprint 5 COMPLETE. 424 tests passing. Deployed to MVP 1 Staging.
- Branch: `mvp-1-staging` (commit `f5801f1`)
- 12 MCP tools registered (acknowledge + archive_conversation added Sprint 5)
- DaisyUI 4 corporate theme + Tailwind CSS CDN. Flat Slack-style messages with initials avatars. HTMX polling (15s sidebar, 10s thread).
- JWT validation, CORS restriction, token cleanup, error pages, search, JSON payloads, ACK protocol, archiving, agent identity all live.
- UI redesigned: corporate theme, flat message layout, monochrome+accent design system, bold names, colored avatars.

## Read These Files (in order)
1. `projects/AI_MAILBOX_PROJECT_PLAN/docs/plans/SPRINT_ROADMAP.md` (Sprint 6 section)
2. `projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_5_SPEC.md` (prior sprint context)
3. `projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md`

## Sprint 6 Scope (write spec first, then implement)

### Core: Self-Service Registration + OAuth
- **Google OAuth** via FastMCP or Starlette OAuth integration (replace custom username/password login form)
- **GitHub OAuth** (secondary provider)
- Schema migration 006: `email`, `auth_provider`, `avatar_url` on users table
- Invite-only mode (configurable via env var, default ON for alpha)
- New user registration flow: OAuth -> check invite list -> create user -> redirect to inbox
- Update `_seed_users` to handle OAuth-registered users alongside seeded users

### User Settings Page
- New route: `GET /web/settings` -- user profile settings
- Display: name, email, user_type, session_mode, auth provider
- Editable: display_name (other fields read-only for now)
- Navbar: add "Settings" link (gear icon or text)
- Uses same corporate design system (borders, no shadows, monochrome labels)

### Onboarding + README
- Generic README.md (not addressed to Amy -- currently the README is project-specific)
- Getting-started guide for new users connecting Claude Desktop
- Web UI: post-login onboarding for first-time users (optional, can be deferred)

### GitHub
- Close issue #13 (self-service registration)

## Your First Action
Write the Sprint 6 spec (`SPRINT_6_SPEC.md`) following the same format as Sprint 5. Include: OAuth flow diagrams, migration 006 DDL, new routes, settings page layout, acceptance criteria, implementation order. Get human approval before implementing.

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

## Do Not Redo
- Sprint 1-5 implementation (complete, tested, deployed)
- UI redesign (corporate theme, flat messages -- done, deployed)
- Three-table conversation model (established, working)
- Rate limiting, group confirmation, JWT/CORS, token cleanup (all working)
- Search, JSON payloads, HTMX polling, ACK protocol, archiving, agent identity (all working)
- Sprint 6 scope decisions (confirmed by user: OAuth + settings + README)

## Architecture Quick Reference
- Backend: Python 3.13 / FastMCP / Starlette / Jinja2
- Database: PostgreSQL (staging), SQLite (tests) -- dual-path queries via isinstance(db, PostgresDB)
- Frontend: DaisyUI 4 corporate theme + Tailwind CSS CDN + HTMX 2.0.4 (server-rendered)
- Auth: OAuth 2.1 + PKCE / JWT sessions (web uses httpOnly cookie)
- Infrastructure: Railway (MVP 1 Staging)
- Tests: pytest (424 tests passing)
- Deploy: `railway up -d -e "MVP 1 Staging"` (auto-deploy from push not working [TD-002])

## Key Files
- `src/ai_mailbox/server.py` -- MCP tool registration, app factory, _seed_users
- `src/ai_mailbox/web.py` -- web routes, Jinja2 env, _is_ai_user cache
- `src/ai_mailbox/oauth.py` -- MailboxOAuthProvider, current_user_id contextvar
- `src/ai_mailbox/db/queries.py` -- all database queries
- `src/ai_mailbox/db/connection.py` -- DBConnection protocol, SQLiteDB, PostgresDB
- `src/ai_mailbox/db/schema.py` -- migration runner (handles $$ blocks, PG-only set)
- `src/ai_mailbox/config.py` -- Config.from_env(), env var validation
- `src/ai_mailbox/errors.py` -- error codes and make_error/is_error
- `src/ai_mailbox/templates/base.html` -- navbar, corporate theme, HTMX/DaisyUI CDN
- `src/ai_mailbox/templates/inbox.html` -- two-panel layout, sidebar filters
- `src/ai_mailbox/templates/users.html` -- user directory
- `tests/conftest.py` -- test fixtures, SQLite DB with schema
- `tests/test_web.py` -- web UI tests (has its own schema copy -- must stay in sync)

## Open Tech Debt
- TD-001: Staging DB legacy columns (to_user, read, project on messages)
- TD-002: Railway auto-deploy not triggering from push
- TD-003: Dual Postgres instances in Railway (both at 0MB)
- TD-005: Tailwind CDN -- add build step for production

## Success Criteria
- Sprint 6 spec written and approved
- All Sprint 6 features implemented with TDD
- 460+ tests, 100% pass rate
- Deployed to MVP 1 Staging
- AI UX UAT passed
- Human UAT passed
- GitHub issue #13 closed
- Generic README committed
