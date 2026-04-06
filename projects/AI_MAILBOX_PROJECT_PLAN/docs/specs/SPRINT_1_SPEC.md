# Sprint 1 Spec: Schema Foundation + Error Framework

**Status:** APPROVED -- 2026-04-05
**Branch:** mvp-1-staging
**Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
**GitHub Issues:** #5 (conversation model), #7 (structured errors), #8 (read tracking)

---

## 1. Overview

Restructure the flat messages table into a three-table conversation model that supports 1:1 messaging, project-scoped groups, and team-based groups. Add cursor-based read tracking, message sequence numbers, idempotency keys, and a structured error framework. Scaffold the web UI with Jinja2 + HTMX + Tailwind.

All existing MCP tools continue to function with the same signatures. The underlying storage changes are transparent to MCP clients. Error responses gain structure but remain backward-compatible (the `error` key still exists for tools that check it as a string).

---

## 2. Schema DDL (Migration 003)

### 2.1 conversations

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY,
    type            VARCHAR(20) NOT NULL DEFAULT 'direct'
                        CHECK (type IN ('direct', 'project_group', 'team_group')),
    project         VARCHAR(128),
    name            VARCHAR(256),
    created_by      VARCHAR(64) NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Fast lookup for find-or-create direct conversations between two users in a project
CREATE INDEX IF NOT EXISTS idx_conv_type_project ON conversations(type, project);

-- Fast lookup for team groups by name
CREATE INDEX IF NOT EXISTS idx_conv_name ON conversations(name) WHERE type = 'team_group';
```

**Column semantics:**

| Column | Purpose |
|---|---|
| `type` | `direct` = 1:1 between exactly two users. `project_group` = all messages in a project go here, any number of participants. `team_group` = named persistent group, any number of participants. |
| `project` | For `direct` and `project_group`: the project context. NULL for `team_group` unless explicitly scoped. |
| `name` | Human-readable name. Required for `team_group`. Optional for `project_group` (defaults to project name). NULL for `direct`. |
| `created_by` | User who initiated the conversation or group. |
| `updated_at` | Timestamp of the last message inserted. Used for conversation ordering in inbox. |

**Uniqueness constraints:**

- For `direct` conversations: enforced at application layer -- at most one `direct` conversation per ordered user pair per project. A unique index is not practical on the conversations table alone because the user pair lives in `conversation_participants`. The application uses a find-or-create pattern with a SELECT before INSERT.
- For `project_group`: at most one per project value. Enforced by unique index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_project_group
    ON conversations(project) WHERE type = 'project_group';
```

- For `team_group`: names are unique per creator (no index -- low cardinality, enforced at app layer).

### 2.2 conversation_participants

```sql
CREATE TABLE IF NOT EXISTS conversation_participants (
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id             VARCHAR(64) NOT NULL REFERENCES users(id),
    joined_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_read_sequence  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (conversation_id, user_id)
);

-- Find all conversations for a user (inbox query)
CREATE INDEX IF NOT EXISTS idx_cp_user ON conversation_participants(user_id);
```

**Column semantics:**

| Column | Purpose |
|---|---|
| `last_read_sequence` | Cursor-based read tracking. Messages with `sequence_number <= last_read_sequence` are considered read by this participant. Advancing this cursor is an explicit action (auto-advanced in Sprint 1 for backward compatibility with `check_messages`, split into explicit `mark_read` in Sprint 2). |

### 2.3 messages (restructured)

```sql
CREATE TABLE IF NOT EXISTS messages (
    id                  UUID PRIMARY KEY,
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    from_user           VARCHAR(64) NOT NULL REFERENCES users(id),
    sequence_number     BIGINT NOT NULL,
    subject             VARCHAR(256),
    body                TEXT NOT NULL,
    content_type        VARCHAR(64) NOT NULL DEFAULT 'text/plain',
    idempotency_key     VARCHAR(256),
    reply_to            UUID REFERENCES messages(id),
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Each conversation has unique sequence numbers
    UNIQUE (conversation_id, sequence_number),

    -- Idempotency: one key per conversation prevents duplicate sends
    UNIQUE (conversation_id, idempotency_key)
);

-- Inbox: fetch latest messages per conversation for a user
CREATE INDEX IF NOT EXISTS idx_msg_conv_seq ON messages(conversation_id, sequence_number);

-- Thread traversal within a conversation
CREATE INDEX IF NOT EXISTS idx_msg_reply ON messages(reply_to) WHERE reply_to IS NOT NULL;

-- Chronological ordering fallback
CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at);
```

**Columns removed from current schema:**
- `to_user` -- recipients are now implicit via `conversation_participants`
- `read` -- replaced by `conversation_participants.last_read_sequence`
- `project` -- lives on `conversations.project`, not individual messages

