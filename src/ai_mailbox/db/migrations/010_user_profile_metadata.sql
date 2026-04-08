-- Sprint 8: User profile metadata for AI-to-AI routing.
-- Stores JSON: {team, department, expertise_tags[], projects[], jira_tickets[], observed_topics[], bio}
-- AI auto-populates from observed context. Human can edit via chat or web settings.

ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_metadata TEXT DEFAULT '{}';
