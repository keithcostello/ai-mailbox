# Sprint 3 Spec: P0 Security + DaisyUI Migration

**Status:** DRAFT -- awaiting approval
**Branch:** mvp-1-staging
**Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
**GitHub Issues:** #1 (token cleanup), #2 (JWT validation), #3 (CORS restriction), #16 (remove auth.py)
**Depends on:** Sprint 2 (complete -- 287 tests, deployed)

---

## 1. Overview

Two parallel tracks: (A) close P0 security gaps (JWT validation, CORS restriction, token cleanup, dead code removal) and (B) migrate the web UI from Semantic UI 2.5.0 to DaisyUI 4 + Tailwind CSS with the `fantasy` theme. The migration rewrites all 8 templates, drops jQuery, adds dedicated error pages, AI user badges, and markdown rendering.

**What changes:** UI framework (Semantic UI -> DaisyUI/Tailwind), all template files, CDN dependencies (drop jQuery + Semantic UI, add Tailwind + DaisyUI), config validation, CORS middleware, token cleanup.

**What does NOT change:** MCP tool signatures, database schema DDL, rate limiting logic, group send confirmation protocol, three-table conversation model, HTMX integration (stays), Python backend logic (web.py route structure stays, only template rendering and error responses change).

---

## 2. JWT Secret Validation at Startup (Issue #2)

### 2.1 Problem

`config.py:16` defines a hardcoded default: `"change-me-in-production-minimum-32-bytes!"`. If `MAILBOX_JWT_SECRET` env var is missing, the server starts with this predictable secret.

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
- Valid custom secret >= 32 bytes: no warning, proceed

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

`server.py:349` sets `allow_origins=["*"]`. Permits any origin to make credentialed requests.

### 3.2 Solution

New config field `allowed_origins`. Environment variable `MAILBOX_CORS_ORIGINS` accepts comma-separated origins.

```python
# config.py
@dataclass
class Config:
    # ... existing fields ...
    allowed_origins: str = ""  # comma-separated, empty = Railway URL only

    def get_cors_origins(self) -> list[str]:
        """Return list of allowed CORS origins."""
        origins = []
        if self.allowed_origins:
            origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        origins.append("https://ai-mailbox-server-mvp-1-staging.up.railway.app")
        origins.append("http://localhost:8000")
        return list(set(origins))
```

### 3.3 Integration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.get_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)
```

---

## 4. OAuth Token/Code Cleanup (Issue #1)

### 4.1 Problem

`oauth_codes` and `oauth_tokens` tables accumulate expired records. No cleanup mechanism exists.

### 4.2 Solution

New module `src/ai_mailbox/token_cleanup.py`:

```python
def cleanup_expired_tokens(db) -> dict:
    """Delete expired OAuth codes and tokens. Returns counts."""
    now = time.time()
    codes_deleted = db.execute("DELETE FROM oauth_codes WHERE expires_at < ?", (now,))
    tokens_deleted = db.execute(
        "DELETE FROM oauth_tokens WHERE expires_at IS NOT NULL AND expires_at < ?", (int(now),)
    )
    return {"codes_deleted": codes_deleted, "tokens_deleted": tokens_deleted}
```

### 4.3 Scheduling

1. **On startup:** runs once after schema migration
2. **Periodic:** asyncio background task every 30 minutes

### 4.4 Health endpoint

Add to `/web/health`: `last_cleanup_at`, `next_cleanup_at`.

### 4.5 SQL compatibility

Both SQLite and PostgreSQL support `DELETE ... WHERE expires_at < ?` with numeric timestamps. `oauth_codes.expires_at` is FLOAT, `oauth_tokens.expires_at` is INTEGER. Both compare correctly against `time.time()`.

---

## 5. Code Cleanup: Remove auth.py (Issue #16)

Delete `src/ai_mailbox/auth.py` (dead code -- legacy API key auth, not imported anywhere).

Remove legacy API key config fields from `Config`: `keith_api_key`, `amy_api_key`, and their `os.environ.get` calls. The `api_key` column on users table is a schema change -- defer to future migration (TD-001).

---

## 6. UI Framework Migration: Semantic UI -> DaisyUI

### 6.1 Rationale

Semantic UI 2.5.0 (2018, unmaintained) produces a dated, prototype-quality UI. DaisyUI 4 on Tailwind CSS provides modern component classes, 32 built-in themes, and active maintenance. The `fantasy` theme (purple/violet primary, warm accents) was selected by the user.

### 6.2 CDN Swap

```html
<!-- REMOVE -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/semantic-ui@2.5.0/dist/semantic.min.css">
<script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/semantic-ui@2.5.0/dist/semantic.min.js"></script>