**Columns added:**
- `conversation_id` -- FK to conversations
- `sequence_number` -- monotonically increasing per conversation, assigned at insert time
- `content_type` -- future-proofs for JSON payloads (Sprint 4)
- `idempotency_key` -- prevents duplicate sends from network retries

### 2.4 Dropped objects

```sql
-- Old indexes on the flat messages table (replaced by new indexes)
DROP INDEX IF EXISTS idx_msg_inbox;
DROP INDEX IF EXISTS idx_msg_thread;
```

The old `messages` table columns (`to_user`, `read`, `project`) are dropped during the ALTER step of the migration. See section 6 for the full migration procedure.

### 2.5 Sequence number assignment

Sequence numbers are assigned at INSERT time using a subquery:

```sql
INSERT INTO messages (id, conversation_id, from_user, sequence_number, subject, body, content_type, idempotency_key, reply_to, created_at)
VALUES (
    %(id)s,
    %(conversation_id)s,
    %(from_user)s,
    COALESCE((SELECT MAX(sequence_number) FROM messages WHERE conversation_id = %(conversation_id)s), 0) + 1,
    %(subject)s,
    %(body)s,
    %(content_type)s,
    %(idempotency_key)s,
    %(reply_to)s,
    %(created_at)s
)
RETURNING sequence_number;
```

For SQLite compatibility in tests, the same pattern works with a subquery. Concurrent inserts on PostgreSQL are safe because the UNIQUE(conversation_id, sequence_number) constraint will cause one of two concurrent inserts to fail and retry. The retry logic is in the application layer (max 3 attempts).

---

## 3. Structured Error Framework

### 3.1 Error response shape

All MCP tools return errors in this format:

```json
{
    "error": {
        "code": "RECIPIENT_NOT_FOUND",
        "message": "User 'bob' does not exist",
        "param": "to",
        "retryable": false
    }
}
```

**Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | Machine-readable error code (UPPER_SNAKE_CASE) |
| `message` | string | yes | Human-readable description |
| `param` | string | no | Which input parameter caused the error (null for non-validation errors) |
| `retryable` | boolean | yes | Whether the client should retry the request |

### 3.2 Error codes

| Code | HTTP-equiv | Retryable | When |
|---|---|---|---|
| `VALIDATION_ERROR` | 400 | no | Missing or malformed required parameter |
| `EMPTY_BODY` | 400 | no | Message body is empty or whitespace-only |
| `SELF_SEND` | 400 | no | Sender and recipient are the same user |
| `RECIPIENT_NOT_FOUND` | 404 | no | Target user does not exist |
| `MESSAGE_NOT_FOUND` | 404 | no | Message ID does not exist |
| `CONVERSATION_NOT_FOUND` | 404 | no | Conversation ID does not exist |
| `PERMISSION_DENIED` | 403 | no | User is not a participant in the conversation |
| `DUPLICATE_MESSAGE` | 409 | no | Idempotency key already used in this conversation |
| `SEQUENCE_CONFLICT` | 409 | yes | Concurrent insert caused sequence collision (client should retry) |
| `INTERNAL_ERROR` | 500 | yes | Unexpected server error |

### 3.3 Error helper

A single `make_error(code, message, param=None, retryable=False)` function in a new `src/ai_mailbox/errors.py` module. All tools use this instead of ad-hoc `{"error": "string"}` dicts.

```python
# src/ai_mailbox/errors.py

ERROR_CODES = {
    "VALIDATION_ERROR":       {"retryable": False},
    "EMPTY_BODY":             {"retryable": False},
    "SELF_SEND":              {"retryable": False},
    "RECIPIENT_NOT_FOUND":    {"retryable": False},
    "MESSAGE_NOT_FOUND":      {"retryable": False},
    "CONVERSATION_NOT_FOUND": {"retryable": False},
    "PERMISSION_DENIED":      {"retryable": False},
    "DUPLICATE_MESSAGE":      {"retryable": False},
    "SEQUENCE_CONFLICT":      {"retryable": True},
    "INTERNAL_ERROR":         {"retryable": True},
}

def make_error(code: str, message: str, param: str | None = None) -> dict:
    """Create structured error response."""
    retryable = ERROR_CODES.get(code, {}).get("retryable", False)
    error = {"code": code, "message": message, "retryable": retryable}
    if param is not None:
        error["param"] = param
    return {"error": error}

def is_error(result: dict) -> bool:
    """Check if a tool result is an error."""
    return "error" in result and isinstance(result["error"], dict)
```

### 3.4 Backward compatibility

