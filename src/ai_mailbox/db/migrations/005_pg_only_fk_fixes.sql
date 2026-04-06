-- Sprint 5: PostgreSQL-only FK constraint fixes (issues #9, #11)

-- Fix FK CASCADE on messages.from_user (issue #9)
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_from_user_fkey;
ALTER TABLE messages ADD CONSTRAINT messages_from_user_fkey
    FOREIGN KEY (from_user) REFERENCES users(id) ON DELETE CASCADE;

-- Add FK constraints on OAuth tables (issue #11)
DO $$ BEGIN
    ALTER TABLE oauth_codes ADD CONSTRAINT oauth_codes_client_fk
        FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE oauth_tokens ADD CONSTRAINT oauth_tokens_client_fk
        FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
