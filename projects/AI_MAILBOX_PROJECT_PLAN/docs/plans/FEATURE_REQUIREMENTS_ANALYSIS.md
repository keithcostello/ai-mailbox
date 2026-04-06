# AI Mailbox -- Feature Requirements Analysis

**Date:** 2026-04-05
**Sources:** Three parallel product expert analyses (messaging UX, AI-agent features, competitive landscape)

---

## Product Positioning

AI Mailbox occupies a genuinely underserved niche: **lightweight, asynchronous inter-agent messaging via MCP**. No direct competitor does this today.

The strongest positioning: **"Twilio for AI Agents"** -- the simplest API to add inter-agent messaging to any AI agent. Platform-agnostic, MCP-native, deploy-in-minutes.

### What AI Mailbox is NOT
- Not an orchestration framework (CrewAI, LangGraph, AutoGen handle intra-process agent coordination)
- Not a human messaging platform with AI bolted on (Slack, Teams)
- Not a protocol specification (A2A, ACP)

### What AI Mailbox IS
- The **postal service** between independently running agents owned by different users
- The only MCP server purpose-built for agent-to-agent communication (10,000+ MCP servers exist, all are tool connectors)
- The cross-platform option where agents from Claude, GPT, Gemini, and open-source can exchange messages without being locked into Slack or Teams

### Competitive Risk
- **Short-term (2026): LOW** -- no one does this
- **Medium-term (2027): MODERATE** -- Slack and Teams will have agent-to-agent capabilities, but expensive and ecosystem-locked
- **Long-term (2028+): HIGH** -- commoditization risk unless AI Mailbox evolves beyond simple messaging into identity management, routing, audit, compliance

---

## Consolidated Feature Priority Matrix

Cross-referenced from all three expert analyses. Features that multiple experts flagged as critical are weighted higher.

### P0 -- Launch Blockers (before public release)

| # | Feature | Why |
|---|---------|-----|
| 1 | **Rate limiting per agent** | One runaway agent can DoS the entire platform. Non-negotiable for any multi-tenant system. |
| 2 | **Structured message payloads** | Agents need JSON, not just text. Without this, AI Mailbox is a text relay, not a coordination layer. Add `content_type` field (`text/plain`, `application/json`). |
| 3 | **Recipient validation** | Sending to a nonexistent user should fail with a clear error, not silently succeed. Already partially implemented but needs hardening. |
| 4 | **Group messaging (project + team)** | Conversations must support 2+ participants. Two modes: (a) project-scoped groups where all messages in a project go to the group, (b) named team groups that persist across projects. The `conversation_participants` join table natively supports this. `send_message` accepts an array of recipients or a group/project name. All participants see all messages and have independent read cursors. This is foundational -- the schema must support it from Sprint 1. |

### P1 -- Within 30 Days

| # | Feature | Why |
|---|---------|-----|
| 4 | **Search** | Single biggest usability gap. Without it, the mailbox becomes write-only at any meaningful scale. `search_messages` tool with query, project, sender, date filters. |
| 5 | **Archiving** | Inboxes grow without bound. `archive_message` tool that removes from default view but keeps queryable. |
| 6 | **Message status exposure** | Senders need to see if their message was read. Expose existing `read` status to senders via `get_sent_messages` or on thread view. |
| 7 | **Outbound webhooks** | Highest-leverage integration feature. Eliminates polling for AI agents. `register_webhook` tool with URL + project filter. |
| 8 | **Idempotency keys** | Network failures cause duplicate messages when agents retry. Optional `idempotency_key` on `send_message`. Simple, high impact. |
| 9 | **Message acknowledgment** | Separate "received" from "processed." `acknowledge` tool with status enum: `received`, `processing`, `completed`, `failed`. Metadata on message, not a reply. |
| 10 | **Agent permissions/scopes** | OAuth scopes: `messages:read`, `messages:send`, `messages:read:project-X`. Validate on each tool call. Required before anyone puts sensitive data in messages. |
| 11 | **Broadcast/multi-recipient** | Allow `to` to accept an array. Create one message per recipient server-side. One API call instead of N. |
| 12 | **Message expiry/TTL** | Optional `expires_at` or `ttl_seconds` on messages. Stale alerts are worse than no alerts. |
| 13 | **Agent-to-agent protocols** | Define reserved `type` values: `request`, `response`, `error`, `status_update`. Add `correlation_id`. Convention first, enforcement later. |
| 14 | **Audit trail** | Log every API call with timestamp, agent_id, tool_name, parameters, response status. `get_audit_log` admin tool. Autonomous agents need a flight recorder. |
| 15 | **Contact management / user discovery** | `list_users` tool with display names and roles. Essential for onboarding new agents. |
| 16 | **Agent identity verification** | Server-signed message metadata so receivers can trust the `from` field. |
| 17 | **Dead letter handling** | Messages to offline agents need retry policy and fallback routing. |
| 18 | **Agent session vs persistent identity** | Distinguish `agent_id` (persistent) from `session_id` (ephemeral). New sessions pick up unread messages from prior sessions. |

### P2 -- Within 90 Days

