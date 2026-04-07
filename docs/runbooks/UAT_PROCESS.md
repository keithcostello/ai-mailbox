# UAT Process — AI Mailbox

**Version:** 1.0
**Created:** 2026-04-06
**Applies to:** All 12 MCP tools + MCP Apps widget

---

## Overview

Three tiers of acceptance testing. Every tool change must pass Tier 1. Production promotion requires all three tiers green.

| Tier | Who | What | When |
|------|-----|------|------|
| **Tier 1: AI Automated** | CI / AI | pytest against all tool test files | Every tool change |
| **Tier 2: AI UX** | AI (Claude in Chrome) | Browser-based verification in claude.ai | 2 tools per cycle, rotating |
| **Tier 3: Human** | Keith | Manual checklist, pass/fail per tool | Before production promotion |

---

## Tier 1: AI Automated UAT

### Trigger
Any change to files in `src/ai_mailbox/tools/`, `src/ai_mailbox/db/queries.py`, `src/ai_mailbox/server.py`, or `src/ai_mailbox/ui/`.

### Command
```bash
py -m pytest tests/ -q
```

### Pass Criteria
- 0 failures
- No regressions (test count >= previous baseline)

### Tool-to-Test Manifest

| # | Tool | Source | Primary Test Files | Test Count |
|---|------|--------|--------------------|------------|
| 1 | `mailbox_send_message` | `tools/send.py` | `test_send_full.py`, `test_tools.py`, `test_queries.py` | 10+ |
| 2 | `mailbox_reply_to_message` | `tools/reply.py` | `test_reply_full.py`, `test_tools.py` | 6+ |
| 3 | `mailbox_list_messages` | `tools/list_messages.py` | `test_list_messages.py`, `test_tools.py` | 21+ |
| 4 | `mailbox_get_thread` | `tools/thread.py` | `test_thread_full.py`, `test_tools.py` | 16+ |
| 5 | `mailbox_search_messages` | `tools/search.py` | `test_search.py`, `test_tools.py` | 24+ |
| 6 | `mailbox_acknowledge` | `tools/acknowledge.py` | `test_acknowledge.py`, `test_tools.py` | 20+ |
| 7 | `mailbox_mark_read` | `tools/mark_read.py` | `test_tools.py`, `test_whoami_full.py` | 5+ |
| 8 | `mailbox_archive_conversation` | `tools/archive.py` | `test_archive.py`, `test_tools.py` | 14+ |
| 9 | `mailbox_create_group` | `tools/create_group.py` | `test_group_tools.py`, `test_tools.py` | 27+ |
| 10 | `mailbox_add_participant` | `tools/add_participant.py` | `test_group_tools.py`, `test_tools.py` | 10+ |
| 11 | `mailbox_list_users` | `tools/list_users.py` | `test_tools.py` | 3+ |
| 12 | `mailbox_whoami` | `tools/identity.py` | `test_whoami_full.py`, `test_tools.py` | 13+ |

### Supporting Test Files (cross-cutting)

| File | Coverage Area | Tests |
|------|---------------|-------|
| `test_queries.py` | Database layer for all tools | 73 |
| `test_web.py` | Web UI (not MCP tools, but regression guard) | 96 |
| `test_mcp_apps.py` | Widget rendering, structured content | 15 |
| `test_schema_parity.py` | Migration vs runtime schema match | 4 |
| `test_migration.py` | All 7 migrations apply cleanly | 22 |
| `test_errors.py` | Error handling across tools | 15 |
| `test_rate_limit.py` | Rate limiting on tool calls | 13 |
| `test_server.py` | Server registration, tool listing | 8 |
| `test_auth.py` | Authentication layer | 3 |
| `test_oauth.py` | OAuth 2.1 flow | 16 |
| `test_oauth_registration.py` | Dynamic client registration | 23 |
| `test_settings.py` | User settings tool | 19 |
| `test_config_validation.py` | Config bounds checking | 10 |
| `test_markdown.py` | Markdown rendering | 15 |
| `test_group_tokens.py` | Group send token workflow | 13 |
| `test_token_cleanup.py` | Expired token cleanup | 8 |
| `test_bug001_to_user_not_null.py` | Regression guard for BUG-001 | 3 |

