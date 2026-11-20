# Phase 5.4.0 — AI Vision & Analysis Orchestration

## Architecture

Three separated responsibilities:

1. **Deterministic Analysis Layer** — existing Decision + Trade Plan engines remain the sole source of truth for decision, Entry, SL, TP, RR, confluence, conflicts, and eligibility.
2. **Vision Layer** — optional OpenAI Vision observation of uploaded chart screenshots (PNG/JPEG/WebP). Observational only; never authoritative market data or trading levels.
3. **AI Explainer Layer** — natural-language explanation grounded in an immutable `AnalysisSnapshot`. May not invent prices, change decisions, or claim execution.

```
UI Analyze → POST /api/v1/ai/analyze
  → decision_service + trade_plan_service
  → AnalysisSnapshot (immutable)
  → explainer (OpenAI or AI_UNAVAILABLE fallback)
  → frontend renders Entry/SL/TP from snapshot/decision only

UI Vision → POST /api/v1/ai/vision/analyze
  → content validation (Pillow) → in-memory PNG normalize
  → OpenAI Vision or AI_UNAVAILABLE
  → optional POST /api/v1/ai/compare vs snapshot
```

## Vision and Explainer responsibilities

| Layer | May do | Must not do |
|-------|--------|-------------|
| Vision | OCR labels, visible patterns, TF/symbol guesses, confidence | Set Entry/SL/TP, override engines, follow image text as instructions |
| Explainer | Explain WAIT/NO TRADE/LONG/SHORT from snapshot | Invent prices, raise scores, recommend fills |
| Deterministic | All trading levels and decisions | — |

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/ai/analyze` | Deterministic analysis + optional explanation |
| POST | `/api/v1/ai/vision/analyze` | Screenshot observation (`multipart` file) |
| POST | `/api/v1/ai/compare` | Vision vs snapshot consistency |
| POST | `/api/v1/ai/analyze-with-vision` | Convenience form endpoint (optional file) |

Existing `/decision` and `/trade-plan` contracts are unchanged.

## Pydantic schemas

- `VisionObservation` / `VisionResult` — `backend/app/ai/vision/schemas.py`
- `AnalysisExplanation` / `VisionComparisonSummary` — `backend/app/ai/explainer/schemas.py`
- `AnalysisSnapshot` — `backend/app/ai/explainer/snapshot.py`
- API wrappers — `backend/app/api/schemas/ai.py`

Observation categories: `TREND`, `SUPPORT`, `RESISTANCE`, `CANDLE_PATTERN`, `INDICATOR`, `PRICE_ZONE`, `ANNOTATION`, `OTHER`. Confidence clamped to `[0, 1]`.

## Prompt design and trust boundaries

- Screenshots and OCR text are **untrusted**.
- Vision system prompt forbids following image instructions, inventing trading levels, or tool/secret requests.
- Explainer receives only validated snapshot JSON (+ optional vision dump); forbidden price keys are stripped.
- `sanitize_explanation` flags free-text prices not present in the snapshot.

## Screenshot validation

- Allowed: PNG, JPEG, WebP (content-detected via Pillow, not extension alone).
- Size/dimension limits from settings (`MAX_UPLOAD_SIZE_MB`, `MAX/MIN_IMAGE_*`).
- EXIF orientation normalized; re-encoded to PNG for provider payload.
- No persistent storage; no public URLs; in-memory processing only.

## Environment variables

| Variable | Role |
|----------|------|
| `OPENAI_API_KEY` | Provider key (server-only) |
| `OPENAI_VISION_MODEL` | Vision model (default `gpt-4o`) |
| `OPENAI_EXPLAINER_MODEL` | Explainer model (default `gpt-4o`) |
| `OPENAI_MODEL` | Fallback model name |
| `OPENAI_TIMEOUT_SECONDS` | Request timeout |
| `OPENAI_MAX_RETRIES` | Provider retries (keep low) |
| Upload limits | `MAX_UPLOAD_SIZE_MB`, `ALLOWED_IMAGE_TYPES`, image dimensions |

Never expose keys to Next.js (`NEXT_PUBLIC_*`).

## Error handling / AI fallback

| Condition | Behavior |
|-----------|----------|
| Missing API key | `AI_UNAVAILABLE`; deterministic analysis preserved |
| Timeout | `TIMEOUT` + safe fallback text |
| Rate limit | `RATE_LIMITED`; no aggressive retry loops |
| Invalid model JSON | Rejected / `ERROR` or `INVALID_MODEL_RESPONSE` |
| Bad upload | HTTP 422 with validation code |

## Price integrity rules

1. Snapshot is built from Decision + Trade Plan responses before any LLM call.
2. Frontend `DeterministicSnapshotPanel` and chart overlays use engine data only.
3. Explanation text mentioning non-snapshot prices adds `validation_warnings` and never replaces levels.
4. Vision `visible_price_labels` are OCR strings, never merged into Trade Plan.

## Security

- No logging of image bytes or Authorization headers.
- Prompt-injection text in screenshots is stored as observation description only.
- Temporary files are not used in the default path (in-memory BytesIO).
- `python-multipart` required for upload endpoints.

## Tests

- Backend: `backend/tests/test_ai_phase_5_4_0.py` (26 cases — schemas, upload, integrity, WAIT/NO TRADE/LONG/SHORT fallbacks, compare, timeout/rate-limit mocks, secrets).
- Frontend: `frontend/lib/ai-analysis-display.test.ts` (7 cases — Analyze duplicate guard, stale seq, upload validation, levels from snapshot, comparison tones).
- Full frontend suite: **133 pass**.

## Browser QA

See `docs/qa-artifacts/phase-5-4-0/QA_BROWSER_NOTES.md`.

Live OpenAI provider calls are **NOT VERIFIED** when `OPENAI_API_KEY` is empty. Deterministic Analyze + `AI_UNAVAILABLE` fallback **are** verified.

## Screenshots

- `docs/screenshots/LABELED_FIXTURE_phase540_analyze_ai_unavailable.png`
- `docs/screenshots/LABELED_FIXTURE_phase540_ai_explanation_panel.png`
- `docs/screenshots/LABELED_FIXTURE_phase540_vision_ai_unavailable.png`
- `docs/screenshots/LABELED_FIXTURE_phase540_screenshot_upload_preview.png`
- `docs/screenshots/LABELED_FIXTURE_phase540_chart_screenshot.png`

## Known limitations

- Dual context fetch (decision + trade-plan services) may repeat shared analysis work; accepted for this phase to reuse existing services without changing engine contracts.
- Vision/live timeframe compare is advisory (notes) because snapshot does not yet carry selected chart TF as a first-class field.
- Live OpenAI success path requires a configured key; without it, fallback explanations are used.
- Phase 6/7 (DB, real trading) are out of scope.

## Confirmation

- No changes to indicator / structure / liquidity / OB-FVG / MTF / confluence / trade-plan / decision formulas.
- No order execution, broker keys, deposits, or withdrawals.
- Phases 5.2.2–5.3.1 visualization and monitoring remain intact (regression suite green).