<!-- ADD -->
<link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
```

jQuery is removed entirely. HTMX stays (`https://unpkg.com/htmx.org@2.0.4`).

### 6.3 Theme Configuration

```html
<html lang="en" data-theme="fantasy">
```

The `fantasy` theme provides:
- Primary: purple/violet
- Secondary: teal
- Accent: gold/amber
- Base: warm off-white backgrounds
- Neutral: slate grays

No custom color overrides needed. DaisyUI semantic classes (`btn-primary`, `bg-base-100`, `text-base-content`) automatically resolve to theme colors.

### 6.4 Template Migration Map

Every template is rewritten. Class-for-class mapping:

| Semantic UI | DaisyUI/Tailwind |
|---|---|
| `ui button` | `btn` |
| `ui primary button` | `btn btn-primary` |
| `ui input` | `input input-bordered` |
| `ui form` | `form` (no wrapper class needed) |
| `ui segment` | `card bg-base-100 shadow` |
| `ui header` | `text-2xl font-bold` |
| `ui label` | `badge` |
| `ui menu` | `navbar bg-base-200` |
| `ui dropdown` | `select select-bordered` or `dropdown` component |
| `ui comments` | `chat` component (DaisyUI chat bubbles) |
| `ui comment` | `chat-bubble` |
| `ui divider` | `divider` |
| `ui negative message` | `alert alert-error` |
| `ui positive message` | `alert alert-success` |
| `ui grid` | Tailwind `grid grid-cols-*` |
| `ui inverted menu` | `navbar bg-neutral text-neutral-content` |

### 6.5 base.html Rewrite

```html
<!DOCTYPE html>
<html lang="en" data-theme="fantasy">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}AI Mailbox{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body class="bg-base-200 min-h-screen">
    {% if user_id %}
    <div class="navbar bg-neutral text-neutral-content shadow-lg">
        <div class="flex-1">
            <a class="btn btn-ghost text-xl" href="/web/inbox">AI Mailbox</a>
        </div>
        <div class="flex-none gap-2">
            <a class="btn btn-ghost btn-sm" href="/web/inbox">Inbox</a>
            <a class="btn btn-ghost btn-sm" hx-get="/web/compose" hx-target="#main-content" hx-push-url="true">Compose</a>
            <div class="divider divider-horizontal mx-0"></div>
            <span class="text-sm opacity-70">{{ display_name }}</span>
            <a class="btn btn-ghost btn-sm text-error" href="/web/logout">Logout</a>
        </div>
    </div>
    {% endif %}

    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

No afterSwap handler needed for DaisyUI -- components are pure CSS, no JS initialization required. This eliminates the Semantic UI dropdown re-init bug class entirely.

### 6.6 login.html Rewrite

Centered card layout with DaisyUI form controls:

```html
{% extends "base.html" %}
{% block content %}
<div class="flex items-center justify-center min-h-[calc(100vh-68px)]">
    <div class="card w-96 bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title justify-center text-2xl">Sign In</h2>
            {% if error %}
            <div class="alert alert-error">
                <span>{{ error }}</span>
            </div>
            {% endif %}
            <form method="POST" action="/web/login" class="space-y-4">
                <div class="form-control">
                    <label class="label"><span class="label-text">Username</span></label>
                    <input type="text" name="username" class="input input-bordered" required autofocus>
                </div>
                <div class="form-control">
                    <label class="label"><span class="label-text">Password</span></label>
                    <input type="password" name="password" class="input input-bordered" required>
                </div>
                <button type="submit" class="btn btn-primary w-full">Sign In</button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
```

### 6.7 inbox.html Rewrite

Two-panel layout using Tailwind grid. Sidebar with filter dropdowns (native `<select>` with DaisyUI classes -- no jQuery needed). Main content area for thread view or compose.

```html
{% extends "base.html" %}
{% block content %}
<div class="grid grid-cols-[320px_1fr] h-[calc(100vh-68px)]">
    <!-- Sidebar -->
    <div class="bg-base-100 border-r border-base-300 flex flex-col">
        <div class="p-3 border-b border-base-300 space-y-2">
            <select id="project-filter" class="select select-bordered select-sm w-full"
                    hx-get="/web/inbox/conversations" hx-target="#conversation-list"
                    hx-include="#participant-filter" name="project">
                <option value="">All Projects</option>
                {% for p in projects %}
                <option value="{{ p }}" {% if filter_project == p %}selected{% endif %}>{{ p }}</option>
                {% endfor %}
            </select>
            <select id="participant-filter" class="select select-bordered select-sm w-full"
                    hx-get="/web/inbox/conversations" hx-target="#conversation-list"
                    hx-include="#project-filter" name="participant">
                <option value="">All Participants</option>
                {% for u in all_users %}
                <option value="{{ u.id }}" {% if filter_participant == u.id %}selected{% endif %}>{{ u.display_name }}</option>
                {% endfor %}
            </select>
        </div>
        <div id="conversation-list" class="flex-1 overflow-y-auto">
            {% include "partials/conversation_list.html" %}
        </div>
    </div>

    <!-- Main content -->
    <div id="main-content" class="overflow-y-auto p-4">
        {% include "partials/empty_state.html" %}
    </div>