The error dict is nested under `"error"` key, same as today. Clients that check `if "error" in result` continue to work. Clients that read `result["error"]` as a string will now get a dict -- this is a **breaking change** for naive string consumers. MCP clients (Claude Desktop) treat tool results as opaque dicts and display them, so this is safe. The `message` field within the error dict provides the human-readable string.

---

## 4. Query Layer Changes

All functions in `src/ai_mailbox/db/queries.py` are rewritten for the new schema. The module is renamed to `src/ai_mailbox/db/queries.py` (same path, new implementation).

### 4.1 New functions

```python
# Conversation management
def find_or_create_direct_conversation(db, user_a: str, user_b: str, project: str) -> str:
    """Find existing direct conversation or create one. Returns conversation_id."""

def find_or_create_project_group(db, project: str, created_by: str) -> str:
    """Find existing project group or create one. Returns conversation_id."""

def create_team_group(db, name: str, created_by: str, member_ids: list[str]) -> str:
    """Create a new team group. Returns conversation_id."""

def add_participant(db, conversation_id: str, user_id: str) -> None:
    """Add a user to a conversation. Idempotent."""

def get_conversation(db, conversation_id: str) -> dict | None:
    """Fetch conversation metadata."""

def get_conversation_participants(db, conversation_id: str) -> list[str]:
    """Return list of user_ids in a conversation."""

# Message operations
def insert_message(db, conversation_id: str, from_user: str, body: str,
                   subject: str | None = None, reply_to: str | None = None,
                   idempotency_key: str | None = None,
                   content_type: str = "text/plain") -> dict:
    """Insert message, assign sequence number. Returns {id, sequence_number}."""

def get_message(db, message_id: str) -> dict | None:
    """Fetch single message by ID, including conversation_id."""

def get_conversation_messages(db, conversation_id: str,
                               after_sequence: int = 0,
                               limit: int = 100) -> list[dict]:
    """Fetch messages in a conversation after a sequence number. Ordered by sequence_number ASC."""

# Read tracking
def get_last_read_sequence(db, conversation_id: str, user_id: str) -> int:
    """Get user's read cursor for a conversation."""

def advance_read_cursor(db, conversation_id: str, user_id: str, sequence: int) -> None:
    """Advance user's read cursor. Only moves forward, never backward."""

# Inbox
def get_inbox(db, user_id: str, project: str | None = None) -> list[dict]:
    """Return conversations for a user with unread counts and last message preview.
    Each entry: {conversation_id, type, project, name, last_message_preview,
                 last_message_at, unread_count, participant_ids}
    Ordered by last_message_at DESC (most recent first)."""

def get_unread_counts(db, user_id: str) -> dict[str, int]:
    """Return unread message count per project for a user.
    Computed from: messages.sequence_number > participant.last_read_sequence."""

# Thread (within conversation)
def get_thread(db, message_id: str) -> list[dict]:
    """Get all messages in the conversation containing message_id.
    Ordered by sequence_number ASC."""

# User queries (unchanged interface)
def get_user(db, user_id: str) -> dict | None:
    """Fetch user by ID."""

def get_all_users(db) -> list[dict]:
    """Fetch all users."""
```

### 4.2 find_or_create_direct_conversation algorithm

```
1. Normalize user pair: user_a, user_b = sorted([sender, recipient])
2. SELECT c.id FROM conversations c
   JOIN conversation_participants cp1 ON c.id = cp1.conversation_id AND cp1.user_id = user_a
   JOIN conversation_participants cp2 ON c.id = cp2.conversation_id AND cp2.user_id = user_b
   WHERE c.type = 'direct' AND c.project = project
3. If found: return c.id
4. If not found:
   a. INSERT INTO conversations (id, type, project, created_by) VALUES (uuid, 'direct', project, sender)
   b. INSERT INTO conversation_participants (conversation_id, user_id) for both users
   c. Return conversation_id
```

### 4.3 Sequence number retry logic

```python
MAX_SEQUENCE_RETRIES = 3

def insert_message(db, conversation_id, from_user, body, ...):
    for attempt in range(MAX_SEQUENCE_RETRIES):
        try:
            # INSERT with subquery for next sequence number
            result = db.fetchone(INSERT_SQL, params)
            db.commit()
            # Update conversations.updated_at
            db.execute(UPDATE_CONV_SQL, [now, conversation_id])
            db.commit()
            return {"id": msg_id, "sequence_number": result["sequence_number"]}
        except UniqueViolation:  # psycopg.errors.UniqueViolation
            if attempt == MAX_SEQUENCE_RETRIES - 1:
                return make_error("SEQUENCE_CONFLICT", "concurrent insert, retry exhausted")
            continue
```

---

## 5. MCP Tool Mapping (Sprint 1)

Tool signatures do not change in Sprint 1. The internal implementation changes to use the new schema.