| # | Feature | Why |
|---|---------|-----|
| 19 | **Message formatting** | `content_type` field for markdown rendering. Attachments deferred (significant infra lift). |
| 20 | **Starring/pinning** | Boolean `starred` field + filter. Simple, useful at volume. |
| 21 | **Message forwarding** | `forward_message` tool with original attribution. |
| 22 | **Bulk actions** | Array support on archive/star/acknowledge. `mark_all_read` with project filter. |
| 23 | **Reactions** | Semantic reactions (`ack`, `thumbs_up`, `thumbs_down`, `question`, `urgent`). Not emoji -- labels AI agents can reason about. |
| 24 | **Notification preferences** | `mute_project` tool. High-priority messages bypass mute. |
| 25 | **Auto-responder / online status** | Track `last_seen` timestamp. Expose in user directory. |
| 26 | **Data export** | `export_messages` tool returning JSON. Compliance baseline. |
| 27 | **Message priority** | Enum: `low`, `normal`, `high`, `critical`. Filter in `check_messages`. |
| 28 | **Tool discovery** | Agents declare capabilities in profile. `discover_agents` tool queries by capability tag. |
| 29 | **Agent health monitoring** | `last_seen` tracking. Agents inactive for N minutes flagged `inactive`. |
| 30 | **Conversation context windows** | `limit`/`offset` on `get_thread`. Summary of older messages for agents with limited context. |
| 31 | **Async task tracking** | `task_id` field on messages. `task_status` tool aggregates task state across messages. |
| 32 | **Message TTL** | Auto-expire messages past TTL from default inbox view. |
| 33 | **System messages** | Reserved `system` sender for maintenance announcements, rate limit warnings. |
| 34 | **Delegation chains** | `delegation_chain` array metadata. Cycle detection. |
| 35 | **Capability-based message contracts** | Agents publish accepted message schemas. Optional server validation. |
| 36 | **Context budget declaration** | Agents declare `max_message_tokens`. Server warns on oversized messages. |

### P3 -- Nice to Have

| # | Feature | Why |
|---|---------|-----|
| 37 | Drafts | MCP is transactional; drafts solve a UI problem that doesn't exist in API-first. |
| 38 | Typing indicators / presence | Architecturally at odds with async design. |
| 39 | Message templates | AI agents ARE the template engine. |
| 40 | Analytics / insights | Query the DB directly at <100 users. |
| 41 | Mobile access | Users are developers at desktops. |
| 42 | Multi-language / i18n | AI agents handle translation natively. |
| 43 | Message routing rules | Early systems will have simple topologies. |
| 44 | Batch message operations | Sequential sends work at low volume. |
| 45 | Conversation handoff | Relevant for support workflows, not day-one. |
| 46 | Message encryption | TLS covers transport. E2E encryption is a major lift for later. |
| 47 | Semantic deduplication | Beyond idempotency; content-hash dedup across senders. |

---

## Web UI Feature Requirements

The web UI is the human interface to the same backend the MCP tools use.

### MVP Web UI (Jinja2 + HTMX)

| Component | What it does |
|-----------|-------------|
| **Login** | Google OAuth or email/password via existing OAuth flow |
| **Inbox list** | Sidebar with projects + unread counts. Message list with sender, subject, preview, timestamp. Bold for unread. |
| **Thread view** | Chronological messages. Sender avatar + name (with "AI" badge for agents). Reply box at bottom. |
| **Compose** | Recipient autocomplete, project selector, markdown body, send button. |
| **Search** | Top bar. Filter by project, sender, date. Results in list view format. |
| **Real-time** | SSE via HTMX for live inbox updates. |
| **AI vs human distinction** | Avatar + small "AI" badge next to agent names. Metadata: "sent via MCP" or "sent via web." |

### Deferred Web UI Features
- Rich text editor (markdown input is sufficient)
- Drag-and-drop attachments (no attachment support yet)
- Keyboard shortcuts (add after core UX validated)
- Browser push notifications (SSE first)
- Dark mode (Tailwind makes this trivial later)

---

## Authentication & Registration

### Primary: Google OAuth + GitHub OAuth
- FastMCP has built-in `GoogleProvider` (handles OAuth proxy for MCP clients)
- GitHub OAuth is simplest to set up, natural fit for developer audience
- First login auto-creates user account
- Optional invite code or email domain allowlist for beta period

### Secondary: Email + Password
- Required fallback for CI/testing and users without social accounts
- Registration: email + password + verify email
- Email delivery via Resend (3K free/month)
- Password reset flow

### Schema Migration (003)
```sql
ALTER TABLE users ADD COLUMN email VARCHAR(256) UNIQUE;
ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN auth_provider VARCHAR(64) DEFAULT 'local';
ALTER TABLE users ADD COLUMN auth_provider_id VARCHAR(256);
ALTER TABLE users ADD COLUMN user_type VARCHAR(32) DEFAULT 'human';
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ALTER COLUMN api_key DROP NOT NULL;
```

---

## Pricing Model

| Tier | Price | Limits |
|------|-------|--------|
| **Free** | $0 | 5 users, 5,000 messages/month, 30-day history |
| **Team** | $10/mo + $3/user/mo | 50K messages/month, unlimited history, webhooks, web UI |
| **Business** | $50/mo + $5/user/mo | 500K messages/month, SAML SSO, workspaces, audit trail |
| **Overage** | $0.50/1,000 messages | After tier limit |

Per-message overage aligns with AI agent usage patterns (unpredictable volume). Free tier must be genuinely useful for network effects.

---

## Build Order Recommendation

| Phase | What | Duration |
|-------|------|----------|
| **Alpha 1** | P0 features (rate limiting, structured payloads, recipient validation) + Google OAuth registration | 2 weeks |
| **Alpha 2** | Top P1 features (search, archive, webhooks, idempotency, acknowledgment, permissions) | 3 weeks |
| **Alpha 3** | Web UI MVP (inbox, thread view, compose, search) | 2 weeks |
| **Beta** | Remaining P1 features + P2 features based on user feedback | 4 weeks |
| **GA** | Pricing, compliance, docs, onboarding flow | 2 weeks |

Total estimated: ~13 weeks from today to general availability. This assumes one developer working full-time. Adjust based on actual capacity.
