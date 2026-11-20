# Phase 5.4.0 — Browser QA Notes

Date: 2026-11-14  
Environment: local Next.js `:3000` + FastAPI `:8000`  
Fixture label: `LABELED_FIXTURE — TEST DATA — NOT LIVE TRADING EVIDENCE`

## Preconditions

- `OPENAI_API_KEY` empty → provider OpenAI path **NOT VERIFIED**
- `python-multipart` installed (required for vision upload routes)
- Backend restarted so `/api/v1/ai/*` routes load

## Results

| # | Check | Result |
|---|-------|--------|
| 1 | Open `/chart-analyzer` | PASS |
| 2 | Select BTC/USDT · 1h | PASS |
| 3 | Analyze button enabled | PASS |
| 4 | Analyze loading (`Analyzing…`, disabled) | PASS |
| 5 | Deterministic analysis panel (`NO TRADE · BTC/USDT`) | PASS |
| 6 | AI explanation with `AI_UNAVAILABLE` fallback text | PASS |
| 7 | Upload labeled fixture screenshot | PASS (preview + filename + size + remove) |
| 8 | Run Vision | PASS → `AI_UNAVAILABLE` (key missing) |
| 9 | Structured vision panel + image metadata 640×400 | PASS |
| 10 | Comparison `INSUFFICIENT_VISUAL_DATA` when vision not OK | PASS |
| 11 | API compare symbol/TF mismatch | PASS (API: `CONFLICTING`) |
| 12 | Invalid image upload | PASS (HTTP 422 `CORRUPTED_IMAGE`) |
| 13 | Missing OpenAI config | PASS (`AI_UNAVAILABLE`, engines intact) |
| 14 | Chart remains live during/after Analyze/Vision | PASS (LIVE price updates) |
| 15 | Entry/SL/TP from engines only | PASS (empty for NO TRADE; disclaimer present) |
| 16 | No execution claims | PASS |
| 17 | No secrets in UI | PASS |
| 18 | Live OpenAI Vision/Explainer success | **NOT VERIFIED** (no API key) |

## Screenshots

- `docs/screenshots/LABELED_FIXTURE_phase540_analyze_ai_unavailable.png`
- `docs/screenshots/LABELED_FIXTURE_phase540_ai_explanation_panel.png`
- `docs/screenshots/LABELED_FIXTURE_phase540_vision_ai_unavailable.png`
- `docs/screenshots/LABELED_FIXTURE_phase540_chart_screenshot.png` (upload fixture)
- `docs/screenshots/LABELED_FIXTURE_phase540_screenshot_upload_preview.png` (if captured)

## Notes

- Hydration warning from existing `ConfluencePanel` (pre-existing; not introduced by Phase 5.4.0 AI panels).
- Dual service fetch (decision + trade-plan) observed; deterministic paths unchanged.
