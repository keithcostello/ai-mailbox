-- Seed test users and profiles for AI-to-AI broadcast testing.
-- 6 users across 4 departments: Engineering (keith, dave), HR (amy, sarah),
-- Finance (gh-keith, mike), Product (lisa).
-- Idempotent: INSERT uses WHERE NOT EXISTS, UPDATE only on empty profiles.

-- New users (dave, sarah, mike, lisa) -- password hashes left empty, OAuth-only
INSERT INTO users (id, display_name, api_key, user_type, session_mode)
SELECT 'dave', 'Dave', 'SEED-dave-key-001', 'human', 'persistent'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 'dave');

INSERT INTO users (id, display_name, api_key, user_type, session_mode)
SELECT 'sarah', 'Sarah', 'SEED-sarah-key-002', 'human', 'persistent'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 'sarah');

INSERT INTO users (id, display_name, api_key, user_type, session_mode)
SELECT 'mike', 'Mike', 'SEED-mike-key-003', 'human', 'persistent'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 'mike');

INSERT INTO users (id, display_name, api_key, user_type, session_mode)
SELECT 'lisa', 'Lisa', 'SEED-lisa-key-004', 'human', 'persistent'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 'lisa');

-- Engineering: keith (already exists, profile set via tool), dave
UPDATE users SET profile_metadata = '{"team":"engineering","department":"backend","expertise_tags":["python","golang","kubernetes","ci-cd","docker"],"projects":["api-gateway","deploy-pipeline"],"bio":"Backend engineer focused on infrastructure and deployment"}'
WHERE id = 'dave' AND (profile_metadata IS NULL OR profile_metadata = '{}');

-- HR: amy, sarah
UPDATE users SET profile_metadata = '{"team":"hr","department":"people-ops","expertise_tags":["hr","onboarding","benefits","compliance","payroll"],"projects":["employee-handbook","benefits-portal"],"bio":"HR specialist handling onboarding and benefits"}'
WHERE id = 'amy' AND (profile_metadata IS NULL OR profile_metadata = '{}');

UPDATE users SET profile_metadata = '{"team":"hr","department":"talent","expertise_tags":["hr","recruiting","interviews","job-descriptions","dei"],"projects":["hiring-pipeline","dei-initiative"],"bio":"Talent acquisition lead managing recruiting and DEI programs"}'
WHERE id = 'sarah' AND (profile_metadata IS NULL OR profile_metadata = '{}');

-- Finance: gh-keith, mike
UPDATE users SET profile_metadata = '{"team":"finance","department":"accounting","expertise_tags":["finance","budgeting","forecasting","compliance"],"projects":["q2-budget","expense-automation"],"bio":"Finance analyst focused on budgeting and compliance"}'
WHERE id = 'gh-keith' AND (profile_metadata IS NULL OR profile_metadata = '{}');

UPDATE users SET profile_metadata = '{"team":"finance","department":"revenue","expertise_tags":["finance","revenue","pricing","contracts","saas-metrics"],"projects":["pricing-model","arr-dashboard"],"bio":"Revenue operations analyst handling pricing and SaaS metrics"}'
WHERE id = 'mike' AND (profile_metadata IS NULL OR profile_metadata = '{}');

-- Product: lisa
UPDATE users SET profile_metadata = '{"team":"product","department":"product-management","expertise_tags":["product","roadmap","user-research","okrs","prioritization"],"projects":["q2-roadmap","customer-feedback"],"bio":"Product manager driving roadmap and user research"}'
WHERE id = 'lisa' AND (profile_metadata IS NULL OR profile_metadata = '{}');
