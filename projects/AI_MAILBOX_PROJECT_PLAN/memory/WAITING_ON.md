# AI_MAILBOX_PROJECT_PLAN

**Status:** ACTIVE
**North Star:** Evolve AI Mailbox from POC to Alpha SaaS -- 8-sprint roadmap, Sprint 6 complete, all environments live, ready for Sprint 7
**Expected Branch:** mvp-1-staging
**PR URL:**
**Relevant Handoff:** projects/AI_MAILBOX_PROJECT_PLAN/docs/handoffs/SPRINT_7_CONTINUATION_PROMPT.md

## Next Steps

- Write Sprint 7 spec (webhooks, notifications, MCP GitHub OAuth, dead letter, migrate_003 fix)
- Implement Sprint 7 via TDD (target 520+ tests)
- Deploy and pass AI UX UAT + Human UAT
- Update Amy's MCP connector to production URL

## Pending Tasks

- MCP login page needs GitHub OAuth (Claude Desktop users can't use GitHub to auth) [SPRINT-7]
- migrate_003 boolean fix for PostgreSQL production data (24 old messages) [TD-008]
- Railway auto-deploy from branch push not working (used CLI fallback) [TD-002]
- Resolve production dual-Postgres question (both at 0MB) [TD-003]
- Staging DB has legacy columns (to_user, read, project on messages) [TD-001]
- Tailwind CDN in production -- add build step [TD-005]
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
