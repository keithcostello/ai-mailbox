# Sprint 6 Spec: Self-Service Registration + Settings + Onboarding

**Status:** APPROVED -- GitHub OAuth only (Google deferred)
**Branch:** mvp-1-staging
**Railway Environment:** MVP 1 Staging (ai-mailbox-server-mvp-1-staging.up.railway.app)
**GitHub Issues:** #13 (version string mismatch), new issue for self-service registration
**Depends on:** Sprint 5 (complete -- 424 tests, deployed)

---

## 1. Overview

Four deliverables: (A) Google and GitHub OAuth replacing the password-based web login, (B) invite-only registration mode for alpha, (C) user settings page, (D) generic README and version fix.

**What changes:** New migration (006), new dependency (authlib), Google/GitHub OAuth login flows, invite table, settings page route, updated login/navbar templates, generic README, version bump.

**What does NOT change:** MCP OAuth provider protocol (Claude Desktop still authenticates via the existing MailboxOAuthProvider flow), rate limiting, group send confirmation, search, HTMX polling, CORS/JWT validation, DaisyUI corporate theme, three-table conversation model.

---

## 2. OAuth Architecture

### 2.1 Two Auth Paths (Unchanged Principle)

The system has two authentication paths that must coexist:

1. **MCP OAuth** (for Claude Desktop and AI agents) -- Uses `MailboxOAuthProvider` which implements the MCP SDK's `OAuthAuthorizationServerProvider`. This flow presents a login page at `/login`, user authenticates, gets an authorization code, which the MCP SDK exchanges for a JWT access token. **This path stays as-is.** Password-based login remains available for MCP clients.

2. **Web UI login** (for humans in browsers) -- Currently uses a password form at `/web/login`. **Sprint 6 replaces this with Google/GitHub OAuth buttons**, while keeping password login as a fallback for seeded users (keith, amy) during development.

### 2.2 Web OAuth Flow (New)

```
User visits /web/login
  -> Clicks "Sign in with Google" (or GitHub)
  -> Redirect to Google/GitHub authorization endpoint
  -> User authenticates with Google/GitHub
  -> Google/GitHub redirects to /web/oauth/callback?code=...&state=...
  -> Server exchanges code for tokens via authlib
  -> Server fetches user info (email, name, avatar)
  -> Server checks invite list (if invite-only mode on)
  -> Server creates or updates user record
  -> Server sets session JWT cookie
  -> Redirect to /web/inbox
```

### 2.3 Provider Configuration

| Provider | Env Vars | Scopes | User Info Fields |
|----------|----------|--------|-----------------|
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `openid email profile` | email, name, picture |
| GitHub | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | `user:email read:user` | email, login, name, avatar_url |

**When OAuth is not configured** (env vars missing): the login page shows only the password form, identical to current behavior. This keeps local development simple -- no Google/GitHub app registration needed.

### 2.4 User ID Generation

OAuth users need a deterministic `user_id` (the primary key). Strategy:

- Google: `g-{email_prefix}` (e.g., `g-keith` for `keith@gmail.com`). If collision, append numeric suffix (`g-keith-2`).
- GitHub: `gh-{github_login}` (e.g., `gh-keithdev`). If collision, append suffix.

The email is stored in the new `email` column for deduplication. On subsequent logins, the system looks up the user by `email + auth_provider`, not by user_id.

### 2.5 Returning User Lookup

```python
def find_or_create_oauth_user(db, *, email, name, avatar_url, provider) -> str:
    """Find existing user by email+provider, or create new one."""
    existing = db.fetchone(
        "SELECT id FROM users WHERE email = ? AND auth_provider = ?",
        (email, provider),
    )
    if existing:
        # Update name/avatar on each login (may change on provider side)
        db.execute(
            "UPDATE users SET display_name = ?, avatar_url = ? WHERE id = ?",
            (name, avatar_url, existing["id"]),
        )
        db.commit()
        return existing["id"]
    # Create new user
    user_id = _generate_user_id(db, email, provider)
    db.execute(
        """INSERT INTO users (id, display_name, api_key, password_hash, email, auth_provider, avatar_url)
           VALUES (?, ?, ?, '', ?, ?, ?)""",
        (user_id, name, f"oauth-{user_id}", email, provider, avatar_url),
    )
    db.commit()
    return user_id
```