</div>
{% endblock %}
```

### 6.8 conversation_list.html Rewrite

Each conversation as a clickable card-like row with unread badge:

```html
{% for conv in conversations %}
<div class="px-3 py-2 hover:bg-base-200 cursor-pointer border-b border-base-300 {% if conv.unread_count > 0 %}bg-primary/5{% endif %}"
     hx-get="/web/conversation/{{ conv.id }}"
     hx-target="#main-content"
     hx-push-url="true">
    <div class="flex items-center justify-between">
        <div class="font-medium text-sm truncate flex-1">
            {{ conv.other_participants | join(', ') }}
        </div>
        {% if conv.unread_count > 0 %}
        <span class="badge badge-primary badge-sm">{{ conv.unread_count }}</span>
        {% endif %}
    </div>
    <div class="flex items-center gap-2 mt-0.5">
        <span class="badge badge-ghost badge-xs">{{ conv.project }}</span>
        {% if conv.type != 'direct' %}
        <span class="badge badge-outline badge-xs">Group</span>
        {% endif %}
    </div>
    <div class="text-xs text-base-content/60 truncate mt-0.5">{{ conv.last_message_preview }}</div>
    <div class="text-xs text-base-content/40 mt-0.5">{{ conv.last_message_at | relative_time }}</div>
</div>
{% endfor %}

{% if has_more %}
<div class="p-3 text-center">
    <button class="btn btn-ghost btn-sm"
            hx-get="/web/inbox/conversations?page={{ next_page }}&project={{ filter_project }}&participant={{ filter_participant }}"
            hx-target="#conversation-list"
            hx-swap="innerHTML">
        Load more
    </button>
</div>
{% endif %}

{% if not conversations %}
<div class="p-6 text-center text-base-content/50">
    <p>No conversations yet</p>
</div>
{% endif %}
```

### 6.9 thread_view.html Rewrite

DaisyUI `chat` component for message bubbles. Sender messages right-aligned (`chat-end`), received messages left-aligned (`chat-start`). AI badge as a DaisyUI badge.

```html
{% if error %}
<div class="alert alert-error mb-4"><span>{{ error }}</span></div>
{% endif %}

<div class="card bg-base-100 shadow">
    <div class="card-body">
        <!-- Header -->
        <div class="flex items-center justify-between">
            <div>
                <h3 class="card-title text-lg">
                    {% set others = [] %}
                    {% for p in participants if p != user_id %}
                        {% if others.append(p) %}{% endif %}
                    {% endfor %}
                    {{ others | join(', ') }}
                </h3>
                <div class="text-sm text-base-content/60">
                    {% if conversation.type == 'direct' %}Direct message
                    {% elif conversation.type == 'team_group' %}Group: {{ conversation.name }}
                    {% else %}Project group{% endif %}
                    &middot; {{ messages | length }} message{{ 's' if messages | length != 1 else '' }}
                    {% if conversation.project %}
                    <span class="badge badge-ghost badge-sm ml-1">{{ conversation.project }}</span>
                    {% endif %}
                </div>
            </div>
        </div>

        <div class="divider my-2"></div>

        <!-- Messages -->
        <div id="message-list" class="space-y-1 max-h-[calc(100vh-320px)] overflow-y-auto">
            {% for msg in messages %}
            <div class="chat {{ 'chat-end' if msg.from_user == user_id else 'chat-start' }}">
                <div class="chat-header text-sm">
                    {{ msg.from_user }}
                    {% if is_ai_user(msg.from_user) %}
                    <span class="badge badge-info badge-xs ml-1">AI</span>
                    {% endif %}
                    <time class="text-xs opacity-50 ml-1">{{ msg.created_at | relative_time }}</time>
                </div>
                <div class="chat-bubble {{ 'chat-bubble-primary' if msg.from_user == user_id else '' }}">
                    <div class="prose prose-sm max-w-none">{{ msg.body | markdown }}</div>
                </div>
                {% if msg.subject %}
                <div class="chat-footer text-xs opacity-50">Re: {{ msg.subject }}</div>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        <div class="divider my-2"></div>

        <!-- Reply form -->
        <form hx-post="/web/conversation/{{ conversation.id }}/reply"
              hx-target="#main-content"
              hx-swap="innerHTML"
              class="flex gap-2">
            <textarea name="body" rows="2" placeholder="Write a reply..."
                      class="textarea textarea-bordered flex-1" required></textarea>
            <button type="submit" class="btn btn-primary self-end">Reply</button>
        </form>
    </div>
