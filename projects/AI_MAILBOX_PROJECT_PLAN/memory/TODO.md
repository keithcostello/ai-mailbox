## Carry Over (Tech Debt)

- Add GitHub OAuth to MCP login page (deferred) [SPRINT-7]
- Investigate Railway auto-deploy from branch push [TD-002]
- Resolve production dual-Postgres question (both at 0MB) [TD-003]
- Tailwind CDN in production -- add build step [TD-005]
- Update Amy's MCP connector URL to production [TD-007]

## Sprint 7 -- MCP Apps Inbox Widget (DONE)

**Decision**: Replaced outbound webhooks with MCP Apps interactive UI.

**Proven working in claude.ai:**
- Inbox view with conversations, timestamps, Compose button
- Click-to-thread via callServerTool through AppBridge proxy
- Thread view with avatars, message bubbles, reply form, project header
- Back navigation, error display
- Fully inline CSS/JS (no CDN -- Claude CSP blocks external resources)
- Correct MCP Apps handshake: protocolVersion 2026-01-26, appInfo, appCapabilities

## Sprint 7 -- UAT Process (DONE)

Three-tier UAT process documented at `docs/runbooks/UAT_PROCESS.md`:
- Tier 1: AI automated -- 581 tests, all 12 tools covered
- Tier 2: AI UX -- Cycle 1 (send + list_messages) verified in claude.ai via Chrome
- Tier 3: Human -- checklist template ready, pending Keith sign-off

## Sprint 7 -- Dead Letter Handling (DONE)

- delivery_status column on messages (migration 008)
- is_user_offline() checks last_seen against 24h threshold
- Messages to offline users get delivery_status='queued'
- process_dead_letters() transitions queued->delivered on next activity
- update_last_seen_and_process_dead_letters() combines both operations
- System message generated when message queued for offline user
- 20 tests in test_dead_letters.py

## Sprint 7 -- System Messages (DONE)

- Reserved 'system' user (migration 009, user_type='system')
- insert_system_message() bypasses participant checks
- System user excluded from get_all_users() and health endpoint
- send_message tool rejects from_user='system'
- add_participant generates system message on join
- Dead letter sends generate system message on queue
- 11 tests in test_system_messages.py

## Sprint 7 -- Remaining Features

- Email notifications
- Production hardening
- Human UAT sign-off (Keith)

## Completed

- Sprints 1-6 implemented via TDD. 471 tests. (2026-04-05 to 2026-04-06)
- BUG-001 fixed: to_user NOT NULL. Migration 007. (2026-04-06)
- TD-001 resolved: conftest.py uses real migration path. (2026-04-06)
- TD-008 resolved: migrate_003 boolean fix for PostgreSQL. (2026-04-06)
- Full MCP tool test coverage: 550 tests, all 12 tools. (2026-04-06)
- Schema parity guard (test_schema_parity.py). (2026-04-06)
- Thread context controls: limit=5, 2K truncation, summary, body_display_note. (2026-04-06)
- Search query column shadowing bug fixed. (2026-04-06)
- MCP Apps inbox widget: 13 commits, rendering in claude.ai. (2026-04-06)
- OAuth issuer URL per-environment fix. (2026-04-06)
- MCP Apps Widget Runbook created. (2026-04-06)
- UAT process doc created (3 tiers). (2026-04-07)
- Dead letter handling: delivery_status, offline detection, auto-redelivery. 20 tests. (2026-04-07)
- System messages: reserved 'system' user, insert_system_message, event messages. 11 tests. (2026-04-07)
- Tier 1 UAT: 581/581 passed. (2026-04-07)
- Tier 2 UAT Cycle 1: send_message + list_messages verified in claude.ai. (2026-04-07)
- Deployed to staging: 15 commits on mvp-1-staging. (2026-04-07)
