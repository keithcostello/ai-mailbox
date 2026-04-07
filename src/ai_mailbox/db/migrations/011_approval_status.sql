-- Sprint 8: Approval status for AI-to-AI response messages.
-- NULL for regular messages. Values: pending_human_approval, approved, rejected.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30);
