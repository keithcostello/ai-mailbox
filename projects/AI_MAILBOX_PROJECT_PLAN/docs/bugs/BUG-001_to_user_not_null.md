---
id: BUG-001
title: "to_user NOT NULL constraint blocks all message sends"
severity: P0
status: triaged
component: ai_mailbox.db / migrations
branch: mvp-1-staging
reported: 2026-04-06
assignee: unassigned
---

# BUG-001: `to_user` NOT NULL Constraint Blocks All Message Sends

## Severity & Impact

**P0 — Critical / Service Down**

Every send and reply operation fails. No messages can be created. The core function of the product is inoperable.

- **Blast radius:** 100% of write operations (send, reply, group send)
- **Users affected:** All
- **Workaround:** None

## Symptom

```
null value in column "to_user" of relation "messages" violates not-null constraint
```

## Root Cause

Migration `003_conversation_model.sql` moved the data model from direct user-to-user addressing to conversation-based addressing. The `insert_message()` function in `queries.py:240-246` was rewritten to omit `to_user` — recipient info now lives in `conversation_participants`.

But `001_initial.sql:13` still defines:
```sql
to_user VARCHAR(64) NOT NULL REFERENCES users(id),
```

Migration 003 never altered this column. No subsequent migration (004-006) fixes it either. Result: every INSERT violates the NOT NULL constraint.

## Affected Code Paths

| File | Line(s) | Function | Impact |
|------|---------|----------|--------|
| `queries.py` | 240-246 | `insert_message()` | INSERT omits `to_user` |
| `tools/send.py` | 111-115 | `_send_direct()` | Direct messages broken |
| `tools/send.py` | 176-180 | `_send_to_conversation()` | Conversation messages broken |
| `tools/send.py` | 239-243 | `_group_confirmation_gate()` | Group sends broken |
| `tools/reply.py` | 58-64 | `tool_reply_to_message()` | All replies broken |

## Why It Wasn't Caught

The `to_user` field is still computed and returned in API responses from conversation participant data (not the DB column). Response shapes look correct — only the write path is broken. No integration test exercises a real INSERT against a database with the NOT NULL constraint active.

## Reproduction

```
mailbox_send_message(to="amy", body="test", project="general")
mailbox_reply_to_message(message_id="<any>", body="test")
```

Both fail with the NOT NULL constraint error.

## Recommended Fix

Create `007_nullable_to_user.sql`:
```sql
ALTER TABLE messages ALTER COLUMN to_user DROP NOT NULL;
```

One line. The column stays for backward compatibility with existing data (24 pre-migration messages reference it). New rows don't need it — recipient info lives in `conversation_participants`.

Alternative: Also drop the FK constraint if `to_user` will never be populated again:
```sql
ALTER TABLE messages ALTER COLUMN to_user DROP NOT NULL;
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_to_user_fkey;
```

## Triage Notes

- This is the highest-priority item for Sprint 7
- Blocks: outbound webhooks, email notifications, dead letter handling, system messages (all depend on message sends)
- Does not block: GitHub OAuth fix (BUG-002), migrate_003 boolean fix, UI work, tech debt
- Fix is one migration file + test. Estimate: <30 minutes
- Should be fixed before any other Sprint 7 work proceeds
