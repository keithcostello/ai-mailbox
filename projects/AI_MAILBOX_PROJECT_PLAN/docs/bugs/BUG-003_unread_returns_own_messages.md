# BUG-003: unread_only returns user's own sent messages

**Reported:** 2026-04-07
**Severity:** Medium
**Status:** Resolved
**Found by:** Keith (production UAT)

## Symptom

`list_messages` with `unread_only=True` returns the caller's own sent messages as "unread". After `mark_read`, new messages sent by the caller still appear in their unread list.

## Root Cause

`list_messages_query` in `queries.py` filters unread as `m.sequence_number > cp.last_read_sequence` but does not exclude `m.from_user = user_id`. The user's own sent messages have sequence numbers above their read cursor, so they match the unread filter.

Affects both query paths:
- Cross-conversation mode (line ~486): `m.sequence_number > cp.last_read_sequence`
- Single-conversation mode (line ~464): subquery against `last_read_sequence`

## Fix

Add `m.from_user != ?` condition to both unread paths in `list_messages_query`.

## Tests

- `test_own_sent_messages_not_unread` -- single conversation
- `test_own_sent_messages_not_unread_cross_conversation` -- multiple conversations

## Impact

Affects both SQLite and PostgreSQL. All users see inflated unread counts when they are active senders.
