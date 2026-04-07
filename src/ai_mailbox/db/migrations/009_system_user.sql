-- Sprint 7: Reserved 'system' user for platform-generated messages.
-- The system user cannot log in and is excluded from list_users.
-- api_key is a non-guessable placeholder (NOT NULL constraint on users table).

INSERT INTO users (id, display_name, api_key, user_type, session_mode)
SELECT 'system', 'System', 'SYSTEM-RESERVED-DO-NOT-USE', 'system', 'persistent'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 'system');
