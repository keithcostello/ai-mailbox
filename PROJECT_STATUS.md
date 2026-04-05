# AI Mailbox — Project Status

**Date:** 2026-04-05
**Version:** 0.2.1 (OAuth 2.1 + User Isolation)
**Railway URL:** https://ai-mailbox-server-production.up.railway.app

## Current State: Human UAT PASSED

Keith and Amy both connected via Claude Desktop with OAuth login. Bidirectional messaging confirmed.

## Completed

| Phase | Status | Evidence |
|-------|--------|----------|
| Scaffold + pyproject.toml | DONE | pip install -e works |
| DB layer (schema, queries, connection) | DONE | 8/8 query tests green |
| OAuth 2.1 provider | DONE | 8/8 OAuth tests green |
| 5 MCP tools (no api_key) | DONE | 18/18 scenario tests green |
| Server integration | DONE | 5/5 server tests green |
| Full test suite | DONE | **42/42 green** |
| Railway deploy | DONE | health=200, auth=oauth2.1 |
| OAuth flow (curl UAT) | DONE | Register → Login → Token → MCP → whoami |
| Keith Claude Desktop | DONE | `check_messages` returns `user=keith` |
| Amy Claude Desktop | DONE | Amy connected, received welcome message |
| User isolation | DONE | Keith=keith, Amy=amy (verified via logs) |
| Human UAT | DONE | Bidirectional messaging verified |

## Bugs Fixed

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| BUG-001 | PG `read = 0` vs BOOLEAN | Use parameterized `False` |
| BUG-002 | PG TIMESTAMP rejects Unix float | Changed `expires_at` to FLOAT |
| BUG-003 | Missing `redirect_uri_provided_explicitly` on AuthCode | Added field to dataclass |
| BUG-004 | `client_id` referenced before assignment in logging | Moved log after variable assignment |
| BUG-005 | All users identified as "keith" (hardcoded) | contextvars for user isolation |
| DEPLOY | PG idle-in-transaction blocking ALTER TABLE | Set autocommit=True on PostgresDB |

## Architecture

```
Claude Desktop (Keith) ──OAuth──┐
                                ├── AI Mailbox MCP Server (Railway)
Claude Desktop (Amy) ───OAuth──┘        │
                                    PostgreSQL (Railway)
```

## Test Summary: 42/42

```
test_auth.py     3 tests  — token-based identity
test_oauth.py    8 tests  — password hashing, JWT, client registration
test_queries.py  8 tests  — DB operations
test_tools.py   18 tests  — 5 scenarios (A-E) covering real communication
test_server.py   5 tests  — server integration + OAuth endpoints
```

## Deliverables: D01-D28

See DELIVERABLES.csv for full traceability. All 28 deliverables DONE.
