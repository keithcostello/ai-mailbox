# Handoff: AI Mailbox Sprint 1 Complete

**Date:** 2026-04-05
**Session:** Sprint 1 implementation (Schema Foundation + Error Framework)
**Handoff Version:** V3

---

## Section 1: Identity

- **Project:** AI_MAILBOX_PROJECT_PLAN
- **Repository:** keithcostello/ai-mailbox
- **Branch:** mvp-1-staging
- **Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
- **Last Commit:** b7d847a (Sprint 1: Schema foundation, error framework, and web UI scaffold)

---

## Section 2: Project Status

| Metric | Value |
|---|---|
| Sprint | 1 of 8 (complete) |
| Tests | 140 passing (up from 43 in Sprint 0) |
| Files changed | 25 (13 modified, 12 new) |
| Lines added | ~3,037 |
| GitHub issues closed | #5, #7, #8 |
| Deployment | MVP 1 Staging healthy, migration applied |
| AI UX UAT | 8/8 checks passed |
| Human UAT | Passed |

---

## Section 3: What Happened This Session

**Grade: A** -- Full Sprint 1 spec written, approved, and implemented via TDD. All acceptance criteria met. Deployed and verified.

### Completed
1. Read 8 context files (AGENTS.md, CLAUDE.md, user.md, ai_settings.md, handoff, WAITING_ON, TODO, SPRINT_ROADMAP)
2. Wrote Sprint 1 spec (SPRINT_1_SPEC.md) -- 12 sections, 3 open questions resolved
3. Implemented 10-step TDD-through-delivery:
   - Step 1: Error framework (errors.py + test_errors.py) -- 14 tests
   - Step 2: Schema DDL (003_conversation_model.sql + conftest.py + test_migration.py) -- 13 tests
   - Step 3: Query layer (queries.py rewrite + test_queries.py) -- 43 tests
   - Step 4: Tool layer (5 tools rewritten + test_tools.py) -- 22 tests
   - Step 5: Web scaffold (web.py + 4 templates + test_web.py) -- 21 tests
   - Step 6: Server integration (web routes mounted + test_server.py) -- 8 tests
   - Step 7: Data migration (migrate_003.py + test_migration.py expansion) -- 8 tests
   - Step 8: Deploy to MVP 1 Staging -- health check verified, migration ran
   - Step 9: AI UX UAT -- 8/8 browser checks passed
   - Step 10: Human UAT -- confirmed by Keith
4. Closed GitHub issues #5, #7, #8
5. Integrated SteerTrue governance (session 1e6cc19a)

### Not Completed
- Sprint 2 spec not started (next action)
- Production deployment not done (mvp-1-staging only)
- Branch auto-deploy from git push not working -- had to use `railway deploy` CLI

---

## Section 4: Session Patterns

### What Worked
- SDD then TDD: spec approved before any code written, clear acceptance criteria
- Parallel exploration: subagent explored full codebase while SteerTrue initialized
- Incremental test verification: ran tests after each step, never accumulated failures
- Per-project conversation uniqueness: clean mapping from old flat model

### What to Avoid
- The editable install (`pip install -e .`) pointed to a different worktree (`dev_pm_branch`). Had to reinstall from the correct directory. Next session: verify `pip show ai-mailbox` points to the right location before running tests.
- Worktree branch mismatch: session started in worktree on `claude/naughty-margulis` but needed to work on `mvp-1-staging` in the main repo. Used absolute paths to work from main repo. Next session: either exit worktree or work from main repo directory directly.
- Chrome extension tab context lost mid-UAT due to extension URL boundary. Had to create new tab and re-navigate.
- Railway push did not auto-trigger deployment. Had to use `railway deploy` CLI manually.

---

## Section 5: Architecture State

### Schema (Sprint 1 -- 3-table conversation model)

```
users (unchanged)
  |
  +-- conversations (NEW: id, type, project, name, created_by, timestamps)
  |     type IN ('direct', 'project_group', 'team_group')
  |     |
  |     +-- conversation_participants (NEW: conversation_id, user_id, last_read_sequence)
  |     |
  |     +-- messages (RESTRUCTURED: conversation_id, sequence_number, content_type, idempotency_key)
  |           Removed: to_user, read, project (now on conversations)
  |
  +-- oauth_clients, oauth_codes, oauth_tokens (unchanged)
```

### Module Map
```
src/ai_mailbox/
  errors.py          -- NEW: make_error(), is_error(), ERROR_CODES
  web.py             -- NEW: Jinja2 web routes (login, inbox, health, logout)
  templates/         -- NEW: base.html, login.html, inbox.html, health.html
  db/
    queries.py       -- REWRITTEN: 15 conversation-based query functions
    schema.py        -- MODIFIED: runs migrate_003 after DDL
    migrations/
      003_conversation_model.sql  -- NEW: DDL for 3 tables
      migrate_003.py              -- NEW: data migration script
  tools/
    send.py          -- MODIFIED: uses find_or_create_direct_conversation
    inbox.py         -- MODIFIED: conversation-based inbox with cursor read tracking
    reply.py         -- MODIFIED: any participant can reply
    thread.py        -- MODIFIED: conversation-based thread retrieval
    identity.py      -- MODIFIED: sequence-cursor unread counts
```

