# AI_MAILBOX_PROJECT_PLAN

**Status:** ACTIVE
**North Star:** Evolve AI Mailbox from POC to Alpha SaaS -- 8-sprint roadmap, Sprint 7 shipped, Sprint 8 next
**Expected Branch:** mvp-1-staging
**PR URL:**
**Relevant Handoff:** docs/handoff/ai-mailbox/HANDOFF_AI-MAILBOX_2026-04-06_V3.md

## Next Steps

- Keith: Send Amy setup instructions for production MCP connector
- Keith: Decide email notification scope for Sprint 8
- Sprint 8 planning (email notifications, TD-002, TD-007)
- Sprint 8 spec document

## Pending Tasks

- Email notifications [SPRINT-8, deferred from Sprint 7]
- Amy onboarding to production MCP [WAITING ON Keith]
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
| `docs/specs/SPRINT_1_SPEC.md` | complete | Claude |
| `docs/specs/SPRINT_2_SPEC.md` | complete | Claude |
| `docs/specs/SPRINT_3_SPEC.md` | complete | Claude |
| `docs/specs/SPRINT_4_SPEC.md` | complete | Claude |
| `docs/specs/SPRINT_5_SPEC.md` | complete | Claude |
| `docs/specs/SPRINT_6_SPEC.md` | complete | Claude |
| `docs/plans/SPRINT_ROADMAP.md` | active | Claude |
| `docs/plans/COMPETITIVE_LANDSCAPE.md` | reference | Claude |
| `docs/plans/FEATURE_REQUIREMENTS_ANALYSIS.md` | reference | Claude |
| `docs/plans/SAAS_PRODUCT_ANALYSIS.md` | reference | Claude |
| `docs/architecture/ARCHITECTURE_DEEP_DIVE.md` | reference | Claude |
| `docs/reference/RAILWAY_ENVIRONMENTS.md` | active | Claude |
| `docs/bugs/BUG-001_to_user_not_null.md` | resolved | Claude |
| `docs/runbooks/MCP_APPS_WIDGET_RUNBOOK.md` | active | Claude |
| `docs/runbooks/STAGING_TO_PRODUCTION.md` | active | Claude |
| `docs/handoffs/SPRINT_7_HANDOFF.md` | current | Claude |
| `docs/handoffs/SPRINT_7_CONTINUATION_PROMPT.md` | current | Claude |

## Recent Activity Log

- 2026-04-05: Sprints 1-2 implemented. 287 tests. Issues #4-8, #12 closed.
- 2026-04-06: Sprints 3-6 implemented. 461 tests. Issues #1-3, #9-11, #13-14, #16 closed.
- 2026-04-06: BUG-001 fixed. Full MCP tool coverage. 550 tests. MCP Apps widget.
- 2026-04-07: Dead letter handling (20 tests). System messages (11 tests). list_participants (8 tests).
- 2026-04-07: BUG-002 fixed (whoami Postgres HAVING alias). UAT process v1.1 (13 prompts).
- 2026-04-07: Tier 3 Human UAT: 13/13 PASS. 589 tests total.
- 2026-04-07: Merged mvp-1-staging to master. Deployed v0.7.0 to production. Health confirmed.
- 2026-04-07: BUG-003 fixed (unread_only returning own messages). 591 tests. Deployed to production.
- 2026-04-07: Production smoke test PASSED (Keith confirmed steps 1, 5, 12). Sprint 7 fully shipped.
