# AI_MAILBOX_PROJECT_PLAN

**Status:** ACTIVE
**North Star:** Evolve AI Mailbox from POC to Alpha SaaS -- 8-sprint roadmap, Sprint 7 nearly complete
**Expected Branch:** mvp-1-staging
**PR URL:**
**Relevant Handoff:** docs/handoff/ai-mailbox/HANDOFF_AI-MAILBOX_2026-04-06_V3.md

## Next Steps

- Keith: Run Human UAT (Tier 3) on claude.ai -- checklist in docs/runbooks/UAT_PROCESS.md
- Implement email notifications (Sprint 7 remaining)
- Production hardening and deploy
- Sprint 8 planning

## Pending Tasks

- Human UAT sign-off (Tier 3) [SPRINT-7, BLOCKING PRODUCTION]
- Email notifications [SPRINT-7]
- Production hardening [SPRINT-7]
- MCP login page GitHub OAuth (deferred) [SPRINT-7]
- Railway auto-deploy from branch push not working [TD-002]
- Resolve production dual-Postgres question (both at 0MB) [TD-003]
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
| `docs/runbooks/MCP_APPS_WIDGET_RUNBOOK.md` | active | Claude |
| `docs/runbooks/UAT_PROCESS.md` | active | Claude |
| `docs/plans/SPRINT_ROADMAP.md` | active | Claude |
| `docs/handoffs/SPRINT_7_HANDOFF.md` | current | Claude |
| `docs/bugs/BUG-001_to_user_not_null.md` | resolved | Claude |

## Recent Activity Log

- 2026-04-05: Sprints 1-2 implemented. 287 tests. Issues #4-8, #12 closed.
- 2026-04-06: Sprints 3-5 implemented. 424 tests. Issues #1-3, #9-11, #14, #16 closed.
- 2026-04-06: Sprint 6 implemented (GitHub OAuth, settings, invite mode, README). 461 tests.
- 2026-04-06: BUG-001 fixed + full MCP tool test coverage (534 tests). conftest migration path.
- 2026-04-06: migrate_003 boolean fix (TD-008). Thread context controls (limit=5, 2K truncation).
- 2026-04-06: MCP Apps inbox widget -- interactive HTML renders inside claude.ai.
- 2026-04-06: Resolved CSP issues (inline all CSS/JS), fixed handshake protocol, UUID serialization.
- 2026-04-06: Widget proven working: inbox view, click-to-thread, avatars, reply form, callServerTool.
- 2026-04-06: OAuth issuer URL fixed per-environment (RAILWAY_PUBLIC_DOMAIN).
- 2026-04-06: MCP Apps Widget Runbook created. 550 tests, 13 commits on mvp-1-staging.
- 2026-04-07: UAT process doc created (3 tiers, tool manifest, rotation schedule, human checklist).
- 2026-04-07: Dead letter handling implemented (20 tests). System messages implemented (11 tests).
- 2026-04-07: 581/581 tests passing. Deployed to staging. Tier 2 UAT Cycle 1 passed in claude.ai.
