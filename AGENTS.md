# Thinkloop — Engineering Rules & Architectural Contract

## Product
A learner chats with an AI tutor. Each turn the backend: diagnoses what the
learner understands or misbelieves, verifies any math deterministically,
updates a per-concept mastery model, picks a teaching strategy by rules,
streams a reply, and persists everything. Principle: the LLM handles
language; Python + Postgres handle logic, state and correctness. The LLM
never has the final say on whether an answer is correct.

## Architecture Summary
Thinkloop is an AI Socratic tutoring platform built with a high-reliability,
async-first Python foundation across 16 sequential phases:
- Phases 1-8: Core Foundation, Content System, Chat/Streaming, Diagnosis Engine,
  Learner Model, Strategy & Orchestrator, Verification, Retention & Operations.
- Phases 9-16: Extended Features (Clock & Groundwork, Streak Calendar, Focus Timer,
  Doubt Log, Flashcards, Battle with AI, YouTube Video Suggestions, Voice Mode).

### Phases 1-8 Foundation & Tutoring Summary
- **Foundation**: FastAPI, async SQLAlchemy 2.x + asyncpg, PostgreSQL 16 (pgvector), Redis sliding-window rate limiting, RS256 JWKS auth, structured JSON logging with `X-Request-ID`.
- **Content**: Safe YAML content (concepts, prerequisite DAG, misconceptions, problems), pgvector cosine retrieval, Embedder protocol (FakeEmbedder / HttpEmbedder).
- **Dialogue & Orchestrator**: Fast Diagnoser, rule-based Strategy Engine, BKT mastery tracking, verification guard, SSE streaming.

### Phases 9-16 Extended Features Summary
- **Phase 9: Shared Groundwork**: Injectable `Clock` protocol (`SystemClock`, `FakeClock`). Feature flags (`FEATURE_*`). `user_preferences` (IANA timezone, daily goal, voice prefs). Idempotent `activity_events` logging with timezone-aware `local_date`.
- **Phase 10: Streak Calendar**: Pure `compute_streaks` function, streak freezes (1 earned per N days, cap M, max 1 consecutive), calendar heatmap, nightly Arq rollup job `streak_rollup`.
- **Phase 11: Focus Timer**: Server-authoritative Pomodoro study sessions (`focus_sessions`). Elapsed time computed via `Clock`. Early completion credit capped. Break suggestions. Arq cleanup job `focus_cleanup`.
- **Phase 12: Doubt Log**: Capture questions (`doubts`), concept auto-suggestion via retrieval, `/ask` binds to Socratic tutor session without dumping answers, resolution requires "own words" note, semantic duplicate detection, insights aggregation.
- **Phase 13: Flashcards**: Deterministic cards first from curated concepts & misconceptions; optional LLM-assisted cards (FAST_MODEL) grounded on source text with dedupe; SM-2 spaced repetition; lapse signals reopen misconceptions.
- **Phase 14: Battle with AI**: Timed duels against simulated AI opponent (reproducible seeded RNG, outcome by code, not LLM); verifier-graded problems; server-authoritative deadlines; Elo ratings; mastery updates with reduced weight; cosmetic LLM flavor text only.
- **Phase 15: YouTube Video Suggestions**: Trust ladder: Curated YAML (`content/videos/curated_videos.yaml`) first -> quota-aware YouTubeClient fallback. LLM never invents URLs or video IDs. Deterministic `video_ranker`.
- **Phase 16: Voice Mode**: Input/output layer wrapping orchestrator turn. STT/TTS protocols (Fake + real HTTP). `responder_voice_v1.md` prompt. Deterministic `speakable_text` and spoken-math normalizers. Ephemeral audio processing.