</div>

<script>
// Refresh sidebar preserving filter state + auto-scroll
(function() {
    var project = document.getElementById('project-filter');
    var participant = document.getElementById('participant-filter');
    var pVal = project ? project.value : '';
    var partVal = participant ? participant.value : '';
    var url = '/web/inbox/conversations?project=' + encodeURIComponent(pVal) + '&participant=' + encodeURIComponent(partVal);
    htmx.ajax('GET', url, '#conversation-list');

    var el = document.getElementById('message-list');
    if (el) el.scrollTop = el.scrollHeight;
})();
</script>
```

### 6.10 compose_form.html Rewrite

```html
{% if error %}
<div class="alert alert-error mb-4"><span>{{ error }}</span></div>
{% endif %}
{% if success %}
<div class="alert alert-success mb-4"><span>{{ success }}</span></div>
{% endif %}

<div class="card bg-base-100 shadow">
    <div class="card-body">
        <h3 class="card-title text-lg">New Message</h3>

        <form hx-post="/web/compose" hx-target="#main-content" hx-swap="innerHTML"
              class="space-y-4 mt-2">
            <div class="form-control">
                <label class="label"><span class="label-text">To</span></label>
                <select name="to" class="select select-bordered w-full" required>
                    <option value="" disabled {{ 'selected' if not form_to }}>Select recipient</option>
                    {% for user in users %}
                    <option value="{{ user.id }}" {% if form_to == user.id %}selected{% endif %}>
                        {{ user.display_name }} ({{ user.id }})
                    </option>
                    {% endfor %}
                </select>
            </div>

            <div class="form-control">
                <label class="label"><span class="label-text">Project</span></label>
                <select name="project" id="project-selector" class="select select-bordered w-full">
                    <option value="general" {{ 'selected' if (form_project or 'general') == 'general' }}>general</option>
                    {% for p in projects %}
                    {% if p != 'general' %}
                    <option value="{{ p }}" {{ 'selected' if form_project == p }}>{{ p }}</option>
                    {% endif %}
                    {% endfor %}
                </select>
            </div>

            <div class="form-control">
                <label class="label"><span class="label-text">Subject (optional)</span></label>
                <input type="text" name="subject" class="input input-bordered w-full"
                       value="{{ form_subject or '' }}" placeholder="Subject">
            </div>

            <div class="form-control">
                <label class="label"><span class="label-text">Message</span></label>
                <textarea name="body" id="compose-body" rows="5"
                          class="textarea textarea-bordered w-full" maxlength="10000"
                          placeholder="Write your message (markdown supported)..."
                          required oninput="updateCharCount()">{{ form_body or '' }}</textarea>
                <label class="label">
                    <span class="label-text-alt" id="char-count">0 / 10,000</span>
                </label>
            </div>

            <button type="submit" class="btn btn-primary">Send Message</button>
        </form>
    </div>
</div>

<script>
function updateCharCount() {
    var body = document.getElementById('compose-body');
    var count = document.getElementById('char-count');
    var len = body.value.length;
    count.textContent = len.toLocaleString() + ' / 10,000';
    count.className = len > 9000 ? 'label-text-alt text-error' : 'label-text-alt';
}
updateCharCount();
</script>
```

### 6.11 empty_state.html Rewrite

```html
<div class="flex items-center justify-center h-full text-base-content/40">
    <div class="text-center">
        <svg class="w-16 h-16 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
        </svg>
        <p>Select a conversation or compose a new message</p>
    </div>
</div>
```

### 6.12 error.html (NEW)

```html
{% extends "base.html" %}
{% block title %}{{ error_title }} - AI Mailbox{% endblock %}
{% block content %}
<div class="flex items-center justify-center min-h-[calc(100vh-68px)]">
    <div class="card w-96 bg-base-100 shadow-xl">
        <div class="card-body items-center text-center">
            <div class="text-6xl font-bold text-primary/30">{{ error_code }}</div>
            <h2 class="card-title">{{ error_title }}</h2>
            <p class="text-base-content/60">{{ error_message }}</p>
            <div class="card-actions mt-4">
                <a href="/web/inbox" class="btn btn-primary">Back to Inbox</a>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### 6.13 health.html Rewrite