### Selective Rerun (when only one tool changed)

```bash
# Example: only send tool changed
py -m pytest tests/test_send_full.py tests/test_tools.py tests/test_queries.py -q

# Example: only search tool changed
py -m pytest tests/test_search.py tests/test_tools.py tests/test_queries.py -q
```

Full suite rerun is always preferred. Selective rerun is a fallback for speed during iteration.

---

## Tier 2: AI UX UAT

### Trigger
Rotation: 2 tools per cycle. Also triggered by any widget change (`inbox_widget.html`, `server.py` structured content).

### Method
AI uses Claude in Chrome MCP tools to test against claude.ai with the staging MCP server connected.

### Rotation Schedule (6 cycles = all 12 tools)

| Cycle | Tools | Focus |
|-------|-------|-------|
| 1 | `send_message`, `list_messages` | Send a message, verify it appears in inbox widget |
| 2 | `reply_to_message`, `get_thread` | Reply to a message, verify thread view renders correctly |
| 3 | `search_messages`, `acknowledge` | Search for a message, acknowledge it, verify state change |
| 4 | `mark_read`, `archive_conversation` | Mark as read, archive, verify unread count and archive state |
| 5 | `create_group`, `add_participant` | Create group, add member, verify group appears |
| 6 | `list_users`, `whoami` | List users, check identity with unread counts |

### AI UX Test Steps (per tool)

1. Navigate to claude.ai with staging MCP server connected
2. Invoke the tool via natural language prompt
3. Verify tool response contains expected data
4. If tool affects widget state: refresh widget, verify update
5. Screenshot proof required for pass

### Pass Criteria
- Tool executes without error
- Response data is correct and complete
- Widget reflects tool side effects (if applicable)
- Screenshot captured as evidence

---

## Tier 3: Human UAT

### Trigger
Before any production promotion. After all Tier 1 and Tier 2 pass.

### Checklist

Copy this checklist for each UAT run. Mark pass/fail per item.

```
## Human UAT Run — [DATE]

**Staging URL:** https://ai-mailbox-server-mvp-1-staging.up.railway.app
**Tester:** Keith
**MCP Server:** Connected to claude.ai via staging URL

### Core Messaging
- [ ] PASS/FAIL — Send message: "check inbox" shows widget with conversations
- [ ] PASS/FAIL — Thread view: click conversation, thread loads with messages
- [ ] PASS/FAIL — Reply: reply form visible, submit sends reply
- [ ] PASS/FAIL — Compose: Compose button creates new conversation

### Message Management
- [ ] PASS/FAIL — Search: search returns relevant results
- [ ] PASS/FAIL — Acknowledge: message state transitions correctly
- [ ] PASS/FAIL — Mark read: unread count decreases
- [ ] PASS/FAIL — Archive: conversation moves to archived

### Group Features
- [ ] PASS/FAIL — Create group: group conversation created
- [ ] PASS/FAIL — Add participant: member added to group

### Identity
- [ ] PASS/FAIL — List users: returns registered users
- [ ] PASS/FAIL — Whoami: returns current user with unread counts

### Widget
- [ ] PASS/FAIL — Widget renders in claude.ai (not blank)
- [ ] PASS/FAIL — Back button works
- [ ] PASS/FAIL — Error states display correctly

### Sign-off
- [ ] ALL PASS — Ready for production promotion
- [ ] BLOCKED — Issues found: [describe]

Signed: _________________ Date: _________________
```

---

## Production Promotion Gate

All three tiers must pass:

| Gate | Requirement |
|------|-------------|
| Tier 1 | `py -m pytest tests/ -q` — 0 failures, test count >= baseline |
| Tier 2 | Current cycle's 2 tools verified in claude.ai with screenshots |
| Tier 3 | Human checklist signed off, all items PASS |

If any tier fails: fix, rerun failed tier, then re-gate.

---

## Baseline Tracking

| Date | Test Count | Tier 1 | Tier 2 Cycle | Tier 3 |
|------|------------|--------|--------------|--------|
| 2026-04-06 | 550 | PASS | — | PENDING |
