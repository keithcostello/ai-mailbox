-- BUG-001: Drop NOT NULL on legacy to_user column.
-- Migration 003 moved to conversation_participants but never relaxed this constraint.
-- PostgreSQL only — SQLite ALTER COLUMN not supported; handled in schema.py.
ALTER TABLE messages ALTER COLUMN to_user DROP NOT NULL;
