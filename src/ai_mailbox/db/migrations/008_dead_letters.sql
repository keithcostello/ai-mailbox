-- Sprint 7: Dead letter handling for offline agents
-- delivery_status tracks whether the recipient was online at send time.
-- 'delivered' = recipient active, 'queued' = recipient offline (dead letter).

ALTER TABLE messages ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(20) DEFAULT 'delivered';
