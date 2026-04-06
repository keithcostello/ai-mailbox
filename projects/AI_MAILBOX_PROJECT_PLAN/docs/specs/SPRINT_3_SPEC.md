# Sprint 3 Spec: P0 Security + Web UI Polish

**Status:** DRAFT -- awaiting approval
**Branch:** mvp-1-staging
**Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
**GitHub Issues:** #1 (token cleanup), #2 (JWT validation), #3 (CORS restriction), #16 (remove auth.py)
**Depends on:** Sprint 2 (complete -- 287 tests, deployed)

---

## 1. Overview

Close the P0 security gaps identified during architecture review: validate JWT secret at startup, restrict CORS to explicit origins, add expired OAuth token/code cleanup, and remove dead code. Polish the web UI with dedicated error pages, an AI user badge in thread view, and markdown rendering for message bodies.

**What does NOT change:** MCP tool signatures, database schema DDL, rate limiting configuration, group send confirmation protocol, Semantic UI framework, three-table conversation model.

---

## 2. JWT Secret Validation at Startup (Issue #2)

### 2.1 Problem

`config.py:16` defines a hardcoded default: `"change-me-in-production-minimum-32-bytes!"`. If `MAILBOX_JWT_SECRET` env var is missing, the server starts with this predictable secret. Any attacker can forge valid JWTs.

### 2.2 Solution

Add `validate()` method to `Config` class. Called during `create_app()` before any route registration.

```python
# config.py
_DEFAULT_SECRET = "change-me-in-production-minimum-32-bytes!"

class Config:
    # ... existing fields ...

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of warnings. Raises on fatal issues."""
        warnings = []
        if self.jwt_secret == _DEFAULT_SECRET:
            if self.database_url:  # PostgreSQL = non-local deployment
                raise ConfigurationError(
                    "JWT secret must be set via MAILBOX_JWT_SECRET in production. "
                    "Do not use the default secret with a real database."
                )
            warnings.append("Using default JWT secret. Set MAILBOX_JWT_SECRET for production.")
        if len(self.jwt_secret) < 32:
            raise ConfigurationError(
                f"JWT secret must be at least 32 bytes (got {len(self.jwt_secret)}). "
                "Use a cryptographically random string."
            )
        return warnings
```

**Behavior:**
- Default secret + SQLite (local dev): log warning, allow startup
- Default secret + PostgreSQL (staging/prod): raise `ConfigurationError`, refuse to start
- Secret < 32 bytes: always fatal regardless of database
- Valid secret: no warning, proceed

### 2.3 ConfigurationError

New exception in `config.py`:

```python
class ConfigurationError(Exception):
    """Raised when server configuration is invalid."""
```

### 2.4 Integration

`server.py` `create_app()` calls `config.validate()` after `Config.from_env()`:

```python
config = Config.from_env()
for warning in config.validate():
    logger.warning(warning)
```

Fatal errors propagate as exceptions, preventing app startup.

---

## 3. CORS Restriction (Issue #3)

### 3.1 Problem

`server.py:349` sets `allow_origins=["*"]`. This permits any origin to make credentialed requests to the API.

### 3.2 Solution

New config field `allowed_origins` with explicit default list. Environment variable `MAILBOX_CORS_ORIGINS` accepts comma-separated origins.

```python
# config.py
@dataclass
class Config:
    # ... existing fields ...
    allowed_origins: str = ""  # comma-separated, empty = Railway URL only

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            # ... existing ...
            allowed_origins=os.environ.get("MAILBOX_CORS_ORIGINS", ""),
        )

    def get_cors_origins(self) -> list[str]:
        """Return list of allowed CORS origins."""
        origins = []
        if self.allowed_origins:
            origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        # Always allow the Railway deployment URL
        origins.append("https://ai-mailbox-server-mvp-1-staging.up.railway.app")
        # Always allow localhost for dev
        origins.append("http://localhost:8000")
        return list(set(origins))
```

### 3.3 Integration

