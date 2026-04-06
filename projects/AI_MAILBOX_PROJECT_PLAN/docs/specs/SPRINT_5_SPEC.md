# Sprint 5 Spec: Acknowledgment + Archiving + Agent Identity

**Status:** DRAFT -- awaiting approval
**Branch:** mvp-1-staging
**Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
**GitHub Issues:** #9 (CASCADE on user FKs), #10 (narrow PostgresDB retry), #11 (OAuth FK constraints)
**Depends on:** Sprint 4 (complete -- 372 tests, deployed)

---

## 1. Overview

Three features: (A) message acknowledgment protocol for agent-to-agent coordination, (B) per-user conversation archiving, (C) agent identity model replacing the heuristic `_is_ai_user` check. Also closes three P2 tech debt issues from the architecture review.

**What changes:** New migration (005), two new MCP tools (`acknowledge`, `archive_conversation`), agent identity fields on users table, `last_seen` tracking on MCP tool calls, web UI user directory + archive management + ACK badges, PostgresDB retry narrowed, FK constraints added.

**What does NOT change:** DaisyUI framework, rate limiting, group send confirmation protocol, search infrastructure, HTMX polling intervals, CORS/JWT validation, template structure (additive changes only).

---

## 2. Message Acknowledgment

### 2.1 Acknowledgment Model

Messages gain an `ack_state` column tracking processing status. This enables agent-to-agent workflows where the sender needs to know whether the recipient has seen, started processing, or completed work on a message.

**State machine:**

```
pending → received → processing → completed
                                → failed
```

- `pending` (default): Message sent, no acknowledgment yet
- `received`: Recipient confirms they received the message
- `processing`: Recipient is actively working on the request
- `completed`: Recipient finished the requested work
- `failed`: Recipient could not complete the requested work

**Transition rules:**
- Only forward transitions allowed (no rollback from completed to processing)
- `failed` is a terminal state (can transition from received or processing)
- Only a conversation participant (not the sender of that specific message) can acknowledge
- The sender of a message cannot acknowledge their own message

### 2.2 acknowledge MCP Tool

