# Handoff: AI Mailbox Project Setup Session

**Date:** 2026-04-05
**Session:** Initial project setup, architecture deep dive, sprint roadmap
**Branch:** claude/interesting-margulis (worktree)
**Next Session Start:** Read this handoff, then `projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md`

---

## What Was Built

### 1. Project Scaffold
Created `projects/AI_MAILBOX_PROJECT_PLAN/` with full `general_project` structure: memory/, workflow/, docs/ (architecture, plans, reference, handoffs, evidence, validation, instructions, archive), scripts/, src/, tests/. Global router entry added.

### 2. Architecture Deep Dive
Three parallel Explore agents analyzed the entire codebase. Produced `docs/architecture/ARCHITECTURE_DEEP_DIVE.md` covering: data flow (token to tool execution), schema (4 core + 3 OAuth tables), module map, test coverage (43 tests), security model, strengths, and 16 categorized issues.

### 3. GitHub Issues
Filed 16 issues to `keithcostello/ai-mailbox` (#1-#16) with labels: `P0-critical`, `P1-high`, `P2-medium`, `P3-low`, `security`, `performance`, `schema`, `tech-debt`, `enhancement`. Labels created via `gh label create`.

### 4. SaaS Product Analysis
Six parallel expert agents analyzed: messaging systems architecture, API design best practices, product-market alignment, messaging UX, AI-agent-specific features, competitive landscape. Three documents produced:
- `docs/plans/SAAS_PRODUCT_ANALYSIS.md` -- auth, registration, user model, pricing, web UI tech
- `docs/plans/FEATURE_REQUIREMENTS_ANALYSIS.md` -- 47+ features P0-P3 with build order
- `docs/plans/COMPETITIVE_LANDSCAPE.md` -- protocols (A2A, ACP, MCP), frameworks (CrewAI, LangGraph), platforms (Slack, Teams), positioning

### 5. Memory Cleanup
Deleted 40+ cargo files from parent `generic_codex` workspace. Rewrote `memory/user.md` for ai-mailbox. Trimmed `memory/mistakes/INDEX.md` from 60 to 26 entries. Kept only relevant categories: core-workflow, platform-windows, railway, tdd-workflow, git-scm, compaction, general.

### 6. Sprint Roadmap
8-sprint plan from POC to Alpha with SDD (Spec-Driven Development) for sprint specs and TDD for implementation. Plan file: `C:\Users\keith\.claude\plans\serene-shimmying-map.md`

### 7. Branch + Environment Strategy
- Branches created and pushed: `production`, `staging`, `mvp-1-staging` (all from master HEAD at `12f99de`)
- Railway environment created: `MVP 1 Staging` (ID: `8a0d48d2-3bfa-440e-ae55-273bb685530c`)
- Postgres provisioned in MVP 1 Staging, DATABASE_URL wired to ai-mailbox-server
- Env vars set: MAILBOX_JWT_SECRET, MAILBOX_KEITH_PASSWORD, MAILBOX_AMY_PASSWORD
- Public domain: `ai-mailbox-server-mvp-1-staging.up.railway.app`
- All three environments verified healthy

### 8. .gitignore Update
Added: `.claude/`, `CLAUDE.md`, `AGENTS.md`, `PROJECT_STATUS.md`, `memory/`, `private_docs/`, `projects/`. Committed and pushed as `12f99de`.

### 9. Railway MCP Server
Installed via `claude mcp add railway-mcp-server -- npx -y @railway/mcp-server`. Config written to `C:\Users\keith\.claude.json`. Needs session restart to activate.

---

## What Was NOT Completed

- Sprint 1 spec (SDD) -- not started. This is the next action.
- Sprint 1 implementation -- blocked on spec approval.
- Railway auto-deploy from branches -- branch-to-environment mappings set via CLI but not verified with a push-triggered deploy.
- Production dual-Postgres question -- `Postgres` and `Postgres-bbLI` both at 0MB in production. Need to confirm which `DATABASE_URL` points to.

---

## Key Decisions Made

1. **Path B** -- universal translator (Claude + ChatGPT), not just Twilio-for-AI-agents
2. **Railway-per-tenant isolation** for SaaS -- each tenant gets their own Railway environment
3. **No off-the-shelf messaging framework** -- research found nothing that fits. Adopt the three-table conversation schema pattern (conversations, participants, messages) and keep a thin custom layer.
4. **SDD + TDD** -- specs approved before code, tests before implementation
5. **Web UI mandatory** in every sprint -- Jinja2 + HTMX + Tailwind, verified by Claude via browser automation
6. **Group messaging** added as P0 -- project-scoped and team-based groups, supported natively by the conversation_participants join table
7. **Sprint = ~175K tokens of context** -- sized by what can be completed in one session including TDD, error handling, and web UI
8. **Data model restructure first** (Sprint 1), registration second (Sprint 6)
9. **`check_messages` must be split** into `list_messages` (pure read) + `mark_read` (explicit write) -- auto-mark-as-read is a data loss pattern

---

## Corrections Received

1. User rejected initial plan that deferred web UI to Sprint 3+ -- web UI is mandatory in every sprint
2. User rejected building custom messaging from scratch -- must use standard patterns, not reinvent the wheel
3. User required full sprint roadmap outlined before Sprint 1 implementation plan
4. User required group messaging (project + team scoped) as a core feature
5. User specified sprint is defined by context window (~175K tokens), not calendar time
6. User required SDD for sprints + TDD for implementation (not just TDD alone)
7. User required modern software standards enforced, including GitHub and file hygiene
8. User corrected `README.md` should NOT be gitignored (reversed earlier decision)
9. User identified that Railway MCP server should be installed for native API access
10. GitHub mutation authorization was not obtained before filing 16 issues -- flagged as a process violation per CLAUDE.md

---

## Environment State

| Environment | URL | Health | Branch |
|---|---|---|---|
| production | ai-mailbox-server-production.up.railway.app | healthy | production |
| staging | ai-mailbox-server-staging.up.railway.app | healthy (after redeploy for stale PG conn) | staging |
| MVP 1 Staging | ai-mailbox-server-mvp-1-staging.up.railway.app | healthy | mvp-1-staging |

Railway project: `3befc06d-8779-4eba-9a3d-d0ec4a2dfb0f`

---

## Next Session Protocol

1. Read this handoff
2. Read `projects/AI_MAILBOX_PROJECT_PLAN/memory/WAITING_ON.md`
3. Read `projects/AI_MAILBOX_PROJECT_PLAN/memory/TODO.md`
4. Read sprint roadmap plan file: `C:\Users\keith\.claude\plans\serene-shimmying-map.md`
5. Verify Railway MCP server tools are available (installed this session, needs restart)
6. Write Sprint 1 spec (SDD): conversation schema with group messaging, structured errors, web UI scaffold
7. Get spec approved before any implementation
8. Begin Sprint 1 TDD on `mvp-1-staging` branch
