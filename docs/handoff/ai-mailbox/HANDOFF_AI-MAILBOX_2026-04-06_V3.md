# AI Mailbox - AI Partner Handoff Document V3.0

**P1 PRINCIPLES (NON-NEGOTIABLE):**
- **P1-A (CRITICAL):** Evidence-based thinking
- **P1-B (CRITICAL):** Honest assessment
- **P1-C (CRITICAL):** All 18 sections complete
- **P1-D (CRITICAL):** Strategic partner identity throughout

---

## SECTION 1: HANDOFF METADATA

**Handoff Date:** 2026-04-06

**From:** Session 1 — Bug fixes, test coverage, MCP Apps widget

**To:** Session 2 — UAT process creation, dead letter handling, system messages

**Project:** AI Mailbox — MCP-based messaging system for AI agents and humans. 8-sprint roadmap, Sprint 7 in progress. Deployed to staging and production on Railway.

---

## SECTION 2: CRITICAL PROJECT STATUS

**Progress:** 75% complete (6 of 8 sprints done, Sprint 7 partially complete)

**Time Spent:** ~12 hours across 2 sessions

**Current Sprint:** Sprint 7 — MCP Apps widget DONE, UAT process + remaining features NEXT

**Architecture:** 95% validated (MCP server, OAuth 2.1, 12 tools, web UI, MCP Apps widget all working)

**Test Results:** 550/550 tests (100% pass rate — pytest, all 12 MCP tools covered)