```python
# src/ai_mailbox/tools/acknowledge.py
def tool_acknowledge(
    db: DBConnection,
    *,
    user_id: str,
    message_id: str,
    state: str,  # received | processing | completed | failed
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_WRITE_LIMIT
2. Validate `state` is one of: received, processing, completed, failed
3. Fetch message, verify it exists
4. Verify user is a participant in the conversation
5. Verify user is NOT the sender of the message (can't ACK your own message)
6. Verify state transition is valid (forward-only)
7. Update `messages.ack_state`
8. Return updated message state

**Response:**
```json
{
    "message_id": "uuid",
    "conversation_id": "uuid",
    "ack_state": "received",
    "previous_state": "pending",
    "acknowledged_by": "amy"
}
```

**Validation errors:**
- Missing/invalid state: `INVALID_PARAMETER`
- Message not found: `MESSAGE_NOT_FOUND`
- Not a participant: `PERMISSION_DENIED`
- ACK own message: `PERMISSION_DENIED` ("Cannot acknowledge your own message")
- Invalid transition: `INVALID_STATE_TRANSITION` (new error code, not retryable)

### 2.3 ACK State Query Enhancement

Add `ack_state` to message results in `get_conversation_messages`, `list_messages_query`, and `search_messages`. The column already exists on the messages table after migration 005, so it flows through `SELECT m.*` automatically. No query changes needed for existing functions.

---

## 3. Conversation Archiving

### 3.1 Archive Model

Archiving is per-user, not per-conversation. User A can archive a conversation while User B keeps it in their inbox. This uses a `archived_at` timestamp on `conversation_participants`.

**Behavior:**
- Archived conversations are excluded from `get_inbox` / `get_inbox_paginated` by default
- A new `include_archived` parameter allows retrieving archived conversations
- When a new message arrives in an archived conversation, the archive flag is automatically cleared (auto-unarchive)
- Archive/unarchive is idempotent

### 3.2 archive_conversation MCP Tool

```python
# src/ai_mailbox/tools/archive.py
def tool_archive_conversation(
    db: DBConnection,
    *,
    user_id: str,
    conversation_id: str,
    archive: bool = True,  # True = archive, False = unarchive
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_WRITE_LIMIT
2. Validate conversation exists
3. Validate user is a participant
4. Set or clear `conversation_participants.archived_at`
5. Return archive status

**Response:**
```json
{
    "conversation_id": "uuid",
    "archived": true,
    "archived_at": "2026-04-06T12:00:00Z"
}
```

Unarchive response:
```json
{
    "conversation_id": "uuid",
    "archived": false,
    "archived_at": null
}
```

**Validation errors:**
- Conversation not found: `CONVERSATION_NOT_FOUND`
- Not a participant: `PERMISSION_DENIED`

### 3.3 Auto-Unarchive on New Message

In `insert_message` (queries.py), after inserting a message, clear `archived_at` for all participants except the sender:

```python
# After successful insert, auto-unarchive for recipients
db.execute(
    """UPDATE conversation_participants
       SET archived_at = NULL
       WHERE conversation_id = ? AND user_id != ? AND archived_at IS NOT NULL""",
    (conversation_id, from_user),
)
```

This ensures archived conversations resurface when new activity occurs.

### 3.4 Inbox Query Changes

Modify `get_inbox` and `get_inbox_paginated` in queries.py:

```python
def get_inbox(
    db: DBConnection, user_id: str, project: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
```

Add to WHERE clause:
```sql
-- Exclude archived unless explicitly requested
AND (cp.archived_at IS NULL OR ? = TRUE)
```

Each inbox entry gains an `archived` boolean field in the response.

---

## 4. Agent Identity

### 4.1 User Fields

Add to `users` table:
- `user_type VARCHAR(20) DEFAULT 'human'` — `human` or `agent`
- `last_seen TIMESTAMP` — updated on every MCP tool call
- `session_mode VARCHAR(20) DEFAULT 'persistent'` — `persistent` or `ephemeral` (metadata, no behavioral difference yet)

### 4.2 last_seen Tracking

In `server.py`, update `_get_user()` to record last_seen on every MCP tool invocation:

```python
def _get_user() -> str:
    uid = current_user_id.get("unknown")
    # Update last_seen
    update_last_seen(db, uid)
    return uid
```

New query in queries.py:
```python
def update_last_seen(db: DBConnection, user_id: str) -> None:
    db.execute(
        "UPDATE users SET last_seen = ? WHERE id = ?",
        (_now(), user_id),
    )
    # No commit needed — autocommit on PostgreSQL, batched on SQLite
```

### 4.3 Replace _is_ai_user Heuristic

Currently `web.py` uses a name-pattern heuristic (`claude`, `gpt`, `bot` in username). Replace with the `user_type` field:

```python
def _is_ai_user(db: DBConnection, user_id: str) -> bool:
    user = get_user(db, user_id)
    return user["user_type"] == "agent" if user else False
```

The Jinja2 global `is_ai_user` changes from a string check to a DB lookup. Cache per-request to avoid N+1 queries in thread view.

### 4.4 whoami Enhancement

Add `user_type`, `last_seen`, and `session_mode` to `tool_whoami` response:

```json
{
    "user_id": "keith",
    "display_name": "Keith",
    "user_type": "human",
    "session_mode": "persistent",
    "last_seen": "2026-04-06T18:30:00Z",
    "unread_counts": {"general": 2, "steertrue": 1}
}
```

### 4.5 list_users Enhancement

Add `user_type`, `last_seen`, and online status to each user in `tool_list_users`:

```json
{
    "users": [
        {
            "id": "amy",
            "display_name": "Amy",
            "user_type": "human",
            "last_seen": "2026-04-06T18:25:00Z",
            "online": true
        }
    ]
}
```

**Online logic:** `last_seen` within 5 minutes of current time.

### 4.6 Seed User Types

Update `_seed_users` in `server.py` to set `user_type = 'human'` for keith and amy. Future agent registration (Sprint 6+) will set `user_type = 'agent'`.

---

## 5. Web UI Changes

### 5.1 ACK Badges in Thread View

In `thread_view.html` and `message_list.html`, display ack_state badge on each message:

```html
{% if msg.ack_state and msg.ack_state != 'pending' %}
<span class="badge badge-xs
    {% if msg.ack_state == 'received' %}badge-info
    {% elif msg.ack_state == 'processing' %}badge-warning
    {% elif msg.ack_state == 'completed' %}badge-success
    {% elif msg.ack_state == 'failed' %}badge-error
    {% endif %}">{{ msg.ack_state }}</span>
{% endif %}
```

Placed in the `chat-footer` area next to the subject line.

### 5.2 Archive Button + Archive View

**Thread header** — add archive/unarchive button:
```html
<button hx-post="/web/conversation/{{ conversation.id }}/archive"
        hx-target="#main-content"
        class="btn btn-ghost btn-sm">
    {% if is_archived %}Unarchive{% else %}Archive{% endif %}
</button>
```

**Sidebar** — add "Show archived" toggle:
```html
<label class="label cursor-pointer gap-2">
    <span class="label-text text-xs">Show archived</span>
    <input type="checkbox" id="show-archived" class="toggle toggle-xs"
           onchange="refreshConversations()">
</label>
```

**Archived badge** on conversation list items:
```html
{% if conv.archived %}
<span class="badge badge-ghost badge-xs">archived</span>
{% endif %}
```

### 5.3 User Directory Page

New route: `GET /web/users` — lists all users with identity info.

New template: `src/ai_mailbox/templates/users.html`

```html
<div class="card bg-base-100 shadow">
    <div class="card-body">
        <h3 class="card-title">Users</h3>
        <div class="overflow-x-auto">
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th>User</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Last Seen</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user in users %}
                    <tr>
                        <td>{{ user.display_name }}</td>
                        <td>
                            {% if user.user_type == 'agent' %}
                            <span class="badge badge-info badge-sm">Agent</span>
                            {% else %}
                            <span class="badge badge-ghost badge-sm">Human</span>
                            {% endif %}
                        </td>
                        <td>
                            {% if user.online %}
                            <span class="badge badge-success badge-xs">online</span>
                            {% else %}
                            <span class="badge badge-ghost badge-xs">offline</span>
                            {% endif %}
                        </td>
                        <td>{{ user.last_seen | relative_time }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
```

**Navbar addition:** Add "Users" link between "Compose" and the display name.

### 5.4 Web Routes

New routes:
- `GET /web/users` — User directory page
- `POST /web/conversation/{conv_id}/archive` — Archive/unarchive (HTMX)

Modified routes:
- `GET /web/inbox/conversations` — Pass `include_archived` from checkbox state
- `GET /web/conversation/{conv_id}` — Pass `is_archived` flag to template

---

## 6. Tech Debt

### 6.1 Issue #9: CASCADE on User FKs

Migration 005 adds ON DELETE CASCADE to `messages.from_user` FK. The legacy `messages.to_user` column (unused since Sprint 1) also gets CASCADE.

**PostgreSQL only** (SQLite doesn't support ALTER CONSTRAINT):
```sql
-- Fix FK CASCADE on messages.from_user (issue #9)
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_from_user_fkey;
ALTER TABLE messages ADD CONSTRAINT messages_from_user_fkey
    FOREIGN KEY (from_user) REFERENCES users(id) ON DELETE CASCADE;
```

### 6.2 Issue #10: Narrow PostgresDB Retry

In `connection.py`, change all `except Exception:` blocks to catch only connection-level errors:

```python
import psycopg

try:
    return self._conn.execute(sql, params)
except (psycopg.OperationalError, psycopg.InterfaceError):
    self._connect()
    return self._conn.execute(sql, params)
```

This lets SQL errors (syntax, constraint violations) propagate immediately instead of triggering a reconnect.

### 6.3 Issue #11: OAuth FK Constraints

Migration 005 adds FK constraints to `oauth_codes.client_id` and `oauth_tokens.client_id`:

```sql
-- Add FK constraints on OAuth tables (issue #11)
-- PostgreSQL only (SQLite FKs defined at table creation)
DO $$ BEGIN
    ALTER TABLE oauth_codes ADD CONSTRAINT oauth_codes_client_fk
        FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_client_fk
        FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
```

---

## 7. Migration 005

New file: `src/ai_mailbox/db/migrations/005_ack_archive_identity.sql`

```sql
-- Sprint 5: Acknowledgment, archiving, agent identity, tech debt fixes

-- Acknowledgment state on messages
ALTER TABLE messages ADD COLUMN IF NOT EXISTS ack_state VARCHAR(20) DEFAULT 'pending';

-- Per-user conversation archiving
ALTER TABLE conversation_participants ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;

-- Agent identity fields on users
ALTER TABLE users ADD COLUMN IF NOT EXISTS user_type VARCHAR(20) DEFAULT 'human';
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_mode VARCHAR(20) DEFAULT 'persistent';
```

**PostgreSQL-only section** (separate file or guarded in schema.py):

```sql
-- Fix FK CASCADE on messages.from_user (issue #9)
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_from_user_fkey;
ALTER TABLE messages ADD CONSTRAINT messages_from_user_fkey
    FOREIGN KEY (from_user) REFERENCES users(id) ON DELETE CASCADE;

-- Add FK constraints on OAuth tables (issue #11)
DO $$ BEGIN
    ALTER TABLE oauth_codes ADD CONSTRAINT oauth_codes_client_fk
        FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_client_fk
        FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
```

**SQLite compatibility:** The ALTER TABLE ADD COLUMN statements work on SQLite. The FK constraint changes are PostgreSQL-only (guarded via `_PG_ONLY_MIGRATIONS` or inline detection). SQLite test schema in `conftest.py` and `test_web.py` must add the new columns.

---

## 8. Edge Cases

### 8.1 ACK on message in group conversation

Any participant except the message sender can acknowledge. In a 3-person group, both non-senders can ACK the same message. The `ack_state` reflects the most recent ACK (last-writer-wins). For alpha, this is acceptable. Per-user ACK tracking (a separate `message_acknowledgments` table) is deferred.

### 8.2 ACK state transition validation

`pending → received` is valid. `completed → processing` is not. `failed → completed` is not. The tool validates against a transition map:

```python
_VALID_TRANSITIONS = {
    "pending": {"received", "processing", "completed", "failed"},
    "received": {"processing", "completed", "failed"},
    "processing": {"completed", "failed"},
    "completed": set(),  # terminal
    "failed": set(),     # terminal
}
```

### 8.3 Archive + new message interaction

When User A archives a conversation and User B sends a new message, User A's `archived_at` is cleared by `insert_message`. The conversation reappears in User A's inbox. The sender's archive state is NOT cleared (they already know about the message since they sent it).

### 8.4 Archive + search

`search_messages` searches across ALL conversations (including archived). Search results include an `archived` flag so the caller knows the conversation's archive state.

### 8.5 last_seen staleness

`last_seen` is updated on every MCP tool call. Web UI sessions do NOT update `last_seen` (web users have their own session tracking). An agent that hasn't called any MCP tool in 5 minutes shows as offline. The threshold is a constant, not configurable.

### 8.6 user_type for existing users

Migration 005 sets `DEFAULT 'human'`. Existing users (keith, amy) get `user_type = 'human'` automatically. The `_seed_users` function in `server.py` does not need to set user_type explicitly since the default handles it.

### 8.7 SQLite ack_state column

SQLite has no VARCHAR constraint — any string can be stored. Validation happens at the tool level (Python), not the DB level. Same pattern as `content_type`.

### 8.8 Archived conversation polling

HTMX sidebar polling (`every 15s`) respects the "show archived" toggle. The `refreshConversations()` JavaScript function reads the checkbox state and passes `archived=true` or omits it.

---

## 9. File Changes Summary

### New files

| File | Purpose |
|---|---|
| `src/ai_mailbox/db/migrations/005_ack_archive_identity.sql` | ACK, archive, identity columns + FK fixes |
| `src/ai_mailbox/tools/acknowledge.py` | `acknowledge` MCP tool |
| `src/ai_mailbox/tools/archive.py` | `archive_conversation` MCP tool |
| `src/ai_mailbox/templates/users.html` | User directory page |
| `tests/test_acknowledge.py` | ACK tool + state transition tests |
| `tests/test_archive.py` | Archive tool + auto-unarchive tests |

### Modified files

| File | Changes |
|---|---|
| `src/ai_mailbox/db/schema.py` | Run migration 005, add to PG-only set for FK section |
| `src/ai_mailbox/db/queries.py` | `update_last_seen()`, `set_archive()`, `get_inbox` archive filter, auto-unarchive in `insert_message` |
| `src/ai_mailbox/db/connection.py` | Narrow `except Exception` to `except (OperationalError, InterfaceError)` (issue #10) |
| `src/ai_mailbox/errors.py` | Add `INVALID_STATE_TRANSITION` error code |
| `src/ai_mailbox/server.py` | Register `acknowledge` + `archive_conversation`, update `_get_user()` for last_seen |
| `src/ai_mailbox/tools/identity.py` | Add user_type, last_seen, session_mode to whoami |
| `src/ai_mailbox/tools/list_users.py` | Add user_type, last_seen, online status |
| `src/ai_mailbox/web.py` | User directory route, archive route, `is_ai_user` from DB, archive toggle in inbox |
| `src/ai_mailbox/templates/base.html` | Add "Users" link to navbar |
| `src/ai_mailbox/templates/inbox.html` | Add "Show archived" toggle |
| `src/ai_mailbox/templates/partials/thread_view.html` | ACK badges, archive button |
| `src/ai_mailbox/templates/partials/message_list.html` | ACK badges (matches thread_view) |
| `src/ai_mailbox/templates/partials/conversation_list.html` | Archived badge |
| `tests/conftest.py` | Add ack_state, archived_at, user_type, last_seen, session_mode to test schema |
| `tests/test_tools.py` | ACK integration, archive integration |
| `tests/test_web.py` | User directory, archive button, ACK badges, archive toggle |
| `tests/test_server.py` | New tool registration assertions |
| `tests/test_errors.py` | Add INVALID_STATE_TRANSITION to expected codes |

### Deleted files

None.

### Unchanged files

| File | Reason |
|---|---|
| `src/ai_mailbox/config.py` | No new config (online threshold is a constant) |
| `src/ai_mailbox/rate_limit.py` | ACK uses existing MCP_WRITE_LIMIT, archive uses MCP_WRITE_LIMIT |
| `src/ai_mailbox/markdown.py` | Unchanged |
| `src/ai_mailbox/group_tokens.py` | Unchanged |
| `src/ai_mailbox/token_cleanup.py` | Unchanged |
| `src/ai_mailbox/tools/send.py` | Unchanged (auto-unarchive is in queries.py) |
| `src/ai_mailbox/tools/search.py` | Unchanged (ack_state flows through SELECT m.*) |
| `Dockerfile` | No new system deps |
| `railway.toml` | Unchanged |

---

## 10. Acceptance Criteria

### 10.1 acknowledge MCP Tool

- [ ] `acknowledge(message_id, state="received")` sets ack_state on the message
- [ ] Only conversation participants (not message sender) can ACK
- [ ] Forward-only state transitions enforced (pending→received OK, completed→processing rejected)
- [ ] `INVALID_STATE_TRANSITION` error on invalid transition
- [ ] `PERMISSION_DENIED` on self-ACK attempt
- [ ] Response includes previous_state and new ack_state
- [ ] Rate limited (MCP_WRITE_LIMIT)

### 10.2 archive_conversation MCP Tool

- [ ] `archive_conversation(conversation_id)` archives for the calling user
- [ ] `archive_conversation(conversation_id, archive=False)` unarchives
- [ ] Only participants can archive their conversations
- [ ] Archive is idempotent (archiving already-archived returns success)
- [ ] Inbox excludes archived conversations by default
- [ ] `include_archived=True` shows archived conversations

### 10.3 Auto-Unarchive

- [ ] New message in archived conversation clears archive for recipients
- [ ] Sender's archive state preserved on send
- [ ] Auto-unarchived conversation appears in recipient's inbox

### 10.4 Agent Identity

- [ ] users.user_type defaults to 'human' for existing users
- [ ] `whoami` response includes user_type, last_seen, session_mode
- [ ] `list_users` response includes user_type, last_seen, online status
- [ ] `last_seen` updated on every MCP tool call
- [ ] Online = last_seen within 5 minutes of current time

### 10.5 Web UI: ACK Badges

- [ ] Messages with ack_state != pending show colored badge
- [ ] Badge colors: info (received), warning (processing), success (completed), error (failed)
- [ ] ACK badges appear in both thread view and polling partial

### 10.6 Web UI: Archive Management

- [ ] Archive button in thread header
- [ ] "Show archived" toggle in sidebar
- [ ] Archived conversations show "archived" badge
- [ ] Archive action via HTMX (no full page reload)

### 10.7 Web UI: User Directory

- [ ] `/web/users` shows all users in a table
- [ ] Table columns: User, Type (human/agent badge), Status (online/offline), Last Seen
- [ ] "Users" link in navbar
- [ ] Requires authentication

### 10.8 Tech Debt

- [ ] Issue #9: messages.from_user has ON DELETE CASCADE
- [ ] Issue #10: PostgresDB catches only OperationalError/InterfaceError
- [ ] Issue #11: oauth_codes and oauth_tokens have FK to oauth_clients with CASCADE

### 10.9 AI UX UAT (browser verification -- required gate)

- [ ] **ACK display:** View thread containing ACK'd messages, verify colored badges
- [ ] **Archive:** Click archive button, verify conversation disappears from inbox
- [ ] **Unarchive:** Toggle "Show archived", click unarchive, verify it reappears
- [ ] **User directory:** Navigate to /web/users, verify table with type + status
- [ ] **Auto-unarchive:** Archive a conversation, send a new message to it via MCP, verify it reappears

### 10.10 Tests

- [ ] test_acknowledge.py: state transitions, permissions, self-ACK rejection, terminal states
- [ ] test_archive.py: archive, unarchive, auto-unarchive, inbox filtering, idempotency
- [ ] test_tools.py additions: ACK + archive integration scenarios
- [ ] test_web.py additions: user directory, archive button, ACK badges, archive toggle
- [ ] test_server.py additions: acknowledge + archive_conversation registration
- [ ] test_errors.py: INVALID_STATE_TRANSITION in expected codes
- [ ] conftest.py: updated schema with new columns
- [ ] Total test count >= 410 (up from 372)

### 10.11 Deployment

- [ ] Migration 005 runs on PostgreSQL staging
- [ ] FK constraints applied (issues #9, #11)
- [ ] ACK badges visible on deployed environment
- [ ] Archive management functional on deployed environment
- [ ] User directory accessible on deployed environment

### 10.12 GitHub

- [ ] Issue #9 closed with commit reference
- [ ] Issue #10 closed with commit reference
- [ ] Issue #11 closed with commit reference

---

## 11. Implementation Order (TDD Through Delivery)

1. **Error codes + ACK state transitions** -- `errors.py` + `acknowledge.py` + tests
   - RED: tests for INVALID_STATE_TRANSITION error, ACK tool validation (self-ACK, invalid state, terminal states)
   - GREEN: add error code, implement transition map, tool logic
   - VERIFY: tests pass
   - **Files created:** `src/ai_mailbox/tools/acknowledge.py`, `tests/test_acknowledge.py`
   - **Files modified:** `src/ai_mailbox/errors.py`, `tests/test_errors.py`

2. **Migration 005 + schema** -- `005_ack_archive_identity.sql` + `schema.py` + `conftest.py`
   - RED: tests for new columns (ack_state on messages, archived_at on participants, user fields)
   - GREEN: create migration, update schema runner, update test fixtures
   - VERIFY: tests pass
   - **Files created:** `src/ai_mailbox/db/migrations/005_ack_archive_identity.sql`
   - **Files modified:** `src/ai_mailbox/db/schema.py`, `tests/conftest.py`, `tests/test_web.py` (schema fixture)

3. **Archive tool + queries** -- `archive.py` + `queries.py` + tests
   - RED: tests for archive, unarchive, idempotency, inbox filtering, auto-unarchive
   - GREEN: implement set_archive query, modify get_inbox, auto-unarchive in insert_message, tool logic
   - VERIFY: tests pass
   - **Files created:** `src/ai_mailbox/tools/archive.py`, `tests/test_archive.py`
   - **Files modified:** `src/ai_mailbox/db/queries.py`

4. **Agent identity + last_seen** -- `queries.py` + `identity.py` + `list_users.py` + tests
   - RED: tests for update_last_seen, whoami with new fields, list_users with online status
   - GREEN: implement update_last_seen, enhance whoami/list_users responses
   - VERIFY: tests pass
   - **Files modified:** `src/ai_mailbox/db/queries.py`, `src/ai_mailbox/tools/identity.py`, `src/ai_mailbox/tools/list_users.py`, `tests/test_tools.py`

5. **Tech debt: PostgresDB retry + FK constraints** -- `connection.py` + tests
   - RED: tests that SQL errors propagate (not retried)
   - GREEN: narrow except clause to OperationalError/InterfaceError
   - VERIFY: tests pass (FK constraints verified on PostgreSQL only -- migration handles it)
   - **Files modified:** `src/ai_mailbox/db/connection.py`

6. **Server integration** -- `server.py` + `test_server.py`
   - RED: tests for new tool registration, last_seen in _get_user
   - GREEN: register acknowledge + archive_conversation, update _get_user
   - VERIFY: tests pass
   - **Files modified:** `src/ai_mailbox/server.py`, `tests/test_server.py`

7. **Web UI: ACK badges + archive + user directory** -- templates + `web.py` + tests
   - RED: tests for ACK badge rendering, archive button, user directory page, archive toggle
   - GREEN: add badges to thread_view + message_list, archive button, users.html, web routes
   - VERIFY: tests pass
   - **Files created:** `src/ai_mailbox/templates/users.html`
   - **Files modified:** `src/ai_mailbox/web.py`, `src/ai_mailbox/templates/base.html`, `src/ai_mailbox/templates/inbox.html`, `src/ai_mailbox/templates/partials/thread_view.html`, `src/ai_mailbox/templates/partials/message_list.html`, `src/ai_mailbox/templates/partials/conversation_list.html`, `tests/test_web.py`

8. **Full test suite + integration verification**
   - RED: any remaining integration tests
   - GREEN: wire remaining pieces
   - VERIFY: full suite green (410+ tests)

9. **Deploy to MVP 1 Staging**
   - VERIFY: migration 005 runs, ACK works, archive works, user directory renders

10. **AI UX UAT** (required gate)
    - Browser verification of section 10.9

11. **Human UAT** (required gate) + **GitHub cleanup** -- close #9, #10, #11

---

## 12. Dependency Changes

No new Python dependencies. All features use existing libraries (FastMCP, psycopg, Jinja2, HTMX).

---

## 13. Resolved Design Decisions

1. **Per-user archiving over conversation-level archiving.** A shared archive flag would force all participants to see/not see the conversation. Per-user archive (on `conversation_participants`) lets each user manage their own inbox independently. This is the pattern used by Gmail, Slack, and every modern messaging system.

2. **Last-writer-wins for ACK state (not per-user ACK).** A separate `message_acknowledgments` join table would support per-user ACK tracking in group conversations, but adds significant complexity for alpha. Since the primary use case is 1:1 agent-to-agent communication, a single `ack_state` on the message is sufficient. Deferred to Sprint 7+ if group ACK tracking becomes needed.

3. **ACK via MCP tool only (no web UI ACK button).** Acknowledgments are an agent protocol feature — agents programmatically ACK messages they've processed. The web UI displays ACK state but doesn't provide a manual ACK button. Humans have read-tracking (mark_read) which serves the equivalent purpose.

4. **Online threshold as constant (5 minutes), not configurable.** Adding a config variable for a single threshold adds complexity without benefit. If the threshold needs tuning, it's a one-line code change. Environment-variable-driven configuration is reserved for values that differ between environments.

5. **auto-unarchive clears for recipients only.** When you send a message to an archived conversation, your own archive state should remain unchanged (you already know about the message). Only recipients need the conversation resurfaced.

6. **user_type on users table (not conversation_participants).** User type is an identity attribute, not a per-conversation role. An agent is always an agent regardless of which conversation it's in. This also simplifies the user directory query.

7. **PostgresDB retry narrowed to OperationalError/InterfaceError.** These represent connection-level failures (network timeout, server restart) that benefit from reconnect-and-retry. SQL errors (syntax, constraint violations, permission denied) should propagate immediately for debugging. The current broad `except Exception` masks real bugs.
