## Carry Over (Tech Debt)

- Add GitHub OAuth to MCP login page (Claude Desktop can't use GitHub to auth) [SPRINT-7, deferred]
- Investigate Railway auto-deploy from branch push [TD-002]
- Resolve production dual-Postgres question (both at 0MB) [TD-003]
- Tailwind CDN in production -- add build step [TD-005]
- Update Amy's MCP connector URL to production [TD-007]

## Sprint 7 — MCP Apps Inbox Widget (IN PROGRESS)

**Decision**: Replaced outbound webhooks with MCP Apps interactive UI. Webhooks are server-to-server; our users are in Claude Desktop, claude.ai, ChatGPT. MCP Apps renders HTML iframes inside chat windows.

**Implementation phases:**
1. Server-side: register `ui://ai-mailbox/inbox.html` resource + attach to `mailbox_list_messages` tool via `meta` — TDD
2. Widget HTML: conversation list, thread view, compose form — vanilla JS + DaisyUI 4 + callServerTool
3. Unit tests: resource registration, HTML content assertions, tool metadata
4. AI UX UAT: Claude Code preview tools verify widget renders and functions in browser
5. Human UAT: Keith tests on Claude Desktop connected to staging
6. Browser testing: basic-host harness + direct HTML testing with mock data

**Detailed plan:** `C:\Users\keith\.claude\plans\drifting-waddling-nest.md`

## Sprint 7 — Remaining Features (after widget)

- Dead letter handling for offline agents
- System messages (reserved `system` sender)
- Email notifications (may consume widget events internally)
- Production hardening

## Completed

- Sprints 1-6 implemented via TDD. 471 tests. (2026-04-05 to 2026-04-06)
- All GitHub issues closed except #15 (soft deletes). (2026-04-06)
- GitHub OAuth live on all environments (separate apps per env). (2026-04-06)
- Handle picker for new OAuth users + change handle in settings. (2026-04-06)
- MCP tool names prefixed mailbox_* to avoid Claude Desktop collisions. (2026-04-06)
- list_messages body truncation to 200 chars. (2026-04-06)
- Promoted to staging and production. All 3 environments live at v0.6.0. (2026-04-06)
- Production promotion runbook created. (2026-04-06)
- Keith's production account linked to GitHub (keith@ivenoclue.com). (2026-04-06)
- Production DB orphaned oauth_codes cleaned (FK constraint fix). (2026-04-06)
- BUG-001 fixed: to_user NOT NULL blocking all message sends. Migration 007. (2026-04-06)
- TD-001 resolved: conftest.py now uses real migration path, legacy columns no longer cause divergence. (2026-04-06)
- Full MCP tool test coverage: 534 tests, all 12 tools covered. (2026-04-06)
- Search query column shadowing bug fixed (legacy messages.project). (2026-04-06)
- Thread context controls: default limit=5, 2K body truncation, summary, body_display_note. (2026-04-06)
- Schema parity guard (test_schema_parity.py) prevents future BUG-001-class bugs. (2026-04-06)