---

## 3. Invite-Only Mode

### 3.1 Configuration

New env var: `MAILBOX_INVITE_ONLY` (default `true` for alpha).

When `true`, OAuth registration is restricted to emails in the `user_invites` table. Password-based login for existing users (keith, amy) is unaffected.

### 3.2 user_invites Table

```sql
CREATE TABLE IF NOT EXISTS user_invites (
    email VARCHAR(255) PRIMARY KEY,
    invited_by VARCHAR(100) REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);
```

### 3.3 Invite Check Flow

In the OAuth callback, after fetching user info from Google/GitHub:

```python
if config.invite_only:
    invite = db.fetchone(
        "SELECT * FROM user_invites WHERE email = ?", (email,)
    )
    if invite is None:
        # Existing user logging back in? Allow if user already exists.
        existing = db.fetchone(
            "SELECT id FROM users WHERE email = ? AND auth_provider = ?",
            (email, provider),
        )
        if existing is None:
            return redirect_to_login(error="not_invited")
    elif invite["used_at"] is None:
        # Mark invite as used
        db.execute(
            "UPDATE user_invites SET used_at = ? WHERE email = ?",
            (_now(), email),
        )
        db.commit()
```

### 3.4 Seeding Invites

`_seed_users` gains invite seeding. Two approaches (depending on config):

```python
# If MAILBOX_INVITED_EMAILS is set, seed those
invited_emails = config.invited_emails  # comma-separated from env
for email in invited_emails:
    db.execute(
        """INSERT INTO user_invites (email, invited_by) VALUES (?, 'keith')
           ON CONFLICT (email) DO NOTHING""",
        (email,),
    )
```

New env var: `MAILBOX_INVITED_EMAILS` -- comma-separated list of emails to pre-seed into `user_invites`. Only used during startup seeding. Empty by default.

---

## 4. User Settings Page

### 4.1 Route

`GET /web/settings` -- authenticated. Renders `settings.html`.

### 4.2 Layout

```
+----------------------------------------------------------+
|  Settings                                                 |
+----------------------------------------------------------+
|                                                           |
|  Display Name    [Keith               ] [Save]            |
|                                                           |
|  Email           keith@gmail.com                          |
|  Auth Provider   google                                   |
|  User Type       human                                    |
|  Session Mode    persistent                               |
|  Member Since    April 5, 2026                            |
|                                                           |
+----------------------------------------------------------+
```

- Display name is the only editable field (text input + Save button via HTMX POST)
- All other fields are read-only, displayed as plain text with monochrome labels
- Follows corporate design system: borders, no shadows, compact spacing

### 4.3 Update Route

`POST /web/settings` -- updates display_name. Returns updated settings page (HTMX swap) or a success indicator.

```python
@app.route("/web/settings", methods=["POST"])
async def web_settings_update(request):
    user_id = _get_session_user(request)
    form = await request.form()
    new_name = form.get("display_name", "").strip()
    if not new_name or len(new_name) > 100:
        return _render("settings.html", error="Invalid display name")
    db.execute(
        "UPDATE users SET display_name = ? WHERE id = ?",
        (new_name, user_id),
    )
    db.commit()
    return _render("settings.html", success=True)
```

### 4.4 Navbar Addition

Add "Settings" link to navbar, placed after the display name (before Logout):

```html
<a href="/web/settings" class="btn btn-ghost btn-xs font-normal">Settings</a>
```

---

## 5. Migration 006

New file: `src/ai_mailbox/db/migrations/006_oauth_registration.sql`

```sql
-- Sprint 6: OAuth registration, invite-only mode

-- OAuth identity fields on users
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'local';
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Invite-only registration
CREATE TABLE IF NOT EXISTS user_invites (
    email VARCHAR(255) PRIMARY KEY,
    invited_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);

-- Index for OAuth user lookup
CREATE INDEX IF NOT EXISTS idx_users_email_provider ON users(email, auth_provider);
```

