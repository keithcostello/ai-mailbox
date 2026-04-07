# Step 2: Tier 1 -- Automated Tests (MANDATORY)

## 2.1: Run full test suite

```bash
cd "C:/Projects/SINGLE PROJECTS/ai-mailbox" && py -m pytest tests/ -q
```

## 2.2: Verify pass criteria

- 0 failures
- Test count >= baseline from Step 1.4
- If test count dropped: investigate. A dropped count means tests were removed or broken.

## 2.3: If failures exist

1. STOP. Do not proceed to Tier 2 or Tier 3.
2. Read the failure output.
3. TDD: if the failure reveals a missing test, write the failing test first, then fix.
4. If the failure is a regression from a code change, fix the code.
5. Re-run `py -m pytest tests/ -q` until green.
6. Only then proceed.

## 2.4: Selective rerun (optional, for speed during iteration)

If you know exactly which tool changed, use the tool-to-test manifest:

```bash
# Example: send tool changed
py -m pytest tests/test_send_full.py tests/test_tools.py tests/test_queries.py -q

# Example: search tool changed
py -m pytest tests/test_search.py tests/test_tools.py tests/test_queries.py -q
```

Full suite rerun is always preferred. Selective is a fallback only.

## Output

```
Tier 1: [PASS/FAIL] -- [N] passed, [M] failed (baseline: [B])
```
