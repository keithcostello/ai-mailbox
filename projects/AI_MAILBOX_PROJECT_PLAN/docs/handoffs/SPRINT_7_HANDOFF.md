# Sprint 7 Session Handoff

## Session Summary

Sprint 7 focused on three areas: critical bug fixes, full test coverage, and the MCP Apps inbox widget.

## Current State

- **Branch:** `mvp-1-staging` — 13 commits this session, all pushed
- **Tests:** 550 passing, 0 failures
- **Staging:** Deployed and live at `ai-mailbox-server-mvp-1-staging.up.railway.app`
- **Widget:** MCP Apps inbox renders inside claude.ai with interactive thread navigation

## What Was Done

### Bug Fixes
- BUG-001: `to_user NOT NULL` constraint blocking all message sends — Migration 007
- TD-008: `migrate_003` boolean comparison — parameterized `True` for PostgreSQL
- Search query column shadowing — `SELECT m.*` exposed legacy `messages.project` over `conversations.project`
- OAuth issuer URL hardcoded to production — now uses `RAILWAY_PUBLIC_DOMAIN` env var
- UUID serialization in `CallToolResult.structuredContent`

### Test Coverage (474 → 550 tests)
- Replaced conftest.py clean-room schema with `ensure_schema_sqlite()` real migration path
- 60 new tests covering all 12 MCP tools (send, reply, thread, whoami, list_messages, mark_read, list_users, create_group, add_participant, search, acknowledge, archive)
- Schema parity guard (`test_schema_parity.py`) prevents future BUG-001-class bugs
- Thread context controls: default limit=5, 2K body truncation, summary field

### MCP Apps Inbox Widget
- Interactive HTML widget renders inside claude.ai conversation
- Inbox view → click conversation → thread view with messages, avatars, reply form
- `callServerTool` works through Claude's AppBridge iframe proxy
- All CSS/JS inlined (Claude CSP blocks external CDN resources)
- MCP Apps handshake: `protocolVersion: "2026-01-26"`, `appInfo`, `appCapabilities`
- `CallToolResult` with `structuredContent` for widget data delivery
- Runbook created: `docs/runbooks/MCP_APPS_WIDGET_RUNBOOK.md`

## Commits (13)

| Hash | Description |
|------|-------------|
| `c0f1df6` | BUG-001 fix + full test coverage (474→534) + context controls |
| `8c8330e` | migrate_003 boolean fix (TD-008) |
| `470d4d1` | MCP Apps inbox widget (initial) |
| `0df77ce` | OAuth issuer URL per-environment |
| `f2a7e58` | CSP on resource, legacy meta key |
| `62d36bd` | CallToolResult with structuredContent |
| `a7d4ef7` | UUID serialization fix |
| `2d95bdd` | Inline all CSS/JS (CSP blocks CDN) |
| `dbea874` | Fix handshake direction |
| `dff8d33` | Correct protocol version + appInfo params |
| `c914de9` | Walking skeleton static content |
| `49346ce` | Debug bar + error display (diagnostic) |
| `61ab184` | Clean up widget, production-ready |

## UAT Requirements (NEW — from user)

The user has defined a three-tier UAT process that must be implemented before further Sprint 7 features:

### Tier 1: AI Automated UAT (every tool, every change)
- Every MCP tool call must have a contextual integration test that runs against live staging
- Any change to a tool's implementation triggers rerun of that tool's UAT
- Tests exercise the full path: tool function → queries → database → response shape
- **Already partially covered by 550 pytest tests — need to formalize as a UAT process**

### Tier 2: AI UX UAT (1 out of 6 tools per cycle)
- Rotational browser-based visual verification using Claude in Chrome / Preview MCP
- Each cycle tests 2 tools (1/6 of 12) through the actual claude.ai interface
- Verifies: tool call succeeds, widget renders, data displays correctly, interactions work
- **Rotation schedule needed**

### Tier 3: Human UAT (required)
- Keith runs manual checklist on claude.ai or Claude Desktop
- Pass/fail for each tool and interaction
- Must sign off before production promotion

## Next Steps

### AI (Next Session)
1. **Create UAT process document** (`docs/runbooks/UAT_PROCESS.md`) defining:
   - Tier 1 test manifest (which tests cover which tools)
   - Tier 2 rotation schedule (which 2 tools per cycle)
   - Tier 3 human checklist template
   - Trigger rules (when to rerun which tier)
2. **Implement Tier 1 staging integration tests** — pytest tests that can run against staging URL
3. **Implement remaining Sprint 7 features**: dead letter handling, system messages
4. **First file to open:** `projects/AI_MAILBOX_PROJECT_PLAN/docs/runbooks/UAT_PROCESS.md` (create it)

### Human (Keith)
1. **Run Human UAT** on claude.ai with staging connector:
   - [ ] Say "check inbox" → widget renders with conversations
   - [ ] Click a conversation → thread view loads
   - [ ] Verify reply form appears at bottom of thread
   - [ ] Test Compose button → form with recipient/project/subject/body
   - [ ] Verify Back button returns to inbox
   - [ ] Try sending a message via the tool (not widget) → verify it appears in widget on refresh
2. **Decide** on dead letter handling scope (what happens when an agent is offline?)
3. **Decide** on system messages format (what does `system` sender look like in the widget?)

## Do Not Redo

- conftest.py migration path — done, tested, committed
- MCP Apps widget rendering — proven working in claude.ai
- BUG-001 fix — migration 007 deployed
- TD-008 boolean fix — deployed
- Schema parity guard — committed
- Thread context controls — committed
- OAuth issuer URL fix — deployed

## Proof/Check

```bash
# Verify tests
cd "C:/Projects/SINGLE PROJECTS/ai-mailbox" && py -m pytest tests/ -q
# Expected: 550 passed

# Verify staging health
curl https://ai-mailbox-server-mvp-1-staging.up.railway.app/health
# Expected: {"status":"healthy","version":"0.6.0",...}

# Verify widget in claude.ai
# Go to claude.ai > new chat > "check inbox" > widget should render
```

## Bounded Scope Guard

Next session should focus on:
1. UAT process document + implementation (Tier 1 and Tier 2)
2. Dead letter handling
3. System messages

Out of scope until UAT is defined:
- Production promotion
- Email notifications (depends on system messages)
- GitHub OAuth on MCP login (deferred)
- Tech debt TD-002 through TD-007