**SQLite compatibility:** All statements use standard SQL supported by SQLite. `ALTER TABLE ADD COLUMN IF NOT EXISTS` works on SQLite 3.35+. The `VARCHAR` types are stored as TEXT in SQLite (acceptable). No PostgreSQL-only section needed for this migration.

**Backfill for existing users:** `email` and `avatar_url` are nullable. `auth_provider` defaults to `'local'` which correctly describes keith and amy's password-based accounts.

---

## 6. Config Changes

```python
@dataclass
class Config:
    # ... existing fields ...
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    invite_only: bool = True
    invited_emails: str = ""  # comma-separated, seeded at startup
```

New env vars:

| Env Var | Default | Purpose |
|---------|---------|---------|
| `GOOGLE_CLIENT_ID` | "" | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | "" | Google OAuth client secret |
| `GITHUB_CLIENT_ID` | "" | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | "" | GitHub OAuth client secret |
| `MAILBOX_INVITE_ONLY` | "true" | Require invite for new OAuth users |
| `MAILBOX_INVITED_EMAILS` | "" | Comma-separated emails to pre-seed as invites |

**OAuth availability logic:** Google OAuth is available when both `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set. Same for GitHub. Login page renders buttons only for configured providers.

---

## 7. New Dependency

**authlib** (MIT license, well-maintained) for OAuth client functionality:

```
authlib>=1.3
```

Authlib integrates with Starlette and handles:
- OAuth 2.0 authorization code flow
- PKCE support
- Google and GitHub provider specifics
- Token exchange
- OpenID Connect (Google)

Add to `pyproject.toml` dependencies and Dockerfile will pick it up via `pip install .`.

---

## 8. Login Page Changes

### 8.1 Web Login (`/web/login`)

Replace the current password-only form with a template that conditionally shows:

1. **OAuth buttons** (when providers are configured):
   - "Sign in with Google" button (Google-branded, links to `/web/oauth/google`)
   - "Sign in with GitHub" button (GitHub-branded, links to `/web/oauth/github`)
2. **Divider** ("or sign in with password")
3. **Password form** (always shown, for seeded users and development)
4. **Error messages** (not_invited, auth_failed, etc.)

Design: corporate theme. Centered card. Max-width 400px. Borders, no shadows.

### 8.2 MCP Login (`/login`)

The existing MCP login page (rendered by `MailboxOAuthProvider.login_page_html()`) stays password-only. MCP clients (Claude Desktop) authenticate via username/password through this page. Adding OAuth buttons to this flow would require a more complex redirect chain that's not worth the complexity for alpha. MCP OAuth will gain social login in a future sprint if needed.

### 8.3 New Web Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/web/oauth/{provider}` | GET | Initiate OAuth flow (redirect to Google/GitHub) |
| `/web/oauth/callback` | GET | Handle OAuth callback (code exchange, user create/lookup) |

---

## 9. Edge Cases

### 9.1 Email collision across providers

User signs in with Google (keith@gmail.com), later tries GitHub (same email). Since lookup is `email + auth_provider`, these are treated as separate accounts. For alpha, this is acceptable. A future sprint can add account linking.

### 9.2 OAuth provider down

If Google/GitHub auth fails, the callback shows an error on the login page. Password login remains available as fallback.

### 9.3 No OAuth configured (local dev)

Login page shows only the password form, exactly as it does today. No behavioral change for developers who don't set up Google/GitHub apps.

### 9.4 Invite check for returning users

A user who previously registered via OAuth can always log back in, even if their email is removed from the invite list. The invite check only gates first-time registration.

### 9.5 Display name update propagation

When a user changes their display_name via settings, it takes effect immediately. Existing messages retain the sender name at the time they were sent (messages store `from_user` as user_id, display_name is looked up at render time, so the update is retroactive in the UI). This is the expected behavior -- like changing your Slack display name.

### 9.6 OAuth callback CSRF

The OAuth state parameter prevents CSRF attacks. Authlib generates and validates state automatically. The state is stored in a session cookie during the redirect.

