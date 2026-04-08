# Step 5: Update Baseline

After all triggered tiers pass, update the baseline tracking.

## 5.1: Update UAT_PROCESS.md baseline table

Append a new row to the Baseline Tracking table at the bottom of `docs/runbooks/UAT_PROCESS.md`:

```
| [DATE] | [test count] | [Tier 1 result] | [Tier 2 cycle/result] | [Tier 3 result] |
```

## 5.2: Update tool-to-test manifest (if new tools added)

If new tools were added this session:
1. Add row to tool-to-test manifest with tool name, source file, primary test files, test count
2. Add tool to Tier 2 rotation schedule
3. Add repeatable prompt to Tier 3 prompts table
4. Add checklist item to Tier 3 checklist

## 5.3: Commit baseline update

```bash
git add docs/runbooks/UAT_PROCESS.md
git commit -m "Update UAT baseline: [test count] tests, [summary]"
```