### 5.1 send_message(to, body, project, subject)

**Current:** Inserts into flat messages table with from_user, to_user.
**New:**
1. Validate inputs (body not empty, to != sender, recipient exists)
2. `find_or_create_direct_conversation(sender, to, project)`
3. `insert_message(conversation_id, sender, body, subject=subject)`
4. Return `{message_id, from_user, to_user, project}` (same shape as today)

### 5.2 check_messages(project, unread_only)

**Current:** Queries messages WHERE to_user=user, marks read.
**New:**
1. Get all conversations where user is a participant
2. For each conversation (optionally filtered by project):
   - Get messages with sequence_number > last_read_sequence (if unread_only)
   - Or get all messages (if not unread_only)
3. Auto-advance last_read_sequence to max sequence_number returned (backward compat)
4. Return `{user, message_count, messages[]}` (same shape)
5. Each message dict includes `to_user` field derived from the other participant(s) for backward compat

### 5.3 reply_to_message(message_id, body)

**Current:** Validates user is to_user on original message, swaps sender/recipient.
**New:**
1. `get_message(message_id)` -- find the message and its conversation_id
2. Validate user is a participant in that conversation
3. `insert_message(conversation_id, sender, body, reply_to=message_id)`
4. Inherit subject from original message
5. Determine `to_user` for response: in direct conversations, it's the other participant. In groups, it's the original sender (for backward compat).
6. Return `{message_id, from_user, to_user, project}` (same shape)

**Behavioral change:** In the current system, only the `to_user` of the original message can reply. In the new system, any participant in the conversation can reply. This is intentional -- it enables group conversations.

### 5.4 get_thread(message_id)

**Current:** Walks reply_to chain to root, then BFS collects descendants.
**New:**
1. `get_message(message_id)` -- find conversation_id
2. Validate user is a participant
3. `get_conversation_messages(conversation_id)` -- all messages ordered by sequence_number
4. Return `{root_message_id, message_count, messages[]}` where root_message_id is the message with sequence_number=1

### 5.5 whoami()

**Current:** Returns user info, other users, unread counts.
**New:** Identical behavior. `get_unread_counts(user_id)` now computed from sequence cursors instead of boolean flags.

---

## 6. Data Migration (003_conversation_model.sql)

The migration runs as part of `ensure_schema_postgres()`. It must be:
- Idempotent (safe to re-run)
- Non-destructive (old data preserved until verified)
- Backward-compatible during transition (no downtime)

### 6.1 Migration steps

```sql
-- Step 1: Create new tables (IF NOT EXISTS makes this idempotent)
-- [conversations, conversation_participants tables from section 2]

-- Step 2: Add new columns to messages (IF NOT EXISTS for idempotency)
ALTER TABLE messages ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sequence_number BIGINT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS content_type VARCHAR(64) NOT NULL DEFAULT 'text/plain';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(256);

-- Step 3: Migrate data -- create conversations from existing messages
-- For each unique (sorted user pair, project), create a direct conversation
INSERT INTO conversations (id, type, project, created_by, created_at, updated_at)
SELECT
    gen_random_uuid(),
    'direct',
    m.project,
    m.from_user,
    MIN(m.created_at),
    MAX(m.created_at)
FROM messages m
WHERE m.conversation_id IS NULL
GROUP BY
    LEAST(m.from_user, m.to_user),
    GREATEST(m.from_user, m.to_user),
    m.project
ON CONFLICT DO NOTHING;

-- Step 4: Link messages to conversations
-- This uses a correlated update to match each message to its conversation
UPDATE messages m
SET conversation_id = c.id
FROM conversations c
JOIN conversation_participants cp1 ON c.id = cp1.conversation_id
JOIN conversation_participants cp2 ON c.id = cp2.conversation_id
WHERE c.type = 'direct'
  AND c.project = m.project
  AND cp1.user_id = LEAST(m.from_user, m.to_user)
  AND cp2.user_id = GREATEST(m.from_user, m.to_user)
  AND m.conversation_id IS NULL;

-- (Step 4 depends on participants existing, so step 3b inserts participants first)

-- Step 3b: Create participants for each conversation
-- After creating conversations, we need to add participants before step 4
-- This is handled procedurally in the migration script (see below)

-- Step 5: Assign sequence numbers within each conversation by created_at order
WITH numbered AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY created_at) AS seq
    FROM messages
    WHERE conversation_id IS NOT NULL AND sequence_number IS NULL
)
UPDATE messages SET sequence_number = numbered.seq
FROM numbered WHERE messages.id = numbered.id;

-- Step 6: Set last_read_sequence for each participant
-- All existing messages were either read or unread. For migrated data,
-- set last_read_sequence to the max sequence of messages the user has "read"
-- Since the old schema tracked read per-message, we find the highest sequence
-- of a read message for each participant in each conversation.
UPDATE conversation_participants cp
SET last_read_sequence = COALESCE(
    (SELECT MAX(m.sequence_number)
     FROM messages m
     JOIN messages_old_read_state mrs ON m.id = mrs.id
     WHERE m.conversation_id = cp.conversation_id
       AND mrs.to_user = cp.user_id
       AND mrs.read = TRUE),
    0
);
-- Note: messages_old_read_state is a temp table preserving old read/to_user before column drops

-- Step 7: Add NOT NULL constraints and new indexes after data is populated
ALTER TABLE messages ALTER COLUMN conversation_id SET NOT NULL;
ALTER TABLE messages ALTER COLUMN sequence_number SET NOT NULL;

-- Step 8: Create new indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_conv_seq ON messages(conversation_id, sequence_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_idempotency ON messages(conversation_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_msg_reply ON messages(reply_to) WHERE reply_to IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at);

-- Step 9: Drop old columns and indexes (after verification)
DROP INDEX IF EXISTS idx_msg_inbox;
DROP INDEX IF EXISTS idx_msg_thread;
ALTER TABLE messages DROP COLUMN IF EXISTS to_user;
ALTER TABLE messages DROP COLUMN IF EXISTS read;
ALTER TABLE messages DROP COLUMN IF EXISTS project;
```

