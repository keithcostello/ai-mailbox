-- Seed test profiles for AI-to-AI testing on staging.
-- These are safe to run on production (UPDATE with WHERE clause, idempotent).

UPDATE users SET profile_metadata = '{"team":"hr","department":"people-ops","expertise_tags":["hr","onboarding","benefits","compliance","payroll"],"projects":["employee-handbook","benefits-portal"],"bio":"HR specialist handling onboarding and benefits"}'
WHERE id = 'amy' AND (profile_metadata IS NULL OR profile_metadata = '{}');

UPDATE users SET profile_metadata = '{"team":"finance","department":"accounting","expertise_tags":["finance","budgeting","forecasting","compliance"],"projects":["q2-budget","expense-automation"],"bio":"Finance analyst focused on budgeting and compliance"}'
WHERE id = 'gh-keith' AND (profile_metadata IS NULL OR profile_metadata = '{}');
