# AI Mailbox -- Sprint 4 Implementation Prompt

## Project
AI Mailbox: MCP messaging server for inter-AI communication.
Python 3.13 / FastMCP / PostgreSQL / Railway. DaisyUI + HTMX web UI.

## Current State
- Sprint 3 COMPLETE. 320 tests passing. Deployed to MVP 1 Staging.
- Branch: `mvp-1-staging` (commit `3ec9955`)
- 10 MCP tools registered (check_messages deprecated, to be removed this sprint)
- DaisyUI 4 + Tailwind CSS (fantasy theme). jQuery removed.
- JWT validation, CORS restriction, token cleanup, error pages all live.

## Read These Files (in order)
1. `projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_4_SPEC.md` (approved spec -- implement this)
2. `projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_3_SPEC.md` (prior sprint context)
3. `projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md`

## Sprint 4 Scope (APPROVED -- do not re-plan)
- **Search:** PostgreSQL tsvector + GIN index (migration 004), `search_messages` MCP tool, web UI search bar + results
- **JSON payloads:** Validate body when content_type is application/json, render as formatted code block in thread view
- **Live polling:** HTMX `every 15s` on sidebar, `every 10s` on active thread
- **Remove check_messages:** Deprecated since Sprint 2, delete tools/inbox.py
- **OAuth scopes:** Normalize comma-separated to JSON array (issue #14)
- **GitHub:** Close issue #14

## Your First Action
Begin Sprint 4 implementation step 1: error codes + JSON validation (TDD). The spec has an 11-step implementation order. Follow it exactly.

## Parallel Execution
Subagents/parallel teams are approved for independent steps. Steps 1-5 can be parallelized (they touch different files). Steps 6-7 depend on 1-5.

## Hard Rules
- TDD required. No exceptions. Write failing test, then implement.
- AI UX UAT required (browser automation).
- Human UAT required after AI testing.
- Group sends require double confirmation. No exceptions.
- Keep responses to 2-3 paragraphs max. No emoji. No celebration.
- Python executable is `py` (Windows), not `python` or `python3`.
- Test command: `py -m pytest tests/ -x -q`

## Do Not Redo
- Sprint 1, 2, or 3 implementation (complete, tested, deployed)
- DaisyUI framework selection or fantasy theme (decided Sprint 3)
- Three-table conversation model (established, working)
- Rate limiting (working, tested)
- Group confirmation token system (working, tested)
- JWT validation / CORS restriction / token cleanup (Sprint 3, working)
- Error pages (Sprint 3, working)
- Markdown rendering (Sprint 3, working)
- Sprint 4 spec (approved, committed at 3ec9955)

## Architecture Quick Reference
- Backend: Python 3.13 / FastMCP / Starlette / Jinja2
- Database: PostgreSQL (staging), SQLite (tests) -- dual-path queries via isinstance(db, PostgresDB)
- Frontend: DaisyUI 4 + Tailwind CSS CDN + HTMX 2.0.4 (server-rendered, no jQuery)
- Auth: OAuth 2.1 + PKCE / JWT sessions
- Infrastructure: Railway (MVP 1 Staging)
- Tests: pytest (320 tests passing)

## Key Files
- `src/ai_mailbox/server.py` -- MCP tool registration, app factory
- `src/ai_mailbox/web.py` -- web routes, Jinja2 env, error helpers
- `src/ai_mailbox/db/queries.py` -- all database queries
- `src/ai_mailbox/db/connection.py` -- DBConnection protocol, SQLiteDB, PostgresDB
- `src/ai_mailbox/db/schema.py` -- migration runner
- `src/ai_mailbox/tools/send.py` -- send_message tool
- `src/ai_mailbox/tools/reply.py` -- reply_to_message tool
- `src/ai_mailbox/errors.py` -- error codes and make_error/is_error
- `tests/conftest.py` -- test fixtures, SQLite DB with schema

## Success Criteria
- All Sprint 4 features implemented with TDD
- 350+ tests, 100% pass rate
- Deployed to MVP 1 Staging
- AI UX UAT passed
- Human UAT passed
- GitHub issue #14 closed
