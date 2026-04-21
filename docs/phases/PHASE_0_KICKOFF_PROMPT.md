# Phase 0 Kickoff Prompt — Foundation Hardening

> **How to use:** Copy the code block below into a fresh Claude Code / agent session. The agent will take it from there.

---

```
You are the implementation agent for **Phase 0 — Foundation Hardening** of the
Nifty Options Bot → AI Tradebot upgrade. Your job is to lay the rails (Postgres,
migrations, tests, CI, logging, feature flags) so later phases don't get stuck.
You are NOT building product features in this phase.

======================================================================
AUTHORITATIVE SOURCES — read in this order before doing anything else
======================================================================
1. docs/phases/MASTER_PLAN.md               (6-phase plan, locked decisions, guardrails)
2. AlgoTrading_App_Features_and_AgentPrompt.md  (full product spec — long-term vision)
3. backend/ and frontend/ (existing code — do NOT rewrite what works)
4. README.md, requirements.txt, frontend/package.json (current stack)

======================================================================
LOCKED DECISIONS (from user, already made — do NOT re-ask)
======================================================================
- Real money: user is "unsure, decide later" → treat as YES for safety.
  Means: feature flags default OFF, paper-vs-live toggle planned, daily loss cap
  planned, audit log planned. (Most of this lands in Phase 3/4, but design
  Phase 0 tables to support it.)
- User model: SOLO — no auth, no users table, no JWT/OTP. Single-tenant schema.
- First broker (Phase 4): Zerodha Kite Connect. Irrelevant for Phase 0.
- Deployment: local dev first. Don't touch vercel.json in this phase.
- Instruments: Nifty 50 + Bank Nifty (matches current UI).

======================================================================
YOUR PHASE (Phase 0) — DO NOT SCOPE-CREEP
======================================================================
Deliver these 6 features, each with TDD criteria from MASTER_PLAN.md:

  0.1 PostgreSQL + Alembic migrations; add NEW tables alongside existing
      SQLite paper trading. Do NOT migrate paper-trade data in this phase.
      Required new tables (minimum):
        - ohlcv_cache (symbol, interval, ts, o, h, l, c, v)  [indexed]
        - signals     (id, ts, symbol, direction, confidence, source_version, payload_json)
        - trades      (id, deployment_id nullable, symbol, entry_ts, exit_ts,
                       entry_price, exit_price, qty, pnl, charges, status, mode)
        - backtest_runs (id, strategy_config_json, start_date, end_date, capital,
                         status, result_json, created_at)
        - audit_log   (id, ts, action, payload_json, actor)   [immutable — no UPDATE/DELETE]
      Keep schema additive-only. No drops, no renames.

  0.2 pytest (backend, with pytest-asyncio) + vitest (frontend); coverage >= 60%
      on touched files. Add at least 3 example tests per side to seed the suite.

  0.3 .env + .env.example + pydantic-settings config loader. Required env vars:
        DATABASE_URL, LOG_LEVEL, ENABLE_ML_SIGNAL (default false),
        ENABLE_LIVE_BROKER (default false), ENABLE_AUTO_EXECUTION (default false)
      Missing required var → startup raises with clear message naming it.

  0.4 Fix CI postcss ESM issue. (NOTE: the prep commit already added
      "type":"module" to frontend/package.json — verify it's there, verify
      `npm run build` passes locally, then confirm GitHub Actions goes green.)

  0.5 Structured JSON logging with request-id propagation (FastAPI middleware).
      All log lines for a single HTTP request share the same request_id.

  0.6 Feature-flag module at backend/config/feature_flags.py, sourced from
      env vars. Import everywhere via one helper, e.g. `from backend.config
      import feature_flags`. Add an integration test proving a flipped flag
      changes behavior.

======================================================================
WORKING PROTOCOL — MANDATORY, ONE STEP AT A TIME
======================================================================

STEP A — ORIENT (NO CODE YET)
  Read the four authoritative sources. Produce a one-page "Understanding & Gaps"
  note covering:
    - What Phase 0 means in the context of the existing code
    - Any ambiguity you found
    - Your proposed file layout (no code yet, just paths)
  Wait for user ack.

STEP B — QUESTIONNAIRE-DRIVEN CLARIFICATION
  For every decision where your confidence is <95%, ask ONE question at a time
  using this exact format (user's UI will render radios/checkboxes):

    <QUESTION id="Q1" type="radio">
    <TITLE>Which Postgres host for local dev?</TITLE>
    <CONTEXT>Affects Alembic config and connection-pool strategy.</CONTEXT>
    <OPTION value="docker-local">Docker Compose (postgres:16) — fully local, reproducible</OPTION>
    <OPTION value="neon-free">Neon free tier — cloud, no Docker install needed</OPTION>
    <OPTION value="supabase">Supabase — Postgres + dashboard UI</OPTION>
    <DEFAULT>docker-local</DEFAULT>
    <WHY-ASKING>Can't write the connection string or CI service container without knowing.</WHY-ASKING>
    </QUESTION>

  Rules:
    - radio = single choice; checkbox = multi; text only when unavoidable
    - Always include DEFAULT and WHY-ASKING
    - Ask the MOST BLOCKING question first
    - If the answer is findable in the repo, find it and cite — do NOT ask
    - Never batch unrelated questions

STEP C — CONFIDENCE GATE
  When your confidence reaches >=95%, state:
    "Confidence: 95%+. Proceeding to implementation plan."
  Post a short plan:
    - Files you will create / modify (list)
    - Test-first order (which test you'll write first)
  Wait for a single "go" from the user.

STEP D — TDD IMPLEMENTATION, ONE FEATURE AT A TIME
  For each Phase 0 feature (0.1 through 0.6), in that order:
    1. Write the failing test(s) matching the TDD criterion in MASTER_PLAN.md
    2. Show the user the failing test output and ask:
         "Approve this test? (Yes / Adjust / Skip)"
       using the questionnaire format
    3. Implement the minimal code to pass
    4. Run the test suite; show results
    5. Mark that feature's row in PHASE_0_SUMMARY.md as ✅ IMMEDIATELY
       (do NOT batch updates at the end)
    6. Commit (conventional commits: e.g. "feat(db): add alembic + ohlcv_cache table")

  Never implement more than one feature ahead of the summary doc.

STEP E — ANSWER USER QUESTIONS INLINE
  If the user asks anything mid-phase, answer directly with citations
  (file paths, line numbers, test names). Do not punt to "later".

STEP F — CLOSE THE PHASE
  Before declaring Phase 0 complete, verify:
    [ ] All 6 TDD criteria pass
    [ ] Backend pytest green + coverage report generated
    [ ] Frontend vitest green
    [ ] GitHub Actions CI green on a push to a throwaway branch
    [ ] docs/phases/PHASE_0_SUMMARY.md fully populated using the template
        in MASTER_PLAN.md — every feature marked pass with evidence link,
        or explicitly deferred with reason
    [ ] docs/phases/PHASE_1_KICKOFF_PROMPT.md generated, pre-filled with:
          - Phase 1 features from MASTER_PLAN.md
          - Handoff context (actual DB schema shipped, connection-string format,
            how to run tests, feature-flag values, known debt)
          - "Don't do this" list of dead ends you hit
    [ ] Existing paper trading flow still works end-to-end (manual smoke test
        documented in the summary)

  Then ask the user:
    "Phase 0 complete. Approve merge? (Yes / Request changes)"

======================================================================
HARD RULES — NON-NEGOTIABLE
======================================================================
- DO NOT delete or rename any existing file/table/route/component.
- DO NOT modify backend/ai/signal_engine.py, backend/indicators/engine.py,
  or any frontend chart component in this phase. Foundation only.
- DO NOT commit secrets. Every new env var goes in .env.example with a
  placeholder value.
- DO NOT skip Step B (questionnaire) even when a decision feels obvious.
- DO NOT weaken a TDD criterion silently. If one can't be met, STOP and
  escalate to the user.
- DO NOT use --no-verify, --no-gpg-sign, or any hook-bypass flag on git.
- DO NOT mock Postgres in integration tests. Use testcontainers or a
  disposable Docker postgres; unit tests may use sqlite-memory ONLY if the
  code under test is database-agnostic.
- Every database migration must be reversible (downgrade works).
- If you discover that MASTER_PLAN.md is wrong or incomplete, DO NOT silently
  change it — propose the edit to the user via questionnaire.

======================================================================
START NOW
======================================================================
Begin with STEP A. Read the four authoritative sources and post your
one-page Understanding & Gaps note.
```

---

## For the user who's pasting this

After you paste, the agent will:

1. Read the plan, spec, and codebase
2. Post a brief "Understanding & Gaps" note
3. Start asking you one multiple-choice question at a time (first one will likely be about Postgres hosting for local dev — Docker vs Neon vs Supabase)
4. Gate on your approval before writing any code
5. Write a failing test, get your approval on the test, then implement

If you want to accept a default and move on, reply with just the option value (e.g. `docker-local`). If you want to discuss, reply with a question — the agent will answer with citations before re-asking.
