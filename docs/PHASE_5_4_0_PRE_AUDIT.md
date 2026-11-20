# Phase 5.4.0 — Pre-Implementation Audit

## Relevant files

| Area | Path |
|------|------|
| Chart Analyzer page | `frontend/app/(app)/chart-analyzer/page.tsx` |
| Analyze button | same — **disabled**, label `Analyze (coming soon)` |
| Screenshot UI | same — local `File` → object URL preview only |
| Frontend API | `frontend/services/api.ts` |
| Decision hook | `frontend/hooks/use-market-data.ts` → `GET /api/v1/decision` |
| Trade plan hook | same → `GET /api/v1/trade-plan` |
| Shared analysis context | `backend/app/services/analysis_context.py` |
| Decision service | `backend/app/services/decision_service.py` |
| Trade plan service | `backend/app/services/trade_plan_service.py` |
| AI package stub | `backend/app/ai/__init__.py` — docstring only (“Phase 5”) |
| Config | `backend/app/core/config.py` — OpenAI + upload settings present |
| Security | `backend/app/core/security.py` — optional X-API-Key (unused by market routes) |
| Env example | `.env.example` — `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_VISION_MODEL` |
| Deps | `backend/requirements.txt` — `openai==1.58.1`, `pillow==11.0.0`, `httpx` |

## Existing endpoints (reuse)

- `GET /api/v1/decision`
- `GET /api/v1/trade-plan`
- `GET /api/v1/confluence`
- `GET /api/v1/multi-timeframe`
- Market / indicators / structure / liquidity / ob-fvg
- **No** `/api/v1/ai/*` routes today

`compute_decision_response` already calls `build_analysis_context` → trade plan → decision (single shared context). Orchestration should reuse this path, not re-fetch engines ad hoc.

## Current Analyze button behavior

- Always `disabled`
- Title: “Decision engines activate in Phases 3.3–5”
- No click handler, no loading/error, no API call
- Sidebar “AI Analysis Summary” is placeholder empty text

## Current screenshot upload behavior

- Accepts `image/png,image/jpeg,image/jpg` via `<input type="file">`
- Creates blob preview URL; shows filename
- **No** remove control, size display, content validation, or upload to backend
- Does **not** trigger analysis on select (correct — user must request analysis)

## Existing AI integrations

- Config keys exist; `openai` SDK is installed
- **No** vision service, explainer, schemas, or routes implemented
- Root `.env`: `OPENAI_API_KEY` line present but **empty** (`key_configured=false`)
- Models default to `gpt-4o` for both chat and vision
- Missing dedicated `OPENAI_EXPLAINER_MODEL` (to add)

## Auth / rate limit / timeouts

- No app-wide auth on analysis routes
- Exchange HTTP client has rate-limit retry; no AI-specific rate limiting yet
- No AI request timeout settings in config yet
- CORS configured; secrets must stay server-side only

## Frontend loading / errors

- TanStack Query used for REST panels; WS for live updates
- Chart Analyzer Analyze path has no request/cancel/stale-seq pattern yet (to add)
- Phase 5.3/5.3.1 charts must remain untouched during AI calls

## Missing components

1. AI orchestration API (`/ai/analyze`, `/ai/vision/analyze`, `/ai/compare`)
2. Vision service + Pydantic validation + image validation (Pillow)
3. Explainer service + immutable analysis snapshot + price integrity checks
4. Vision↔live comparison
5. Enabled Analyze button + explanation / vision / comparison panels
6. Upload validation UX (size, remove, WebP, errors)
7. `AI_UNAVAILABLE` graceful fallback when key missing
8. Backend + frontend tests for AI layer

## Proposed architecture

```
Analyze click
  → POST /api/v1/ai/analyze
      → build_analysis_context + decision + trade_plan (existing services)
      → AnalysisSnapshot (immutable)
      → Explainer (OpenAI) OR AI_UNAVAILABLE
  → Frontend renders snapshot levels from deterministic fields only
      + explanation panel from validated schema

Optional screenshot
  → POST /api/v1/ai/vision/analyze (multipart)
      → validate image (type/size/dims/content)
      → VisionResult (structured, observational)
  → POST /api/v1/ai/compare
      → CONSISTENT | PARTIALLY_CONSISTENT | CONFLICTING | INSUFFICIENT_VISUAL_DATA
```

## Security considerations

- Never expose `OPENAI_API_KEY` to Next.js
- Treat image OCR/text as untrusted (prompt-injection resistant system prompts)
- No public URL storage of screenshots; temp/in-memory only + cleanup
- Validate model JSON with Pydantic; strip unauthorized prices
- No secret logging; safe HTTP errors

## Implementation risks

- Missing API key → must not break deterministic Analyze
- Model inventing prices → reject/sanitize; FE always uses snapshot levels
- Large uploads → enforce max size + dimensions
- Latency/timeouts → AbortController + request sequence on FE
- Must not touch Decision/Trade Plan/5.2–5.3.1 formulas

## Exact implementation plan

1. Extend settings (`openai_explainer_model`, timeouts, image dims, webp).
2. Implement `app/ai/vision`, `app/ai/explainer`, `app/ai/compare`, snapshot builder.
3. Add `api/routes/ai.py` + schemas; register in `main.py`.
4. Wire frontend Analyze + panels + API client.
5. Unit tests (backend heavy; FE for button/states).
6. Build + browser QA (live AI = NOT VERIFIED if key absent; test AI_UNAVAILABLE + deterministic path).
7. Phase docs + README status update only after verify.
