# Step 1: Identify Scope

Determine what changed and which tiers need to run.

## 1.1: Check git diff for tool changes

```bash
git diff --name-only HEAD~1
```

Or if scope is explicit from user, use that.

## 1.2: Map changes to tiers

Read `docs/runbooks/UAT_PROCESS.md` trigger rules:

| Changed file pattern | Required action |
|---------------------|-----------------|
| `src/ai_mailbox/tools/*.py` | Tier 1 full suite |
| `src/ai_mailbox/db/queries.py` | Tier 1 full suite |
| `src/ai_mailbox/server.py` | Tier 1 full suite |
| `src/ai_mailbox/ui/` | Tier 1 + Tier 2 (widget cycle) |
| New tool file created | Tier 1 + update manifest + update Tier 3 prompts |

## 1.3: Check for new tools

If a new tool was added:
1. Verify it exists in the tool-to-test manifest in `docs/runbooks/UAT_PROCESS.md`
2. If missing, add it before proceeding
3. Verify it has a corresponding test file
4. Verify it is registered in `server.py`
5. Verify it has a Tier 3 repeatable prompt in the UAT checklist

## 1.4: Read current baseline

Read the Baseline Tracking table at the bottom of `docs/runbooks/UAT_PROCESS.md` to get the current test count baseline.

## Output

State: which tiers will run, which tools are in scope, current baseline test count.
