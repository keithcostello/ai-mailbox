# Workflow Routing Table: Tool Test

Follow steps in order. Load each step file ONLY when reached. Conditional steps have skip gates.

## Input

| Input | Required | Default |
|-------|----------|---------|
| Scope | yes | "all" |
| Tier | no | infer from trigger rules |

## Step Routing

| Step | File | Gate | Description |
|------|------|------|-------------|
| 1 | `references/steps/step-1-identify-scope.md` | -- | Determine which tools changed and which tiers to run |
| 2 | `references/steps/step-2-tier-1-automated.md` | MANDATORY | Run pytest, verify pass count >= baseline |
| 3 | `references/steps/step-3-tier-2-ai-ux.md` | conditional (skip if tier=1 only) | Browser test in claude.ai via Claude in Chrome |
| 4 | `references/steps/step-4-tier-3-human.md` | conditional (skip if not pre-production) | Present checklist to human, wait for sign-off |
| 5 | `references/steps/step-5-update-baseline.md` | -- | Update baseline tracking in UAT_PROCESS.md |

## Fail Handling

If any tier fails:
1. Stop. Do not proceed to next tier.
2. Fix the failure (TDD: write failing test if missing, then fix).
3. Re-run the failed tier from the top.
4. Only proceed after green.