### 6.2 Migration implementation

Because the migration involves procedural logic (creating participants from message pairs), it will be implemented as a Python function called from `ensure_schema_postgres()`, not as a single SQL file. The SQL file `003_conversation_model.sql` will contain the DDL (CREATE TABLE, CREATE INDEX). The data migration logic will be in `src/ai_mailbox/db/migrations/migrate_003.py`.

### 6.3 SQLite compatibility

For testing, `ensure_schema_sqlite()` will:
1. Create the new tables
2. Create a new `messages` table with the new schema (SQLite does not support DROP COLUMN before 3.35)
3. Skip data migration (tests create fresh data)

The test `conftest.py` fixture creates the new schema directly without migration.

---

## 7. Web UI Scaffold

### 7.1 Technology

- **Jinja2** for server-side templates
- **HTMX** for dynamic updates without full page reloads
- **Tailwind CSS** via CDN (no build step in Sprint 1)
- **Session cookies** for web authentication (JWT stored in httpOnly cookie)

### 7.2 Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/web/login` | no | Login form |
| POST | `/web/login` | no | Authenticate, set session cookie, redirect to inbox |
| GET | `/web/logout` | yes | Clear session cookie, redirect to login |
| GET | `/web/inbox` | yes | Conversation list with unread counts |
| GET | `/web/health` | no | System health dashboard |

### 7.3 Templates

```
src/ai_mailbox/templates/
    base.html          -- Tailwind CDN, nav bar, HTMX script tag
    login.html         -- Username/password form
    inbox.html         -- Conversation list (empty state in Sprint 1)
    health.html        -- Health metrics display
    _nav.html          -- Navigation partial (included in base)
```

### 7.4 Login flow

1. User visits `/web/login`
2. Enters username + password
3. POST `/web/login` validates credentials via `authenticate_user()`
4. On success: creates JWT, sets `session` cookie (httpOnly, SameSite=Lax, path=/web), redirects to `/web/inbox`
5. On failure: re-renders login form with error message

### 7.5 Session middleware

A Starlette middleware on `/web/*` routes:
1. Reads `session` cookie
2. Decodes JWT, extracts user_id
3. If valid: sets user context, proceeds
4. If missing/expired: redirects to `/web/login`

### 7.6 Inbox page (Sprint 1 scope)

Sprint 1 inbox is read-only. It displays:
- User's display name in nav
- List of conversations (conversation type icon, project, participant names, last message preview, unread count badge, last activity timestamp)
- Empty state: "No conversations yet" with a muted explanation

No compose, no thread view, no reply form in Sprint 1. Those come in Sprint 2-3.

### 7.7 Health page

Public page showing:
- Server status (healthy/unhealthy)
- Version
- User count
- Database connectivity
- Uptime (if available)

---

## 8. Edge Cases

### 8.1 Concurrent sequence number assignment

Two users send messages to the same conversation simultaneously. The UNIQUE(conversation_id, sequence_number) constraint prevents duplicates. The application retries up to 3 times on UniqueViolation. If all retries fail, return `SEQUENCE_CONFLICT` error.

### 8.2 Idempotency key collision

A client sends the same idempotency_key twice for the same conversation. The UNIQUE(conversation_id, idempotency_key) constraint catches this. Return `DUPLICATE_MESSAGE` error with the existing message_id in the response.

