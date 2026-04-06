# Sprint 4 Spec: Search + Structured Payloads + Live Updates

**Status:** DRAFT -- awaiting approval
**Branch:** mvp-1-staging
**Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
**GitHub Issues:** #14 (normalize scopes storage)
**Depends on:** Sprint 3 (complete -- 320 tests, deployed)

---

## 1. Overview

Three features: (A) full-text search with a new `search_messages` MCP tool and web UI search bar, (B) structured JSON payload validation and rendering for agent-to-agent data exchange, (C) live inbox updates via HTMX polling. Also normalizes OAuth scopes storage (issue #14) and removes the deprecated `check_messages` tool per the Sprint 2 deprecation schedule.

**What changes:** New migration (004), new MCP tool (`search_messages`), JSON payload validation in send/reply, web UI search bar + results + JSON rendering + live polling, OAuth scopes storage format, `check_messages` removed.

**What does NOT change:** DaisyUI framework, rate limiting, group send confirmation protocol, CORS/JWT validation, token cleanup, template structure (additive changes only).

---

## 2. Full-Text Search

### 2.1 Migration 004: Search Infrastructure

New file: `src/ai_mailbox/db/migrations/004_search.sql`

```sql
-- Full-text search on messages (PostgreSQL only)
-- SQLite tests use LIKE fallback in queries.py

ALTER TABLE messages ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Populate existing rows
UPDATE messages SET search_vector =
    setweight(to_tsvector('english', COALESCE(subject, '')), 'A') ||
    setweight(to_tsvector('english', body), 'B');

-- GIN index for fast search
CREATE INDEX IF NOT EXISTS idx_msg_search ON messages USING GIN(search_vector);

-- Auto-populate on INSERT/UPDATE
CREATE OR REPLACE FUNCTION messages_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.subject, '')), 'A') ||
        setweight(to_tsvector('english', NEW.body), 'B');
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_messages_search ON messages;
CREATE TRIGGER trg_messages_search
    BEFORE INSERT OR UPDATE ON messages
    FOR EACH ROW
    EXECUTE FUNCTION messages_search_trigger();
```

Subject is weight A (higher relevance), body is weight B. The trigger auto-populates `search_vector` on every insert, so no application code changes needed for indexing.

### 2.2 SQLite Test Compatibility

SQLite has no `tsvector` or GIN indexes. The migration runs only on PostgreSQL (guarded in `ensure_schema_postgres`). SQLite tests skip the migration.

The search query function detects the database type and uses the appropriate strategy:
- **PostgreSQL:** `search_vector @@ plainto_tsquery('english', ?)` with `ts_rank` for ordering
- **SQLite:** `body LIKE ? OR subject LIKE ?` with `%query%` wrapping

### 2.3 search_messages MCP Tool

```python
# src/ai_mailbox/tools/search.py
def tool_search_messages(
    db: DBConnection,
    *,
    user_id: str,
    query: str,
    project: str | None = None,
    from_user: str | None = None,
    since: str | None = None,      # ISO 8601 timestamp
    until: str | None = None,      # ISO 8601 timestamp
    limit: int = 20,
) -> dict
```

**Behavior:**
1. Rate limit check: MCP_READ_LIMIT
2. Validate `query` is non-empty (1-500 chars)
3. Validate `limit` is 1-100
4. Search messages across all conversations where user is a participant
5. Apply optional filters: project, from_user, since, until
6. Order by relevance (ts_rank on PostgreSQL, created_at on SQLite)
7. Return matching messages with conversation context

**Response:**
```json
{
    "query": "deployment status",
    "result_count": 3,
    "messages": [
        {
            "id": "uuid",
            "conversation_id": "uuid",
            "from_user": "keith",
            "subject": "Deployment update",
            "body": "Sprint 2 is deployed. 254 tests passing.",
            "body_preview": "Sprint 2 is deployed. 254 tests...",
            "content_type": "text/plain",
            "project": "ai-mailbox",
            "created_at": "2026-04-06T12:00:00Z",
            "conversation_participants": ["keith", "amy"]
        }
    ]
}
```

`body_preview` is truncated to 200 chars for large messages.

**Validation:**
- Empty query: `MISSING_PARAMETER`
- Query > 500 chars: `INVALID_PARAMETER`
- `limit` out of range: `INVALID_PARAMETER`
- `since`/`until` invalid ISO 8601: `INVALID_PARAMETER`

### 2.4 Search Query Function

```python
# db/queries.py addition
def search_messages(
    db: DBConnection,
    user_id: str,
    query: str,
    *,
    project: str | None = None,
    from_user: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
) -> list[dict]:
```

**PostgreSQL path:**
```sql
SELECT m.*, c.project, c.type,
       ts_rank(m.search_vector, plainto_tsquery('english', ?)) AS rank
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
JOIN conversation_participants cp ON c.id = cp.conversation_id
WHERE cp.user_id = ?
  AND m.search_vector @@ plainto_tsquery('english', ?)
  [AND c.project = ?]
  [AND m.from_user = ?]
  [AND m.created_at >= ?]
  [AND m.created_at <= ?]
ORDER BY rank DESC, m.created_at DESC
LIMIT ?
```

**SQLite path:**
```sql
SELECT m.*, c.project, c.type
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
JOIN conversation_participants cp ON c.id = cp.conversation_id
WHERE cp.user_id = ?
  AND (m.body LIKE ? OR m.subject LIKE ?)
  [AND c.project = ?]
  [AND m.from_user = ?]
  [AND m.created_at >= ?]
  [AND m.created_at <= ?]
ORDER BY m.created_at DESC
LIMIT ?
```

The function detects DB type via `isinstance(db, PostgresDB)` (already used elsewhere in the codebase for DB-specific logic).

---

## 3. Structured JSON Payloads

### 3.1 Validation

When `content_type` is `application/json`, validate that `body` is parseable JSON before inserting.

```python
# In tool_send_message and tool_reply_to_message, after body length check:
if content_type == "application/json":
    try:
        json.loads(body)
    except (json.JSONDecodeError, TypeError) as e:
        return make_error("INVALID_JSON", f"Body is not valid JSON: {e}", param="body")
```

New error code: `INVALID_JSON` (not retryable).

### 3.2 Web UI: JSON Message Rendering

In `thread_view.html`, detect content_type and render JSON messages differently from markdown:

```html
{% if msg.content_type == 'application/json' %}
<div class="prose-msg text-sm">
    <pre class="bg-base-200 p-3 rounded-lg text-xs overflow-x-auto"><code>{{ msg.body | pretty_json }}</code></pre>
</div>
{% else %}
<div class="prose-msg text-sm">{{ msg.body | markdown }}</div>
{% endif %}
```

New Jinja2 filter `pretty_json`:
```python
import json

def _pretty_json(text: str) -> str:
    """Format JSON string with indentation. Returns original if not valid JSON."""
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, TypeError):
        return text

_jinja_env.filters["pretty_json"] = _pretty_json
```

### 3.3 Search Across Content Types

`search_messages` searches both `text/plain` and `application/json` messages. The full-text index covers the raw body text regardless of content_type. JSON keys and values are searchable.

---

## 4. Live Inbox Updates via HTMX Polling

### 4.1 Design Decision: Polling vs SSE

**Chosen: HTMX polling.** True SSE via PostgreSQL LISTEN/NOTIFY requires an async connection (`psycopg.AsyncConnection`), which is a different connection model from the current synchronous `psycopg.Connection`. This is a significant architectural change for marginal benefit at alpha scale (2 users, single process).

HTMX polling achieves the same UX with zero new dependencies:

```html
<div id="conversation-list"
     hx-get="/web/inbox/conversations?project=...&participant=..."
     hx-trigger="load, every 15s"
     hx-swap="innerHTML">
</div>
```

The sidebar refreshes every 15 seconds. New messages appear without manual reload. Cost: one GET request per 15 seconds per connected browser tab. Acceptable for alpha.

**Deferred:** True SSE with `sse-starlette` and PostgreSQL LISTEN/NOTIFY to Sprint 6+ when horizontal scaling or sub-second latency is needed.

### 4.2 Unread Count Badge Update

The conversation list partial already renders unread badges. Polling refreshes the list, so badges update automatically. No additional logic needed.

### 4.3 Thread View Auto-Refresh

When viewing a conversation, poll for new messages:

```html
<div id="message-list"
     hx-get="/web/conversation/{{ conversation.id }}/messages"
     hx-trigger="every 10s"
     hx-swap="innerHTML">
```

New route: `GET /web/conversation/{conv_id}/messages` -- returns just the message list HTML (no header, no reply form). This is a lighter partial than the full thread view.

---

## 5. Web UI: Search Bar and Results

### 5.1 Search Bar in Navbar

Add a search input to the navbar in `base.html`:

```html
<div class="flex-1 flex items-center gap-4">
    <a class="btn btn-ghost text-xl normal-case" href="/web/inbox">AI Mailbox</a>
    {% if user_id %}
    <div class="form-control">
        <input type="text" placeholder="Search messages..."
               class="input input-bordered input-sm w-64"
               id="search-input"
               hx-get="/web/search"
               hx-trigger="keyup changed delay:300ms"
               hx-target="#main-content"
               hx-include="this"
               name="q">
    </div>
    {% endif %}
</div>
```

Debounced (300ms) search-as-you-type. Results load in the main content area.

### 5.2 Search Results Template

New partial: `src/ai_mailbox/templates/partials/search_results.html`

```html
<div class="card bg-base-100 shadow">
    <div class="card-body">
        <h3 class="card-title text-lg">
            Search: "{{ query }}"
            <span class="badge badge-ghost">{{ results | length }} result{{ 's' if results | length != 1 else '' }}</span>
        </h3>
        <div class="divider my-2"></div>
        {% if results %}
        <div class="space-y-3">
            {% for msg in results %}
            <div class="p-3 rounded-lg hover:bg-base-200 cursor-pointer border border-base-300"
                 hx-get="/web/conversation/{{ msg.conversation_id }}"
                 hx-target="#main-content"
                 hx-push-url="true">
                <div class="flex items-center justify-between mb-1">
                    <span class="font-medium text-sm">{{ msg.from_user }}</span>
                    <span class="text-xs text-base-content/40">{{ msg.created_at | relative_time }}</span>
                </div>
                {% if msg.subject %}
                <div class="text-sm font-medium">{{ msg.subject }}</div>
                {% endif %}
                <div class="text-sm text-base-content/70 line-clamp-2">{{ msg.body_preview }}</div>
                <div class="flex items-center gap-2 mt-1">
                    <span class="badge badge-ghost badge-xs">{{ msg.project }}</span>
                    {% if msg.content_type == 'application/json' %}
                    <span class="badge badge-info badge-xs">JSON</span>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <p class="text-base-content/50 text-center py-4">No messages match your search.</p>
        {% endif %}
    </div>
</div>
```

### 5.3 Search Route

```python
async def web_search(request: Request):
    user_id = _require_auth(request)
    if not user_id:
        return RedirectResponse(url="/web/login", status_code=302)

    if not check_rate_limit(WEB_PAGE_LIMIT, "web", user_id):
        return _htmx_error(429)

    query = request.query_params.get("q", "").strip()
    if not query:
        return _render("partials/empty_state.html")

    results = search_messages(db, user_id, query, limit=20)
    # Add body_preview to each result
    for r in results:
        r["body_preview"] = r["body"][:200] + ("..." if len(r["body"]) > 200 else "")

    return _render("partials/search_results.html", user_id=user_id, query=query, results=results)
```

---

## 6. Remove Deprecated check_messages Tool

Per Sprint 2 spec section 4.11: `check_messages` was deprecated in Sprint 2 with removal scheduled for Sprint 4.

**Changes:**
- Remove `@mcp.tool() def check_messages(...)` from `server.py`
- Remove `from ai_mailbox.tools.inbox import tool_check_messages` import
- Delete `src/ai_mailbox/tools/inbox.py`
- Update tests that reference `check_messages` to use `list_messages` + `mark_read`

---

## 7. Normalize OAuth Scopes Storage (Issue #14)

### 7.1 Problem

`oauth_codes.scopes` and `oauth_tokens.scopes` store scopes as comma-separated strings. The MCP SDK represents scopes as lists.

### 7.2 Solution

Change serialization in `oauth.py`:
- **Write:** `json.dumps(scopes_list)` instead of `",".join(scopes_list)`
- **Read:** `json.loads(scopes_str)` instead of `scopes_str.split(",")`

Add a fallback reader that handles both formats during transition:
```python
def _parse_scopes(scopes_str: str | None) -> list[str]:
    """Parse scopes from DB. Handles both JSON array and comma-separated formats."""
    if not scopes_str:
        return []
    try:
        parsed = json.loads(scopes_str)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return [s.strip() for s in scopes_str.split(",") if s.strip()]
```

No migration needed -- the format change is backward-compatible via the fallback reader. New records write JSON, old records are read correctly either way.

---

## 8. Edge Cases

### 8.1 Search with special characters

PostgreSQL `plainto_tsquery` handles special characters safely -- it strips punctuation and treats input as plain text (no query operators). `LIKE` in SQLite wraps with `%`, so `%` and `_` in user input need escaping. Use `query.replace('%', '\\%').replace('_', '\\_')` for SQLite path.

### 8.2 Search returns messages from conversations user left

The JOIN on `conversation_participants` ensures only messages from conversations where the user is currently a participant are returned. If a "leave conversation" feature is added later, search results automatically exclude those conversations.

### 8.3 JSON validation on very large bodies

`json.loads()` on a 10KB body is fast (< 1ms). No performance concern. The existing `MAX_BODY_LENGTH = 10_000` char limit applies before JSON validation.

### 8.4 Pretty JSON with deeply nested structures

`json.dumps(parsed, indent=2)` can produce very long output for deeply nested JSON. The `<pre>` block has `overflow-x-auto` to handle width, and the chat bubble constrains height via the existing `max-h` on the message list.

### 8.5 Polling rate and Railway costs

15-second polling on conversation list, 10-second on active thread. Each request is a lightweight DB query + HTML render. Railway charges by CPU time, not request count. At 2 users with ~4 tabs, this is ~16 requests/minute total. Negligible cost.

### 8.6 Search on empty database

Returns `{"query": "...", "result_count": 0, "messages": []}`. Web UI shows "No messages match your search."

### 8.7 tsvector column on existing messages

Migration 004 backfills `search_vector` for all existing messages via the UPDATE statement. New messages are auto-populated by the trigger. No manual reindexing needed.

### 8.8 check_messages removal -- client migration

Any MCP client still calling `check_messages` will get a "tool not found" error. The deprecation notice has been in the tool description since Sprint 2 (2 sprints of warning).

---

## 9. File Changes Summary

### New files

| File | Purpose |
|---|---|
| `src/ai_mailbox/db/migrations/004_search.sql` | tsvector column, GIN index, auto-populate trigger |
| `src/ai_mailbox/tools/search.py` | `search_messages` MCP tool |
| `src/ai_mailbox/templates/partials/search_results.html` | Search results partial |
| `tests/test_search.py` | Search tool + query tests |

### Modified files

| File | Changes |
|---|---|
| `src/ai_mailbox/db/schema.py` | Run migration 004 on PostgreSQL |
| `src/ai_mailbox/db/queries.py` | Add `search_messages()` query (dual-path: PostgreSQL FTS + SQLite LIKE) |
| `src/ai_mailbox/errors.py` | Add `INVALID_JSON` error code |
| `src/ai_mailbox/tools/send.py` | JSON validation when content_type is application/json |
| `src/ai_mailbox/tools/reply.py` | JSON validation when content_type is application/json |
| `src/ai_mailbox/oauth.py` | Scopes serialization: comma-separated to JSON array |
| `src/ai_mailbox/server.py` | Register `search_messages` tool, remove `check_messages`, add `pretty_json` filter |
| `src/ai_mailbox/web.py` | Add search route, add message-list partial route, pass content_type to templates |
| `src/ai_mailbox/templates/base.html` | Add search input to navbar |
| `src/ai_mailbox/templates/inbox.html` | Add `hx-trigger="load, every 15s"` to conversation list |
| `src/ai_mailbox/templates/partials/thread_view.html` | JSON rendering, add polling trigger for messages |
| `tests/test_tools.py` | JSON validation tests, check_messages removal tests |
| `tests/test_web.py` | Search route tests, polling attributes |
| `tests/test_queries.py` | search_messages query tests (SQLite path) |
| `tests/test_server.py` | search_messages tool registration, check_messages removed |

### Deleted files

| File | Reason |
|---|---|
| `src/ai_mailbox/tools/inbox.py` | `check_messages` deprecated in Sprint 2, removed Sprint 4 |

### Unchanged files

| File | Reason |
|---|---|
| `src/ai_mailbox/config.py` | No config changes |
| `src/ai_mailbox/rate_limit.py` | Search uses existing MCP_READ_LIMIT |
| `src/ai_mailbox/group_tokens.py` | Unchanged |
| `src/ai_mailbox/markdown.py` | Unchanged |
| `src/ai_mailbox/token_cleanup.py` | Unchanged |
| `src/ai_mailbox/templates/login.html` | Unchanged |
| `src/ai_mailbox/templates/error.html` | Unchanged |
| `Dockerfile` | No new system deps |
| `railway.toml` | Unchanged |

---

## 10. Acceptance Criteria

### 10.1 search_messages MCP Tool

- [ ] `search_messages(query="deployment")` returns messages containing "deployment"
- [ ] Results only include messages from conversations the user participates in
- [ ] `project` filter limits results to that project
- [ ] `from_user` filter limits results to messages from that sender
- [ ] `since` and `until` filter by date range
- [ ] `limit` controls max results (default 20, max 100)
- [ ] Empty query returns `MISSING_PARAMETER` error
- [ ] Results include `body_preview` (200 char truncation)
- [ ] Results ordered by relevance (PostgreSQL) or date (SQLite)
- [ ] Rate limited (MCP_READ_LIMIT)

### 10.2 Full-Text Search Infrastructure

- [ ] Migration 004 adds `search_vector` tsvector column to messages
- [ ] GIN index created on `search_vector`
- [ ] Trigger auto-populates `search_vector` on INSERT
- [ ] Existing messages backfilled by UPDATE in migration
- [ ] Subject weighted higher (A) than body (B)
- [ ] SQLite tests use LIKE fallback without tsvector

### 10.3 JSON Payload Validation

- [ ] `send_message(body='{"key": "value"}', content_type="application/json")` succeeds
- [ ] `send_message(body='not json', content_type="application/json")` returns `INVALID_JSON` error
- [ ] `send_message(body='hello', content_type="text/plain")` works as before (no JSON check)
- [ ] `reply_to_message` with `content_type="application/json"` validates JSON body
- [ ] `INVALID_JSON` error is not retryable

### 10.4 Web UI: JSON Rendering

- [ ] Messages with `content_type: application/json` render as formatted JSON code block
- [ ] Messages with `content_type: text/plain` render as markdown (unchanged)
- [ ] JSON code block has syntax highlighting via `<pre><code>`
- [ ] Invalid JSON stored before Sprint 4 renders as plain text (no crash)

### 10.5 Web UI: Search

- [ ] Search input in navbar with placeholder text
- [ ] Typing triggers search after 300ms debounce
- [ ] Results show in main content area with message preview, sender, date, project badge
- [ ] Clicking a result navigates to that conversation's thread view
- [ ] Empty search input returns to empty state
- [ ] No results shows "No messages match your search" message
- [ ] JSON messages show "JSON" badge in results

### 10.6 Live Inbox Updates

- [ ] Conversation list refreshes every 15 seconds via HTMX polling
- [ ] Unread badges update when new messages arrive
- [ ] Active thread refreshes every 10 seconds (new messages appear)
- [ ] Polling uses lightweight partials (not full page reloads)
- [ ] Polling stops when user navigates away from inbox

### 10.7 check_messages Removal

- [ ] `check_messages` tool no longer registered in server.py
- [ ] `tools/inbox.py` deleted
- [ ] Existing tests updated to use `list_messages` + `mark_read`
- [ ] No import of `tool_check_messages` anywhere

### 10.8 OAuth Scopes Normalization (Issue #14)

- [ ] New OAuth codes store scopes as JSON array: `'["read","write"]'`
- [ ] New OAuth tokens store scopes as JSON array
- [ ] Reader handles both JSON and comma-separated formats (backward compatible)
- [ ] Existing tests pass without migration

### 10.9 AI UX UAT (browser verification -- required gate)

- [ ] **Search:** Type in navbar search bar, verify results appear in main content
- [ ] **Search results:** Click a result, verify navigation to conversation thread
- [ ] **JSON message:** View a conversation containing a JSON message, verify formatted code block
- [ ] **Live updates:** Open inbox, send a message via MCP tool, verify it appears within 15 seconds
- [ ] **Thread updates:** View a conversation, send a reply via MCP, verify it appears within 10 seconds

### 10.10 Tests

- [ ] test_search.py: search query, filters, pagination, empty results, permissions
- [ ] test_tools.py additions: JSON validation, check_messages removed
- [ ] test_queries.py additions: search_messages (SQLite LIKE path)
- [ ] test_web.py additions: search route, search results rendering, polling attributes
- [ ] test_server.py additions: search_messages registration, check_messages absent
- [ ] Total test count >= 350 (up from 320)

### 10.11 Deployment

- [ ] Migration 004 runs on PostgreSQL staging
- [ ] Existing messages searchable after migration
- [ ] Search bar functional on deployed environment
- [ ] JSON messages render correctly on deployed environment
- [ ] AI UX UAT passed on deployed environment

### 10.12 GitHub

- [ ] Issue #14 (normalize scopes) closed with commit reference

---

## 11. Implementation Order (TDD Through Delivery)

1. **Error codes + JSON validation** -- `errors.py` + `send.py` + `reply.py` + tests
   - RED: tests for INVALID_JSON error, JSON validation in send/reply
   - GREEN: add error code, validation logic
   - VERIFY: tests pass

2. **Search query + migration** -- `queries.py` + `004_search.sql` + `schema.py` + tests
   - RED: tests for search_messages (SQLite LIKE path), empty results, permission filtering
   - GREEN: implement dual-path search query, add migration
   - VERIFY: tests pass

3. **search_messages tool** -- `tools/search.py` + `server.py` + tests
   - RED: tests for tool behavior, parameter validation, rate limiting
   - GREEN: implement tool, register in server
   - VERIFY: tests pass

4. **Remove check_messages** -- delete `tools/inbox.py`, update server.py + tests
   - RED: verify check_messages tests are removed/updated
   - GREEN: delete file, remove registration, update test assertions
   - VERIFY: full test suite passes

5. **OAuth scopes normalization** -- `oauth.py` + tests
   - RED: tests for JSON serialization, backward-compatible reader
   - GREEN: implement `_parse_scopes`, update write paths
   - VERIFY: tests pass

6. **Web UI: search + JSON rendering + polling** -- templates + web.py + tests
   - RED: tests for search route, JSON filter, polling attributes in HTML
   - GREEN: add search bar to navbar, search_results.html, search route, pretty_json filter, JSON rendering in thread view, polling triggers
   - VERIFY: tests pass

7. **Server integration + full test suite**
   - RED: integration tests
   - GREEN: wire everything
   - VERIFY: full suite green (350+ tests)

8. **Deploy to MVP 1 Staging**
   - VERIFY: migration 004 runs, search works, JSON renders, polling active

9. **AI UX UAT** (required gate)
   - Browser verification of section 10.9

10. **Human UAT** (required gate)

11. **GitHub cleanup** -- close #14

---

## 12. Dependency Changes

No new Python dependencies. HTMX polling uses existing HTMX CDN. PostgreSQL full-text search uses built-in PostgreSQL features. `sse-starlette` deferred to Sprint 6+.

---

## 13. Resolved Design Decisions

1. **HTMX polling over SSE.** True SSE requires `psycopg.AsyncConnection` and `sse-starlette`, which is a significant architectural change for the current sync DB layer. HTMX polling at 10-15 second intervals achieves near-real-time UX with zero new dependencies. Deferred SSE to Sprint 6+ when horizontal scaling demands sub-second latency.

2. **Dual-path search (PostgreSQL FTS + SQLite LIKE).** Maintaining SQLite test compatibility is a hard constraint. The query function uses `isinstance(db, PostgresDB)` to select the search strategy. PostgreSQL gets proper ranking via `ts_rank`; SQLite gets basic substring matching. Both paths are tested.

3. **Subject weighted higher than body.** PostgreSQL `setweight` with 'A' for subject and 'B' for body means a match in the subject ranks higher than the same match in the body. This matches user expectations -- subject lines are more intentional signals.

4. **check_messages removal.** The deprecation was announced in Sprint 2 with a 2-sprint grace period. Clients have had Sprint 2 and Sprint 3 to migrate to `list_messages` + `mark_read`. Removal keeps the API surface clean.

5. **JSON validation at tool level, not DB level.** PostgreSQL supports `jsonb` column types with native validation, but changing `body TEXT` to `body JSONB` would break `text/plain` messages. Validation at the tool level (before insert) is the right layer.

6. **No JSON schema validation.** `content_type: application/json` only validates that the body is parseable JSON. Schema validation (e.g., enforcing specific keys) is deferred -- it requires a schema registry and versioning system that is beyond alpha scope.

7. **Search debounce 300ms.** HTMX `delay:300ms` on `keyup changed` prevents search-on-every-keystroke while still feeling responsive. Standard UX pattern.

8. **Polling intervals: 15s sidebar, 10s thread.** Thread view is the active context (user is reading), so shorter interval. Sidebar is background context. Both are well within Railway request capacity.
