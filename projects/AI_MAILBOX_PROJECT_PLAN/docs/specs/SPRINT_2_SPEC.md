# Sprint 2 Spec: API Redesign + Rate Limiting

**Status:** DRAFT -- awaiting approval
**Branch:** mvp-1-staging
**Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
**GitHub Issues:** #4 (rate limiting), #6 (inbox pagination), #12 (body length limit)
**Depends on:** Sprint 1 (complete -- 140 tests, deployed)

---

## 1. Overview

Split `check_messages` into `list_messages` (pure read) + `mark_read` (explicit write). Enhance `send_message` to accept array recipients for group messaging. Add `create_group`, `add_participant`, and `list_users` tools. Implement rate limiting on all MCP tools and web routes. Build web inbox displaying real conversation data with pagination.

**What does NOT change:** Schema DDL (no new tables, no new columns), error framework (`make_error`/`is_error`), web scaffold (templates, session middleware, login flow), OAuth flow, deployment config.

---

## 2. New Error Codes

| Code | Retryable | When |
|---|---|---|
| `RATE_LIMITED` | yes | Per-user or per-IP rate limit exceeded |
| `BODY_TOO_LONG` | no | Message body exceeds 10,000 characters |
| `GROUP_TOO_LARGE` | no | Group exceeds 50 participants |
| `INVALID_PARAMETER` | no | Parameter value is wrong type or out of range (e.g., limit < 1) |
| `MISSING_PARAMETER` | no | Required parameter not provided (e.g., neither `to` nor `conversation_id`) |
| `GROUP_CONFIRMATION_REQUIRED` | no | Group send requires a valid group_send_token (see section 4.11) |
| `GROUP_TOKEN_EXPIRED` | no | group_send_token has expired (5-minute TTL) |
| `GROUP_TOKEN_INVALID` | no | group_send_token does not match conversation_id + body |

Add to `ERROR_CODES` in `errors.py`. Existing codes unchanged.

---

## 3. Rate Limiting

### 3.1 Library

`limits` library (PyPI: `limits`). In-memory storage for Sprint 2 (single-process Railway deployment). Moving window strategy.

### 3.2 Architecture

New module: `src/ai_mailbox/rate_limit.py`

```python
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

storage = MemoryStorage()
limiter = MovingWindowRateLimiter(storage)

# Limit definitions
MCP_READ_LIMIT = parse("60/minute")     # list_messages, get_thread, whoami, list_users
MCP_WRITE_LIMIT = parse("30/minute")    # send_message, reply_to_message, mark_read
MCP_GROUP_LIMIT = parse("10/minute")    # create_group, add_participant
WEB_LOGIN_LIMIT = parse("5/minute")     # POST /web/login, POST /login
WEB_PAGE_LIMIT = parse("30/minute")     # GET /web/*

def check_rate_limit(limit, *identifiers) -> bool:
    """Returns True if within limit, False if exceeded."""
    return limiter.hit(limit, *identifiers)
```

### 3.3 Enforcement

**MCP tools:** Each tool checks rate limit before executing. Key: `("mcp", user_id)`. On exceed: return `make_error("RATE_LIMITED", "Rate limit exceeded. Try again in a few seconds.", retryable=True)`.

**Web login:** Key: `("login", client_ip)`. On exceed: render login page with error "Too many login attempts. Try again in 1 minute." HTTP 429.

**Web pages:** Key: `("web", user_id)`. On exceed: render a simple 429 page.

### 3.4 Rate limit headers (web routes only)

Web responses include:
- `X-RateLimit-Limit`: max requests in window
- `X-RateLimit-Remaining`: remaining requests
- `X-RateLimit-Reset`: seconds until window resets

MCP tool responses do not include headers (they return dicts, not HTTP responses).

### 3.5 Body length limit (Issue #12)

Constant: `MAX_BODY_LENGTH = 10_000` in `config.py`.

Enforced in `send_message` and `reply_to_message` before any DB operation:
```python
if len(body) > MAX_BODY_LENGTH:
    return make_error("BODY_TOO_LONG", f"Body exceeds {MAX_BODY_LENGTH} characters ({len(body)} given)", param="body")
```

---

## 4. MCP Tool Signatures

### 4.1 list_messages (NEW -- replaces check_messages)