### 8.3 User sends to nonexistent user

Unchanged from current behavior. Return `RECIPIENT_NOT_FOUND` error with structured format.

### 8.4 User sends to self

Unchanged from current behavior. Return `SELF_SEND` error with structured format.

### 8.5 Empty inbox

`check_messages` returns `{user, message_count: 0, messages: []}`. No error.

### 8.6 Reply to message in conversation user is not part of

`get_message` finds the message, but the user is not in `conversation_participants`. Return `PERMISSION_DENIED`.

### 8.7 Read cursor cannot go backward

`advance_read_cursor` uses `UPDATE ... SET last_read_sequence = GREATEST(last_read_sequence, %(new_seq)s)`. A stale client sending an old sequence number has no effect.

### 8.8 Migration with zero messages

If the database has users but no messages, the migration creates no conversations. This is correct -- conversations are created on first message.

### 8.9 Migration with orphaned reply_to chains

If a message has `reply_to` pointing to a message in a different (user_pair, project) group, the reply_to FK is preserved but the messages end up in different conversations. This is acceptable for migration -- the original data model allowed cross-conversation reply_to, and the new model preserves the FK without enforcing same-conversation.

### 8.10 Group conversation participant leaves

Not in Sprint 1 scope. Participants are only added, never removed. Future sprint will add `remove_participant`.

---

## 9. File Changes Summary

### New files

| File | Purpose |
|---|---|
| `src/ai_mailbox/errors.py` | `make_error()`, error code registry |
| `src/ai_mailbox/db/migrations/003_conversation_model.sql` | DDL for new tables |
| `src/ai_mailbox/db/migrations/migrate_003.py` | Python data migration logic |
| `src/ai_mailbox/web.py` | Web routes, session middleware, template rendering |
| `src/ai_mailbox/templates/base.html` | Base template with Tailwind + HTMX |
| `src/ai_mailbox/templates/login.html` | Login form |
| `src/ai_mailbox/templates/inbox.html` | Inbox page |
| `src/ai_mailbox/templates/health.html` | Health page |
| `src/ai_mailbox/templates/_nav.html` | Navigation partial |
| `tests/test_errors.py` | Error framework tests |
| `tests/test_migration.py` | Migration logic tests |
| `tests/test_web.py` | Web route tests |

### Modified files

| File | Changes |
|---|---|
| `src/ai_mailbox/db/queries.py` | Complete rewrite for new schema |
| `src/ai_mailbox/db/schema.py` | Add migration 003 handling, update `ensure_schema_sqlite()` |
| `src/ai_mailbox/tools/send.py` | Use `find_or_create_direct_conversation` + `insert_message` + structured errors |
| `src/ai_mailbox/tools/inbox.py` | Use conversation-based inbox query + structured errors |
| `src/ai_mailbox/tools/reply.py` | Use conversation-based reply + any-participant-can-reply + structured errors |
| `src/ai_mailbox/tools/thread.py` | Use `get_conversation_messages` + structured errors |
| `src/ai_mailbox/tools/identity.py` | Use new `get_unread_counts` + structured errors |
| `src/ai_mailbox/server.py` | Mount web routes, update DB setup for new schema |
| `tests/conftest.py` | New schema in SQLite fixture |
| `tests/test_queries.py` | Rewrite for new query functions |
| `tests/test_tools.py` | Update assertions for structured error format |
| `tests/test_server.py` | Add web route tests |

### Unchanged files

| File | Reason |
|---|---|
| `src/ai_mailbox/config.py` | No new env vars in Sprint 1 |
| `src/ai_mailbox/oauth.py` | OAuth flow unchanged |
| `src/ai_mailbox/__main__.py` | Entry point unchanged |
| `Dockerfile` | No new system dependencies |
| `railway.toml` | Health check path unchanged |

---

## 10. Acceptance Criteria

All criteria must be verified by running tests and/or inspecting the deployed MVP 1 Staging environment.

### 10.1 Schema

- [ ] Migration 003 applies cleanly to a fresh PostgreSQL database
- [ ] Migration 003 applies cleanly to a database with existing Sprint 0 data (users + messages)
- [ ] `conversations`, `conversation_participants`, `messages` tables exist with correct columns and constraints
- [ ] Old `to_user`, `read`, `project` columns removed from `messages`
- [ ] Old `idx_msg_inbox`, `idx_msg_thread` indexes removed
- [ ] New indexes exist and are used by query plans

### 10.2 Data migration

- [ ] Existing messages are grouped into direct conversations by (user pair, project)
- [ ] Each migrated message has a valid conversation_id and sequence_number
- [ ] Sequence numbers within each conversation are contiguous starting from 1
- [ ] reply_to FKs are preserved
- [ ] Participant read cursors reflect pre-migration read state (read messages have sequence <= cursor)