`server.py` replaces the wildcard:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.get_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)
```

Changes from current:
- `allow_origins`: explicit list instead of `["*"]`
- `allow_methods`: restricted to GET/POST/OPTIONS (no PUT/DELETE/PATCH -- not used)
- `allow_headers`: restricted to Authorization + Content-Type
- `allow_credentials`: `True` (needed for session cookies)

---

## 4. OAuth Token/Code Cleanup (Issue #1)

### 4.1 Problem

`oauth_codes` and `oauth_tokens` tables accumulate expired records. Codes expire after 5 minutes but are only deleted when exchanged. Tokens expire but are never pruned.

### 4.2 Solution

New module `src/ai_mailbox/token_cleanup.py` with a cleanup function. Called on a schedule during app lifecycle.

```python
# token_cleanup.py
import logging
import time

logger = logging.getLogger(__name__)

def cleanup_expired_tokens(db) -> dict:
    """Delete expired OAuth codes and tokens. Returns counts."""
    now = time.time()

    codes_deleted = db.execute(
        "DELETE FROM oauth_codes WHERE expires_at < ?", (now,)
    )
    tokens_deleted = db.execute(
        "DELETE FROM oauth_tokens WHERE expires_at IS NOT NULL AND expires_at < ?", (int(now),)
    )

    if codes_deleted or tokens_deleted:
        logger.info(f"Token cleanup: {codes_deleted} expired codes, {tokens_deleted} expired tokens removed")

    return {"codes_deleted": codes_deleted, "tokens_deleted": tokens_deleted}
```

### 4.3 Scheduling

Cleanup runs in two contexts:

1. **On startup:** `create_app()` calls `cleanup_expired_tokens(db)` once after schema migration
2. **Periodic:** Background task via `asyncio.create_task` that runs every 30 minutes

```python
# server.py addition
import asyncio