### 9.7 Avatar URL usage

`avatar_url` from Google/GitHub is stored but not rendered in Sprint 6. The existing initials-based avatars (colored circles with first letter) remain. Avatar rendering is deferred to a future polish sprint to keep scope manageable.

### 9.8 Version string

Issue #13: `__init__.py` has `0.1.0`, pyproject.toml has `0.1.0`, but git history references `v0.2.1`. Sprint 6 bumps both to `0.6.0` (matching sprint number) to establish a clean baseline.

---

## 10. README Rewrite

Replace the current README.md (which is project-specific, addressed to Amy) with a generic public README:

**Structure:**
1. **What is AI Mailbox** -- One-paragraph description
2. **Features** -- Bullet list of current capabilities
3. **Quick Start** -- How to connect Claude Desktop (MCP config example)
4. **Web UI** -- Screenshots description, URL, login
5. **Self-Hosting** -- Railway deployment instructions, env vars table
6. **Development** -- Clone, install, test commands
7. **API** -- Brief MCP tools reference (tool name + one-line description)
8. **License** -- MIT

Not addressed to any specific user. Written for someone discovering the project on GitHub.

---

## 11. File Changes Summary

### New files

| File | Purpose |
|------|---------|
| `src/ai_mailbox/db/migrations/006_oauth_registration.sql` | email, auth_provider, avatar_url columns + user_invites table |
| `src/ai_mailbox/web_oauth.py` | Google/GitHub OAuth routes (initiate, callback, user creation) |
| `src/ai_mailbox/templates/login.html` | Jinja2 login template (replaces inline HTML) |
| `src/ai_mailbox/templates/settings.html` | User settings page |
| `tests/test_oauth_registration.py` | OAuth flow, invite check, user creation tests |
| `tests/test_settings.py` | Settings page display and update tests |

### Modified files

| File | Changes |
|------|---------|
| `src/ai_mailbox/config.py` | Add OAuth client IDs/secrets, invite_only, invited_emails |
| `src/ai_mailbox/server.py` | Mount web_oauth routes, seed invites in _seed_users |
| `src/ai_mailbox/web.py` | Update /web/login to render template, add /web/settings routes, add Settings link context |
| `src/ai_mailbox/db/schema.py` | Run migration 006 |
| `src/ai_mailbox/templates/base.html` | Add "Settings" link to navbar |
| `src/ai_mailbox/__init__.py` | Bump version to 0.6.0 |
| `pyproject.toml` | Add authlib dependency, bump version to 0.6.0 |
| `README.md` | Complete rewrite (generic, public-facing) |
| `tests/conftest.py` | Add email, auth_provider, avatar_url, user_invites to test schema |
| `tests/test_web.py` | Update login tests, add Settings link assertions |

### Deleted files

None.

### Unchanged files

| File | Reason |
|------|--------|
| `src/ai_mailbox/oauth.py` | MCP OAuth provider unchanged -- password auth for MCP clients |
| `src/ai_mailbox/db/queries.py` | No query changes (new queries in web_oauth.py are self-contained) |
| `src/ai_mailbox/db/connection.py` | No changes |
| `src/ai_mailbox/rate_limit.py` | Login rate limit already exists |
| `src/ai_mailbox/tools/*` | No tool changes |
| `src/ai_mailbox/templates/inbox.html` | No changes |
| `src/ai_mailbox/templates/users.html` | No changes |
| All template partials | No changes |
| `Dockerfile` | No new system deps (authlib is pure Python) |
| `railway.toml` | Unchanged |

---

## 12. Acceptance Criteria

### 12.1 Google OAuth

- [ ] "Sign in with Google" button on `/web/login` (when configured)
- [ ] Clicking redirects to Google consent screen
- [ ] Callback creates new user with email, auth_provider='google', display_name from Google
- [ ] Returning user (same email+provider) logs in without creating duplicate
- [ ] Session cookie set, redirects to inbox
- [ ] Display name and avatar_url updated on each login

### 12.2 GitHub OAuth

