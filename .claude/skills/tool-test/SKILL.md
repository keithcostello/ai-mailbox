---
name: tool-test
description: Run the three-tier UAT process for AI Mailbox MCP tools. Use when the user says "test tools", "run UAT", "run tests", "tool test", or after any tool implementation change. Enforces TDD, Tier 1 automated tests, Tier 2 AI UX browser tests, and Tier 3 human checklist.
---

# Tool Test -- Three-Tier UAT

Runs the AI Mailbox acceptance testing process. Every tool change must pass Tier 1. Production promotion requires all three tiers.

## Required Input

- **Scope** -- infer from context: "all" (full suite), "changed" (tools modified this session), or specific tool name(s)
- **Tier** -- infer from context: "1" (automated only), "1-2" (automated + browser), "all" (all three tiers)

## Execution

Follow step routing table: `references/workflow.md`

Load each step file ONLY when reached. Do not preload all steps.

## Standards

- Tier 1 is MANDATORY after any tool change. No exceptions.
- Tier 2 requires Claude in Chrome MCP tools against claude.ai with staging MCP server.
- Tier 3 requires human (Keith) to run the checklist. AI cannot sign off Tier 3.
- Every new tool must be added to the tool-to-test manifest in `docs/runbooks/UAT_PROCESS.md`.
- Every new tool must be added to the Tier 3 repeatable prompts table.
- `py` not `python` for all test commands.

## Trigger Rules

| Change | Required Tiers |
|--------|----------------|
| Any file in `src/ai_mailbox/tools/` | Tier 1 (full suite) |
| `src/ai_mailbox/db/queries.py` | Tier 1 (full suite) |
| `src/ai_mailbox/server.py` | Tier 1 (full suite) |
| `src/ai_mailbox/ui/` | Tier 1 + Tier 2 (widget) |
| New tool added | Tier 1 + update manifest + update Tier 3 prompts |
| Pre-production promotion | All three tiers |

## Output

Report results as:
```
Tier 1: [PASS/FAIL] -- [test count] passed, [failures] failed
Tier 2: [PASS/FAIL/SKIPPED] -- [tools tested] in claude.ai
Tier 3: [PASS/FAIL/PENDING] -- [steps passed]/[total] by [tester]
```

## Source of Truth

`docs/runbooks/UAT_PROCESS.md` -- tool-to-test manifest, rotation schedule, repeatable prompts, checklist, baseline tracking.
