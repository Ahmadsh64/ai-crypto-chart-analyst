# Phase 5.4.2 — AI Market Analyzer UX & Automated Chart Vision

## Summary

Chart Analyzer is upgraded into **AI Market Analyzer**: searchable Binance/Bybit markets, automatic Lightweight Charts screenshot export, unified Analyze + Vision workflow, and structured deterministic result panels.

## Key behaviors

- Manual screenshot upload removed from the UI (backend Vision endpoints remain).
- One Analyze click → chart `takeScreenshot()` → `POST /api/v1/ai/analyze-with-vision` → at most one persistence bundle.
- Vision failures are soft: deterministic Decision / Trade Plan still return.
- AI never overwrites Entry / SL / TP.

## Markets

- Server TTL cache (5 minutes) for instrument catalogs.
- Search by symbol / native / base / quote.
- Optional `limit` / `offset` pagination.
- Bybit instruments-info cursor pagination.

## Out of scope

Trading formula changes, real execution, Phase 6.0.4.