- [ ] "Sign in with GitHub" button on `/web/login` (when configured)
- [ ] Same flow as Google but with GitHub endpoints
- [ ] User ID uses `gh-{login}` format

### 12.3 Password Fallback

- [ ] Password form always present on login page
- [ ] keith/amy can still log in with passwords
- [ ] When no OAuth providers configured, login page looks like current (no OAuth buttons)

### 12.4 Invite-Only Mode

- [ ] When `MAILBOX_INVITE_ONLY=true`, uninvited email gets error on OAuth callback
- [ ] Invited email can register
- [ ] Invite marked as used after first registration
- [ ] Returning user (already registered) can always log in regardless of invite state
- [ ] When `MAILBOX_INVITE_ONLY=false`, any OAuth user can register
- [ ] `MAILBOX_INVITED_EMAILS` seeds invite entries on startup

### 12.5 Settings Page

- [ ] `GET /web/settings` renders user profile with current values
- [ ] Display name is editable, other fields read-only
- [ ] `POST /web/settings` updates display_name
- [ ] Empty or >100 char display name rejected
- [ ] "Settings" link in navbar
- [ ] Requires authentication (redirects to login if not logged in)

### 12.6 Migration 006

- [ ] email, auth_provider, avatar_url columns added to users
- [ ] user_invites table created
- [ ] Index on (email, auth_provider) created
- [ ] Existing users get auth_provider='local', NULL email
- [ ] Runs on both SQLite and PostgreSQL

### 12.7 README

- [ ] Generic, not addressed to specific user
- [ ] Covers: what, features, quick start, web UI, self-hosting, development, API
- [ ] Env vars table for deployment

### 12.8 Version Fix (Issue #13)

- [ ] `__init__.py` version = "0.6.0"
- [ ] `pyproject.toml` version = "0.6.0"
- [ ] Issue #13 closed

### 12.9 AI UX UAT (browser verification -- required gate)

- [ ] **Login page:** Visit /web/login, verify OAuth buttons visible (or password-only if not configured)
- [ ] **Password login:** Log in with keith credentials, verify inbox loads
- [ ] **Settings page:** Navigate to /web/settings, verify profile fields displayed
- [ ] **Settings update:** Change display name, verify success
- [ ] **Navbar:** Verify Settings link visible in navbar
- [ ] **Logout/re-login:** Verify session cycle works

### 12.10 Tests

- [ ] test_oauth_registration.py: callback flow (mock OAuth provider), invite check, user creation, returning user, collision handling
- [ ] test_settings.py: settings page render, display_name update, validation errors, auth required
- [ ] test_web.py additions: login page renders OAuth buttons when configured, Settings link in navbar
- [ ] conftest.py: updated schema with new columns + user_invites table
- [ ] Total test count >= 460 (up from 424)

### 12.11 Deployment

- [ ] Migration 006 runs on PostgreSQL staging
- [ ] OAuth env vars set on Railway (Google and/or GitHub)
- [ ] Invite-only mode active
- [ ] Login page shows OAuth buttons on staging
- [ ] Settings page accessible on staging

### 12.12 GitHub

- [ ] Issue #13 closed (version fix)
- [ ] New issue for self-service registration created and closed (or update existing tracking)

---

## 13. Implementation Order (TDD Through Delivery)

1. **Config + migration 006** -- `config.py` + `006_oauth_registration.sql` + `schema.py` + `conftest.py`
   - RED: tests for new config fields, new columns exist, user_invites table exists
   - GREEN: add config fields, create migration, update schema runner, update test fixtures
   - VERIFY: tests pass
   - **Files modified:** `src/ai_mailbox/config.py`, `src/ai_mailbox/db/schema.py`, `tests/conftest.py`, `tests/test_web.py` (schema)
   - **Files created:** `src/ai_mailbox/db/migrations/006_oauth_registration.sql`

2. **OAuth routes + user creation** -- `web_oauth.py` + tests
   - RED: tests for OAuth initiate redirect, callback user creation, returning user lookup, invite check
   - GREEN: implement OAuth routes with authlib, find_or_create_oauth_user, invite logic
   - VERIFY: tests pass (OAuth providers mocked in tests)
   - **Files created:** `src/ai_mailbox/web_oauth.py`, `tests/test_oauth_registration.py`

