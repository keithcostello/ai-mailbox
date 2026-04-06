# AI_MAILBOX_PROJECT_PLAN

**Status:** ACTIVE
**North Star:** Evolve AI Mailbox from POC to Alpha SaaS -- 8-sprint roadmap, Sprint 6 complete, ready for Sprint 7
**Expected Branch:** mvp-1-staging
**PR URL:**
**Relevant Handoff:** projects/AI_MAILBOX_PROJECT_PLAN/docs/handoffs/SPRINT_6_CONTINUATION_PROMPT.md

## Next Steps

- Write Sprint 7 spec (webhooks, notifications, dead letter, system messages)
- Implement Sprint 7 via TDD
- Configure GitHub OAuth app and set env vars on Railway for live OAuth testing
- Deploy and pass AI UX UAT + Human UAT

## Pending Tasks

- Railway auto-deploy from mvp-1-staging push not working (used CLI fallback) [TD-002]
- Resolve production dual-Postgres question (Postgres vs Postgres-bbLI, both at 0MB) [TD-003]
- Staging DB has legacy columns (to_user, read, project on messages) -- migration 003 didn't drop them [TD-001]
- Tailwind CDN in production -- acceptable for alpha, track for Sprint 6+ build step [TD-005]
- GitHub OAuth not yet tested live (no GitHub OAuth app configured on Railway) [TD-006]

## Document Index (Required)

### Structural Hygiene References

| Document | Path | Purpose |
| --- | --- | --- |
| Placement Standard | `.codex/agents/librarian/STRUCTURAL_HYGIENE_STANDARD.md` | Where every doc type goes |
| Migration Guide | `.codex/agents/librarian/MIGRATION_GUIDE.md` | How to reorganize docs |

### Project Documents

| Document | Status | Owner | Linked Task / Usage Evidence |
| --- | --- | --- | --- |
| `memory/WAITING_ON.md` | active | Claude | Project tracker |
| `memory/TODO.md` | active | Claude | Carry-over ledger |
| `docs/specs/SPRINT_1_SPEC.md` | complete | Claude | Sprint 1 spec, approved and implemented |
| `docs/specs/SPRINT_2_SPEC.md` | complete | Claude | Sprint 2 spec, approved, implemented, deployed |
| `docs/specs/SPRINT_3_SPEC.md` | complete | Claude | Sprint 3 spec, approved, implemented, deployed |
| `docs/specs/SPRINT_4_SPEC.md` | complete | Claude | Sprint 4 spec, approved, implemented, deployed |
| `docs/specs/SPRINT_5_SPEC.md` | complete | Claude | Sprint 5 spec, approved, implemented, deployed |
| `docs/specs/SPRINT_6_SPEC.md` | complete | Claude | Sprint 6 spec, approved, implemented, deployed |
| `docs/architecture/ARCHITECTURE_DEEP_DIVE.md` | complete | Claude | Codebase analysis, 16 issues filed |
| `docs/reference/RAILWAY_ENVIRONMENTS.md` | complete | Claude | Environment documentation |
| `docs/plans/SAAS_PRODUCT_ANALYSIS.md` | complete | Claude | Auth, registration, pricing, UI analysis |
| `docs/plans/FEATURE_REQUIREMENTS_ANALYSIS.md` | complete | Claude | 47 features prioritized P0-P3 |
| `docs/plans/COMPETITIVE_LANDSCAPE.md` | complete | Claude | Protocols, frameworks, positioning |
| `docs/plans/SPRINT_ROADMAP.md` | active | Claude | 8-sprint plan |
| `docs/handoffs/SPRINT_5_CONTINUATION_PROMPT.md` | archived | Claude | Sprint 5 continuation prompt (used) |
| `docs/handoffs/SPRINT_6_CONTINUATION_PROMPT.md` | archived | Claude | Sprint 6 continuation prompt (used) |

## Recent Activity Log

- 2026-04-05: Sprints 1-2 implemented. 287 tests. Issues #4-8, #12 closed.
- 2026-04-06: Sprint 3 implemented (security + DaisyUI). 320 tests. Issues #1-3, #16 closed.
- 2026-04-06: Sprint 4 implemented (search, JSON, polling). 372 tests. Issue #14 closed.
- 2026-04-06: Sprint 5 implemented (ACK, archiving, agent identity, tech debt). 424 tests. Issues #9-11 closed.
- 2026-04-06: UI redesign: fantasy->corporate theme, chat bubbles->flat Slack-style, monochrome+accent design.
- 2026-04-06: UI polish: bolder names, colored avatars, primary unread counts (f5801f1). Human UAT passed.
- 2026-04-06: Sprint 6 implemented (GitHub OAuth, settings page, invite mode, README, version fix). 461 tests. Issue #13 closed.
