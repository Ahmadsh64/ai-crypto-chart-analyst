# Phase 5.4.2.2 — User-Uploaded Chart Image Analysis & Reconstructed SMC Chart

## Modes

| Mode | UI | Vision input | Deterministic input |
|------|-----|--------------|---------------------|
| **LIVE_MARKET** | Binance/Bybit search + timeframe | Auto LWC `takeScreenshot()` | Selected live market |
| **UPLOADED_IMAGE** | PNG/JPEG/WebP upload + confirmation | Uploaded file | User-confirmed symbol/TF after recognition |

Both modes remain available. Neither replaces the other.

## Recognition

`POST /api/v1/ai/vision/analyze` returns `VisionResult` + `recognition` summary:

- Detected symbol / timeframe / exchange / platform with confidence
- Screenshot-observed price (OCR estimate only)
- `needs_symbol_confirmation` / `needs_timeframe_confirmation` when missing or confidence &lt; 0.7

Ambiguous fields are never silently guessed. The UI requires confirmation/correction before Analyze.

## Analyze

`POST /api/v1/ai/analyze-with-vision` accepts `analysis_mode=LIVE_MARKET|UPLOADED_IMAGE`.

- UPLOADED_IMAGE requires a file
- Deterministic engines still use confirmed exchange OHLCV only
- Vision never overrides Entry/SL/TP
- Response includes `recognition` and `price_comparison` (screenshot-observed vs verified ticker)

## Persistence (no schema migration)

Phase 6.0.3 semantics preserved (one Analyze → one soft persistence attempt).

| Mode | `analysis_sessions.source` | `snapshot_kind` |
|------|----------------------------|-----------------|
| LIVE_MARKET | `live_market` | `live_decision_bundle` |
| UPLOADED_IMAGE | `uploaded_image` | `uploaded_image_decision_bundle` |

Uploaded image bytes are **not** persisted (memory only during the request).

### Future migration (optional)

If product requires a dedicated `analysis_mode` column on `analysis_snapshots` (or first-class history filter), add an Alembic migration later. Current text fields already distinguish modes without changing schema.

## Reconstructed chart

After confirmation, `MarketChartPanel` loads verified candles for the confirmed market and renders existing SMC overlays + Trade Plan levels. Title: **Reconstructed chart (verified exchange OHLCV)**.

## Security

- Existing `validate_image_bytes` + EXIF normalize + size/dimension limits
- Client MIME/size validation
- Image bytes are not logged

## QA

Browser + API verification: `docs/qa-artifacts/phase-5-4-2-2/QA_REPORT.md`  
**Verdict: PASS WITH LIMITATIONS** (Vision key unset in QA env; mode stored via `source` / `snapshot_kind` without schema migration).
