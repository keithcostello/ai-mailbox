# AI Mailbox -- SaaS Product Analysis

**Date:** 2026-04-05
**Status:** Draft -- pending product usage expert review

## Current State

A working MVP (v0.2.1) with 2 hardcoded users, OAuth 2.1 via custom login form, 5 MCP tools, PostgreSQL on Railway. Proves the concept: two Claude Desktop instances can message each other through MCP.

## Three Fundamental Product Questions

### 1. How do humans interact with the mailbox?

The MVP has no human-facing UI. Humans can only interact through their AI (Claude Desktop). For a SaaS product, humans need a **web inbox** to review, search, and manage messages independently of their AI.

**Recommended approach: Jinja2 + HTMX**

The backend is already Starlette/ASGI. Server-rendered templates with HTMX provide:
- No JS build toolchain (stays in Python ecosystem)
- HTMX handles inbox interactions (load thread on click, submit reply, poll for new messages)
- SSE via HTMX for real-time inbox updates
- Ships in days, not weeks

The web UI and MCP tools share the same service layer:

```
                 Web Browser              Claude Desktop
                     |                         |
                  HTTP/SSE                   MCP/JSON-RPC
                     |                         |
              +------+-------------------------+------+
              |          Starlette ASGI               |
              |  /inbox, /thread, /compose  |  /mcp   |
              +------+-------------------------+------+
                     |                         |
              +------+-------------------------+------+
              |        Core Service Layer             |
              |  (messages, threads, users, projects) |
              +------+-------------------------+------+
                     |
                  PostgreSQL
```

**AI vs. human message distinction:** Avatar + small "AI" badge next to agent names. Message body renders identically regardless of sender type. Metadata line ("sent via MCP" or "sent via web") as subtle secondary text.

**Essential web UI components:**
- Sidebar: projects/folders, unread counts
- Message list: sender, subject/preview, timestamp, read/unread state
- Thread view: chronological, reply anchored at bottom
- Compose: recipient autocomplete, project selector, markdown body
- Search: by sender, project, date, content

### 2. How do AIs work within the messaging system?

Currently: Claude Desktop connects via MCP, authenticates via OAuth, uses 5 tools. This works but is pull-only (AI must call `check_messages` to see new messages).

**Evolution needed:**
- **Webhook notifications**: AI agents register a callback URL. When a message arrives, the server POSTs to the URL. Eliminates polling.
- **Scoped permissions**: Not all AI agents should see all messages. Tool-level scoping based on OAuth scopes (e.g., `messages:read`, `messages:write`, `admin`).
- **Agent identity**: Distinguish human users from AI agents in the user model. An AI agent acts on behalf of a human but has its own identity and message history.
- **Multi-client support**: A user may connect from Claude Desktop, Claude Code, VS Code, or a custom MCP client. Each client gets its own OAuth registration but maps to the same user identity.

**MCP spec alignment (Nov 2025):**
The MCP spec now supports the server acting purely as an OAuth Resource Server, delegating authentication to an external IdP (Google, Microsoft, Auth0). The server validates tokens but doesn't issue them. FastMCP v2.12+ has built-in `GoogleProvider` and `AzureProvider` that handle the OAuth proxy pattern (because Google/Microsoft don't support Dynamic Client Registration).

### 3. How do people register?

**Recommended: Google OAuth primary + GitHub OAuth secondary + email/password fallback**

| Method | Friction | Cost | Fit |
|--------|---------|------|-----|
| Google OAuth | Low (one click) | Free | Best for consumers. FastMCP has built-in `GoogleProvider`. |
| GitHub OAuth | Low (one click) | Free | Best for developers. Simplest setup of all three. |
| Email + password | High (form, verify, remember) | Email delivery cost | Required fallback for CI/testing and users without social accounts. |
| Magic link | Medium (switch to email) | Email delivery cost | Good for web admin UI, bad for MCP flow (breaks OAuth redirect chain). Defer. |
| Microsoft/Azure AD | Low (one click) | Free | Good for enterprise. Complex setup (tenant types, dual account systems). Add later for B2B. |
| Managed (Auth0/Clerk) | Varies | $0-500+/mo at scale | Premature. Already have working OAuth. Revisit when SAML/enterprise SSO needed. |

**How Google OAuth works with MCP:**
1. User adds MCP server URL in Claude Desktop
2. Claude Desktop discovers OAuth metadata, opens browser
3. FastMCP's `GoogleProvider` redirects to Google consent screen
4. User signs in with Google
5. Server receives Google token, extracts email, creates/looks up user
6. Issues JWT access token back to Claude Desktop
7. All subsequent MCP calls carry the token

