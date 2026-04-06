# AI_MAILBOX_PROJECT_PLAN

**Status:** ACTIVE
**North Star:** Evolve AI Mailbox from POC to Alpha SaaS -- 8-sprint roadmap, Sprint 4 complete, Sprint 5 spec written
**Expected Branch:** mvp-1-staging
**PR URL:**
**Relevant Handoff:** projects/AI_MAILBOX_PROJECT_PLAN/docs/handoffs/SPRINT_5_CONTINUATION_PROMPT.md

## Next Steps

- Approve Sprint 5 spec (SPRINT_5_SPEC.md)
- Implement Sprint 5 via 11-step TDD (target 410+ tests)
- Deploy and pass AI UX UAT + Human UAT
- Close GitHub issues #9, #10, #11

## Pending Tasks

- Sprint 5 spec written, awaiting approval
- Railway auto-deploy from mvp-1-staging push not working (used CLI fallback) [TD-002]
- Resolve production dual-Postgres question (Postgres vs Postgres-bbLI, both at 0MB) [TD-003]
- Staging DB has legacy columns (to_user, read, project on messages) -- migration 003 didn't drop them [TD-001]
- Tailwind CDN in production -- acceptable for alpha, track for Sprint 6+ build step [TD-005]

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
| `docs/specs/SPRINT_5_SPEC.md` | written | Claude | Sprint 5 spec, awaiting approval |
| `docs/architecture/ARCHITECTURE_DEEP_DIVE.md` | complete | Claude | Codebase analysis, 16 issues filed |
| `docs/reference/RAILWAY_ENVIRONMENTS.md` | complete | Claude | Environment documentation |
| `docs/plans/SAAS_PRODUCT_ANALYSIS.md` | complete | Claude | Auth, registration, pricing, UI analysis |
| `docs/plans/FEATURE_REQUIREMENTS_ANALYSIS.md` | complete | Claude | 47 features prioritized P0-P3 |
| `docs/plans/COMPETITIVE_LANDSCAPE.md` | complete | Claude | Protocols, frameworks, positioning |
| `docs/plans/SPRINT_ROADMAP.md` | active | Claude | 8-sprint plan |
| `docs/handoffs/SPRINT_5_CONTINUATION_PROMPT.md` | current | Claude | Sprint 5 continuation prompt |

## Recent Activity Log

- 2026-04-05: Sprint 1 spec written, 3 open questions resolved, approved.
- 2026-04-05: Sprint 1 implemented via 10-step TDD-through-delivery. 140 tests.
- 2026-04-05: Deployed to MVP 1 Staging. AI UX UAT + Human UAT passed.
- 2026-04-05: GitHub issues #5, #7, #8 closed.
- 2026-04-05: Sprint 2 spec written and approved (API redesign, rate limiting, group messaging).
- 2026-04-05: Sprint 2 core implemented via 8-step TDD. 254 tests passing. 29 files changed.
- 2026-04-05: 10 MCP tools registered (5 new, 4 enhanced, 1 deprecated).
- 2026-04-05: Deployed v0.4.0 to MVP 1 Staging. Health verified. AI UX UAT passed (9/9).
- 2026-04-05: Human UAT: inbox renders but lacks functional messaging UX.
- 2026-04-05: Decision: Replace Tailwind with Semantic UI. Add thread view, compose, reply, filtering.
- 2026-04-05: Semantic UI messaging UX implemented. Web UX functional.
- 2026-04-05: Human UAT found 3 filter bugs. Fixed. 287 tests passing.
- 2026-04-05: Filter bug fixes deployed. Ready for Human UAT re-verification.
- 2026-04-06: Human UAT passed. Sprint 2 committed (850aca8). GitHub issues #4, #6, #12 closed.
- 2026-04-06: Sprint 3 spec written (P0 security + DaisyUI migration). Approved.
- 2026-04-06: Sprint 3 implemented via parallel TDD. 320 tests passing. Deployed (988c2dc).
- 2026-04-06: Human UAT passed. GitHub issues #1, #2, #3, #16 closed. Sprint 3 COMPLETE.
- 2026-04-06: Sprint 4 spec written and approved (search, JSON payloads, live polling, check_messages removal, scopes normalization).
- 2026-04-06: Sprint 4 implemented via parallel TDD. 372 tests passing. 22 files changed.
- 2026-04-06: Migration runner fix for $$ dollar-quoted PL/pgSQL blocks (f172d9e).
- 2026-04-06: Deployed to MVP 1 Staging. Migration 004 (FTS) applied. AI UX UAT passed (5/5).
- 2026-04-06: Human UAT passed. GitHub issue #14 closed. Sprint 4 COMPLETE.
- 2026-04-06: Sprint 5 spec written (ACK, archiving, agent identity, tech debt #9/#10/#11). Awaiting approval.
