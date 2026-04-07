# AI Mailbox -- Sprint 8 Continuation Prompt

## Identity
Project: AI Mailbox (MCP messaging for AI agents + humans)
Branch: `mvp-1-staging`
Tests: 589 passing
Production: https://ai-mailbox-server-production.up.railway.app (v0.7.0)
Staging: https://ai-mailbox-server-mvp-1-staging.up.railway.app (v0.7.0)

## Read These Files First
1. `CLAUDE.md` -- hard rules (TDD, SteerTrue, no sycophancy)
2. `projects/AI_MAILBOX_PROJECT_PLAN/memory/TODO.md` -- current task list
3. `projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md` -- project status
4. `docs/runbooks/UAT_PROCESS.md` -- three-tier UAT with 13 repeatable prompts

## What's Done (Do Not Redo)
- Sprints 1-7 complete. 589 tests. 13 MCP tools. v0.7.0.
- Dead letter handling: delivery_status column, offline detection (24h threshold), auto-redelivery on next activity, system message on queue
- System messages: reserved 'system' user, insert_system_message(), event messages on participant join and dead letter
- list_participants tool (#13): authoritative group membership
- BUG-001 (to_user NOT NULL), BUG-002 (whoami Postgres HAVING alias) both fixed
- conftest.py uses real migration path + schema parity guard
- MCP Apps inbox widget renders in claude.ai (inline CSS/JS)
- Three-tier UAT process: Tier 3 Human UAT 13/13 PASS
- Staging-to-production runbook at docs/runbooks/STAGING_TO_PRODUCTION.md
- Merged to master, deployed to production, health confirmed

## What's Next (Sprint 8)

### AI Tasks
1. **Email notifications** -- notify users when they receive messages while offline (pairs with dead letter handling)
2. **Resolve TD-002** -- Railway auto-deploy from branch push broken
3. **Resolve TD-007** -- Update Amy's MCP connector URL to production
4. **Sprint 8 spec** -- write docs/specs/SPRINT_8_SPEC.md

### Human Tasks (Keith)
1. Production smoke test: steps 1, 5, 12 from UAT checklist against production URL
2. Send Amy her setup instructions and credentials
3. Decide email notification scope (which events trigger emails? SMTP provider?)

## Tech Debt

| ID | Description | Priority |
|----|-------------|----------|
| TD-002 | Railway auto-deploy from branch push broken | P2 |
| TD-003 | Dual Postgres instances on Railway, both 0MB | P3 |
| TD-005 | Tailwind CDN in production -- add build step | P3 |
| TD-007 | Amy's MCP connector URL needs production update | P2 |
| #15 | Soft deletes for messages (GitHub issue) | P3 |

## Hard Rules
- `py` not `python`
- TDD always -- failing test first
- Every tool change triggers Tier 1 UAT rerun
- Human UAT required before production promotion
- No sycophancy (SteerTrue governance enforced)
- 2-3 paragraphs max, one question per response

## Key Files
- `src/ai_mailbox/server.py` -- MCP server, 13 tool registrations, widget resource
- `src/ai_mailbox/ui/inbox_widget.html` -- MCP Apps widget (inline CSS/JS)
- `src/ai_mailbox/db/queries.py` -- all database operations incl. dead letters
- `src/ai_mailbox/tools/*.py` -- 13 tool implementations
- `tests/conftest.py` -- db fixture via ensure_schema_sqlite
- `src/ai_mailbox/config.py` -- MAX_BODY_LENGTH, DEAD_LETTER_THRESHOLD_HOURS
- `docs/runbooks/UAT_PROCESS.md` -- 13 repeatable test prompts

## First Action
Open `projects/AI_MAILBOX_PROJECT_PLAN/memory/TODO.md`, then provide a concise current-state dashboard and WAIT FOR INSTRUCTION.

## Proof Command
```bash
cd "C:/Projects/SINGLE PROJECTS/ai-mailbox" && py -m pytest tests/ -q
# Expected: 589 passed
```
