# Plan: AI Mailbox — POC to Alpha Sprint Roadmap

## Context

The AI Mailbox POC (v0.2.1) works for Keith and Amy but has a structural foundation that blocks growth. Six expert analyses converged: the data model is the real problem. No off-the-shelf messaging framework fits -- the right path is adopting the proven three-table conversation schema pattern, keeping a thin custom layer, and building a web UI with HTMX + Tailwind.

**Direction:** Path B (universal translator, Claude + ChatGPT), Railway-per-tenant isolation, modular codebase. SDD (Spec-Driven Development) for sprint specs, TDD for implementation. Web UI mandatory in every sprint, verified by Claude via browser automation.

---

## Branch + Environment Strategy

### Git Branches (all created from current master HEAD)

| Branch | Purpose | Railway Environment |
|---|---|---|
| `master` | Main branch. PRs merge here. | (not directly deployed) |
| `production` | Production-stable code. Merges from master after validation. | `production` (existing) |
| `staging` | Pre-production testing of master-ready code. | `staging` (existing) |
| `mvp-1-staging` | Active sprint development for alpha. All sprint work happens here. | `MVP 1 Staging` (new) |

### Railway Environments

| Environment | Branch | URL | Purpose |
|---|---|---|---|
| `production` | `production` | `ai-mailbox-server-production.up.railway.app` | Live service for Keith + Amy |
| `staging` | `staging` | `ai-mailbox-server-staging.up.railway.app` | Pre-production validation |
| `MVP 1 Staging` | `mvp-1-staging` | `ai-mailbox-server-mvp-1-staging.up.railway.app` | Sprint development + testing |

Railway project ID: `3befc06d-8779-4eba-9a3d-d0ec4a2dfb0f`

### Promotion Flow

```
mvp-1-staging → staging → production
(sprint work)   (validation)  (live)
```

Each promotion is a PR merge. Schema migrations are additive and backward-compatible. Production data is never touched during development.

---

## Development Methodology

### Spec-Driven Development (Sprint Level)

Each sprint begins with a **specification** that defines:
- API contracts (MCP tool signatures, parameters, response shapes, error codes)
- Schema changes (DDL, migration SQL)
- Web UI routes and expected behaviors
- Edge cases and error scenarios
- Acceptance criteria (what "done" means)

The spec is reviewed and approved before any implementation begins. The spec is the source of truth.

### Test-Driven Development (Implementation Level)

Within each sprint, implementation follows RED-GREEN-REFACTOR:
1. Write failing test from the spec
2. Implement minimum code to pass
3. Run full suite, verify green
4. Refactor only if tests stay green

No exceptions. Error handling is tested, not assumed.

### Cross-Sprint Standards

| Standard | Enforcement |
|---|---|
| TDD | Every implementation change starts with a failing test |
| Error handling | Structured error codes on every tool. Error paths tested. |
| Web UI | Every feature has MCP tool AND web interface |
| Claude verification | Claude tests web UI via browser automation each sprint |
| GitHub hygiene | Issues updated/closed. PRs with descriptions. Branch clean. |
| File hygiene | No orphaned files. No dead code. Imports clean. |
| Modular codebase | Protocol layer -> Service layer -> Storage layer. No cross-layer imports. |
| Pagination | Every list endpoint cursor-paginated |
| Security | No hardcoded secrets. CORS locked. Rate limits enforced. |
| Spec compliance | Implementation matches approved spec. Deviations require spec update first. |

---

## Full Sprint Roadmap

Sprint = work completable within ~175K tokens of context, including TDD, error handling, web UI, and verification.

### Sprint 1: Schema Foundation + Error Framework
**Spec focus:** Conversation data model (including group conversations), structured error format, web UI scaffold.

- Migration 003: `conversations`, `conversation_participants`, `messages` tables
- **Group conversations** -- conversations support 2+ participants. `conversation_participants` is a many-to-many join. All participants see all messages. Groups can be project-scoped (all messages in project "deployment-alerts" go to the group) or team-based (a named group like "backend-team" that persists across projects). Schema natively supports 1:1, project groups, and team groups with the same model.
- Cursor-based read tracking (replaces per-message boolean)
- Sequence numbers for deterministic ordering
- Data migration from existing `reply_to` chains
- Structured error framework (codes, param attribution, retryable flag)
- Rewrite all queries for new schema
- Web UI scaffold: Jinja2 + HTMX + Tailwind. Login page, empty inbox, health page.
- GitHub: close issues #5, #7, #8

### Sprint 2: API Redesign + Rate Limiting
**Spec focus:** MCP tool contracts, pagination spec, rate limit thresholds.

- `list_messages` replaces `check_messages` (no auto-mark-read, cursor pagination, filters)
- `mark_read` new tool (explicit batch acknowledgment)
- `send_message` enhanced (thread_id, content_type, idempotency_key, **`to` accepts array for group messages**)
- `reply_to_message` enhanced (any-participant-can-reply, content_type, idempotency_key)
- `get_thread` enhanced (pagination, conversation metadata, **participant list**)
- `list_users` new tool (extracted from whoami)
- **`create_group` or `add_participant`** -- add users to existing conversations for group messaging
- Rate limiting via `limits` library (per-user, all tools)
- Web UI: inbox list with projects, unread counts, conversation list
- GitHub: close issues #4, #6, #12