## Target Structure
```text
backend/
  app/
    main.py config.py logging.py errors.py
    api/        deps.py health.py me.py concepts.py sessions.py chat.py
                mastery.py focus.py doubts.py flashcards.py battles.py
                streak.py videos.py voice.py preferences.py
    core/       security.py rate_limit.py orchestrator.py diagnoser.py
                strategy.py responder.py verifier.py learner_model.py
                activity.py streak_calc.py battle_engine.py opponent.py
                flashcard_gen.py video_ranker.py voice_pipeline.py clock.py
    content/    schemas.py validator.py loader.py embedder.py retrieval.py
                service.py cli.py
    services/   llm.py history.py stt.py tts.py youtube.py
    db/         base.py session.py models.py migrations/
    schemas/    user.py error.py content.py chat.py diagnosis.py mastery.py
                preferences.py activity.py streak.py focus.py doubt.py
                flashcard.py battle.py video.py voice.py
    prompts/    diagnoser_v1.md responder_basic_v1.md strategy_*_v1.md
                flashcard_gen_v1.md doubt_resolve_v1.md opponent_flavor_v1.md
                responder_voice_v1.md
    jobs/       focus_cleanup.py streak_rollup.py
  content/
    physics/mechanics/  topic.yaml concepts.yaml misconceptions.yaml problems.yaml
    videos/             curated_videos.yaml
  evals/
    retrieval_cases.yaml      run_retrieval_eval.py
    flashcard_cases/          run_flashcard_eval.py
    video_cases.yaml          run_video_eval.py
    battle_sim/               run_battle_sim.py
  tests/
    unit/ integration/ content/ e2e/
  docs/         content-authoring.md architecture.md
  Makefile docker-compose.yml pyproject.toml .env.example .github/workflows/ci.yml
  AGENTS.md CLAUDE.md PROGRESS.md
```

## Product Principles
1. **The Thinkloop Principle**: The LLM handles language; Python + Postgres handle logic, state, correctness, scoring, and scheduling. The LLM never decides who wins a battle, whether an answer is correct, or whether a streak day counts.
2. **Every feature feeds the core**: Every feature feeds the learner model or the activity log; none is a disconnected mini-app.
3. **No answer leakage**: Never reveal `answer_spec` before policy allows (battles included).
4. **No hallucinated IDs or URLs**: The LLM may never invent URLs or video IDs. Only IDs returned by a verified source (curated YAML or YouTube API client) may be served.
5. **Reuse existing building blocks**: SM-2 pure functions, verifier, retrieval, orchestrator, rate limiter, and token budget. Do not duplicate them.

## Global Rules
1. **No real network calls in tests**: All external dependencies (LLM, embeddings, STT, TTS, YouTube, JWKS) use Fake implementations in tests.
2. **Authoritative Clock**: All time-dependent logic uses the injectable `Clock` (`SystemClock` / `FakeClock`), never `datetime.now()` directly. Server time is authoritative; never trust client timestamps for scoring, timers, or streaks.
3. **No business logic in routes**: Services injected with `Depends`; async only.
4. **Endpoint isolation & security**: Every endpoint requires auth, rate limiting, and strict user isolation (404 for other users' resources, never 403).
5. **Privacy in logs**: No learner message text, transcripts, or raw audio in logs (log IDs and lengths only). Audio is deleted immediately after transcription unless opted in.
6. **Database schema**: UUID pk, user_id FK, created_at, updated_at on all new tables. Reversible Alembic migrations with clean upgrade and downgrade.
7. **Feature flags**: Every new feature is behind a flag in `Settings` (`FEATURE_BATTLE`, `FEATURE_FOCUS`, `FEATURE_FLASHCARDS`, `FEATURE_DOUBTS`, `FEATURE_STREAK`, `FEATURE_VOICE`, `FEATURE_VIDEOS`). Disabled -> 404 with uniform error envelope. Tested.
8. **Versioned prompts**: Prompts stay versioned in `app/prompts/`. Models come from env (`FAST_MODEL`, `STRONG_MODEL`). No hardcoded model names, keys, or magic thresholds.
9. **Idempotency**: Every mutating endpoint that a client might retry accepts an optional `Idempotency-Key` header and is safe to repeat.
10. **Uniform error envelope**:
    ```json
    {
      "error": {
        "code": "STRING_CODE",
        "message": "Human-readable description",
        "request_id": "uuid-string"
      }
    }
    ```

## Definition of Done (DoD)
- `make verify` passes from a clean checkout (lint, types, test, migration checks, content validation, retrieval eval, flashcards eval, video eval, battle sim).
- All earlier phases pass without regression.
- Total test coverage >= 85%.
- All 7 feature flags supported and tested (disabled -> 404).
- Injectable `Clock` used everywhere; zero `datetime.now()` in `app/`.
- User isolation: 404 on accessing other users' resources.
- Migrations work up and down cleanly.
- Phase gates respected: cannot start Phase N+1 until Phase N gate is green and logged in `PROGRESS.md`.
- Checkpoints with user respected after Phase 10, Phase 14, and Phase 16.
- Final end-to-end integration test (`tests/e2e/test_features_flow.py`) passes cleanly.