```python
def tool_list_messages(
    db: DBConnection,
    *,
    user_id: str,
    project: str | None = None,
    unread_only: bool = True,
    conversation_id: str | None = None,
    limit: int = 50,
    after_sequence: int = 0,
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_READ_LIMIT
2. If `conversation_id` provided: validate user is participant, fetch messages from that conversation
3. If `conversation_id` not provided: fetch messages across all conversations where user is participant
4. Filter by `project` if provided
5. Filter to unread (sequence_number > last_read_sequence) if `unread_only=True`
6. Paginate: messages with sequence_number > `after_sequence`, up to `limit` (max 200)
7. **Does NOT advance read cursor** -- pure read operation

**Response:**
```json
{
    "user": "keith",
    "message_count": 5,
    "has_more": true,
    "next_cursor": 42,
    "messages": [
        {
            "id": "uuid",
            "conversation_id": "uuid",
            "from_user": "keith",
            "to_user": "amy",
            "sequence_number": 38,
            "project": "general",
            "subject": "Hello",
            "body": "Message text",
            "content_type": "text/plain",
            "reply_to": null,
            "created_at": "2026-04-05T12:00:00Z"
        }
    ]
}
```

`next_cursor` is the highest sequence_number in the returned messages. Pass as `after_sequence` for next page. `null` if `has_more` is false.

**Validation:**
- `limit` must be 1-200 (default 50). Out of range: `INVALID_PARAMETER`.
- `after_sequence` must be >= 0. Negative: `INVALID_PARAMETER`.
- `conversation_id` if provided must exist and user must be participant: `CONVERSATION_NOT_FOUND` or `PERMISSION_DENIED`.

### 4.2 mark_read (NEW)

```python
def tool_mark_read(
    db: DBConnection,
    *,
    user_id: str,
    conversation_id: str,
    up_to_sequence: int | None = None,
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_WRITE_LIMIT
2. Validate user is participant in conversation
3. Compute `max_seq = get_max_sequence(conversation_id)`
4. If `up_to_sequence` is None: advance cursor to `max_seq`
5. If `up_to_sequence` is provided: advance cursor to `min(up_to_sequence, max_seq)` (clamped to actual messages -- prevents pre-marking future messages as read)
6. Cursor never goes backward (advance_read_cursor uses GREATEST)
7. Return new cursor position

**Response:**
```json
{
    "conversation_id": "uuid",
    "user": "keith",
    "marked_up_to": 42,
    "previous_cursor": 35
}
```

**Validation:**
- `conversation_id` required: `MISSING_PARAMETER` if absent
- Conversation must exist: `CONVERSATION_NOT_FOUND`
- User must be participant: `PERMISSION_DENIED`
- `up_to_sequence` if provided must be > 0: `INVALID_PARAMETER`

### 4.3 send_message (ENHANCED)

```python
def tool_send_message(
    db: DBConnection,
    *,
    user_id: str,
    to: str | list[str] | None = None,
    body: str,
    project: str = "general",
    subject: str | None = None,
    conversation_id: str | None = None,
    content_type: str = "text/plain",
    idempotency_key: str | None = None,
    group_name: str | None = None,
    group_send_token: str | None = None,
) -> dict
```

**New parameters:**
- `to` now accepts `list[str]` for group messages (2+ recipients)
- `conversation_id` sends to an existing conversation (overrides `to`)
- `content_type` message content type (default "text/plain")
- `idempotency_key` deduplication key
- `group_name` optional name when creating group via `to` array
- `group_send_token` required for group sends (see section 4.10)

**Behavior:**

Mode 1 -- Direct (existing): `to` is a string
1. Rate limit check: MCP_WRITE_LIMIT
2. Body length check
3. `find_or_create_direct_conversation(sender, to, project)`
4. `insert_message(conversation_id, sender, body, ...)`

Mode 2 -- Group by recipients: `to` is a list with 2+ elements
1. Rate limit check: MCP_WRITE_LIMIT
2. Body length check
3. Validate all recipients exist and are not sender
4. `find_or_create_group_by_members(sender, to, project, group_name)`
5. **Group confirmation gate (section 4.10):** If `group_send_token` not provided or invalid, return confirmation payload. Do NOT send.
6. `insert_message(conversation_id, sender, body, ...)`

Mode 3 -- To existing conversation: `conversation_id` provided
1. Rate limit check: MCP_WRITE_LIMIT
2. Body length check
3. Validate user is participant in conversation
4. **If conversation type is NOT `direct`:** Group confirmation gate (section 4.10). Requires valid `group_send_token`.
5. `insert_message(conversation_id, sender, body, ...)`

**Precedence:** If both `conversation_id` and `to` are provided, `conversation_id` takes precedence. If neither is provided: `MISSING_PARAMETER`.

**Response (all modes):**
```json
{
    "message_id": "uuid",
    "conversation_id": "uuid",
    "from_user": "keith",
    "to_user": "amy",
    "to_users": ["amy", "bob"],
    "project": "general"
}
```

- `to_user`: first recipient (backward compat for direct messages)
- `to_users`: all recipients (new field, always a list)
- For direct messages: `to_users` has 1 element
- For groups: `to_users` has all non-sender participants

**Validation (new):**
- `to` list with 1 element: treated as string (direct message)
- `to` list with 0 elements: `MISSING_PARAMETER`
- `to` list with sender in it: sender is silently removed (not an error)
- All recipients in `to` list must exist: `RECIPIENT_NOT_FOUND` with first missing user
- Group size (sender + recipients) > 50: `GROUP_TOO_LARGE`
- Body > 10,000 chars: `BODY_TOO_LONG`
- Existing validation unchanged: `EMPTY_BODY`, `SELF_SEND` (only for direct), `DUPLICATE_MESSAGE`

### 4.4 reply_to_message (ENHANCED)

```python
def tool_reply_to_message(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    body: str,
    content_type: str = "text/plain",
    idempotency_key: str | None = None,
) -> dict
```

**New parameters:** `content_type`, `idempotency_key`

**Behavior:** Unchanged from Sprint 1 except:
1. Rate limit check: MCP_WRITE_LIMIT
2. Body length check (new)
3. Passes `content_type` and `idempotency_key` to `insert_message`

**Response:** Same shape as Sprint 1 plus `conversation_id`:
```json
{
    "message_id": "uuid",
    "conversation_id": "uuid",
    "from_user": "keith",
    "to_user": "amy",
    "project": "general"
}
```

### 4.5 get_thread (ENHANCED)

```python
def tool_get_thread(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    limit: int = 100,
    after_sequence: int = 0,
) -> dict
```

**New parameters:** `limit`, `after_sequence` for pagination

**Response (enhanced):**
```json
{
    "conversation": {
        "id": "uuid",
        "type": "direct",
        "project": "general",
        "name": null,
        "participants": ["keith", "amy"]
    },
    "root_message_id": "uuid",
    "message_count": 5,
    "has_more": false,
    "next_cursor": null,
    "messages": [...]
}
```

New fields: `conversation` object with metadata and participant list, `has_more`, `next_cursor`.

**Validation:** `limit` 1-200, `after_sequence` >= 0 (same rules as `list_messages`).

### 4.6 whoami (UNCHANGED)

No changes to signature or behavior. Rate limit check added: MCP_READ_LIMIT.

### 4.7 list_users (NEW)

```python
def tool_list_users(
    db: DBConnection,
    *,
    user_id: str,
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_READ_LIMIT
2. Return all registered users with display names
3. Excludes the calling user from the list (they know who they are)

**Response:**
```json
{
    "users": [
        {"id": "amy", "display_name": "Amy Costello"}
    ],
    "count": 1,
    "calling_user": "keith"
}
```

### 4.8 create_group (NEW)

```python
def tool_create_group(
    db: DBConnection,
    *,
    user_id: str,
    name: str,
    members: list[str],
    project: str = "general",
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_GROUP_LIMIT
2. Validate `name` is non-empty (max 256 chars)
3. Validate all members exist
4. Creator is automatically added as participant
5. Create `team_group` conversation via `create_team_group`
6. If group with same name already exists for this creator in this project: return existing group (idempotent)

**Response:**
```json
{
    "conversation_id": "uuid",
    "name": "Backend Team",
    "project": "general",
    "participants": ["amy", "bob", "keith"],
    "created": true
}
```

`created: false` if existing group was returned.

**Validation:**
- `name` empty: `VALIDATION_ERROR` with param "name"
- `name` > 256 chars: `VALIDATION_ERROR` with param "name"
- `members` empty: `VALIDATION_ERROR` with param "members"
- Any member not found: `RECIPIENT_NOT_FOUND`
- Total participants > 50: `GROUP_TOO_LARGE`

### 4.9 add_participant (NEW)

```python
def tool_add_participant(
    db: DBConnection,
    *,
    user_id: str,
    conversation_id: str,
    user_to_add: str,
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_GROUP_LIMIT
2. Validate calling user is participant in conversation
3. Validate `user_to_add` exists
4. Validate conversation is not `direct` type (cannot add third person to 1:1)
5. Add participant (idempotent -- no error if already member)

**Response:**
```json
{
    "conversation_id": "uuid",
    "user_added": "charlie",
    "already_member": false,
    "participant_count": 4
}
```

**Validation:**
- Conversation not found: `CONVERSATION_NOT_FOUND`
- Caller not participant: `PERMISSION_DENIED`
- User to add not found: `RECIPIENT_NOT_FOUND`
- Conversation is `direct`: `VALIDATION_ERROR` with message "Cannot add participants to direct conversations"
- Would exceed 50 participants: `GROUP_TOO_LARGE`

### 4.10 Group Send Confirmation Protocol (HARD CONSTRAINT)

**Rule:** Sending a message to any group conversation (type `team_group` or `project_group`) requires a valid `group_send_token`. No exceptions. This is enforced at the tool level -- the token cannot be fabricated by the AI client.

**Two-confirmation flow:**

```
Step 1: AI calls send_message(to=[...], body="...", project="general")
        Target is a group -> tool returns confirmation payload (NOT an error):
        {
            "confirmation_required": true,
            "group_send_token": "server-generated-uuid",
            "token_expires_at": "2026-04-05T12:05:00Z",
            "group": {
                "conversation_id": "uuid",
                "name": "Backend Team",
                "type": "team_group",
                "project": "general",
                "participants": ["amy", "bob", "keith"],
                "participant_count": 3
            },
            "message_preview": "First 100 chars of body...",
            "instruction": "Show group details to user and get explicit approval before proceeding."
        }

        AI shows this to user -> Confirmation 1: "Send to group 'Backend Team' (3 members)?"
        User approves.

Step 2: AI calls send_message(to=[...], body="...", group_send_token="server-generated-uuid")
        Token valid -> tool checks body matches -> sends message.
        But BEFORE calling, AI must ask user AGAIN:
        Confirmation 2: "Send message '[preview]' to 3 participants in 'Backend Team'? Confirm?"
        User approves -> AI makes the call.
```

**Token mechanics:**
- Generated by the server: `uuid4()`, stored in memory dict `{token: {conversation_id, body_hash, expires_at}}`
- TTL: 5 minutes from generation
- Bound to: `conversation_id` + SHA-256 hash of `body`. Changing the body after getting a token requires a new token.
- Single-use: token is consumed on successful send
- Not an error response: the confirmation payload does NOT have an `error` key. It has `confirmation_required: true`.

**Enforcement:**
- `send_message` to a group without `group_send_token`: returns confirmation payload
- `send_message` with expired token: `GROUP_TOKEN_EXPIRED` error
- `send_message` with token that doesn't match conversation_id or body: `GROUP_TOKEN_INVALID` error
- Direct messages (`to` is a string, conversation type is `direct`): no token required

**AI client instructions (included in tool description):**
"When sending to a group, you will receive a confirmation payload. You MUST:
(1) Show the user the group name, participant list, and participant count. Ask: 'Send to this group?' Wait for explicit 'yes'.
(2) Show the user the message content and recipient count. Ask: 'Confirm sending this message to N participants?' Wait for explicit 'yes'.
Only after BOTH confirmations, re-call with the group_send_token."

### 4.11 check_messages (DEPRECATED)

Kept as backward-compatible alias. Internally calls `list_messages` then `mark_read` on each conversation.

```python
def tool_check_messages(
    db: DBConnection,
    *,
    user_id: str,
    project: str | None = None,
    unread_only: bool = True,
) -> dict
```

Behavior identical to Sprint 1. Returns same shape. Marked deprecated in tool description: "Deprecated: use list_messages + mark_read instead."

---

## 5. Query Layer Changes

### 5.1 New functions

```python
def find_or_create_group_by_members(
    db, creator: str, member_ids: list[str], project: str, name: str | None = None
) -> tuple[str, bool]:
    """Find existing team_group with exact member set or create one.
    Returns (conversation_id, created: bool).

    Matching: sort all participants (creator + members), join with comma.
    Look for team_group where name matches auto-generated name in this project.
    If name parameter is provided, use that instead of auto-generated.
    """

def get_max_sequence(db, conversation_id: str) -> int:
    """Return the highest sequence_number in a conversation. 0 if no messages."""

def get_inbox_paginated(
    db, user_id: str, project: str | None = None, limit: int = 50, offset: int = 0
) -> tuple[list[dict], bool]:
    """Paginated inbox. Returns (conversations, has_more).
    Each conversation dict same shape as get_inbox but with pagination.
    Ordered by last_message_at DESC."""

def list_messages_query(
    db, user_id: str, project: str | None = None, unread_only: bool = True,
    conversation_id: str | None = None, after_sequence: int = 0, limit: int = 50
) -> tuple[list[dict], bool]:
    """Fetch messages for list_messages tool. Returns (messages, has_more).
    If conversation_id specified: messages from that conversation only.
    If not: messages across all user's conversations.
    Ordered by (conversation_id, sequence_number) ASC."""
```

### 5.2 Modified functions

- `get_conversation_messages` -- add `has_more` return value: `-> tuple[list[dict], bool]`
- `get_inbox` -- keep existing signature for backward compat, add `get_inbox_paginated` for web

### 5.3 Unchanged functions

All other query functions remain unchanged.

---

## 6. Web Routes

### 6.1 Modified routes

**GET /web/inbox** -- now displays real data

Current (Sprint 1): shows conversation list from `get_inbox()` or empty state.

Sprint 2 changes:
- Pagination: `?page=1` query parameter (default 1), 20 conversations per page
- Conversations grouped visually by project (sorted by most recent activity)
- Each conversation row shows:
  - Conversation type indicator (text: "DM" or "Group")
  - Participant names (truncated at 3, e.g., "amy, bob +2 more")
  - Project tag
  - Last message preview (truncated to 80 chars)
  - Last message timestamp (relative: "2m ago", "1h ago", "yesterday")
  - Unread count badge (hidden if 0)
- "Previous" / "Next" pagination links
- Empty state unchanged

Rate limit: WEB_PAGE_LIMIT per authenticated user.

### 6.2 Rate-limited routes

**POST /web/login** -- rate limited by IP (WEB_LOGIN_LIMIT: 5/minute)

On rate limit exceed:
- HTTP 429
- Re-render login form with error: "Too many login attempts. Try again in 1 minute."

**POST /login** (OAuth login) -- same IP-based rate limit

### 6.3 New template

`src/ai_mailbox/templates/_conversation_row.html` -- HTMX partial for a single conversation row in the inbox. Used by the inbox template and by future HTMX polling.

### 6.4 Template changes

- `inbox.html` -- rewrite to render real conversation data with pagination
- `base.html` -- add rate limit error styling (429 banner)

### 6.5 Health page

Add rate limit status to `/web/health`:
- Current in-memory storage type
- Number of active rate limit entries (approximate)

---

## 7. Edge Cases

### 7.1 send_message with array `to` containing duplicates

Deduplicate silently. `send_message(to=["amy", "amy", "bob"])` is equivalent to `send_message(to=["amy", "bob"])`.

### 7.2 send_message with array `to` containing only sender

After removing sender and deduplicating, if the list is empty: `MISSING_PARAMETER` error with param "to".

### 7.3 send_message with `conversation_id` to a conversation user left

User is not a participant: `PERMISSION_DENIED`. (Sprint 2 has no leave mechanism, but guards against future state.)

### 7.4 mark_read with sequence higher than max

`mark_read(up_to_sequence=999)` when max sequence is 42: cursor is clamped to 42. The tool calls `get_max_sequence(conversation_id)` and uses `min(up_to_sequence, max_seq)`. This prevents AI clients from accidentally skipping future messages. The response shows the actual cursor position (`marked_up_to: 42`), so the client knows what happened.

### 7.5 list_messages with conversation_id for a different user's conversation

User not a participant: `PERMISSION_DENIED`.

### 7.6 add_participant to direct conversation

Direct conversations are strictly 1:1. Return `VALIDATION_ERROR`: "Cannot add participants to direct conversations." The user should create a group instead.

### 7.7 create_group with same name as existing group

If the caller has already created a group with the same name in the same project, return the existing group with `created: false`. Different callers can create groups with the same name (names are unique per creator per project, per Sprint 1 spec).

### 7.8 Rate limit race condition (concurrent requests)

`MemoryStorage` in `limits` is not thread-safe across processes but is safe within a single process. Railway deploys a single Uvicorn process. If horizontal scaling is added later, switch to Redis-backed storage. The `limits` library supports this via configuration change only (no code changes).

### 7.9 list_messages across conversations with different sequence spaces

When `conversation_id` is not specified, messages from multiple conversations are returned. Each conversation has independent sequence numbers. The `next_cursor` in this case is not usable for pagination across conversations.

Resolution: when fetching across conversations (no `conversation_id`), pagination uses `created_at` timestamp instead of sequence numbers. The `after_sequence` parameter is ignored when `conversation_id` is null. A separate `after_timestamp` parameter handles cross-conversation pagination.

Updated `list_messages` signature:

```python
def tool_list_messages(
    db: DBConnection,
    *,
    user_id: str,
    project: str | None = None,
    unread_only: bool = True,
    conversation_id: str | None = None,
    limit: int = 50,
    after_sequence: int = 0,        # used when conversation_id is provided
    after_timestamp: str | None = None,  # ISO 8601, used when conversation_id is null
) -> dict
```

When `conversation_id` is provided: paginate by `after_sequence`. When null: paginate by `after_timestamp` (messages with `created_at > after_timestamp`).

### 7.10 Backward compat: check_messages auto-marks read

`check_messages` calls `list_messages(unread_only=unread_only)` then for each conversation in the results, calls `advance_read_cursor` to the max sequence returned. This preserves Sprint 1 behavior. AI clients using `check_messages` will not notice the change.

---

## 8. File Changes Summary

### New files

| File | Purpose |
|---|---|
| `src/ai_mailbox/rate_limit.py` | Rate limiter setup, limit definitions, check function |
| `src/ai_mailbox/group_tokens.py` | Group send token generation, validation, expiry, single-use store |
| `src/ai_mailbox/tools/list_messages.py` | `list_messages` tool (replaces inbox.py role for MCP) |
| `src/ai_mailbox/tools/mark_read.py` | `mark_read` tool |
| `src/ai_mailbox/tools/list_users.py` | `list_users` tool |
| `src/ai_mailbox/tools/create_group.py` | `create_group` tool |
| `src/ai_mailbox/tools/add_participant.py` | `add_participant` tool |
| `src/ai_mailbox/templates/_conversation_row.html` | Inbox conversation row partial |
| `tests/test_rate_limit.py` | Rate limiter unit tests |
| `tests/test_group_tokens.py` | Group send token unit tests (generation, validation, expiry, single-use) |
| `tests/test_list_messages.py` | list_messages tool tests |
| `tests/test_mark_read.py` | mark_read tool tests |
| `tests/test_group_tools.py` | create_group + add_participant tests |

### Modified files

| File | Changes |
|---|---|
| `pyproject.toml` | Add `limits` dependency |
| `src/ai_mailbox/errors.py` | Add RATE_LIMITED, BODY_TOO_LONG, GROUP_TOO_LARGE, INVALID_PARAMETER, MISSING_PARAMETER |
| `src/ai_mailbox/config.py` | Add MAX_BODY_LENGTH constant |
| `src/ai_mailbox/db/queries.py` | Add find_or_create_group_by_members, get_max_sequence, get_inbox_paginated, list_messages_query. Modify get_conversation_messages return. |
| `src/ai_mailbox/tools/send.py` | Array `to`, conversation_id, content_type, idempotency_key, group_name, body length check, rate limit |
| `src/ai_mailbox/tools/reply.py` | content_type, idempotency_key, body length check, rate limit |
| `src/ai_mailbox/tools/inbox.py` | Delegate to list_messages + mark_read, add deprecation notice |
| `src/ai_mailbox/tools/thread.py` | Pagination params, conversation metadata in response, rate limit |
| `src/ai_mailbox/tools/identity.py` | Rate limit check |
| `src/ai_mailbox/server.py` | Register new tools, pass rate limiter |
| `src/ai_mailbox/web.py` | Login rate limiting, inbox pagination, real data rendering |
| `src/ai_mailbox/templates/inbox.html` | Conversation rows, pagination, unread badges |
| `src/ai_mailbox/templates/base.html` | 429 error banner styling |
| `tests/conftest.py` | Add rate limiter fixture, add more seed data for group tests |
| `tests/test_queries.py` | Tests for new query functions |
| `tests/test_tools.py` | Updated send_message tests (array to, conversation_id), body length tests |
| `tests/test_web.py` | Login rate limit tests, inbox pagination tests, real data rendering |
| `tests/test_server.py` | New tool registration tests |

### Unchanged files

| File | Reason |
|---|---|
| `src/ai_mailbox/db/schema.py` | No DDL changes |
| `src/ai_mailbox/db/migrations/*` | No new migrations |
| `src/ai_mailbox/oauth.py` | Unchanged |
| `src/ai_mailbox/__main__.py` | Unchanged |
| `Dockerfile` | No new system deps (`limits` is pure Python) |
| `railway.toml` | Unchanged |

---

## 9. Acceptance Criteria

### 9.1 list_messages

- [ ] `list_messages()` returns messages without advancing read cursor
- [ ] Calling `list_messages()` twice returns identical results (no side effects)
- [ ] `list_messages(conversation_id="uuid")` returns messages from that conversation only
- [ ] `list_messages(project="general")` filters to conversations in that project
- [ ] `list_messages(unread_only=True)` returns only messages after user's read cursor
- [ ] `list_messages(unread_only=False)` returns all messages
- [ ] `list_messages(limit=5)` returns at most 5 messages with `has_more=True` if more exist
- [ ] `list_messages(after_sequence=10)` returns messages with sequence > 10 (when conversation_id provided)
- [ ] `list_messages(after_timestamp="2026-04-05T00:00:00Z")` paginates across conversations
- [ ] Non-participant accessing conversation returns `PERMISSION_DENIED`

### 9.2 mark_read

- [ ] `mark_read(conversation_id="uuid")` advances cursor to max sequence
- [ ] `mark_read(conversation_id="uuid", up_to_sequence=10)` advances cursor to 10
- [ ] Cursor never goes backward (mark_read with lower sequence is no-op)
- [ ] Non-participant returns `PERMISSION_DENIED`
- [ ] Missing conversation returns `CONVERSATION_NOT_FOUND`

### 9.3 send_message (enhanced)

- [ ] `send_message(to="amy", body="hello")` works as before (backward compat, no token needed)
- [ ] `send_message(to=["amy", "bob"], body="hello")` WITHOUT token returns confirmation payload with `group_send_token`
- [ ] `send_message(to=["amy", "bob"], body="hello", group_send_token="valid")` sends message
- [ ] Sending to same group of people again reuses the conversation
- [ ] `send_message(conversation_id="uuid", body="hello")` to a group WITHOUT token returns confirmation payload
- [ ] `send_message(conversation_id="uuid", body="hello")` to a direct conversation sends without token
- [ ] `conversation_id` takes precedence over `to` when both provided
- [ ] Response includes both `to_user` and `to_users` fields
- [ ] `content_type` and `idempotency_key` are stored correctly
- [ ] Body > 10,000 chars returns `BODY_TOO_LONG`
- [ ] `to` list with 50+ recipients returns `GROUP_TOO_LARGE`
- [ ] `group_name` sets the group name when creating via array

### 9.3b Group send confirmation (HARD CONSTRAINT)

- [ ] Group send without `group_send_token` returns confirmation payload (not an error -- no `error` key)
- [ ] Confirmation payload includes: `group_send_token`, group details, participant list, message preview
- [ ] Token is server-generated UUID, stored in memory
- [ ] Token expires after 5 minutes: `GROUP_TOKEN_EXPIRED` error
- [ ] Token is bound to conversation_id + SHA-256(body): changing body invalidates token -> `GROUP_TOKEN_INVALID`
- [ ] Token is single-use: second send with same token returns `GROUP_TOKEN_INVALID`
- [ ] Direct messages (1:1) never require a token
- [ ] Tool description includes two-confirmation instructions for AI clients

### 9.4 reply_to_message (enhanced)

- [ ] `content_type` parameter is stored on the message
- [ ] `idempotency_key` parameter prevents duplicate replies
- [ ] Body > 10,000 chars returns `BODY_TOO_LONG`
- [ ] Existing behavior unchanged for basic reply case

### 9.5 get_thread (enhanced)

- [ ] Response includes `conversation` object with type, project, name, participants
- [ ] `limit` and `after_sequence` paginate within the conversation
- [ ] `has_more` and `next_cursor` present in response

### 9.6 list_users

- [ ] Returns all users except the calling user
- [ ] Response includes `id`, `display_name`, `count`
- [ ] Rate limited

### 9.7 create_group

- [ ] Creates a team_group conversation with all specified members + creator
- [ ] Returns conversation_id, participants, created flag
- [ ] Same name + project + creator returns existing group (idempotent)
- [ ] Empty name returns `VALIDATION_ERROR`
- [ ] Non-existent member returns `RECIPIENT_NOT_FOUND`
- [ ] > 50 participants returns `GROUP_TOO_LARGE`

### 9.8 add_participant

- [ ] Adds user to group or project_group conversation
- [ ] Returns participant_count and already_member flag
- [ ] Adding to direct conversation returns `VALIDATION_ERROR`
- [ ] Adding non-existent user returns `RECIPIENT_NOT_FOUND`
- [ ] Non-participant caller returns `PERMISSION_DENIED`
- [ ] Idempotent: adding existing member returns `already_member: true`

### 9.9 check_messages (deprecated)

- [ ] Still works identically to Sprint 1 behavior
- [ ] Tool description includes deprecation notice
- [ ] Internally delegates to list_messages + mark_read

### 9.10 Rate limiting

- [ ] MCP read tools return `RATE_LIMITED` error after 60 calls/minute per user
- [ ] MCP write tools return `RATE_LIMITED` error after 30 calls/minute per user
- [ ] Group tools return `RATE_LIMITED` after 10 calls/minute per user
- [ ] Web login returns 429 after 5 attempts/minute per IP
- [ ] Web pages return 429 after 30 requests/minute per user
- [ ] Rate limit resets after the window passes (moving window, not fixed)
- [ ] Error response includes `retryable: true`

### 9.11 Web inbox (real data)

- [ ] Inbox page displays conversation list with participant names, project, preview, timestamp
- [ ] Unread count badges show on conversations with unread messages
- [ ] Conversations ordered by most recent activity
- [ ] Pagination links work (next/previous)
- [ ] Empty state still shows when user has no conversations
- [ ] Rate limit exceeded shows 429 error on login page

### 9.12 AI UX UAT (browser verification -- required gate)

- [ ] **Inbox with data:** Login, verify inbox shows conversation rows with participant names, last message preview, timestamps, and unread badges
- [ ] **Pagination:** If > 20 conversations exist, verify next/previous pagination links work
- [ ] **Rate limit on login:** Submit 6 rapid login attempts, verify 429 response on the 6th
- [ ] **Empty state:** Login as a user with no conversations, verify empty state renders
- [ ] **Visual consistency:** Verify conversation rows are styled, badges are visible, pagination links work

### 9.13 Tests

- [ ] test_rate_limit.py: limiter setup, hit/miss, window reset, per-user isolation
- [ ] test_list_messages.py: all list_messages scenarios (filters, pagination, no side effects)
- [ ] test_mark_read.py: cursor advancement, no-backward, permissions
- [ ] test_group_tools.py: create_group, add_participant, idempotency, validation
- [ ] test_tools.py: enhanced send_message (array to, conversation_id, body limit), enhanced reply
- [ ] test_queries.py: new query functions
- [ ] test_web.py: login rate limit, inbox pagination, real data rendering
- [ ] Total test count >= 200 (up from 140)

### 9.14 Deployment

- [ ] MVP 1 Staging deploys and passes health check
- [ ] All new MCP tools functional on deployed environment
- [ ] Rate limiting active on deployed environment
- [ ] Web inbox shows real conversation data on deployed environment
- [ ] AI UX UAT passed on deployed environment

### 9.15 GitHub

- [ ] Issue #4 (rate limiting) closed with commit reference
- [ ] Issue #6 (inbox pagination) closed with commit reference
- [ ] Issue #12 (body length limit) closed with commit reference

---

## 10. Implementation Order (TDD Through Delivery)

1. **Error codes + rate limit + group token store** -- `rate_limit.py` + `group_tokens.py` + error code additions + `test_rate_limit.py` + `test_group_tokens.py`
   - RED: tests for rate limiter (hit, miss, reset, isolation), tests for new error codes, tests for token generation/validation/expiry/single-use
   - GREEN: implement rate_limit.py, group_tokens.py, add error codes to errors.py
   - VERIFY: tests pass locally

2. **Query layer** -- new query functions + `test_queries.py` additions
   - RED: tests for find_or_create_group_by_members, get_max_sequence, get_inbox_paginated, list_messages_query
   - GREEN: implement query functions
   - VERIFY: tests pass locally

3. **list_messages + mark_read** -- new tools + `test_list_messages.py` + `test_mark_read.py`
   - RED: tests for all list_messages scenarios (pagination, filters, no side effects), mark_read scenarios
   - GREEN: implement tool modules
   - VERIFY: tests pass locally

4. **send_message + reply_to_message enhancements** -- `test_tools.py` updates
   - RED: tests for array to, conversation_id, body length, content_type, idempotency_key, group_name
   - GREEN: update send.py and reply.py
   - VERIFY: tests pass locally

5. **create_group + add_participant + list_users** -- new tools + `test_group_tools.py`
   - RED: tests for group creation, participant addition, user listing
   - GREEN: implement tool modules
   - VERIFY: tests pass locally

6. **check_messages deprecation** -- update inbox.py + test_tools.py
   - RED: verify check_messages still passes existing tests
   - GREEN: refactor to delegate to list_messages + mark_read
   - VERIFY: full test suite green

7. **Server integration** -- register all new tools + `test_server.py`
   - RED: tests for new tool registration, rate limit wiring
   - GREEN: wire tools in server.py
   - VERIFY: full local test suite green

8. **Web inbox + rate limiting** -- template updates + `test_web.py` additions
   - RED: tests for real data inbox, pagination, login rate limit 429
   - GREEN: update web.py and templates
   - VERIFY: full local test suite green (all tests, zero failures)

9. **Deploy to MVP 1 Staging**
   - VERIFY:
     - `/health` returns healthy
     - New MCP tools respond correctly
     - Rate limits enforce (60/30/10/5 per minute)
     - Web inbox shows conversation data

10. **AI UX UAT** (required gate)
    - Browser verification of all section 9.12 checks
    - Failures block sprint completion

11. **Human UAT** (required gate)
    - User verifies web inbox, rate limiting, tool behavior
    - Sprint not complete until passed

12. **GitHub cleanup**
    - Close #4, #6, #12 with commit references

---

## 11. Resolved Open Questions

### Q1: mark_read cursor clamping -- RESOLVED: (B) Clamp

`mark_read(up_to_sequence=999)` when max is 42 clamps to 42. Prevents AI clients from accidentally pre-marking future messages as read. One extra `get_max_sequence()` query per call -- minimal cost.

### Q2: send_message to array -- RESOLVED: (A) Find-or-create

Same participant set + project reuses existing group. Auto-generated name (sorted, comma-joined) serves as lookup key. Named groups via `create_group` use explicit names.

### Q3: check_messages removal -- RESOLVED: (A) Deprecate Sprint 2, remove Sprint 4

Deprecation notice in tool description starting Sprint 2. AI clients have Sprint 3 to migrate. Removed in Sprint 4.

### Q4: Group send confirmation -- RESOLVED: Token-based enforcement

All group sends require a `group_send_token` obtained from the confirmation payload (section 4.10). Two user confirmations required: (1) group selection approval, (2) message send approval. Enforced at tool level -- token is server-generated, single-use, 5-minute TTL, bound to conversation + body hash. No exceptions.

---

## 12. Resolved Design Decisions

1. **Group send confirmation is tool-enforced, not AI-behavior-dependent.** The `group_send_token` mechanism ensures no group message can be sent without the AI first receiving (and displaying) the confirmation payload. The token is server-generated, single-use, and expires. An AI client cannot bypass this by fabricating a token. The two-confirmation requirement (group selection + message approval) is enforced by: (a) token generation requires a call without a token, (b) AI client instructions in tool description mandate two user approvals before re-calling with the token.

2. **list_messages is pure read.** No side effects. Read cursor advancement is exclusively via mark_read. This matches the CQRS principle (command-query separation) and gives AI clients explicit control.

2. **send_message `to` union type.** `str | list[str]` is valid JSON Schema (`oneOf`). FastMCP handles this. Checked: FastMCP 1.9+ supports union annotations.

3. **conversation_id parameter on send_message.** Enables sending to existing groups without re-specifying recipients. Takes precedence over `to` when both provided. This is the primary mechanism for ongoing group conversations.

4. **Rate limits are per-user for MCP tools, per-IP for web login.** MCP tools have authenticated user context. Web login happens before authentication, so IP is the only identifier. Per-IP rate limiting has known limitations with shared IPs -- acceptable for alpha.

5. **MemoryStorage for rate limiter.** Single-process Railway deployment. No Redis dependency in Sprint 2. The `limits` library supports swapping to Redis with a config change when horizontal scaling is needed.

6. **50-participant group limit.** Arbitrary but reasonable ceiling. Messaging systems with more participants per group need different architecture (pub/sub). Can raise later.

7. **Body length 10,000 characters.** From issue #12 analysis. Covers most messaging use cases. Structured JSON payloads (Sprint 4) will have separate validation.

---

## Appendix A: Rate Limit Summary

| Scope | Limit | Key | Response |
|---|---|---|---|
| MCP read tools | 60/minute | user_id | `RATE_LIMITED` error dict |
| MCP write tools | 30/minute | user_id | `RATE_LIMITED` error dict |
| MCP group tools | 10/minute | user_id | `RATE_LIMITED` error dict |
| Web login | 5/minute | client IP | HTTP 429 + error on form |
| Web pages | 30/minute | user_id | HTTP 429 page |

## Appendix B: Tool Registration (server.py)

```python
# New tools to register
@mcp.tool()
async def list_messages(project: str | None = None, unread_only: bool = True,
                        conversation_id: str | None = None, limit: int = 50,
                        after_sequence: int = 0, after_timestamp: str | None = None) -> dict: ...

@mcp.tool()
async def mark_read(conversation_id: str, up_to_sequence: int | None = None) -> dict: ...

@mcp.tool()
async def list_users() -> dict: ...

@mcp.tool()
async def create_group(name: str, members: list[str], project: str = "general") -> dict: ...

@mcp.tool()
async def add_participant(conversation_id: str, user_to_add: str) -> dict: ...

# Enhanced existing tools
@mcp.tool()
async def send_message(to: str | list[str] | None = None, body: str = "",
                       project: str = "general", subject: str | None = None,
                       conversation_id: str | None = None,
                       content_type: str = "text/plain",
                       idempotency_key: str | None = None,
                       group_name: str | None = None) -> dict: ...
```

## Appendix C: Dependency Addition

```toml
# pyproject.toml
dependencies = [
    "mcp[cli]>=1.9.0",
    "uvicorn>=0.34.0",
    "psycopg[binary]>=3.1.0",
    "bcrypt>=4.0",
    "PyJWT>=2.8",
    "jinja2>=3.1",
    "limits>=3.0",    # NEW
]
```
