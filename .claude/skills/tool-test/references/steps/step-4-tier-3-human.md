# Step 4: Tier 3 -- Human UAT (Conditional)

**Skip if:** Not a pre-production promotion run. Only required before merging to master and deploying to production.

## 4.1: Present checklist to human

Read the Tier 3 checklist from `docs/runbooks/UAT_PROCESS.md` and present the repeatable test prompts table to the user.

The AI CANNOT sign off Tier 3. Only the human tester can mark PASS/FAIL.

## 4.2: Provide testing instructions

Tell the user:
1. Open claude.ai with staging MCP server connected
2. Run the prompts in order from the repeatable test prompts table
3. Mark each step PASS or FAIL
4. Report results back

## 4.3: Record results

When the human reports results:
1. If ALL PASS: record in baseline tracking table
2. If any FAIL: document the failure, create a bug report, fix via TDD, re-run from Tier 1

## 4.4: Production gate

All three tiers must be green before merge to master:

| Gate | Requirement |
|------|-------------|
| Tier 1 | 0 failures, count >= baseline |
| Tier 2 | Current cycle tools verified |
| Tier 3 | Human checklist signed off |

## Output

```
Tier 3: [PASS/FAIL/PENDING] -- [N]/[total] steps by [tester]
```
