-- Sprint 8: Broadcast claims -- tracks who claimed a broadcast request.
-- Two-gate approval: Gate 1 (approve question), Gate 2 (approve answer).
-- Cooldown prevents re-evaluation spam after decline.

CREATE TABLE IF NOT EXISTS broadcast_claims (
    id UUID PRIMARY KEY,
    broadcast_id UUID NOT NULL REFERENCES broadcast_requests(id),
    claimant_id VARCHAR(64) NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'claimed',
    gate1_approved_at TIMESTAMP,
    gate1_declined_at TIMESTAMP,
    gate2_approved_at TIMESTAMP,
    gate2_declined_at TIMESTAMP,
    response_draft TEXT,
    seen_at TIMESTAMP NOT NULL,
    cooldown_until TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (broadcast_id, claimant_id)
);

CREATE INDEX IF NOT EXISTS idx_claim_broadcast ON broadcast_claims(broadcast_id);
CREATE INDEX IF NOT EXISTS idx_claim_claimant ON broadcast_claims(claimant_id);