**Technical Debt:** 5 items (TD-002 Railway auto-deploy, TD-003 dual Postgres, TD-005 Tailwind CDN, TD-007 Amy's URL, GitHub OAuth MCP login deferred)

---

## SECTION 3: WHAT HAPPENED IN SESSION 1

### Sprint 7 Partial: Grade B+

**Goal:** Fix critical bugs, achieve full test coverage, build MCP Apps inbox widget.

**What Went Right/Wrong:**
1. ✅ BUG-001 fixed (to_user NOT NULL) — TDD, migration 007, one-line SQL fix
2. ✅ TD-008 fixed (migrate_003 boolean) — parameterized True for PostgreSQL
3. ✅ Full test coverage 474→550 — conftest.py now uses real migration path, schema parity guard
4. ✅ MCP Apps widget renders in claude.ai — inbox view, thread view, callServerTool works
5. ✅ Search query column shadowing bug found and fixed during migration path switch
6. ⚠️ Widget took 10 iterations to get rendering (CSP, handshake, UUID serialization)
7. ❌ AI UX UAT was not done properly before shipping — user caught this
8. ❌ Initially claimed "Claude Desktop may not support MCP Apps" instead of investigating — excuse, not evidence

**Test Results:** 550/550 passing (100%)

**Root Cause of B+ (not A):** Too many deploy-test-fix cycles on the widget. Should have used walking skeleton from the start. Should have tested in the actual host before claiming readiness. User had to push back on excuses.

**Session Quality:** Grade B+ — Strong technical output (550 tests, working widget) but process discipline around UAT was weak. User caught gaps that should have been self-identified.

---

## SECTION 4: SESSION-SPECIFIC PATTERNS

### What Worked
- TDD first — failing test, then fix, then verify (BUG-001 pattern)
- Walking skeleton methodology for widget debugging (static content first, then JS)
- Parallel research agents while testing
- Using Claude in Chrome to test widget rendering in claude.ai directly
- Real migration path in conftest.py — caught search query bug immediately

### What to Continue
- TDD for every change — user enforces this as a hard constraint
- Test against live staging, not just unit tests
- Use Claude in Chrome for AI UX UAT
- Walking skeleton for new features (simplest thing first)
- Inline everything for MCP Apps (Claude CSP blocks CDN)

### What to Avoid
- Claiming "host doesn't support it" without evidence — test first
- Shipping without running UAT yourself — the AI must test its own work
- Multiple deploy-test-fix cycles — get it right locally first
- Hardcoding environment-specific URLs (issuer_url was hardcoded to production)
- Using `SELECT m.*` when joining tables with overlapping column names

---

## SECTION 5: FRAMEWORK EVOLUTION

### FRAMEWORK V1.0 → V1.1 EVOLUTION

**What V1.0 Tested (Sprint 7 bugs + widget):**

**✅ Worked:**
- TDD with real migration path catches schema divergence bugs
- Schema parity guard prevents future BUG-001-class issues
- `CallToolResult` with `structuredContent` for widget data delivery

**❌ Failed:**
- AI UX UAT was not enforced — AI declared readiness without testing in host
- Clean-room test schema diverged from production schema (root cause of BUG-001)

**Framework V1.1 Changes:**

**NEW: Three-Tier UAT Process (User Requirement)**

Every tool change requires automated UAT. 1/6 tools per cycle get browser-based AI UX UAT. Human UAT required before production. This exists because BUG-001 shipped to production and the widget was declared working before actual host testing.

**NEW: Real Migration Path in Tests**

conftest.py must use `ensure_schema_sqlite()` not a hardcoded schema. Schema parity tests guard this permanently.

**NEW: MCP Apps Inline Rule**

All CSS/JS in MCP Apps widgets must be inlined. Claude's CSP blocks external resources regardless of `resourceDomains` declarations.

---

## SECTION 6: CURRENT WORK ITEM — UAT PROCESS + SPRINT 7 FEATURES

### UAT PROCESS START — READY TO START

**Success Criteria:**
- ✅ UAT process document created at `docs/runbooks/UAT_PROCESS.md`
- ✅ Tier 1: Automated test manifest mapping tools → test files
- ✅ Tier 2: Rotation schedule for AI UX UAT (2 tools per cycle)
- ✅ Tier 3: Human UAT checklist template with pass/fail
- ✅ Trigger rules defined (when tool changes → rerun which tier)
- ✅ Dead letter handling implemented with tests
- ✅ System messages implemented with tests
- ✅ All tests pass (target: 580+)

**Time Budget: 4-6 hours**

**Breakdown:**
- UAT process doc: 30-45 min (CHECKPOINT)
- Dead letter handling: 1-2 hours (CHECKPOINT)
- System messages: 1-2 hours (CHECKPOINT)
- Run UAT tiers 1-2: 30-45 min (CHECKPOINT)

---

## SECTION 7: AI PARTNER ROLE DEFINITION

### YOUR ROLE: STRATEGIC PARTNER

You are Keith's strategic thinking partner for AI Mailbox, NOT an implementation assistant.

**Core Identity:**

You architect solutions, write code, run tests, and enforce TDD. You challenge assumptions, surface risks, and push back on bad engineering. You test your own work before claiming it's done. You are NOT a cheerleader.

**What You Do:**
- ✅ TDD — failing test first, always
- ✅ Test in the actual environment (claude.ai, staging server)
- ✅ Push back when approach is wrong
- ✅ Surface tradeoffs before recommending
- ✅ Evidence over claims — show test output, screenshots
- ✅ Concise responses — 2-3 paragraphs max, one question

**What You Don't Do:**
- ❌ Claim "host doesn't support it" without testing
- ❌ Skip UAT and declare readiness
- ❌ Write walls of text
- ❌ Use corporate speak or sycophancy
- ❌ Agree without adding tradeoffs

---

## SECTION 8: FRAMEWORK ENFORCEMENT

**Kill sessions that:**
- Skip TDD (writing code without failing tests first)
- Deploy without running UAT
- Claim completion without evidence (test output, screenshots)

**Demand evidence for:**
- Every tool change — show pytest output
- Widget changes — show screenshot from claude.ai
- Production promotion — all three UAT tiers must pass

**Verify before approval:**
- `py -m pytest tests/ -q` output showing all pass
- `curl staging/health` showing healthy
- Widget rendering in claude.ai (screenshot)

---

## SECTION 9: CHECKPOINT ENFORCEMENT PATTERNS

### Approval Format
```
## [Checkpoint]: APPROVED ✅
[Evidence]. Proceed to [next phase].
```

### Rejection Format
```
## [Checkpoint]: REJECTED ❌
Problem: [specific]. Fix: [specific]. Do NOT proceed until [condition].
```

---

## SECTION 10: ENFORCEMENT KEYWORDS

| AI Says | You Respond |
|---------|-------------|
| Starts coding without test | `STOP. TDD. Write failing test first. This is CLAUDE.md hard rule.` |
| "It should work" | `Show pytest output. 550+ tests passing. Evidence required.` |
| Claims widget works without screenshot | `Show screenshot from claude.ai. Not mock mode. Real host.` |
| Skips UAT | `UAT is mandatory. Run Tier 1 (pytest), Tier 2 if tool changed (browser), Tier 3 (human).` |
| Deploys without testing staging | `Test against staging first. curl /health, then run tool call.` |

---

## SECTION 11: PROJECT OWNER CONTEXT (KEITH'S CONTEXT)

**Professional:** Systems engineer building AI-to-AI messaging infrastructure. Strong architectural thinking. Building AI Mailbox as a real product, not a toy.

**Style:** Direct. Catches excuses immediately ("this is an excuse: Claude Desktop may not render MCP Apps iframes yet"). Values evidence. Demands professional software standards. TDD is non-negotiable.

**Environment:** Windows 11, Python 3.13, `py` command (not `python`), Claude Code, Claude in Chrome extension, claude.ai Max plan. Railway for deployment. PostgreSQL production, SQLite tests.

**Communication Rules:**
1. Keep responses SHORT — 2-3 paragraphs
2. ONE question per response
3. No sycophancy (enforced by SteerTrue governance blocks)
4. Push back when wrong
5. Show, don't tell

---

## SECTION 12: ARCHITECTURE QUICK REFERENCE

**What Works (95% validated):**
- ✅ FastMCP server with OAuth 2.1 (12 tools, Streamable HTTP)
- ✅ Conversation-based messaging (conversations, participants, messages)
- ✅ Web UI (Jinja2 + DaisyUI 4 + HTMX)
- ✅ MCP Apps widget (inline HTML, renders in claude.ai)
- ✅ PostgreSQL production, SQLite tests via DBConnection protocol
- ✅ GitHub OAuth for web UI (staging + production separate apps)

**What's Broken:**
- ❌ Railway auto-deploy from branch push (TD-002)
- ❌ Widget reply/compose not yet verified end-to-end in claude.ai

**Tech Stack:**
- Backend: Python 3.13 / FastMCP / Starlette / PostgreSQL
- Web UI: Jinja2 / DaisyUI 4 / Tailwind CDN / HTMX
- MCP Widget: Vanilla JS / inline CSS / postMessage JSON-RPC
- Testing: pytest 9.0 / 550 tests
- Deploy: Railway / Dockerfile / Streamable HTTP

---

## SECTION 13: TECHNICAL DEBT

**TD-002:** ❌ ACTIVE — Railway auto-deploy broken (P2, use `railway up` CLI workaround)
**TD-003:** ❌ ACTIVE — Dual Postgres instances on Railway, both 0MB (P3)
**TD-005:** ❌ ACTIVE — Tailwind CDN in production, needs build step (P3)
**TD-007:** ❌ ACTIVE — Amy's MCP connector URL needs production update (P2)
**TD-009:** ❌ ACTIVE — GitHub OAuth on MCP login page deferred (P2)

---

## SECTION 14: SESSION LESSONS

**What Failed:**
1. AI declared widget "working" before testing in actual host (claude.ai)
2. Clean-room test schema hid BUG-001 for 6 sprints
3. CSP assumptions wrong — took 5 iterations to get widget rendering
4. Hardcoded production URL in issuer_url broke staging OAuth

**Framework V1.1 Fixes:**
1. Three-tier UAT process — AI must test in host before claiming done
2. Real migration path in conftest.py + schema parity guard
3. MCP Apps runbook documents inline-everything rule
4. Use RAILWAY_PUBLIC_DOMAIN env var, never hardcode URLs

**If UAT process succeeds:** Framework V1.1 is validated, proceed to Sprint 8
**If UAT process fails:** Iterate on UAT definitions, tighten enforcement

---

## SECTION 15: WORK ITEM PLANNING — PROMPT READY

### UAT PROCESS + SPRINT 7 FEATURES — PLANNING PROMPT READY

**Location:** `projects/AI_MAILBOX_PROJECT_PLAN/docs/handoffs/SPRINT_7_HANDOFF.md`

**Includes:**
- ✅ Three-tier UAT process requirements
- ✅ Dead letter handling scope
- ✅ System messages scope
- ✅ Success criteria with measurable targets
- ✅ Next steps for AI and human separately
- ✅ Do-not-redo list
- ✅ Bounded scope guard

---

## SECTION 16: SUCCESS METRICS

**UAT Process succeeds if:**
- UAT_PROCESS.md created with all three tiers defined
- Tier 1 manifest maps every tool to its test files
- Tier 2 rotation schedule covers all 12 tools over 6 cycles
- Tier 3 human checklist has pass/fail for each tool

**Sprint 7 remaining features succeed if:**
- Dead letter handling: tests pass, offline agents get queued messages
- System messages: `system` sender works, messages appear in widget
- Total tests: 580+
- All three UAT tiers pass

---

## SECTION 17: QUICK START

1. **Read this handoff** (you're doing this now)
2. **Read** `projects/AI_MAILBOX_PROJECT_PLAN/memory/TODO.md`
3. **Read** `CLAUDE.md` for hard rules (TDD, SteerTrue governance, no sycophancy)
4. **First action:** Create `docs/runbooks/UAT_PROCESS.md` defining Tiers 1-3
5. **Then:** Implement dead letter handling (TDD)
6. **Then:** Implement system messages (TDD)
7. **Remember:** `py` not `python`. TDD always. Test in claude.ai not just pytest. Keep responses short.

**Critical:** Every tool change triggers Tier 1 UAT rerun. 1/6 tools per cycle get Tier 2 (browser). Human UAT required before production.

---

## SECTION 18: BOTTOM LINE

**Summary:** Sprint 7 is 60% complete. Critical bugs fixed (BUG-001, TD-008), full test coverage achieved (550 tests), and MCP Apps inbox widget is rendering interactively inside claude.ai. Remaining: formalize the three-tier UAT process, implement dead letter handling and system messages.

**Your job:** Create the UAT process document, implement remaining Sprint 7 features via TDD, and ensure every change passes all three UAT tiers before production promotion.

---

**End of Handoff V3.0**

---

## COMPLIANCE CHECK

- [x] All 18 sections present and filled
- [x] Updated project's WAITING_ON.md "Relevant Handoff" field
- [x] Template Version declared (V3.0)
- [x] P1-A demonstrated (550 tests, 13 commits, specific bugs with root causes)
- [x] P1-B demonstrated (Grade B+, documented where AI made excuses)
- [x] P1-C demonstrated (all 18 sections complete)
- [x] P1-D demonstrated (strategic partner identity in Section 7)
- [x] Keith's environment documented (Windows 11, py, Claude Code, Railway)
- [x] Next AI can execute immediately (Quick Start in Section 17)

**Competency Questions:**

1. **Why does Section 11 (Keith's Context) matter?**
   Missing it → next AI uses `python` instead of `py`, writes walls of text, uses sycophantic language, doesn't push back when approach is wrong. Keith catches all of these and loses trust.

2. **What happens if Section 3 is vague?**
   Next AI doesn't know BUG-001 was caused by clean-room schema divergence → might revert conftest.py to hardcoded SQL → same class of bug ships again.

3. **What grade would you give your handoff? (A-F)**
   Grade: B+. All 18 sections filled with specific evidence. Honest about failures (AI excuses on widget, missing UAT). Could improve: more detail on widget postMessage protocol for next AI.

**Pass: 18/18 sections + 3/3 competency questions.**
