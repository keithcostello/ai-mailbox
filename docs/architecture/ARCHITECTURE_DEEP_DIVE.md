# AI Mailbox — Architecture Deep Dive

**Date:** 2026-04-05
**Version:** v0.2.1 (commit b009b90)
**Repo:** keithcostello/ai-mailbox

## Stack

Python 3.11+, FastMCP (mcp[cli]>=1.9.0), OAuth 2.1, PostgreSQL 18 (psycopg3), SQLite (testing), JWT (PyJWT), bcrypt, Uvicorn, Starlette ASGI

**Size:** ~15 source files, ~1,200 LOC, 43 tests across 5 test modules

## Architecture Overview

```
Client (Claude Desktop)
  |  OAuth 2.1 (PKCE S256)
  v
server.py -- FastMCP + Starlette ASGI
  |-- /login (GET/POST) -- oauth.py (MailboxOAuthProvider)
  |-- /health -- status endpoint
  |-- /mcp -- MCP JSON-RPC (5 tools)
  |    +-- Bearer JWT -> current_user_id contextvar -> tool functions
  +-- CORS middleware (allow_origins=["*"])

oauth.py -- OAuthAuthorizationServerProvider protocol
  |-- Client registration (dynamic)
  |-- Authorization code flow with PKCE S256
  |-- JWT access tokens (1hr, HS256)
  |-- Refresh token rotation
  +-- current_user_id contextvar (identity threading)

tools/ -- 5 tool modules (all receive user_id, return dict)
  |-- send.py    -> tool_send_message()
  |-- inbox.py   -> tool_check_messages()
  |-- reply.py   -> tool_reply_to_message()
  |-- thread.py  -> tool_get_thread()
  +-- identity.py -> tool_whoami()

db/ -- Dual-database abstraction
  |-- connection.py -> DBConnection protocol, SQLiteDB, PostgresDB
  |-- schema.py     -> Migration runner (SQLite compat layer)
  |-- queries.py    -> All SQL operations
  +-- migrations/   -> 001_initial.sql, 002_oauth.sql
```

## Data Flow: Token to Tool Execution

```
1. Client -> POST /mcp with "Authorization: Bearer <JWT>"
2. MCP SDK middleware calls load_access_token(token)
3. oauth.py decodes JWT -> extracts "sub" (user_id)
4. current_user_id.set(user_id) [contextvar]
5. Tool wrapper in server.py calls _get_user()
6. _get_user() reads current_user_id.get() -> returns user_id
7. Tool function receives user_id + db, executes business logic
8. Response returned to client
```

## Key Design Decisions

1. **Protocol-based DB abstraction** -- `DBConnection` protocol allows SQLite for tests, Postgres for prod. SQL placeholder conversion (`?` to `%s`) is transparent in PostgresDB.

2. **Context variable identity threading** -- `current_user_id` contextvar set in `load_access_token()`, read by tool wrappers. Async-safe per-request isolation.

3. **Python-generated UUIDs/timestamps** -- `uuid4()` and ISO 8601 strings generated in Python, not DB functions. Cross-DB compatible.

4. **Error-as-data pattern** -- Tools return `{"error": "..."}` dicts instead of raising exceptions. Consistent error handling for MCP clients.

5. **Iterative thread traversal** -- Walk-up + BFS instead of recursive CTE. Works with SQLite (test-only DB).

## Database Schema

### Core Tables (001_initial.sql)

**users** (4 columns):
- `id` VARCHAR(64) PK
- `display_name` VARCHAR(128) NOT NULL
- `api_key` VARCHAR(128) NOT NULL UNIQUE (legacy, unused)
- `created_at` TIMESTAMP DEFAULT NOW()

**messages** (9 columns):
- `id` UUID PK DEFAULT gen_random_uuid()
- `from_user` VARCHAR(64) NOT NULL FK -> users(id)
- `to_user` VARCHAR(64) NOT NULL FK -> users(id)
- `project` VARCHAR(128) NOT NULL DEFAULT 'general'
- `subject` VARCHAR(256) DEFAULT NULL
- `body` TEXT NOT NULL
- `reply_to` UUID FK -> messages(id) (self-referential threading)
- `read` BOOLEAN DEFAULT FALSE
- `created_at` TIMESTAMP DEFAULT NOW()

**Indexes:**
- `idx_msg_inbox` on (to_user, project, read, created_at)
- `idx_msg_thread` on (reply_to)

### OAuth Tables (002_oauth.sql)

**users.password_hash** VARCHAR(256) -- added column, bcrypt hash

**oauth_clients** -- dynamic client registration
- `client_id` VARCHAR(128) PK
- `client_info` TEXT NOT NULL (JSON blob)
- `created_at` TIMESTAMP

**oauth_codes** -- authorization codes (5-min TTL)
- `code` VARCHAR(256) PK
- `client_id`, `user_id` FK, `code_challenge`, `redirect_uri`, `scopes`
- `expires_at` FLOAT NOT NULL

