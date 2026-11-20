"""PDF export for the backtest report (Phase 5.2.6).

Uses reportlab. Multi-page layout: executive summary, performance analysis
(equity + drawdown line plots), and paginated trade history. The same
disclaimer footer appears on every page.
"""

from __future__ import annotations

import io
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.replay.analytics.models import EquityCurve, MetricValue
from app.replay.reporting.config import format_decimal
from app.replay.reporting.models import BacktestReportSnapshot


# ─── Formatting helpers ───


def _iso(ts: datetime | None) -> str:
    if ts is None:
        return "—"
    return ts.isoformat().replace("+00:00", "Z")


def _dec(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return format_decimal(value) or "—"


def _metric(m: MetricValue | None) -> str:
    if m is None:
        return "N/A"
    if m.availability == "available":
        return _dec(m.value)
    if m.availability == "infinite":
        return "∞"
    return "N/A"


# ─── Page frame with disclaimer footer ───


def _make_footer(disclaimer: str, report_id: str, generated_at: datetime):
    def _draw(canvas: Canvas, doc: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        page_text = f"Page {doc.page}"
        canvas.drawString(15 * mm, 10 * mm, disclaimer)
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, page_text)
        canvas.drawString(
            15 * mm,
            13 * mm,
            f"Report {report_id} · generated {_iso(generated_at)}",
        )
        canvas.restoreState()

    return _draw


# ─── Equity / drawdown plot (plain PDF canvas drawing) ───


def _points_for_curve(curve: EquityCurve, initial: Decimal | None) -> list[float]:
    base = float(initial) if initial is not None else 0.0
    pts: list[float] = []
    for p in curve.points:
        if p.equity is not None:
            pts.append(float(p.equity))
        else:
            pts.append(base + float(p.cumulative_net_pnl))
    return pts


class _InlinePlot:
    """Minimal flowable that draws a line plot inline inside a Platypus flow."""

    def __init__(self, values: Sequence[float], *, width: float, height: float, title: str) -> None:
        self.values = list(values)
        self.width = width
        self.height = height
        self.title = title

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        return (self.width, self.height + 14)

    def drawOn(self, canvas: Canvas, x: float, y: float, _sW: float = 0.0) -> None:  # noqa: N803
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(colors.black)
        canvas.drawString(x, y + self.height + 2, self.title)

        canvas.setStrokeColor(colors.lightgrey)
        canvas.setLineWidth(0.5)
        canvas.rect(x, y, self.width, self.height, stroke=1, fill=0)

        if len(self.values) < 2:
            canvas.setFillColor(colors.grey)
            canvas.setFont("Helvetica", 8)
            canvas.drawCentredString(
                x + self.width / 2.0,
                y + self.height / 2.0,
                "Not enough data points",
            )
            canvas.restoreState()
            return

        vmin = min(self.values)
        vmax = max(self.values)
        span = (vmax - vmin) or 1.0
        n = len(self.values)
        step = self.width / (n - 1)

        canvas.setStrokeColor(colors.HexColor("#1f77b4"))
        canvas.setLineWidth(1.0)
        path = canvas.beginPath()
        for i, v in enumerate(self.values):
            px = x + i * step
            py = y + ((v - vmin) / span) * (self.height - 4) + 2
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        canvas.drawPath(path, stroke=1, fill=0)
        canvas.restoreState()

    # Platypus compatibility
    def getSpaceBefore(self) -> float:
        return 0.0

    def getSpaceAfter(self) -> float:
        return 6.0

    def getKeepWithNext(self) -> bool:
        return False

    def splitOn(self, _canvas, _availWidth, _availHeight):  # noqa: D401
        return []

    def split(self, _availWidth, _availHeight):  # noqa: D401
        return []


# ─── Document assembly ───


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Heading1"], fontSize=18, spaceAfter=6),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=13, spaceAfter=4),
        "muted": ParagraphStyle(
            "Muted",
            parent=base["BodyText"],
            fontSize=9,
            textColor=colors.grey,
        ),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=10),
        "disclaimer": ParagraphStyle(
            "Disclaimer",
            parent=base["BodyText"],
            fontSize=9,
            textColor=colors.HexColor("#8a4b00"),
            spaceAfter=6,
        ),
        # Compact wrapping cells for trade tables (full trade IDs + dense numerics).
        "cell": ParagraphStyle(
            "TradeCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=6.5,
            leading=8,
            wordWrap="CJK",
        ),
        "cell_header": ParagraphStyle(
            "TradeCellHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=8,
        ),
    }


