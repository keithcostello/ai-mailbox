# Global Daily Log

---

### 2026-04-07 - AI_MAILBOX_PROJECT_PLAN - BUG-003 hotfix deployed to production

**Ticket ID / Project Name:** AI_MAILBOX_PROJECT_PLAN
**Type:** fix
**Files:**
- `src/ai_mailbox/db/queries.py` - added from_user != caller to unread filter
- `tests/test_list_messages.py` - 2 new tests for own-message exclusion
- `projects/AI_MAILBOX_PROJECT_PLAN/docs/bugs/BUG-003_unread_returns_own_messages.md` - bug doc

**What:** list_messages unread_only filter returned the caller's own sent messages as unread. Added from_user exclusion to both query paths.
**Why:** Production UAT found inflated unread counts for active senders.
**Evidence:** 591/591 tests, production health confirmed, commit 865d61b
**LOE:** trivial (<30m)
**Status:** done

### 2026-04-07 - AI_MAILBOX_PROJECT_PLAN - Sprint 7 complete, v0.7.0 production

**Ticket ID / Project Name:** AI_MAILBOX_PROJECT_PLAN
**Type:** feature
**Files:**
- `src/ai_mailbox/db/migrations/008_dead_letters.sql` - delivery_status column
- `src/ai_mailbox/db/migrations/009_system_user.sql` - reserved system user
- `src/ai_mailbox/db/queries.py` - dead letter + system message functions
- `src/ai_mailbox/tools/list_participants.py` - new tool #13
- `src/ai_mailbox/tools/send.py` - dead letter detection + system messages
- `src/ai_mailbox/server.py` - v0.7.0, list_participants registration
- `docs/runbooks/UAT_PROCESS.md` - three-tier UAT v1.1 with 13 prompts
- `docs/runbooks/STAGING_TO_PRODUCTION.md` - promotion runbook

**What:** Sprint 7 delivered dead letter handling, system messages, list_participants tool, whoami Postgres fix, UAT process, and production promotion.
**Why:** Complete Sprint 7 deliverables and promote validated staging to production.
**Evidence:** 589/589 tests, Tier 3 Human UAT 13/13 PASS, production health `{"status":"healthy","version":"0.7.0"}`, commit 0dc41b0
**LOE:** medium (2-4h)
**Status:** done