---

## Section 6: Current Work Item

**Next:** Sprint 2 spec (API Redesign + Rate Limiting)

### Sprint 2 Scope (from SPRINT_ROADMAP.md)
- `list_messages` replaces `check_messages` (no auto-mark-read, cursor pagination, filters)
- `mark_read` new tool (explicit batch acknowledgment)
- `send_message` enhanced (thread_id, content_type, idempotency_key, `to` accepts array for group messages)
- `reply_to_message` enhanced (any-participant-can-reply already done, add content_type, idempotency_key)
- `get_thread` enhanced (pagination, conversation metadata, participant list)
- `list_users` new tool (extracted from whoami)
- `create_group` or `add_participant` -- add users to existing conversations
- Rate limiting via `limits` library (per-user, all tools)
- Web UI: inbox list with projects, unread counts, conversation list
- GitHub: close issues #4, #6, #12

### Success Criteria
- All new/modified MCP tool signatures documented in spec before implementation
- Rate limit tests verify 429 responses on exceed
- Web inbox displays real conversation data (not just empty state)
- 160+ tests passing
- Deployed to MVP 1 Staging with all tools functional

---

## Section 7: Blocking Issues

None. Sprint 1 is complete and deployed. Sprint 2 can begin immediately.

---

## Section 8: Dependencies

| Dependency | Status | Notes |
|---|---|---|
| Railway MVP 1 Staging | Healthy | Auto-deploy from push not working; use `railway deploy` |
| PostgreSQL (MVP 1 Staging) | Healthy | Migration 003 applied |
| jinja2 | Added to pyproject.toml | Installed in Docker build |
| `limits` library | Not yet added | Needed for Sprint 2 rate limiting |

---

## Section 9: Environment

| Item | Value |
|---|---|
| OS | Windows 11 Pro |
| Python | 3.13.6 |
| Shell | bash (via Claude Code) |
| Python launcher | `py` (not `python`) |
| Package manager | pip + hatchling |
| Test runner | pytest 9.0.2 |
| Railway CLI | npx @railway/cli@latest |
| Git branch | mvp-1-staging |
| Railway env | MVP 1 Staging |
| Domain | ai-mailbox-server-mvp-1-staging.up.railway.app |

---

## Section 10: Files Modified This Session

### New Files (12)
- `src/ai_mailbox/errors.py`
- `src/ai_mailbox/web.py`
- `src/ai_mailbox/templates/base.html`
- `src/ai_mailbox/templates/login.html`
- `src/ai_mailbox/templates/inbox.html`
- `src/ai_mailbox/templates/health.html`
- `src/ai_mailbox/db/migrations/003_conversation_model.sql`
- `src/ai_mailbox/db/migrations/migrate_003.py`
- `tests/test_errors.py`
- `tests/test_migration.py`
- `tests/test_web.py`
- `projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_1_SPEC.md`

### Modified Files (13)
- `pyproject.toml` (added jinja2, hatch artifacts)
- `src/ai_mailbox/db/queries.py` (complete rewrite)
- `src/ai_mailbox/db/schema.py` (migration 003 integration)
- `src/ai_mailbox/server.py` (web routes mounted)
- `src/ai_mailbox/tools/send.py` (structured errors + conversations)
- `src/ai_mailbox/tools/inbox.py` (conversation-based + cursor tracking)
- `src/ai_mailbox/tools/reply.py` (any-participant + structured errors)
- `src/ai_mailbox/tools/thread.py` (conversation-based + structured errors)
- `src/ai_mailbox/tools/identity.py` (sequence-cursor unread counts)
- `tests/conftest.py` (new schema, no migration path)
- `tests/test_queries.py` (complete rewrite)
- `tests/test_tools.py` (structured errors, new scenarios)
- `tests/test_server.py` (web route tests added)

---

## Section 11: Keith's Context

- Windows 11, Claude Code CLI, bash shell
- Direct communication, no walls of text
- TDD-first is non-negotiable
- SDD (Spec-Driven Development) for sprint specs -- spec approved before code
- Web UI mandatory in every sprint
- AI UX UAT required (browser verification by Claude)
- Human UAT required after AI UAT
- TDD extends through delivery (not just local tests)
- `py` not `python` on this machine
- Railway staging deployments permitted; production requires authorization
- GitHub mutations require explicit session authorization

---

## Section 12: Decisions Made This Session

1. **Direct conversation uniqueness: per-project.** keith+amy in "general" and keith+amy in "deployment" are separate conversations. Could expand to global in future.
2. **check_messages auto-advances read cursor in Sprint 1.** Backward compat. Sprint 2 splits into list_messages + mark_read.
3. **Web UI uses password-based login as Sprint 1 placeholder.** Google OAuth replaces in Sprint 6. Session cookie middleware carries forward.
4. **Any participant can reply.** Behavioral change from Sprint 0 (only to_user could reply). Enables group messaging.
5. **Human UAT is a required gate** after AI UX UAT. Sprint does not complete without both.
6. **Version bumped to 0.3.0** for web health page (API /health still shows 0.2.0 -- different code path).