### 10.3 MCP tools

- [ ] `send_message("amy", "hello", "general")` creates a direct conversation and returns `{message_id, from_user, to_user, project}`
- [ ] Sending again to the same user+project reuses the existing conversation
- [ ] `check_messages()` returns messages across all conversations, advances read cursors
- [ ] `check_messages(project="general")` filters to conversations in that project
- [ ] `reply_to_message(msg_id, "reply")` inserts into the correct conversation, any participant can reply
- [ ] `get_thread(msg_id)` returns all messages in the conversation ordered by sequence_number
- [ ] `whoami()` returns unread counts computed from sequence cursors
- [ ] All error responses use structured format `{error: {code, message, retryable}}`

### 10.4 Error framework

- [ ] `make_error()` produces correct structure for all defined error codes
- [ ] `is_error()` correctly identifies error responses
- [ ] Send to nonexistent user returns `RECIPIENT_NOT_FOUND` with `param: "to"`
- [ ] Send to self returns `SELF_SEND`
- [ ] Empty body returns `EMPTY_BODY` with `param: "body"`
- [ ] Reply to nonexistent message returns `MESSAGE_NOT_FOUND`
- [ ] Access to non-participant conversation returns `PERMISSION_DENIED`
- [ ] Duplicate idempotency key returns `DUPLICATE_MESSAGE`

### 10.5 Web UI (automated tests)

- [ ] `/web/login` renders a styled login form (Tailwind)
- [ ] POST `/web/login` with valid credentials sets session cookie and redirects to `/web/inbox`
- [ ] POST `/web/login` with invalid credentials shows error on login page
- [ ] `/web/inbox` requires authentication (redirects to login if no session)
- [ ] `/web/inbox` displays conversation list with unread counts (or empty state)
- [ ] `/web/logout` clears session and redirects to login
- [ ] `/web/health` shows server status publicly
- [ ] All pages use consistent Tailwind styling and nav bar
- [ ] HTMX script tag is loaded (used in future sprints)

### 10.5b AI UX UAT (browser verification -- required gate)

Claude performs browser-based UAT against the running MVP 1 Staging environment using preview tools. This is a required gate -- the sprint is not complete until AI UAT passes.

- [ ] **Login flow:** Navigate to `/web/login`, verify form renders with username/password fields and submit button. Enter valid credentials, submit, verify redirect to `/web/inbox`.
- [ ] **Login error:** Enter invalid credentials, verify error message renders on login page without redirect.
- [ ] **Inbox rendering:** Verify inbox page loads with nav bar, user display name, and conversation list (or empty state). Verify unread count badges display correctly.
- [ ] **Session enforcement:** Access `/web/inbox` without session cookie, verify redirect to `/web/login`.
- [ ] **Logout:** Click logout, verify redirect to login, verify `/web/inbox` is no longer accessible.
- [ ] **Health page:** Navigate to `/web/health`, verify status, version, and user count display publicly (no auth required).
- [ ] **Visual consistency:** Verify Tailwind styling is applied (no unstyled HTML), nav bar appears on all authenticated pages, layout is responsive at desktop width.
- [ ] **HTMX loaded:** Verify HTMX script tag present in page source (foundation for future sprints).

### 10.6 Tests

- [ ] All existing tests pass (updated for new schema and error format)
- [ ] New test_errors.py: error code registry, make_error output, is_error
- [ ] New test_migration.py: migration on empty DB, migration on populated DB, idempotency
- [ ] New test_web.py: login flow, session validation, inbox rendering, health page
- [ ] test_queries.py: rewritten for all new query functions
- [ ] test_tools.py: updated assertions for structured errors, conversation-based operations
- [ ] Total test count >= 60 (up from 43)

### 10.7 Deployment (TDD-through-delivery verification)

- [ ] MVP 1 Staging environment deploys and passes health check
- [ ] `/health` returns `{"status": "healthy"}` on mvp-1-staging domain
- [ ] Migration 003 applied successfully (conversations, conversation_participants tables exist)
- [ ] MCP tools functional on deployed environment: send_message, check_messages, reply_to_message, get_thread, whoami
- [ ] Structured error responses returned on deployed environment (send to nonexistent user, empty body, etc.)
- [ ] Web UI accessible at `/web/login` on deployed environment
- [ ] AI UX UAT passed (section 10.5b) -- all browser checks green on deployed environment

### 10.8 GitHub

- [ ] Issue #5 (conversation model) closed with reference to implementation commit
- [ ] Issue #7 (structured errors) closed with reference to implementation commit
- [ ] Issue #8 (read tracking) closed with reference to implementation commit

