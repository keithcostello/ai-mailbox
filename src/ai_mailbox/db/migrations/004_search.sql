-- Full-text search on messages (PostgreSQL only)
-- SQLite tests use LIKE fallback in queries.py

ALTER TABLE messages ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Populate existing rows
UPDATE messages SET search_vector =
    setweight(to_tsvector('english', COALESCE(subject, '')), 'A') ||
    setweight(to_tsvector('english', body), 'B');

-- GIN index for fast search
CREATE INDEX IF NOT EXISTS idx_msg_search ON messages USING GIN(search_vector);

-- Auto-populate on INSERT/UPDATE
CREATE OR REPLACE FUNCTION messages_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.subject, '')), 'A') ||
        setweight(to_tsvector('english', NEW.body), 'B');
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_messages_search ON messages;
CREATE TRIGGER trg_messages_search
    BEFORE INSERT OR UPDATE ON messages
    FOR EACH ROW
    EXECUTE FUNCTION messages_search_trigger();
