# AI Mailbox -- TODO

## Carry Over (Tech Debt)

- Railway auto-deploy from branch push broken [TD-002]
- Resolve production dual-Postgres question (both at 0MB) [TD-003]
- Tailwind CDN in production -- add build step [TD-005]
- Update Amy's MCP connector URL to production [TD-007]
- GitHub issue #15: soft deletes for messages

## Sprint 8 -- Planned

- Email notifications (deferred from Sprint 7)
- Amy onboarding to production
- Production hardening: remaining tech debt items

## Completed

- Sprints 1-6 implemented via TDD. 471 tests. (2026-04-05 to 2026-04-06)
- BUG-001 fixed: to_user NOT NULL. Migration 007. (2026-04-06)
- TD-001 resolved: conftest.py uses real migration path. (2026-04-06)
- TD-008 resolved: migrate_003 boolean fix for PostgreSQL. (2026-04-06)
- Full MCP tool test coverage: 550 tests, all 12 tools. (2026-04-06)
- Schema parity guard (test_schema_parity.py). (2026-04-06)
- Thread context controls: limit=5, 2K truncation. (2026-04-06)
- MCP Apps inbox widget: rendering in claude.ai. (2026-04-06)
- OAuth issuer URL per-environment fix. (2026-04-06)
- UAT process doc v1.1 (3 tiers, 13 repeatable prompts). (2026-04-07)
- Dead letter handling: delivery_status, offline detection, auto-redelivery. 20 tests. (2026-04-07)
- System messages: reserved system user, insert_system_message, event messages. 11 tests. (2026-04-07)
- list_participants tool #13: authoritative group membership. 8 tests. (2026-04-07)
- BUG-002 fixed: whoami Postgres HAVING alias. (2026-04-07)
- Version bump to v0.7.0. Web health system user exclusion. (2026-04-07)
- Tier 3 Human UAT: 13/13 PASS. 589 tests total. (2026-04-07)
- Merged to master. Deployed v0.7.0 to production. (2026-04-07)
- BUG-003 fixed: unread_only returning own sent messages. 591 tests. (2026-04-07)
- BUG-003 merged to master and deployed to production. (2026-04-07)