**Self-registration flow:**
- First Google/GitHub login auto-creates the user account
- Optional: require invite code or email domain allowlist during beta
- Email verification is implicit with social login (Google/GitHub verify emails)
- For email+password: require email verification before sending messages

## User Model Evolution

### Current schema
```
users: id (PK), display_name, api_key (legacy), password_hash, created_at
```

### Target schema (migration 003)
```
users:
  id VARCHAR(64) PK              -- user-chosen handle or auto-generated
  email VARCHAR(256) UNIQUE      -- for login, discovery, notifications
  email_verified BOOLEAN         -- gate sending on this
  display_name VARCHAR(128)
  password_hash VARCHAR(256)     -- nullable (social-only users have no password)
  auth_provider VARCHAR(64)      -- "local", "google", "github"
  auth_provider_id VARCHAR(256)  -- sub/id from social provider
  user_type VARCHAR(32)          -- "human" or "agent"
  created_at TIMESTAMP
```

Drop `api_key` column (already P2 issue #7).

### User discovery

- `whoami` tool already returns `other_users` -- this is the directory
- Add email-based lookup for `send_message` (resolve email to user_id)
- At scale: paginated search endpoint (`GET /users?q=searchterm`)

### Spam/abuse prevention

| Mechanism | Priority |
|-----------|----------|
| Email verification required before sending | Ship first |
| Rate limiting (100 msgs/hour per user) | Ship first |
| Block list (user can block senders) | Ship second |
| New account throttle (stricter limits for <24hr accounts) | Ship second |
| Invite-only mode (configurable) | Ship second |

## Workspace Model

**Recommendation: start flat, add workspaces later.**

The current model (all users in one pool, `project` field for topic grouping) works. Adding workspaces now would complicate the schema and every query for a benefit that only matters at B2B enterprise scale.

When to add workspaces:
- A paying customer asks for isolated communication within their team
- Message volume makes the global user pool unwieldy
- Enterprise customers need admin controls (member management, audit logs)

## Notifications

| Channel | Use Case | Priority |
|---------|----------|----------|
| SSE (in-browser) | Live inbox updates when web UI tab is open | Ship with web UI |
| Email notifications | "You have N new messages" digest | Ship second |
| Webhooks | AI agent notifications (eliminates polling) | Ship second |
| Browser push | Notify when tab is closed | Ship third |

## Pricing Model

**Recommended: generous free tier + hybrid (base + per-message overage)**

Per-seat pricing breaks with AI agents (one agent doing the work of five shouldn't cost five seats). Per-message aligns cost with value.

| Tier | Price | Includes |
|------|-------|----------|
| Free | $0 | 5 users, 5,000 messages/month, 30-day history |
| Team | $10/mo base + $3/user/mo | 50K messages/month, unlimited history, web UI, webhooks |
| Business | $50/mo base + $5/user/mo | 500K messages/month, SAML SSO, workspace management, priority support |
| Overage | $0.50 per 1,000 messages | Applied after tier limit |

Free tier must be genuinely useful -- this product needs network effects.

## Technology Decisions Summary

| Decision | Choice | Alternative considered |
|----------|--------|----------------------|
| Auth | Google OAuth + GitHub OAuth via FastMCP providers | Auth0 (premature), email-only (too much friction) |
| Web UI | Jinja2 + HTMX + Tailwind CSS | React SPA (slower to ship, two codebases) |
| Real-time | SSE via HTMX | WebSocket (overkill for inbox updates) |
| Email delivery | Resend (3K free/month, Python SDK) | SendGrid, SES |
| CSS | Tailwind via CDN | Pico CSS (simpler but less flexible) |
| Rich text | Markdown input | Trix editor (heavier) |

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| FastMCP GoogleProvider has bugs with Claude Desktop redirect | Blocks Google OAuth | Test early. Fallback: custom OAuth proxy using Authlib. |
| MCP spec changes again in 2026 | Auth rework | Build against latest spec (Nov 2025). Minimize custom auth code. |
| Low adoption (network effects problem) | Product dies | Generous free tier. Focus on developer experience. |
| Abuse in open registration | Platform trust | Rate limiting + email verification + invite-only mode as kill switch |
| Railway scaling limits | Availability | Single instance sufficient for alpha. Connection pooling (asyncpg) needed before scaling. |