3. **Login template + integration** -- `login.html` + `web.py` changes
   - RED: tests for login page rendering (with/without OAuth buttons), password form still works
   - GREEN: create Jinja2 login template, update /web/login to render template, pass provider availability
   - VERIFY: tests pass
   - **Files created:** `src/ai_mailbox/templates/login.html`
   - **Files modified:** `src/ai_mailbox/web.py`

4. **Settings page** -- `settings.html` + web routes + tests
   - RED: tests for settings page display, display_name update, validation, auth required
   - GREEN: create settings template, add /web/settings GET+POST routes
   - VERIFY: tests pass
   - **Files created:** `src/ai_mailbox/templates/settings.html`, `tests/test_settings.py`
   - **Files modified:** `src/ai_mailbox/web.py`, `src/ai_mailbox/templates/base.html`

5. **Server integration** -- `server.py` + invite seeding
   - RED: tests for web_oauth routes mounted, invite seeding from env
   - GREEN: mount routes, update _seed_users with invite seeding
   - VERIFY: tests pass
   - **Files modified:** `src/ai_mailbox/server.py`

6. **Version fix + README** -- `__init__.py` + `pyproject.toml` + `README.md`
   - Implement: bump versions, rewrite README
   - VERIFY: full suite green (460+ tests)
   - **Files modified:** `src/ai_mailbox/__init__.py`, `pyproject.toml`, `README.md`

7. **Full test suite + integration verification**
   - RED: any remaining integration tests
   - GREEN: wire remaining pieces
   - VERIFY: full suite green (460+ tests)

8. **Deploy to MVP 1 Staging**
   - Set OAuth env vars on Railway
   - Set `MAILBOX_INVITE_ONLY=true` and `MAILBOX_INVITED_EMAILS` on Railway
   - VERIFY: migration 006 runs, login page shows OAuth, settings works

9. **AI UX UAT** (required gate)
   - Browser verification of section 12.9

10. **Human UAT** (required gate) + **GitHub cleanup** -- close #13, track registration issue

---

## 14. Dependency Changes

New: `authlib>=1.3` (MIT license, pure Python). No new system-level dependencies. Dockerfile unchanged.

---

## 15. Resolved Design Decisions

1. **Web-only OAuth, MCP stays password-based.** Adding Google/GitHub to the MCP OAuth flow would require a complex multi-hop redirect (MCP SDK -> our login page -> Google -> callback -> back to MCP redirect_uri) and would break the simple login form that Claude Desktop expects. For alpha, password auth for MCP clients is sufficient. Social login for MCP can be added later.

2. **authlib over manual OAuth.** Rolling our own OAuth client means handling state generation, PKCE, token exchange, and provider quirks. Authlib handles all of this with Starlette integration out of the box. One dependency vs hundreds of lines of security-critical code.

3. **Separate web_oauth.py module.** OAuth routes are complex enough to warrant their own module rather than bloating web.py further. web.py already handles inbox, compose, search, archive, settings -- adding OAuth callback logic would push it past maintainable size.

4. **Invite table over env var list.** A `user_invites` table is mutable without redeployment, supports tracking who invited whom and when, and enables a future admin UI. The env var `MAILBOX_INVITED_EMAILS` is just a seeding mechanism.

5. **user_id format: prefix + name.** `g-keith` and `gh-keithdev` are human-readable and indicate the auth provider at a glance. This is better than opaque UUIDs for a messaging system where user IDs appear in conversations.

6. **Avatar URL stored but not rendered.** Storing the URL now means we have the data for a future polish sprint. Rendering it requires fallback logic (broken image URLs, missing avatars) that would expand scope without clear alpha value. The initials avatars work well.

7. **Version bump to 0.6.0.** Aligns version with sprint number, resolves issue #13, and establishes a convention going forward. Semantic versioning will be adopted properly at 1.0 (alpha release, Sprint 8).
