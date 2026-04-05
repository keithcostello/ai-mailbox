# BUG-002: Login returns Internal Server Error

## Symptom
Browser navigates to `/login`, user submits credentials, gets "Internal Server Error" (500).

## Root Cause
`oauth_codes.expires_at` column is `TIMESTAMP` in PostgreSQL, but `create_authorization_code()` inserts `time.time()` (a Unix float like `1775420779.37`). PostgreSQL rejects this with:
```
invalid input syntax for type timestamp: "1775420779.3794575"
```

## Location
- `oauth.py:278` — `create_authorization_code()` passes `str(expires_at)` where `expires_at = time.time() + 300`
- `002_oauth.sql` — `expires_at TIMESTAMP NOT NULL`

## Fix Options
1. Change SQL column to `FLOAT` or `BIGINT` (store Unix timestamp)
2. Convert Python `time.time()` to ISO datetime string before INSERT

**Chosen:** Option 1 — change `oauth_codes.expires_at` to `FLOAT` and `oauth_tokens.expires_at` to `BIGINT`. Consistent with how the code uses these values (numeric comparisons).

## Affected Files
- `002_oauth.sql` — change column types
- `oauth.py:278` — remove `str()` wrapping
- Railway PG — ALTER TABLE to fix live schema

## Test Gap
- `test_oauth.py` covers `create_authorization_code` but only in SQLite (which accepts anything as TEXT)
- SQLite's weak typing masked the PG TIMESTAMP incompatibility
- AI UAT tested GET /login (renders form) but not POST /login (submit credentials)

## Corrective Actions
1. Changed `oauth_codes.expires_at` from TIMESTAMP to FLOAT in migration
2. Removed `str()` wrapping on the float value in `create_authorization_code`
3. Fixed live PG schema via manual ALTER
4. **Future:** AI UAT must include POST /login test to verify full auth flow end-to-end