---

## 11. Implementation Order (TDD Through Delivery)

TDD does not end when local tests pass. The RED-GREEN-REFACTOR cycle extends through deployment: a feature is not GREEN until it passes on the deployed environment. Each step below includes its verification scope.

1. **Error framework** -- `errors.py` + `test_errors.py` (standalone, no schema dependency)
   - RED: write tests for make_error, is_error, all error codes
   - GREEN: implement errors.py
   - VERIFY: tests pass locally

2. **Schema DDL** -- migration SQL + updated `conftest.py` + `test_migration.py`
   - RED: write migration tests (empty DB, populated DB, idempotency)
   - GREEN: implement migration SQL + Python migration script
   - VERIFY: tests pass locally

3. **Query layer** -- `queries.py` rewrite + `test_queries.py` rewrite
   - RED: write tests for all new query functions (conversation CRUD, message insert with sequence numbers, read cursors, inbox query, unread counts)
   - GREEN: implement queries.py
   - VERIFY: tests pass locally

4. **Tool layer** -- update all 5 tools + `test_tools.py` updates
   - RED: update test assertions for structured errors, conversation-based operations
   - GREEN: update tool implementations
   - VERIFY: tests pass locally, full suite green

5. **Web scaffold** -- `web.py` + templates + `test_web.py`
   - RED: write tests for login flow, session validation, inbox rendering, health page
   - GREEN: implement web routes + templates
   - VERIFY: tests pass locally

6. **Server integration** -- mount web routes in `server.py`, update `test_server.py`
   - RED: update server tests for web route registration
   - GREEN: wire web routes into server
   - VERIFY: full local test suite green (all tests pass, zero failures)

7. **Data migration** -- `migrate_003.py` + migration test on populated SQLite
   - RED: write tests for data migration on populated DB
   - GREEN: implement migration logic
   - VERIFY: tests pass locally

8. **Deploy to MVP 1 Staging** -- push to mvp-1-staging, verify health
   - VERIFY (deployment TDD):
     - `/health` returns 200 with `{"status": "healthy"}`
     - Migration applied (new tables exist)
     - MCP tools respond correctly (send, check, reply, thread, whoami)
     - Structured errors returned on invalid inputs

9. **AI UX UAT** -- browser-based verification of deployed web UI (required gate)
   - Claude navigates to MVP 1 Staging web UI via preview tools
   - Executes all checks from section 10.5b
   - Screenshots captured as evidence
   - Failures block sprint completion -- fix and re-verify

10. **Human UAT** -- user verifies deployed web UI (required gate)
    - User navigates the deployed web UI and confirms:
      - Login flow works
      - Inbox renders correctly
      - Health page accessible
      - Overall UX acceptable
    - Sprint is not complete until human UAT passes

11. **GitHub cleanup** -- close issues, update project board
    - Close #5, #7, #8 with commit references
    - Update project board status

---

## 12. Resolved Design Decisions

1. **Direct conversation uniqueness: per-project.** `send_message(to="amy", project="general")` and `send_message(to="amy", project="deployment")` create two separate conversations. This matches the current project-as-filter behavior and supports group interaction within projects. Could expand to global uniqueness in a future sprint if needed.

2. **check_messages auto-advances read cursor in Sprint 1.** Backward compatible with current behavior. Sprint 2 splits into `list_messages` (pure read) + `mark_read` (explicit write).

3. **Web UI uses password-based login as Sprint 1 placeholder.** Reuses existing `authenticate_user()` with JWT in httpOnly session cookie. Google OAuth replaces this in Sprint 6. The session cookie middleware carries forward unchanged.

---

## Appendix A: Message dict shape (returned by tools)

For backward compatibility, message dicts returned by tools include a synthetic `to_user` field:

```json
{
    "id": "uuid",
    "conversation_id": "uuid",
    "from_user": "keith",
    "to_user": "amy",
    "sequence_number": 1,
    "project": "general",
    "subject": "Hello",
    "body": "Message text",
    "content_type": "text/plain",
    "reply_to": null,
    "created_at": "2026-04-05T12:00:00Z"
}
```

`to_user` is derived from conversation participants (the other user in direct conversations, or the original sender's target in groups). `project` is derived from `conversations.project`.

## Appendix B: Conversation dict shape (returned by inbox)

```json
{
    "conversation_id": "uuid",
    "type": "direct",
    "project": "general",
    "name": null,
    "participants": ["keith", "amy"],
    "last_message_preview": "Message text truncated to 100 chars...",
    "last_message_at": "2026-04-05T12:00:00Z",
    "last_message_from": "keith",
    "unread_count": 3,
    "total_messages": 12
}
```
