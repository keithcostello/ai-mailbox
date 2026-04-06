## Carry Over

- Add GitHub OAuth to MCP login page (Claude Desktop can't use GitHub to auth) [SPRINT-7]
- Fix migrate_003 boolean query for PostgreSQL production (m.read = TRUE not = 1) [TD-008]
- Investigate Railway auto-deploy from branch push [TD-002]
- Resolve production dual-Postgres question (both at 0MB) [TD-003]
- Tailwind CDN in production -- add build step [TD-005]
- Staging DB has legacy columns (to_user, read, project on messages) [TD-001]
- Update Amy's MCP connector URL to production [TD-007]

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
