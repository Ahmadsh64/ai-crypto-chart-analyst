# AI Market Analyzer — UI/UX Specification

## Page hierarchy

1. Market Overview  
2. Decision  
3. Trade Levels  
4. Reconstructed Interactive Chart  
5. Expandable SMC Analysis  

---

## Market Overview

- Cryptocurrency name and trading pair  
- Exchange and timeframe  
- Verified live price and 24-hour change  
- Update timestamp and connection status  

---

## Trade Levels

- Entry price or entry zone  
- Stop Loss  
- Exit / invalidation  
- TP1, TP2, TP3  
- Missing levels display as **Unavailable**  

---

## Decision

- LONG, SHORT, WAIT, NO TRADE  
- Display the deterministic engine's reason  

---

## Chart and SMC

- Interactive chart with supported deterministic overlays  
- Seven expandable SMC sections  
- Avoid unnecessary information on the main screen  

---

## Uploaded Image Mode

- Distinguish screenshot-observed price from verified exchange price  
- Keep manual confirmation and deterministic analysis  

---

## Integrity

- Exchange data supplies live prices  
- Deterministic trade plan supplies trading levels  
- Vision cannot override trading decisions  
- No fabricated TP or Entry levels  

---

## QA results

- 153 frontend tests passed  
- Production build passed  
- Browser QA: live NO TRADE, upload price separation, mobile layout  
- QA artifacts: `docs/qa-artifacts/ui-ux-dashboard/`  

---

## Scope

- Trading formulas unchanged  
- SMC engines unchanged  
- Database schema and persistence unchanged  
- Phase 6.0.4 not started by this UI/UX change  

---

## Protected requirement (Phase 6.0.4+)

This approved UI/UX **must be preserved**. Cursor rule: `.cursor/rules/ai-market-analyzer-ui-ux-protected.mdc`.

During Phase 6.0.4:

- Do not redesign or restructure the AI Market Analyzer page.  
- Do not modify its Market Overview, Decision, Trade Levels, chart hierarchy, or expandable SMC sections.  
- Do not remove or change Uploaded Image Analysis or Live Market Analysis workflows.  
- Do not change the visual presentation of live prices, Entry, SL, Exit, or TP1–TP3.  
- Any Replay UI integration must follow the existing application design system and remain **separate** from the AI Market Analyzer layout.  
- Run the existing UI/UX regression tests and production build after implementation.  
- Treat this specification as a protected project requirement.  