def _escape(text: str) -> str:
    return (text or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cell(text: str, styles: dict, *, header: bool = False) -> Paragraph:
    """Wrap table cell text so long IDs stay readable without clipping."""
    style = styles["cell_header"] if header else styles["cell"]
    return Paragraph(_escape(text), style)


def _num_cell(text: str, styles: dict) -> Paragraph:
    """Numeric cell — right-aligned so values stay in their column."""
    style = ParagraphStyle(
        "TradeNumCell",
        parent=styles["cell"],
        alignment=TA_RIGHT,
    )
    return Paragraph(_escape(text), style)


def _ts_cell(ts: datetime | None, styles: dict) -> Paragraph:
    """Compact UTC timestamp (MM-DD + HH:MMZ) stacked to fit the column."""
    raw = _iso(ts)
    if raw == "—" or "T" not in raw:
        return Paragraph(_escape(raw), styles["cell"])
    date, time = raw.split("T", 1)
    # 2024-01-01 → 01-01 ; 00:21:00Z → 00:21Z
    md = date[5:] if len(date) >= 10 else date
    hm = time[:5] + "Z" if len(time) >= 5 else time
    html = f"{_escape(md)}<br/>{_escape(hm)}"
    return Paragraph(html, styles["cell"])


def _trade_id_cell(trade_id: str, styles: dict) -> Paragraph:
    """Full trade ID; long IDs wrap at '_' so every character remains visible."""
    raw = trade_id or "—"
    safe = _escape(raw)
    if len(raw) > 16 and "_" in raw:
        # Explicit line breaks after underscores — avoids mid-token clipping.
        safe = "_<br/>".join(safe.split("_"))
    return Paragraph(safe, styles["cell"])


def _summary_page(snapshot: BacktestReportSnapshot, styles: dict):
    meta = snapshot.metadata
    s = snapshot.summary
    story: list = []
    story.append(Paragraph("Historical Backtest Report", styles["title"]))
    story.append(Paragraph(snapshot.disclaimer, styles["disclaimer"]))
    story.append(Spacer(1, 4))

    header = [
        ["Session", meta.session_id],
        ["Exchange", meta.exchange.value],
        ["Symbol", meta.symbol],
        ["Market type", meta.market_type.value],
        ["Timeframes", ", ".join(tf.value for tf in meta.timeframes)],
        ["Replay window", f"{_iso(meta.replay_start)} → {_iso(meta.replay_end)}"],
        ["Replay clock", _iso(meta.replay_timestamp)],
        ["Initial equity", _dec(meta.initial_equity) + f" ({meta.initial_equity_source})"],
        ["Analytics version", meta.analytics_version or "—"],
    ]
    t = Table(header, colWidths=[40 * mm, 130 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Key metrics", styles["h2"]))
    metric_rows = [["Metric", "Value", "Availability"]]
    for km in s.key_metrics:
        if km.availability == "available":
            val = _dec(km.value) + (f" {km.unit}" if km.unit else "")
        elif km.availability == "infinite":
            val = "∞"
        else:
            val = "N/A"
        metric_rows.append([km.label, val, km.availability])
    mt = Table(metric_rows, colWidths=[60 * mm, 60 * mm, 50 * mm])
    mt.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(mt)

    story.append(Spacer(1, 8))
    extras = [
        ["Completed trades", str(s.completed_trade_count)],
        ["Winning", str(s.winning_trades)],
        ["Losing", str(s.losing_trades)],
        ["Break-even", str(s.break_even_trades)],
        ["Open", str(s.open_trades)],
        ["Partially closed", str(s.partially_closed_trades)],
        ["Excluded (open)", str(s.excluded_open_trades)],
        ["Excluded (partial)", str(s.excluded_partial_trades)],
    ]
    e = Table(extras, colWidths=[60 * mm, 110 * mm])
    e.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
            ]
        )
    )
    story.append(e)
    return story


def _performance_page(snapshot: BacktestReportSnapshot, styles: dict):
    story: list = [Paragraph("Performance Analysis", styles["h2"])]
    width = 170 * mm
    initial = snapshot.summary.initial_equity
    completed_values = _points_for_curve(snapshot.equity.completed, initial)
    cashflow_values = _points_for_curve(snapshot.equity.cashflow, initial)
    story.append(
        _InlinePlot(completed_values, width=width, height=55 * mm, title="Equity (completed-trade)")
    )
    story.append(Spacer(1, 6))
    story.append(
        _InlinePlot(cashflow_values, width=width, height=55 * mm, title="Equity (realized cash-flow)")
    )
    story.append(Spacer(1, 6))
    dd_vals = [float(p.drawdown) for p in snapshot.drawdown.points]
    story.append(
        _InlinePlot([-abs(v) for v in dd_vals], width=width, height=45 * mm, title="Drawdown")
    )
    story.append(Spacer(1, 8))

    dd = snapshot.drawdown.summary
    rows = [
        ["Max Drawdown", _dec(dd.max_drawdown), "Max Drawdown %", _metric(dd.max_drawdown_pct)],
        ["Current DD", _dec(dd.current_drawdown), "Current DD %", _metric(dd.current_drawdown_pct)],
        ["Peak", _iso(dd.peak_timestamp), "Trough", _iso(dd.trough_timestamp)],
        ["Recovery", _iso(dd.recovery_timestamp), "Available", "yes" if dd.available else "no"],
    ]
    t = Table(rows, colWidths=[35 * mm, 50 * mm, 35 * mm, 50 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.grey),
                ("BOX", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
            ]
        )
    )
    story.append(t)
    return story


