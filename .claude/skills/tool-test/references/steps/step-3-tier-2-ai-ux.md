# Step 3: Tier 2 -- AI UX Browser Test (Conditional)

**Skip if:** Tier was not triggered by scope analysis (Step 1), or user explicitly says "Tier 1 only".

## 3.1: Prerequisites

- Staging must be deployed with the latest code
- Claude in Chrome MCP tools must be available
- Staging MCP server: `https://ai-mailbox-server-mvp-1-staging.up.railway.app/mcp`

## 3.2: Deploy to staging if needed

```bash
cd "C:/Projects/SINGLE PROJECTS/ai-mailbox" && railway up --detach
```

Wait for health check:
```bash
curl -s https://ai-mailbox-server-mvp-1-staging.up.railway.app/health
```

## 3.3: Determine which tools to test

Read the rotation schedule from `docs/runbooks/UAT_PROCESS.md`. Pick the current cycle's tools, or test the specific tools that changed.

## 3.4: Execute browser tests

For each tool in scope:

1. Open a new tab in Chrome, navigate to claude.ai
2. Start a new chat
3. Type the natural language prompt that exercises the tool
4. Wait for response
5. Verify: tool executed without error, response data is correct, widget reflects changes (if applicable)
6. Screenshot as proof

## 3.5: If a tool fails in browser

1. Check staging logs: `railway logs --lines 50`
2. Check if the tool works in pytest (Tier 1 passed, so the logic is correct -- the issue is likely deployment, OAuth, or Postgres-specific)
3. Fix, redeploy, retest

## Output

```
Tier 2: [PASS/FAIL/SKIPPED] -- [tools tested] in claude.ai
```
