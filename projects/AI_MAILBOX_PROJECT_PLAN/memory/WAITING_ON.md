# AI_MAILBOX_PROJECT_PLAN

**Status:** ACTIVE
**North Star:** Evolve AI Mailbox from POC to Alpha SaaS -- 8-sprint roadmap, Sprint 7 in progress
**Expected Branch:** mvp-1-staging
**PR URL:**
**Relevant Handoff:** projects/AI_MAILBOX_PROJECT_PLAN/docs/handoffs/SPRINT_7_CONTINUATION_PROMPT.md

## Next Steps

- Implement MCP Apps inbox widget (Sprint 7 primary feature)
- Run AI UX UAT (preview tools) + Human UAT (Keith on Claude Desktop)
- Deploy widget to staging, then production
- Implement remaining Sprint 7: dead letter handling, system messages, email notifications

## Pending Tasks

- MCP Apps inbox widget — server resource + HTML + tests + UAT [SPRINT-7, IN PROGRESS]
- Dead letter handling for offline agents [SPRINT-7]
- System messages (reserved `system` sender) [SPRINT-7]
- Email notifications [SPRINT-7]
- MCP login page GitHub OAuth (deferred — password login works for testing) [SPRINT-7]
- Railway auto-deploy from branch push not working [TD-002]
- Resolve production dual-Postgres question (both at 0MB) [TD-003]
- Tailwind CDN in production — add build step [TD-005]
- Amy's MCP connector URL needs updating for production [TD-007]
- GitHub issue #15 open: soft deletes for messages

## Document Index (Required)

| Document | Status | Owner |
| --- | --- | --- |
| `memory/WAITING_ON.md` | active | Claude |
| `memory/TODO.md` | active | Claude |
| `docs/specs/SPRINT_1_SPEC.md` through `SPRINT_6_SPEC.md` | complete | Claude |
| `docs/runbooks/STAGING_TO_PRODUCTION.md` | active | Claude |
| `docs/plans/SPRINT_ROADMAP.md` | active | Claude |
| `docs/handoffs/SPRINT_7_CONTINUATION_PROMPT.md` | current | Claude |

## Recent Activity Log

- 2026-04-05: Sprints 1-2 implemented. 287 tests. Issues #4-8, #12 closed.
- 2026-04-06: Sprints 3-5 implemented. 424 tests. Issues #1-3, #9-11, #14, #16 closed.
- 2026-04-06: Sprint 6 implemented (GitHub OAuth, settings, invite mode, README). 461 tests. Issue #13 closed.
- 2026-04-06: Handle picker + change handle. 471 tests.
- 2026-04-06: GitHub OAuth apps configured (staging + production separate apps).
- 2026-04-06: Tool names prefixed mailbox_* to fix Claude Desktop collision.
- 2026-04-06: list_messages body truncation (200 chars) to prevent token overflow.
- 2026-04-06: Promoted to staging and production. All 3 environments live at v0.6.0.
- 2026-04-06: Production runbook created at docs/runbooks/STAGING_TO_PRODUCTION.md.
- 2026-04-06: BUG-001 fixed (to_user NOT NULL blocking all sends). Migration 007.
- 2026-04-06: Full MCP tool test coverage (534 tests, all 12 tools). conftest.py uses real migration path.
- 2026-04-06: Search query column shadowing bug fixed (legacy messages.project vs conversations.project).
- 2026-04-06: Thread context controls: default limit=5, 2K body truncation, summary field.
- 2026-04-06: Schema parity guard (test_schema_parity.py) prevents future BUG-001-class bugs.
- 2026-04-06: TD-001 resolved — legacy columns no longer cause test/prod divergence.
