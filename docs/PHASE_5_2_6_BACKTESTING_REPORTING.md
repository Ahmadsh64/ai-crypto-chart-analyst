# Phase 5.2.6 — Backtesting Reporting & Export

## Purpose

Professional historical backtesting reporting and export on top of existing replay, simulation, execution-cost, and analytics engines. This phase **assembles and formats** existing state — it does not invent metrics or change strategy / sim / cost / analytics formulas.

## Architecture

```
ReplaySession (clock T)
  → AnalyticsEngine.snapshot (source of truth for PF/WR/R/DD/equity)
  → TradeSimulator + CostEngine (join for prices, SL/TP, fees)
  → report_builder.build_report (read-only)
  → JSON / CSV / PDF
```

Reports are **in-memory only**. Each GET rebuilds from current session state. `report_id` and `generated_at` vary; content fingerprint (excluding those) is deterministic for identical state.

## Module

`backend/app/replay/reporting/`

| File | Role |
|------|------|
| `config.py` | `REPORT_VERSION`, disclaimer |
| `models.py` | `BacktestReportSnapshot`, trade/summary models |
| `report_builder.py` | Assembler; clock filter; no mutation |
| `trade_serializer.py` | Join analytics + sim + ledger VWAP exit |
| `summary_builder.py` | Pass-through `PerformanceSummary` → report view |
| `csv_export.py` | UTF-8 CSV (summary/trades/equity/drawdown) |
| `pdf_export.py` | reportlab multi-page PDF |
| `validation.py` | Safe filenames, no-future assert, fingerprint |

## API

| Method | Path | Status |
|--------|------|--------|
| GET | `/api/v1/replay/sessions/{id}/report` | 200 / 400 / 404 |
| GET | `.../report/summary` | 200 |
| GET | `.../report/trades` | 200 |
| GET | `.../report/equity` | 200 |
| GET | `.../report/drawdown` | 200 |
| GET | `.../report/export/csv?kind=summary\|trades\|equity\|drawdown` | 200 CSV |
| GET | `.../report/export/pdf` | 200 PDF |

Requires analytics enabled. Filters reuse `PUT .../analytics/filter`; metadata embeds `filter_context`.

## Field notes

- **Average exit price**: derived ledger VWAP of exit-role fills; `null` if none (`average_exit_price_source=ledger_vwap`).
- **Exit reason**: report uses `exit_type` + `lifecycle_status` (no free-text field invented).
- **Unavailable / infinite** metrics preserved; never shown as fabricated zeros.
- Trades / equity / drawdown points after the replay clock are excluded.

## Frontend

- `HistoricalBacktestReportPanel` under analytics on `/backtesting`
- Summary cards, equity/drawdown sparklines, completed trades table, export buttons
- `lib/download.ts` for Blob downloads

## Dependencies

- `reportlab==4.2.5` (PDF)
- stdlib `csv` (CSV)

## Limitations

- No persistent report store.
- No REST seek (unchanged from 5.2.5).
- Live sessions may have zero completed trades; fixture tests cover populated reports.
- Does not claim strategy profitability.

## Disclaimer

`HISTORICAL BACKTEST — SIMULATED RESULTS — NOT REAL ORDERS — NOT FINANCIAL ADVICE`