```html
{% extends "base.html" %}
{% block content %}
<div class="container mx-auto p-8 max-w-2xl">
    <div class="card bg-base-100 shadow">
        <div class="card-body">
            <h2 class="card-title">System Health</h2>
            <div class="overflow-x-auto">
                <table class="table">
                    <tbody>
                        {% for key, value in health.items() %}
                        <tr><td class="font-medium">{{ key }}</td><td>{{ value }}</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### 6.14 jQuery Removal

All Semantic UI jQuery initialization code is deleted:
- `base.html`: Remove `htmx:afterSwap` handler that re-initialized `.ui.dropdown`
- `compose_form.html`: Remove `$('.ui.dropdown').dropdown()` call
- `inbox.html`: Remove all `$(...).dropdown({clearable: true})` calls

DaisyUI dropdowns are pure CSS (using `<details>` or native `<select>`). No initialization needed. This eliminates the entire class of Semantic UI afterSwap re-initialization bugs.

Filter dropdowns in the sidebar use native `<select>` elements with HTMX `hx-get` triggers on change. Clearing a filter is done by selecting the "All Projects" / "All Participants" default option.

---

## 7. Web UI: Error Pages

### 7.1 Helper function

```python
# web.py
def _render_error(status_code: int, title: str, message: str, request=None, **ctx) -> HTMLResponse:
    html = templates.TemplateResponse("error.html", {
        "request": request,
        "error_code": status_code,
        "error_title": title,
        "error_message": message,
        "user_id": ctx.get("user_id"),
        "display_name": ctx.get("display_name"),
    })
    return HTMLResponse(html.body.decode(), status_code=status_code)
```

### 7.2 Error configurations

| Code | Title | Message |
|------|-------|---------|
| 404 | Not Found | The page or conversation you requested does not exist. |
| 403 | Forbidden | You do not have permission to access this resource. |
| 429 | Too Many Requests | You've made too many requests. Wait a moment and try again. |
| 500 | Server Error | Something went wrong. Try again or contact support. |

### 7.3 HTMX vs full-page detection

```python
is_htmx = request.headers.get("HX-Request") == "true"
if is_htmx:
    return HTMLResponse('<div class="alert alert-error"><span>Not found</span></div>', status_code=404)
else:
    return _render_error(404, "Not Found", "...", request=request)
```

### 7.4 Global 500 handler

Starlette exception handler for unhandled errors, rendering `error.html` instead of default.

---

## 8. Thread View Enhancements

### 8.1 AI User Badge

Heuristic identification of AI users:

```python
_AI_PATTERNS = {"claude", "gpt", "bot", "gemini", "copilot"}

def _is_ai_user(user_id: str) -> bool:
    lower = user_id.lower()
    return any(pat in lower for pat in _AI_PATTERNS) or lower.startswith("ai-")
```

Registered as Jinja2 global. Renders as `<span class="badge badge-info badge-xs">AI</span>` next to the author name in chat bubbles. Sprint 5 adds explicit `is_ai` DB field.

### 8.2 Mark-as-read on view

Already implemented (`web.py:262-264`). No changes needed.

### 8.3 Markdown rendering

New module `src/ai_mailbox/markdown.py` using `mistune`:

```python
import mistune

_renderer = mistune.create_markdown(escape=True, plugins=['strikethrough', 'table'])

def render_markdown(text: str) -> str:
    """Render markdown text to safe HTML."""
    return _renderer(text)