### Sprint 3: P0 Security + Web UI Thread View
**Spec focus:** Security requirements, thread view UX spec, compose flow.

- JWT secret validation at startup
- CORS restriction (explicit origin list)
- Token/code cleanup (expired OAuth records)
- Delete dead `auth.py`
- Web UI: thread view (chronological messages, AI badge, reply form, mark-as-read)
- Web UI: compose (recipient autocomplete, project selector, markdown body)
- Web UI: error pages (404, 403, 500, rate limit, validation feedback)
- Claude browser verification of full web UI flow
- GitHub: close issues #1, #2, #3, #16

### Sprint 4: Search + Structured Payloads + Real-Time
**Spec focus:** Search API contract, JSON payload schema, SSE event spec.

- PostgreSQL full-text search (`tsvector` + GIN index)
- `search_messages` MCP tool (query, project, date filters)
- Structured payloads (`content_type: application/json`, validation)
- Real-time SSE via PostgreSQL LISTEN/NOTIFY + `sse-starlette`
- Message body length limit (10KB)
- Web UI: search bar, results, JSON message rendering, live inbox updates
- GitHub: close issue #14

### Sprint 5: Acknowledgment + Archiving + Agent Identity
**Spec focus:** ACK protocol spec, archive lifecycle, agent identity model.

- `acknowledge` tool (received/processing/completed/failed)
- `archive_conversation` tool
- Agent identity: `user_type` field, `last_seen` tracking, persistent vs ephemeral sessions
- Web UI: archive management, ACK display in threads, user directory with online status
- GitHub: close issues #9, #10, #11

### Sprint 6: Self-Service Registration + Onboarding
**Spec focus:** OAuth flow spec, registration UX, invite-only mode spec.

- Google OAuth via FastMCP GoogleProvider (replace custom login form)
- GitHub OAuth (secondary)
- Schema migration: email, auth_provider, user_type on users table
- Invite-only mode (configurable)
- Web UI: Google/GitHub sign-in, onboarding flow, generic getting-started
- Generic README (not addressed to Amy)
- GitHub: close issue #13, update README

### Sprint 7: Webhooks + Notifications + Hardening
**Spec focus:** Webhook delivery spec, notification preferences, dead letter spec.

- Outbound webhooks (register, deliver, retry with backoff, HMAC signature)
- Email notifications via Resend API
- Dead letter handling for offline agents
- System messages (reserved `system` sender)
- Web UI: notification preferences, webhook management
- Production hardening (connection pooling review, graceful shutdown, health check expansion)

### Sprint 8: Alpha Polish + Compliance + Release
**Spec focus:** Data export format, audit trail spec, priority system spec.

- Data export (`export_messages` tool, JSON, web download)
- Audit trail (API call logging, `get_audit_log` admin tool, web viewer)
- Message priority (low/normal/high/critical, filter, visual indicator)
- Starring/pinning
- Full test suite review + coverage gaps
- Performance testing (1000-message inbox, 100-message thread, rate limit under load)
- API reference documentation
- Alpha release (version bump, GitHub release, changelog)

---

## Alpha Completion Criteria

1. New user signs up via Google OAuth without founder intervention
2. User connects Claude Desktop, authenticates, sees inbox within 5 minutes
3. Full conversation lifecycle: send, list, mark_read, reply, get_thread, archive -- including **group conversations with 3+ participants**
4. Web UI: inbox, threads (1:1 and group), compose, search, user directory, notifications
5. Structured JSON payloads work through both MCP and web
6. Rate limiting prevents abuse (429 on exceed)
7. Real-time updates via SSE in web UI
8. Webhooks notify agents of new messages
9. All tests pass, including error handling edge cases
10. Claude has verified every web UI flow via browser automation
11. Documentation: API reference, getting started, deployment guide

---

## Existing Code to Reuse

| File | Status |
|---|---|
| `src/ai_mailbox/db/connection.py` | Keep -- DBConnection protocol, SQLiteDB, PostgresDB |
| `src/ai_mailbox/oauth.py` | Modify Sprint 3 (cleanup), replace Sprint 6 (Google OAuth) |
| `src/ai_mailbox/config.py` | Extend with new env vars each sprint |
| `src/ai_mailbox/__main__.py` | Unchanged |
| `Dockerfile`, `railway.toml` | Unchanged until scaling needed |

## Reference Architectures

| What | Source | Use |
|---|---|---|
| Three-table conversation schema | pinax-messages pattern | Data model for Sprint 1 |
| Web UI approach | mcp_agent_mail (Tailwind + server rendering) | Web UI reference |
| PostgreSQL FTS | Built-in tsvector + GIN | Search in Sprint 4 |
| Real-time notifications | PostgreSQL LISTEN/NOTIFY + sse-starlette | SSE in Sprint 4 |
| Rate limiting | `limits` library | Sprint 2 |
