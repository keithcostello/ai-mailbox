# AI Mailbox -- Sprint 5 Implementation Prompt

## Project
AI Mailbox: MCP messaging server for inter-AI communication.
Python 3.13 / FastMCP / PostgreSQL / Railway. DaisyUI + HTMX web UI.

## Current State
- Sprint 4 COMPLETE. 372 tests passing. Deployed to MVP 1 Staging.
- Branch: `mvp-1-staging` (commit `f172d9e`)
- 10 MCP tools registered (search_messages added Sprint 4, check_messages removed Sprint 4)
- DaisyUI 4 + Tailwind CSS (fantasy theme). HTMX polling (15s sidebar, 10s thread).
- JWT validation, CORS restriction, token cleanup, error pages, search, JSON payloads all live.

## Read These Files (in order)
1. `projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_5_SPEC.md` (approved spec -- implement this)
2. `projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_4_SPEC.md` (prior sprint context)
3. `projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md`

## Sprint 5 Scope (APPROVED -- do not re-plan)
- **Acknowledgment:** ack_state on messages (pending/received/processing/completed/failed), `acknowledge` MCP tool
- **Archiving:** per-user conversation archive, `archive_conversation` MCP tool, auto-unarchive on new message
- **Agent Identity:** user_type/last_seen/session_mode on users, replace _is_ai_user heuristic, user directory
- **Tech Debt:** issue #9 (CASCADE on user FKs), #10 (narrow PostgresDB retry), #11 (OAuth FK constraints)
- **Web UI:** ACK badges in threads, archive button + toggle, user directory page
- **GitHub:** Close issues #9, #10, #11

## Your First Action
Begin Sprint 5 implementation step 1: error codes + ACK state transitions (TDD). The spec has an 11-step implementation order. Follow it exactly.

## Parallel Execution
Subagents/parallel teams are approved for independent steps. Steps 1-5 can be parallelized (they touch different files). Steps 6-7 depend on 1-5.

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

## Do Not Redo
- Sprint 1, 2, 3, or 4 implementation (complete, tested, deployed)
- DaisyUI framework selection or fantasy theme (decided Sprint 3)
- Three-table conversation model (established, working)
- Rate limiting (working, tested)
- Group confirmation token system (working, tested)
- JWT validation / CORS restriction / token cleanup (Sprint 3, working)
- Search / JSON payloads / HTMX polling (Sprint 4, working)
- Sprint 5 spec (approved, committed)

## Architecture Quick Reference
- Backend: Python 3.13 / FastMCP / Starlette / Jinja2
- Database: PostgreSQL (staging), SQLite (tests) -- dual-path queries via isinstance(db, PostgresDB)
- Frontend: DaisyUI 4 + Tailwind CSS CDN + HTMX 2.0.4 (server-rendered)
- Auth: OAuth 2.1 + PKCE / JWT sessions
- Infrastructure: Railway (MVP 1 Staging)
- Tests: pytest (372 tests passing)

## Key Files
- `src/ai_mailbox/server.py` -- MCP tool registration, app factory
- `src/ai_mailbox/web.py` -- web routes, Jinja2 env, error helpers
- `src/ai_mailbox/db/queries.py` -- all database queries
- `src/ai_mailbox/db/connection.py` -- DBConnection protocol, SQLiteDB, PostgresDB
- `src/ai_mailbox/db/schema.py` -- migration runner (handles $$ blocks)
- `src/ai_mailbox/tools/mark_read.py` -- pattern reference for simple tools
- `src/ai_mailbox/tools/search.py` -- pattern reference for search tool
- `src/ai_mailbox/errors.py` -- error codes and make_error/is_error
- `tests/conftest.py` -- test fixtures, SQLite DB with schema

## Success Criteria
- All Sprint 5 features implemented with TDD
- 410+ tests, 100% pass rate
- Deployed to MVP 1 Staging
- AI UX UAT passed
- Human UAT passed
- GitHub issues #9, #10, #11 closed