```

Registered as Jinja2 filter `markdown`. Used in thread view: `{{ msg.body | markdown }}`. The `escape=True` parameter prevents XSS. Output wrapped in DaisyUI `prose prose-sm` class for typography.

---

## 9. Compose Improvements

### 9.1 Project selector

Native `<select>` dropdown populated from `get_distinct_projects(db, user_id)`. "general" always present. Users select from existing projects or can be extended with a custom input approach in future sprints.

### 9.2 Character count

Vanilla JS `oninput` handler on body textarea. Shows `len / 10,000`. Text turns `text-error` (DaisyUI) above 9,000 chars. `maxlength="10000"` on the textarea for client-side enforcement.

---

## 10. Edge Cases

### 10.1 JWT validation with empty string

`MAILBOX_JWT_SECRET=""` -- length check (< 32) catches as fatal.

### 10.2 CORS with no env var set

Defaults to Railway URL + localhost only.

### 10.3 Token cleanup on empty tables

DELETE returns 0, no error.

### 10.4 Markdown XSS

`mistune.create_markdown(escape=True)` escapes HTML entities. `<script>` renders as literal text.

### 10.5 AI badge false positives

User named "robotics-bob" matches "bot". Acceptable for Sprint 3. Sprint 5 adds authoritative `is_ai` field.

### 10.6 HTMX error page rendering

`HX-Request` header detection prevents nested documents. HTMX gets inline alerts, direct navigation gets full error pages.

### 10.7 Tailwind CDN in production

The Tailwind CDN play script (`cdn.tailwindcss.com`) is intended for development. For production, a build step with `tailwindcss` CLI would produce an optimized CSS file. Acceptable for alpha/staging -- track as tech debt for Sprint 6+ production hardening.

### 10.8 DaisyUI chat bubble direction

`chat-end` (right-aligned) for current user's messages, `chat-start` (left-aligned) for others. The `msg.from_user == user_id` comparison determines direction.

---

## 11. File Changes Summary

### New files

| File | Purpose |
|---|---|
| `src/ai_mailbox/token_cleanup.py` | Expired OAuth code/token cleanup |
| `src/ai_mailbox/markdown.py` | Markdown rendering via mistune |
| `src/ai_mailbox/templates/error.html` | Unified error page template (DaisyUI) |
| `tests/test_token_cleanup.py` | Token cleanup tests |
| `tests/test_config_validation.py` | JWT secret and config validation tests |
| `tests/test_markdown.py` | Markdown rendering + XSS safety tests |
| `tests/test_error_pages.py` | Error page rendering tests (404, 403, 429, 500) |

### Rewritten files (Semantic UI -> DaisyUI)

| File | Changes |
|---|---|
| `src/ai_mailbox/templates/base.html` | Full rewrite: DaisyUI CDN, fantasy theme, navbar, remove jQuery + afterSwap handler |
| `src/ai_mailbox/templates/login.html` | Full rewrite: DaisyUI card + form controls |
| `src/ai_mailbox/templates/inbox.html` | Full rewrite: Tailwind grid layout, DaisyUI select filters |
| `src/ai_mailbox/templates/health.html` | Full rewrite: DaisyUI card + table |
| `src/ai_mailbox/templates/partials/thread_view.html` | Full rewrite: DaisyUI chat bubbles, AI badge, markdown rendering, vanilla JS |
| `src/ai_mailbox/templates/partials/compose_form.html` | Full rewrite: DaisyUI form controls, project dropdown, char count |
| `src/ai_mailbox/templates/partials/conversation_list.html` | Full rewrite: Tailwind layout, DaisyUI badges |
| `src/ai_mailbox/templates/partials/empty_state.html` | Full rewrite: Tailwind centered layout, SVG icon |

### Modified files

| File | Changes |
|---|---|
| `pyproject.toml` | Add `mistune` dependency |
| `src/ai_mailbox/config.py` | Add `validate()`, `get_cors_origins()`, `ConfigurationError`, `allowed_origins` field, remove `keith_api_key`/`amy_api_key` |
| `src/ai_mailbox/server.py` | Call `config.validate()`, use `get_cors_origins()`, start cleanup task, register `is_ai_user` as Jinja2 global, register `markdown` filter |
| `src/ai_mailbox/web.py` | Add `_render_error()`, replace inline errors with error template, add HTMX detection, pass `projects` to compose template |
| `src/ai_mailbox/db/queries.py` | Add `get_distinct_projects()` query |
| `tests/test_web.py` | Error page tests, compose project dropdown tests, DaisyUI class assertions |
| `tests/test_queries.py` | get_distinct_projects tests |

### Deleted files

| File | Reason |
|---|---|
| `src/ai_mailbox/auth.py` | Dead code -- legacy API key auth |

### Unchanged files

| File | Reason |
|---|---|
| `src/ai_mailbox/db/schema.py` | No DDL changes |
| `src/ai_mailbox/db/migrations/*` | No new migrations |
| `src/ai_mailbox/oauth.py` | Unchanged |
| `src/ai_mailbox/rate_limit.py` | Unchanged |
| `src/ai_mailbox/group_tokens.py` | Unchanged |
| `src/ai_mailbox/tools/*` | No MCP tool changes |
| `Dockerfile` | No new system deps |
| `railway.toml` | Unchanged |

---

## 12. Acceptance Criteria

### 12.1 JWT Secret Validation (Issue #2)

- [ ] Default secret + PostgreSQL `DATABASE_URL`: startup fails with `ConfigurationError`
- [ ] Default secret + SQLite (no `DATABASE_URL`): startup succeeds with logged warning
- [ ] Secret < 32 bytes: startup fails regardless of database
- [ ] Valid custom secret >= 32 bytes: startup succeeds, no warning

### 12.2 CORS Restriction (Issue #3)

- [ ] `MAILBOX_CORS_ORIGINS` unset: only Railway URL + localhost allowed
- [ ] `MAILBOX_CORS_ORIGINS` set: those origins + Railway + localhost
- [ ] `allow_methods` restricted to GET, POST, OPTIONS
- [ ] `allow_credentials` is True

### 12.3 Token/Code Cleanup (Issue #1)

- [ ] `cleanup_expired_tokens()` deletes expired codes and tokens
- [ ] Non-expired records preserved
- [ ] Runs on startup and every 30 minutes
- [ ] `/web/health` includes cleanup timestamps
- [ ] Empty tables: returns zero counts without error

### 12.4 Dead Code Removal (Issue #16)

- [ ] `src/ai_mailbox/auth.py` deleted
- [ ] `keith_api_key` and `amy_api_key` removed from Config
- [ ] Full test suite passes after deletion

### 12.5 DaisyUI Migration

- [ ] All templates use DaisyUI/Tailwind classes (no Semantic UI classes remain)
- [ ] `data-theme="fantasy"` applied to `<html>` element
- [ ] jQuery completely removed (no `<script>` tag, no `$()` calls)
- [ ] Semantic UI CDN completely removed
- [ ] DaisyUI CDN + Tailwind CDN loaded
- [ ] HTMX stays functional (partial swaps, `hx-get`, `hx-post`, `hx-target`)
- [ ] Navbar renders with neutral background and navigation links
- [ ] Filter dropdowns use native `<select>` with HTMX triggers
- [ ] No afterSwap JS re-initialization needed

### 12.6 Error Pages

- [ ] 404: renders DaisyUI card with error code, title, message, "Back to Inbox" link
- [ ] 403: renders with "Forbidden" title
- [ ] 429: renders with "Too Many Requests" title
- [ ] 500: renders error page (not Starlette default)
- [ ] HTMX requests receive inline `alert` elements, not full pages

### 12.7 Thread View

- [ ] Messages render as DaisyUI chat bubbles
- [ ] Current user's messages right-aligned (`chat-end`), others left-aligned (`chat-start`)
- [ ] AI users show `badge badge-info` "AI" label next to name
- [ ] Message bodies render markdown (bold, lists, code, tables)
- [ ] XSS in message body renders as escaped text
- [ ] Reply form uses DaisyUI `textarea` + `btn` components

### 12.8 Compose

- [ ] Recipient selector is DaisyUI `select` with all users
- [ ] Project selector populated from user's existing projects
- [ ] Character count updates on keystroke, turns red > 9,000 chars
- [ ] Form validation errors render as DaisyUI `alert-error`
- [ ] Successful send shows DaisyUI `alert-success`

### 12.9 AI UX UAT (browser verification -- required gate)

- [ ] **Login flow:** Login page renders with DaisyUI card, credentials work, redirects to inbox
- [ ] **Inbox:** Two-panel layout, sidebar with filter dropdowns, conversations with badges
- [ ] **Thread view:** Chat bubbles with correct alignment, AI badges visible, markdown rendered
- [ ] **Compose:** Project dropdown populated, character count functional, send works
- [ ] **Error pages:** Navigate to invalid URL, verify 404 error page renders with DaisyUI styling
- [ ] **Theme:** Fantasy theme colors visible (purple primary, warm accents)
- [ ] **No jQuery:** Browser console shows no jQuery-related errors

### 12.10 Tests

- [ ] test_config_validation.py: default secret detection, length check, production vs dev, CORS origins
- [ ] test_token_cleanup.py: expired deletion, non-expired preservation, empty table, counts
- [ ] test_markdown.py: rendering, XSS escape, plain text passthrough
- [ ] test_error_pages.py: 404/403/429/500 rendering, HTMX vs full-page
- [ ] test_web.py additions: DaisyUI class presence in rendered HTML, compose improvements
- [ ] test_queries.py additions: get_distinct_projects
- [ ] Total test count >= 320 (up from 287)

### 12.11 Deployment

- [ ] MVP 1 Staging deploys and passes health check
- [ ] Health endpoint shows cleanup stats
- [ ] CORS restricted
- [ ] All pages render with DaisyUI fantasy theme
- [ ] AI UX UAT passed on deployed environment

### 12.12 GitHub

- [ ] Issue #1 (token cleanup) closed with commit reference
- [ ] Issue #2 (JWT validation) closed with commit reference
- [ ] Issue #3 (CORS restriction) closed with commit reference
- [ ] Issue #16 (remove auth.py) closed with commit reference

---

## 13. Implementation Order (TDD Through Delivery)

1. **Config validation + CORS** -- `config.py` changes + `test_config_validation.py`
   - RED: tests for default secret detection (dev vs prod), length check, CORS origin parsing
   - GREEN: implement `validate()`, `get_cors_origins()`, `ConfigurationError`, `allowed_origins`
   - VERIFY: tests pass locally

2. **Token cleanup** -- `token_cleanup.py` + `test_token_cleanup.py`
   - RED: tests for expired code/token deletion, non-expired preservation, empty tables
   - GREEN: implement `cleanup_expired_tokens()`
   - VERIFY: tests pass locally

3. **Remove dead code** -- delete `auth.py`, remove API key config fields
   - RED: verify no imports break
   - GREEN: delete file, remove config fields
   - VERIFY: full test suite passes

4. **Markdown renderer** -- `markdown.py` + `test_markdown.py`
   - RED: tests for markdown rendering, XSS escape, plain text passthrough
   - GREEN: implement renderer with mistune
   - VERIFY: tests pass locally

5. **DaisyUI template migration** -- rewrite all 8 templates + `error.html`
   - RED: tests for DaisyUI class presence in rendered HTML, no Semantic UI classes, no jQuery, error page content
   - GREEN: rewrite `base.html`, `login.html`, `inbox.html`, `health.html`, all partials, new `error.html`
   - VERIFY: tests pass locally

6. **Web route updates** -- error handling, HTMX detection, compose improvements
   - RED: tests for `_render_error()`, HTMX detection, project dropdown data, character count HTML
   - GREEN: update `web.py`, add `get_distinct_projects` query, wire `is_ai_user` + `markdown` filter
   - VERIFY: tests pass locally

7. **Server integration** -- wire validation, CORS, cleanup task, Jinja2 extensions
   - RED: integration tests for startup validation, CORS headers, cleanup scheduling
   - GREEN: update `server.py` with all Sprint 3 wiring
   - VERIFY: full local test suite green (all tests, zero failures)

8. **Deploy to MVP 1 Staging**
   - VERIFY:
     - `/web/health` returns healthy with cleanup stats
     - All pages render with DaisyUI fantasy theme
     - CORS restricted
     - Error pages render

9. **AI UX UAT** (required gate)
   - Browser verification of all section 12.9 checks
   - Failures block sprint completion

10. **Human UAT** (required gate)
    - User verifies DaisyUI design quality, error pages, thread view, compose
    - Sprint not complete until passed

11. **GitHub cleanup**
    - Close #1, #2, #3, #16 with commit references

---

## 14. Dependency Changes

```toml
# pyproject.toml
dependencies = [
    # ... existing ...
    "mistune>=3.0",    # NEW - markdown rendering
]
```

No DaisyUI or Tailwind Python dependencies -- both are CDN-only.

---

## 15. Resolved Design Decisions

1. **DaisyUI fantasy theme over Semantic UI.** User evaluated alternatives and selected DaisyUI with `fantasy` theme. Semantic UI 2.5.0 is unmaintained (2018) and produces dated UI. DaisyUI is actively maintained, provides 32 themes, and its pure-CSS components eliminate the jQuery re-initialization bug class entirely.

2. **jQuery removal.** DaisyUI components are pure CSS. HTMX handles all dynamic behavior. No JavaScript framework needed. Filter dropdowns use native `<select>` with HTMX triggers instead of Semantic UI's jQuery-dependent dropdown widget.

3. **Chat bubbles for messages.** DaisyUI's `chat` component with `chat-start`/`chat-end` alignment provides a modern messaging UX (similar to iMessage/WhatsApp). Better than the flat comment list in Semantic UI.

4. **Tailwind CDN for now.** The play CDN (`cdn.tailwindcss.com`) is not recommended for production but is acceptable for alpha/staging. Production hardening (Sprint 6+) would add a `tailwindcss` build step for optimized CSS. Tracked as edge case 10.7.

5. **Native `<select>` for dropdowns.** Instead of DaisyUI's `<details>`-based dropdown (which has accessibility issues), use native `<select>` elements styled with DaisyUI classes. Works with HTMX out of the box, no JS initialization, accessible by default.

6. **Single error template.** One `error.html` with context variables. Error code displayed as large number, title, message, and "Back to Inbox" button. Consistent across all error types.

7. **JWT validation: warn vs fail.** Fail on production (PostgreSQL), warn on dev (SQLite).

8. **Cleanup: in-process asyncio.** Railway doesn't have native cron. In-process task is simplest.

9. **Markdown: mistune.** Lightest pure-Python option. `escape=True` for XSS safety.

10. **AI badge: heuristic.** Pattern matching for Sprint 3. DB field in Sprint 5.
