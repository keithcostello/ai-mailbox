-- GIN index on profile_metadata expertise_tags for tag-based expert search (Postgres only).

CREATE INDEX IF NOT EXISTS idx_user_profile_tags
    ON users USING GIN ((profile_metadata::jsonb -> 'expertise_tags'));