**oauth_tokens** -- access/refresh tokens
- `token` VARCHAR(256) PK
- `client_id`, `user_id` FK, `scopes`, `refresh_token`
- `expires_at` INTEGER
- Index: `idx_oauth_tokens_refresh` on (refresh_token)

## Module Map

| Module | Role | Key Exports |
|---|---|---|
| `server.py` | App factory, tool registration, routes | `create_app()` |
| `oauth.py` | OAuth 2.1 provider, JWT tokens | `MailboxOAuthProvider`, `current_user_id`, `hash_password()` |
| `auth.py` | Legacy API key validation (UNUSED) | `authenticate()`, `AuthError` |
| `config.py` | Environment configuration | `Config`, `Config.from_env()` |
| `__main__.py` | Entry point | `main()` -> uvicorn |
| `db/connection.py` | DB abstraction | `DBConnection` protocol, `SQLiteDB`, `PostgresDB` |
| `db/schema.py` | Migration runner | `ensure_schema_sqlite()`, `ensure_schema_postgres()` |
| `db/queries.py` | SQL operations | `insert_message()`, `get_inbox()`, `get_thread()`, etc. |
| `tools/send.py` | Send message | `tool_send_message()` |
| `tools/inbox.py` | Check inbox | `tool_check_messages()` |
| `tools/reply.py` | Reply to message | `tool_reply_to_message()` |
| `tools/thread.py` | Get thread | `tool_get_thread()` |
| `tools/identity.py` | Identity check | `tool_whoami()` |

## Test Coverage

| Suite | Tests | Coverage |
|---|---|---|
| `test_tools.py` | 20 | Scenarios A-E: first contact, threads, multi-project, isolation, edge cases |
| `test_queries.py` | 8 | Insert, inbox filter, mark read, thread walk, unread counts |
| `test_oauth.py` | 7 | Password hashing, JWT create/validate/expire/reject, client registration |
| `test_server.py` | 5 | App creation, health endpoint, tool registration, login form |
| `test_auth.py` | 3 | Token-based identity (valid, invalid, user isolation) |
| **Total** | **43** | |

## Strengths

| Area | Detail |
|---|---|
| OAuth 2.1 | PKCE S256, dynamic client registration, refresh rotation, revocation |
| Separation | Auth, tools, DB, config are isolated modules |
| Test coverage | 43 tests covering happy path, edge cases, and security |
| Deployment | Dockerfile + Railway health checks with cold-start resilience (5 retry) |
| Dual-DB | Same code runs against SQLite (tests) and PostgreSQL (production) |
| Identity isolation | Context variables properly isolate user identity per async request |

## Issues Found (16 total)

All issues filed to GitHub: keithcostello/ai-mailbox#1 through #16.

### P0 - Critical (3)

| # | Issue | Location |
|---|---|---|
| #1 | No OAuth token/code cleanup -- expired records accumulate | oauth.py, 002_oauth.sql |
| #2 | Default JWT secret not validated at startup | config.py |
| #3 | CORS allows all origins | server.py |

### P1 - High (3)

| # | Issue | Location |
|---|---|---|
| #4 | No rate limiting on login endpoint | server.py |
| #5 | N+1 query in get_thread() | db/queries.py |
| #6 | No inbox pagination | db/queries.py, tools/inbox.py |

### P2 - Medium (6)

| # | Issue | Location |
|---|---|---|
| #7 | Legacy api_key column still NOT NULL UNIQUE | 001_initial.sql |
| #8 | expires_at type mismatch (FLOAT vs INTEGER) | 002_oauth.sql |
| #9 | No ON DELETE CASCADE on user FKs | 001_initial.sql |
| #10 | PostgresDB retry catches ALL exceptions | db/connection.py |
| #11 | Missing FK on oauth tables to oauth_clients | 002_oauth.sql |
| #12 | No message body length limit | tools/send.py |

### P3 - Low (4)

| # | Issue | Location |
|---|---|---|
| #13 | Version string mismatch (0.1.0 vs 0.2.1) | __init__.py |
| #14 | Scopes stored as comma-separated string | 002_oauth.sql |
| #15 | No soft deletes for messages | schema |
| #16 | auth.py retained but unused | auth.py |

## Security Model

**Authentication:** OAuth 2.1 with PKCE S256. Users authenticate via browser login form, receive JWT access token (1hr, HS256). Refresh token rotation supported.

**Authorization:** User identity extracted from JWT `sub` claim via contextvar. Tools verify user participation (e.g., reply only to messages addressed to you, thread access requires being a participant).

**Password storage:** bcrypt with salt via `hash_password()` / `verify_password()`.

**Transport:** HTTPS enforced by Railway. Localhost allowed for dev.

**Gaps:** No rate limiting (#4), no JWT secret validation (#2), CORS too permissive (#3). See GitHub issues.
