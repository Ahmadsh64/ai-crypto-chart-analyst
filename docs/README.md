# Documentation index

Start here for product orientation. Living status lives in **[STATUS.md](STATUS.md)**.

## Product & status

| Doc | Purpose |
|-----|---------|
| [STATUS.md](STATUS.md) | Phase table, UI ownership, deferred surfaces |
| [architecture.md](architecture.md) | System layers, analysis modes, phase map |
| [setup_guide.md](setup_guide.md) | Local install (frontend + backend) |
| [api.md](api.md) | REST / WebSocket surface |

## UI / UX

| Doc | Purpose |
|-----|---------|
| [AI_MARKET_ANALYZER_UI_UX_SPEC.md](AI_MARKET_ANALYZER_UI_UX_SPEC.md) | Protected Analyzer layout (do not redesign) |
| [qa-artifacts/ui-ux-dashboard/](qa-artifacts/ui-ux-dashboard/) | UI regression artifacts |

## Engine specs (Phases 3–4)

| Doc | Phase |
|-----|-------|
| [indicators.md](indicators.md) | 3.1 |
| [strategy_definitions.md](strategy_definitions.md) | 3.2 (+ ICT roadmap notes) |
| [liquidity_definitions.md](liquidity_definitions.md) | 3.3 |
| [ob_fvg_definitions.md](ob_fvg_definitions.md) | 3.4 |
| [multi_timeframe_architecture.md](multi_timeframe_architecture.md) | 4.1 |
| [confluence_engine.md](confluence_engine.md) | 4.2 |
| [trade_plan_engine.md](trade_plan_engine.md) | 4.3 |
| [final_decision_engine.md](final_decision_engine.md) | 4.4 |

## Phase delivery notes (5–6)

Numbered `PHASE_*.md` files in this folder document delivery/audit for:

- **5.1–5.2.x** Historical replay, simulation, costs, analytics, robustness, reporting, seek, trade overlays
- **5.3 / 5.3.1** Trade-plan chart visualization + monitoring
- **5.4.x** AI vision orchestration + Market Analyzer + uploaded image analysis
- **5.5** Market Opportunities scanner
- **6.0.1–6.0.3.1** Database design, persistence foundation, Analyze soft-persist, History UI

Prefer [STATUS.md](STATUS.md) over individual PRE_AUDIT files when checking “is this shipped?”.

## QA artifacts

See [qa-artifacts/](qa-artifacts/) for phase-specific PASS reports and screenshots.