---

## Section 13: Corrections Received

1. "AI UX UAT is required and TDD extends through delivery" -- added AI UAT gate (section 10.5b) and expanded implementation order to 10 steps including deployment verification.
2. "Human UAT is required after AI UX UAT" -- added Step 10 (human UAT) as a required gate before GitHub cleanup.
3. Dev server launch config was wrong (`python -m steertrue`). Fixed to `py -m ai_mailbox`.

---

## Section 14: Session Lessons

| Failure | Fix |
|---|---|
| Editable install pointed to wrong worktree | Verify `pip show ai-mailbox` location before testing |
| Railway push didn't auto-deploy | Use `railway deploy` CLI as fallback; investigate branch-to-env mapping |
| Chrome extension tab lost context mid-UAT | Create fresh tab for each UAT sequence; don't reuse tabs from other sessions |
| SQLite cross-thread error in web tests | Use `check_same_thread=False` for SQLite in async test fixtures |
| conftest.py schema diverged from migrations | Test conftest creates fresh schema directly (no migration), so it must be kept in sync manually with any DDL changes |

---

## Section 15: Test Evidence

```
140 passed, 8 warnings in 9.46s

Breakdown:
- test_errors.py:     14 tests (error framework)
- test_migration.py:  21 tests (schema + data migration)
- test_queries.py:    43 tests (query layer)
- test_tools.py:      22 tests (MCP tool integration)
- test_web.py:        21 tests (web UI routes)
- test_server.py:      8 tests (server integration)
- test_auth.py:        3 tests (unchanged from Sprint 0)
- test_oauth.py:       8 tests (unchanged from Sprint 0, 8 warnings about key length)
```

---

## Section 16: Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| Railway auto-deploy not working for mvp-1-staging | Medium | Manual `railway deploy` works. Investigate branch-env mapping. |
| Production migration on real data | High | Migration script is idempotent and tested. Test on staging first before any production promotion. |
| conftest.py schema drift | Medium | Any DDL change must update both migration SQL and conftest.py schema string. |
| OAuth tests have key length warnings | Low | Test JWT secret is 23 bytes (below 32-byte minimum). Production secret is 64+ bytes. |

---

## Section 17: Quick Start for Next Session

```
1. Read this handoff
2. Read projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md
3. Read projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_1_SPEC.md (for reference)
4. Read docs/plans/SPRINT_ROADMAP.md (Sprint 2 scope)
5. Verify: cd "C:/Projects/SINGLE PROJECTS/ai-mailbox" && git branch (should be mvp-1-staging)
6. Verify: py -m pytest -q (should be 140 passed)
7. Verify: curl https://ai-mailbox-server-mvp-1-staging.up.railway.app/health (should be healthy)
8. Write Sprint 2 spec (SDD): API redesign, rate limiting, enhanced tools, web inbox
9. Get spec approved before any implementation
10. Begin Sprint 2 TDD on mvp-1-staging branch
```

**First file to open:** `projects/AI_MAILBOX_PROJECT_PLAN/docs/plans/SPRINT_ROADMAP.md` (Sprint 2 section)

**Do NOT redo:**
- Sprint 1 implementation (complete and deployed)
- Schema design (conversations + participants + messages is locked)
- Error framework (make_error/is_error are stable)
- Web scaffold (templates + web.py are in place)

---

## Section 18: Continuation Prompt

```
Read these files in order, then begin Sprint 2 spec work:

1. projects/AI_MAILBOX_PROJECT_PLAN/docs/handoffs/2026-04-05-SPRINT1-HANDOFF-V3.md
2. projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md
3. projects/AI_MAILBOX_PROJECT_PLAN/docs/specs/SPRINT_1_SPEC.md
4. projects/AI_MAILBOX_PROJECT_PLAN/docs/plans/SPRINT_ROADMAP.md

Context: AI Mailbox is an MCP messaging server (Python/FastMCP/PostgreSQL/Railway)
being evolved from POC to Alpha SaaS. Sprint 1 is complete -- three-table
conversation model deployed, structured errors, cursor-based read tracking,
web UI scaffold (login, inbox, health). 140 tests passing on mvp-1-staging.

Your task: Write the Sprint 2 spec (Spec-Driven Development). Sprint 2 is
"API Redesign + Rate Limiting" -- replace check_messages with list_messages
(pure read) + mark_read (explicit write), enhance send_message to accept
array recipients for group messaging, add create_group/add_participant tools,
add list_users tool, implement rate limiting via limits library, and build
web inbox with real conversation data. The spec must define MCP tool signatures,
rate limit thresholds, web routes, edge cases, and acceptance criteria.
Get the spec approved before writing any code. Then implement via TDD on the
mvp-1-staging branch, deploying to the MVP 1 Staging Railway environment.

Work from: C:\Projects\SINGLE PROJECTS\ai-mailbox
Branch: mvp-1-staging
Railway environment: MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
```