# Completed-trade column widths (sum = 180mm inside A4 content frame).
# Exit type sits beside Dir (not after R) so type labels never collide with R.
_TRADE_COL_WIDTHS = [
    28 * mm,  # ID (full trade_id, wraps at '_')
    12 * mm,  # Dir (fits SHORT)
    10 * mm,  # Type (exit_type)
    16 * mm,  # Entry (compact UTC)
    16 * mm,  # Exit (compact UTC)
    15 * mm,  # Entry px
    22 * mm,  # Avg exit
    22 * mm,  # Net P&L
    18 * mm,  # Fees
    18 * mm,  # R
]

_OPEN_TRADE_COL_WIDTHS = [
    36 * mm,  # ID
    14 * mm,  # Dir
    22 * mm,  # Entry (compact UTC)
    28 * mm,  # Entry px
    28 * mm,  # Remaining
    50 * mm,  # Status
]


def _trade_table(snapshot: BacktestReportSnapshot, styles: dict):
    story: list = [Paragraph("Trade History", styles["h2"])]
    story.append(
        Paragraph(
            "Completed trades included in performance statistics. Open or incomplete "
            "trades are listed separately and excluded from completed-trade metrics.",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 4))

    header = [
        "ID",
        "Dir",
        "Type",
        "Entry",
        "Exit",
        "Entry Px",
        "Avg Exit",
        "Net P&L",
        "Fees",
        "R",
    ]
    data = [[_cell(h, styles, header=True) for h in header]]
    for row in snapshot.completed_trades:
        data.append(
            [
                _trade_id_cell(row.trade_id, styles),
                _cell(row.direction, styles),
                _cell(row.exit_type or "—", styles),
                _ts_cell(row.entry_timestamp, styles),
                _ts_cell(row.exit_timestamp, styles),
                _num_cell(_dec(row.entry_price), styles),
                _num_cell(_dec(row.average_exit_price), styles),
                _num_cell(_dec(row.net_realized_pnl), styles),
                _num_cell(_dec(row.fees), styles),
                _num_cell(_dec(row.r_multiple), styles),
            ]
        )
    if len(data) == 1:
        story.append(Paragraph("No completed trades in this report.", styles["body"]))
        return story

    tbl = Table(data, colWidths=_TRADE_COL_WIDTHS, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("BOX", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(tbl)
    if snapshot.completed_trades_truncated:
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"Table truncated to first {len(snapshot.completed_trades)} of "
                f"{snapshot.completed_trade_total} completed trades; full set available via CSV export.",
                styles["muted"],
            )
        )

    if snapshot.open_trades:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Open / incomplete trades", styles["h2"]))
        oheader = [
            "ID",
            "Dir",
            "Entry",
            "Entry Px",
            "Remaining",
            "Status",
        ]
        odata = [[_cell(h, styles, header=True) for h in oheader]]
        for row in snapshot.open_trades:
            odata.append(
                [
                    _trade_id_cell(row.trade_id, styles),
                    _cell(row.direction, styles),
                    _ts_cell(row.entry_timestamp, styles),
                    _num_cell(_dec(row.entry_price), styles),
                    _num_cell(_dec(row.remaining_quantity), styles),
                    _cell(row.lifecycle_status, styles),
                ]
            )
        otbl = Table(odata, colWidths=_OPEN_TRADE_COL_WIDTHS, repeatRows=1)
        otbl.setStyle(
            TableStyle(
                [
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("BOX", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(otbl)

    if snapshot.limitations:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Notes", styles["h2"]))
        for note in snapshot.limitations:
            story.append(Paragraph(f"• {note}", styles["muted"]))
    return story


def render_pdf(snapshot: BacktestReportSnapshot) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=f"Backtest Report {snapshot.metadata.report_id}",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="main",
    )
    footer = _make_footer(
        snapshot.disclaimer, snapshot.metadata.report_id, snapshot.metadata.generated_at
    )
    doc.addPageTemplates(
        [PageTemplate(id="default", frames=[frame], onPage=footer)]
    )

    styles = _styles()
    story: list = []
    story.extend(_summary_page(snapshot, styles))
    story.append(PageBreak())
    story.extend(_performance_page(snapshot, styles))
    story.append(PageBreak())
    story.extend(_trade_table(snapshot, styles))
    doc.build(story)
    return buf.getvalue()