async def _periodic_cleanup(db, interval_seconds=1800):
    """Run token cleanup every 30 minutes."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            cleanup_expired_tokens(db)
        except Exception:
            logger.exception("Token cleanup failed")

# In create_app(), after schema migration:
cleanup_expired_tokens(db)

# Starlette lifespan or on_startup hook:
@app.on_event("startup")
async def start_cleanup_task():
    asyncio.create_task(_periodic_cleanup(db))
```

### 4.4 Health endpoint

Add cleanup stats to `/web/health`:
- `last_cleanup_at`: ISO timestamp of last cleanup run
- `next_cleanup_at`: ISO timestamp of next scheduled run

### 4.5 SQL compatibility

Both SQLite and PostgreSQL support `DELETE ... WHERE expires_at < ?` with numeric timestamps. The `oauth_codes.expires_at` is FLOAT, `oauth_tokens.expires_at` is INTEGER. Both compare correctly against `time.time()`.

---

## 5. Code Cleanup: Remove auth.py (Issue #16)

### 5.1 Problem

`src/ai_mailbox/auth.py` contains legacy API key authentication (`AuthError` exception + `authenticate()` function). It is not imported anywhere in the codebase. OAuth 2.1 in `oauth.py` replaced it.

### 5.2 Solution

Delete the file. No migration needed -- nothing imports it.

Also remove the legacy API key config fields from `Config`:
- `keith_api_key`
- `amy_api_key`

And their corresponding `os.environ.get` calls. The `api_key` column on the `users` table is unused but is a schema change -- defer column removal to a future migration (tracked as existing TD-001).

---

## 6. Web UI: Error Pages

### 6.1 Problem

Current error handling uses inline text or empty states:
- 404: Returns `empty_state.html` with status 404 (`web.py:253`)
- 403: Returns `empty_state.html` with status 403 (`web.py:257`)
- 429: Returns plain text "Rate limited" (`web.py:248`)
- 500: Unhandled -- Starlette default

### 6.2 Solution

New template: `src/ai_mailbox/templates/error.html`

A single error template that handles all error types via context variables:

```html
{# error.html - Semantic UI error page #}
{% extends "base.html" %}
{% block title %}{{ error_title }} - AI Mailbox{% endblock %}
{% block content %}
<div class="ui container" style="padding-top: 80px;">
    <div class="ui center aligned segment">
        <h1 class="ui icon header">
            <i class="{{ error_icon }} icon"></i>
            <div class="content">
                {{ error_code }}
                <div class="sub header">{{ error_title }}</div>
            </div>
        </h1>
        <p>{{ error_message }}</p>
        <a class="ui primary button" href="/web/inbox">Back to Inbox</a>
    </div>
</div>
{% endblock %}
```

### 6.3 Error configurations

| Code | Title | Icon | Message |
|------|-------|------|---------|
| 404 | Not Found | `search` | The page or conversation you requested does not exist. |
| 403 | Forbidden | `lock` | You do not have permission to access this resource. |
| 429 | Too Many Requests | `hourglass half` | You've made too many requests. Wait a moment and try again. |
| 500 | Server Error | `exclamation triangle` | Something went wrong. Try again or contact support. |

### 6.4 Helper function

```python
# web.py
def _render_error(status_code: int, title: str, message: str, icon: str, **ctx) -> HTMLResponse:
    html = templates.TemplateResponse("error.html", {
        "request": ctx.get("request"),
        "error_code": status_code,
        "error_title": title,
        "error_message": message,
        "error_icon": icon,
        "user_id": ctx.get("user_id"),
        "display_name": ctx.get("display_name"),
    })
    return HTMLResponse(html.body.decode(), status_code=status_code)
```

### 6.5 Route changes

Replace all inline error responses:

| Location | Current | New |
|----------|---------|-----|
| `web_conversation` 404 | `_render("partials/empty_state.html", status_code=404)` | `_render_error(404, ...)` for full-page requests; keep partial for HTMX |
| `web_conversation` 403 | `_render("partials/empty_state.html", status_code=403)` | `_render_error(403, ...)` for full-page; partial for HTMX |
| Rate limit 429s | `HTMLResponse("Rate limited", status_code=429)` | `_render_error(429, ...)` |

### 6.6 HTMX vs full-page detection

Check `HX-Request` header to distinguish HTMX partial requests from full-page loads:

```python
is_htmx = request.headers.get("HX-Request") == "true"
if is_htmx:
    return HTMLResponse('<div class="ui negative message"><p>Not found</p></div>', status_code=404)
else:
    return _render_error(404, "Not Found", "The conversation does not exist.", "search", request=request)
```

### 6.7 Global 500 handler

Add Starlette exception handler for unhandled errors:

```python
from starlette.exceptions import HTTPException

async def http_exception_handler(request, exc):
    if exc.status_code == 500:
        return _render_error(500, "Server Error", "Something went wrong.", "exclamation triangle", request=request)
    return _render_error(exc.status_code, str(exc.detail), "", "warning sign", request=request)
```

---

## 7. Web UI: Thread View Enhancements

### 7.1 AI User Badge

Add a visual badge next to message author names for AI/bot users. Identification: any user_id containing "claude", "gpt", "bot", or "ai-" prefix. Also check a new `is_ai` field on the users table (deferred to Sprint 5 agent identity work). For Sprint 3, use a heuristic function.

```python
# web.py helper
_AI_PATTERNS = {"claude", "gpt", "bot", "gemini", "copilot"}

def _is_ai_user(user_id: str) -> bool:
    lower = user_id.lower()
    return any(pat in lower for pat in _AI_PATTERNS) or lower.startswith("ai-")
```

Template change in `thread_view.html`:
```html
<a class="author">{{ msg.from_user }}</a>
{% if is_ai_user(msg.from_user) %}
<span class="ui tiny blue label">AI</span>
{% endif %}
```

Pass `is_ai_user` function to template context via Jinja2 globals.

### 7.2 Mark-as-read on view

Already implemented in `web.py:262-264`. No changes needed. Verified: `advance_read_cursor` is called with `max_seq` when viewing a conversation.

### 7.3 Markdown rendering in thread view

Add lightweight markdown rendering for message bodies using `mistune` (pure Python, no C dependencies).

```python
# New: src/ai_mailbox/markdown.py
import mistune

_renderer = mistune.create_markdown(
    escape=True,  # escape HTML in input
    plugins=['strikethrough', 'table'],
)

def render_markdown(text: str) -> str:
    """Render markdown text to safe HTML."""
    return _renderer(text)
```

Template change in `thread_view.html`:
```html
<!-- Before: -->
<div class="text" style="white-space: pre-wrap;">{{ msg.body }}</div>

<!-- After: -->
<div class="text markdown-body">{{ msg.body | markdown }}</div>
```

Register `markdown` as a Jinja2 filter. Add minimal CSS for markdown output (code blocks, lists, headers within messages).

**Scope limit:** Rendering only. The compose/reply forms stay as plain textarea. Users type markdown, it renders in the thread view.

---

## 8. Web UI: Compose Improvements

### 8.1 Current state

The compose form (`compose_form.html`) already has:
- Recipient search dropdown (Semantic UI search dropdown)
- Project text input
- Subject text input
- Body textarea

### 8.2 Project selector enhancement

Replace the free-text project input with a Semantic UI dropdown populated from known projects, with allowAdditions for new project names.

```html
<select name="project" class="ui search selection dropdown" id="project-selector">
    <option value="general">general</option>
    {% for project in projects %}
    <option value="{{ project }}">{{ project }}</option>
    {% endfor %}
</select>
```

Initialize with `allowAdditions: true` so users can type new project names:
```javascript
$('#project-selector').dropdown({allowAdditions: true, forceSelection: false});
```

**Data source:** New query function `get_distinct_projects(db, user_id)` returns project names from the user's conversations.

### 8.3 Character count on body

Add a character count indicator below the body textarea showing current/max (e.g., "142 / 10,000"). Updates on keyup. Turns red when approaching the limit (> 9,000 chars).

```html
<div class="field">
    <label>Message</label>
    <textarea name="body" id="compose-body" rows="5" maxlength="10000" required>{{ form_body or '' }}</textarea>
    <div class="ui small text" id="char-count" style="text-align: right; color: #999;">0 / 10,000</div>
</div>
```

---

## 9. Edge Cases

### 9.1 JWT validation with empty string

`MAILBOX_JWT_SECRET=""` results in empty string. Length check (< 32) catches this as a fatal error.

### 9.2 CORS with no env var set

`MAILBOX_CORS_ORIGINS=""` (empty or unset): defaults to Railway URL + localhost only. Sufficient for current deployment.

### 9.3 Token cleanup on empty tables

`DELETE FROM oauth_codes WHERE expires_at < ?` returns 0 rows on empty table. No error. Cleanup function handles this gracefully.

### 9.4 Token cleanup concurrency

Single-process Railway deployment. No concurrent cleanup issues. If multiple processes run in the future, the DELETE is idempotent -- worst case, both processes delete 0 rows for the same expired token.

### 9.5 Markdown XSS

`mistune.create_markdown(escape=True)` escapes HTML entities in input. User-supplied `<script>` tags render as literal text, not executable HTML. The `escape=True` parameter is the critical safety setting.

### 9.6 AI badge false positives

A human user named "robotics-bob" would match the "bot" pattern. Acceptable for Sprint 3 heuristic. Sprint 5 adds explicit `is_ai` field on users table, which will be the authoritative source.

### 9.7 HTMX error page rendering

HTMX requests expect partial HTML. Returning a full error page (with `<html>`, `<head>`) inside an HTMX target would nest documents. Solution: detect `HX-Request` header and return inline error messages for HTMX, full error pages for direct navigation.

### 9.8 Periodic cleanup on shutdown

`asyncio.create_task` for the cleanup loop. If the server shuts down, the task is cancelled automatically. No cleanup-in-progress protection needed -- the DELETE queries are atomic.

---

## 10. File Changes Summary

### New files

| File | Purpose |
|---|---|
| `src/ai_mailbox/token_cleanup.py` | Expired OAuth code/token cleanup |
| `src/ai_mailbox/markdown.py` | Markdown rendering via mistune |
| `src/ai_mailbox/templates/error.html` | Unified error page template |
| `tests/test_token_cleanup.py` | Token cleanup tests |
| `tests/test_config_validation.py` | JWT secret and config validation tests |
| `tests/test_markdown.py` | Markdown rendering + XSS safety tests |
| `tests/test_error_pages.py` | Error page rendering tests (404, 403, 429, 500) |

### Modified files

| File | Changes |
|---|---|
| `pyproject.toml` | Add `mistune` dependency |
| `src/ai_mailbox/config.py` | Add `validate()`, `get_cors_origins()`, `ConfigurationError`, `allowed_origins` field, remove `keith_api_key`/`amy_api_key` |
| `src/ai_mailbox/server.py` | Call `config.validate()`, use `get_cors_origins()`, start cleanup task, register `is_ai_user` as Jinja2 global, register `markdown` filter |
| `src/ai_mailbox/web.py` | Add `_render_error()`, replace inline errors with error template, add HTMX detection, pass `projects` to compose template |
| `src/ai_mailbox/db/queries.py` | Add `get_distinct_projects()` query |
| `src/ai_mailbox/templates/base.html` | Add markdown CSS styles |
| `src/ai_mailbox/templates/partials/thread_view.html` | AI badge, markdown rendering for message body |
| `src/ai_mailbox/templates/partials/compose_form.html` | Project dropdown with allowAdditions, character count |
| `tests/test_web.py` | Error page tests, compose project dropdown tests |
| `tests/test_queries.py` | get_distinct_projects tests |

### Deleted files

| File | Reason |
|---|---|
| `src/ai_mailbox/auth.py` | Dead code -- legacy API key auth, not imported anywhere |

### Unchanged files

| File | Reason |
|---|---|
| `src/ai_mailbox/db/schema.py` | No DDL changes |
| `src/ai_mailbox/db/migrations/*` | No new migrations |
| `src/ai_mailbox/oauth.py` | Unchanged (cleanup runs externally) |
| `src/ai_mailbox/rate_limit.py` | Unchanged |
| `src/ai_mailbox/group_tokens.py` | Unchanged |
| `src/ai_mailbox/tools/*` | No MCP tool changes |
| `Dockerfile` | No new system deps (mistune is pure Python) |
| `railway.toml` | Unchanged |

---

## 11. Acceptance Criteria

### 11.1 JWT Secret Validation (Issue #2)

- [ ] Default secret + PostgreSQL `DATABASE_URL`: startup fails with `ConfigurationError`
- [ ] Default secret + SQLite (no `DATABASE_URL`): startup succeeds with logged warning
- [ ] Secret < 32 bytes: startup fails regardless of database
- [ ] Valid custom secret >= 32 bytes: startup succeeds, no warning
- [ ] `ConfigurationError` message includes remediation instructions

### 11.2 CORS Restriction (Issue #3)

- [ ] `MAILBOX_CORS_ORIGINS` unset: only Railway URL + localhost allowed
- [ ] `MAILBOX_CORS_ORIGINS="https://example.com,https://other.com"`: those origins + Railway + localhost
- [ ] Requests from unlisted origins receive no `Access-Control-Allow-Origin` header
- [ ] `allow_methods` restricted to GET, POST, OPTIONS
- [ ] `allow_headers` restricted to Authorization, Content-Type
- [ ] `allow_credentials` is True (for session cookies)

### 11.3 Token/Code Cleanup (Issue #1)

- [ ] `cleanup_expired_tokens()` deletes codes with `expires_at < now`
- [ ] `cleanup_expired_tokens()` deletes tokens with `expires_at < now`
- [ ] Non-expired records are preserved
- [ ] Cleanup runs once on startup
- [ ] Cleanup runs every 30 minutes via background task
- [ ] `/web/health` includes `last_cleanup_at` and `next_cleanup_at`
- [ ] Empty tables: cleanup returns `{codes_deleted: 0, tokens_deleted: 0}` without error

### 11.4 Dead Code Removal (Issue #16)

- [ ] `src/ai_mailbox/auth.py` deleted
- [ ] `keith_api_key` and `amy_api_key` removed from Config
- [ ] No import of `auth` module anywhere in codebase
- [ ] Full test suite passes after deletion

### 11.5 Error Pages

- [ ] 404: Navigating to `/web/conversation/nonexistent-id` renders error page with "Not Found" title and search icon
- [ ] 403: Accessing a conversation the user is not part of renders error page with "Forbidden" title and lock icon
- [ ] 429: Exceeding rate limit renders error page with "Too Many Requests" title
- [ ] 500: Unhandled exception renders error page (not Starlette default)
- [ ] All error pages include "Back to Inbox" link
- [ ] HTMX requests receive inline error messages, not full pages

### 11.6 Thread View: AI Badge

- [ ] Messages from users matching AI patterns show blue "AI" label next to author name
- [ ] Messages from regular users do not show the badge
- [ ] Badge renders in both full-page and HTMX partial loads

### 11.7 Thread View: Markdown Rendering

- [ ] Message body with `**bold**` renders as bold text
- [ ] Message body with `- list item` renders as a list
- [ ] Message body with `` `code` `` renders as inline code
- [ ] Message body with `<script>alert('xss')</script>` renders as escaped text (not executed)
- [ ] Plain text messages (no markdown) render correctly (no broken formatting)

### 11.8 Compose: Project Selector

- [ ] Project field is a dropdown populated from user's existing projects
- [ ] Dropdown allows typing new project names (allowAdditions)
- [ ] "general" is always present as an option
- [ ] Selected project is preserved on form validation errors

### 11.9 Compose: Character Count

- [ ] Character count displays below body textarea
- [ ] Count updates on each keystroke
- [ ] Count turns red when body exceeds 9,000 characters
- [ ] Body textarea has maxlength="10000"

### 11.10 AI UX UAT (browser verification -- required gate)

- [ ] **Login flow:** Navigate to login page, enter credentials, verify redirect to inbox
- [ ] **Thread view:** Click a conversation, verify messages render with markdown, AI badges visible on AI user messages
- [ ] **Compose flow:** Click Compose, verify project dropdown works with autocomplete, send a message, verify it appears in thread
- [ ] **Error pages:** Navigate to invalid conversation URL, verify 404 error page renders
- [ ] **Rate limit error:** Trigger rate limit, verify 429 error page renders
- [ ] **Character count:** Type in compose body, verify count updates

### 11.11 Tests

- [ ] test_config_validation.py: default secret detection, length check, production vs dev, CORS origins
- [ ] test_token_cleanup.py: expired deletion, non-expired preservation, empty table, counts
- [ ] test_markdown.py: rendering, XSS escape, plain text passthrough
- [ ] test_error_pages.py: 404/403/429/500 rendering, HTMX vs full-page, "Back to Inbox" link
- [ ] test_web.py additions: compose project dropdown, character count
- [ ] test_queries.py additions: get_distinct_projects
- [ ] Total test count >= 320 (up from 287)

### 11.12 Deployment

- [ ] MVP 1 Staging deploys and passes health check
- [ ] Health endpoint shows cleanup stats
- [ ] CORS restricted (verify via browser DevTools or curl)
- [ ] JWT validation prevents startup with default secret on staging (secret must be set in Railway env vars)
- [ ] Error pages render on deployed environment
- [ ] AI UX UAT passed on deployed environment

### 11.13 GitHub

- [ ] Issue #1 (token cleanup) closed with commit reference
- [ ] Issue #2 (JWT validation) closed with commit reference
- [ ] Issue #3 (CORS restriction) closed with commit reference
- [ ] Issue #16 (remove auth.py) closed with commit reference

---

## 12. Implementation Order (TDD Through Delivery)

1. **Config validation + ConfigurationError** -- `config.py` changes + `test_config_validation.py`
   - RED: tests for default secret detection (dev vs prod), length check, CORS origin parsing
   - GREEN: implement `validate()`, `get_cors_origins()`, `ConfigurationError`
   - VERIFY: tests pass locally

2. **Token cleanup** -- `token_cleanup.py` + `test_token_cleanup.py`
   - RED: tests for expired code deletion, expired token deletion, non-expired preservation, empty tables
   - GREEN: implement `cleanup_expired_tokens()`
   - VERIFY: tests pass locally

3. **Remove dead code** -- delete `auth.py`, remove API key config fields
   - RED: verify no imports break (grep for `from ai_mailbox.auth` and `import auth`)
   - GREEN: delete file, remove config fields
   - VERIFY: full test suite passes

4. **Markdown renderer** -- `markdown.py` + `test_markdown.py`
   - RED: tests for markdown rendering, XSS escape, plain text passthrough
   - GREEN: implement renderer with mistune
   - VERIFY: tests pass locally

5. **Error page template + helper** -- `error.html` + `test_error_pages.py`
   - RED: tests for 404/403/429/500 rendering, HTMX detection, error content
   - GREEN: implement `error.html` template, `_render_error()` helper, replace inline errors in `web.py`
   - VERIFY: tests pass locally

6. **Thread view enhancements** -- AI badge + markdown filter
   - RED: tests for AI badge rendering, markdown filter in template output
   - GREEN: implement `is_ai_user()`, register Jinja2 filter/global, update `thread_view.html`
   - VERIFY: tests pass locally

7. **Compose improvements** -- project dropdown + char count + `get_distinct_projects` query
   - RED: tests for project dropdown options, get_distinct_projects query, char count in HTML
   - GREEN: implement query, update `compose_form.html`, update web route to pass projects
   - VERIFY: tests pass locally

8. **Server integration** -- wire validation, CORS, cleanup task, Jinja2 extensions
   - RED: integration tests for startup validation, CORS headers, cleanup scheduling
   - GREEN: update `server.py` with all Sprint 3 wiring
   - VERIFY: full local test suite green (all tests, zero failures)

9. **Deploy to MVP 1 Staging**
   - VERIFY:
     - `/web/health` returns healthy with cleanup stats
     - CORS restricted (test with curl from disallowed origin)
     - Error pages render on navigation errors
     - Markdown renders in thread view

10. **AI UX UAT** (required gate)
    - Browser verification of all section 11.10 checks
    - Failures block sprint completion

11. **Human UAT** (required gate)
    - User verifies error pages, thread view, compose improvements, security config
    - Sprint not complete until passed

12. **GitHub cleanup**
    - Close #1, #2, #3, #16 with commit references

---

## 13. Dependency Addition

```toml
# pyproject.toml
dependencies = [
    # ... existing ...
    "mistune>=3.0",    # NEW - markdown rendering
]
```

`mistune` is pure Python, no C extensions, no system dependencies. Compatible with Python 3.13.

---

## 14. Resolved Design Decisions

1. **Single error template vs per-code templates.** One `error.html` template with context variables. Avoids file proliferation for what is essentially the same layout with different text/icons.

2. **JWT validation: warn vs fail.** Fail on production (PostgreSQL), warn on dev (SQLite). This prevents accidental deployment with default secret while keeping local development frictionless.

3. **CORS: config-driven vs hardcoded.** Environment variable for flexibility. Defaults are conservative (Railway URL + localhost only). Adding origins doesn't require code changes.

4. **Cleanup: cron job vs in-process.** In-process asyncio task. Railway doesn't have native cron. External cron (Railway cron jobs) would add operational complexity for a simple prune query. If the process restarts, cleanup runs on startup anyway.

5. **Markdown: mistune vs markdown vs commonmark.** `mistune` is the lightest pure-Python option (~2000 lines, no dependencies). The `markdown` library has optional C extensions. `commonmark` is heavier. For rendering message bodies, mistune is sufficient.

6. **AI badge: heuristic vs database field.** Heuristic for Sprint 3 (pattern matching on user_id). Sprint 5 adds `user_type` field and `is_ai` tracking per the roadmap. The heuristic is a temporary bridge.

7. **Project selector: dropdown vs free text.** Dropdown with `allowAdditions` combines discoverability (see existing projects) with flexibility (create new ones). Better UX than plain text input.
