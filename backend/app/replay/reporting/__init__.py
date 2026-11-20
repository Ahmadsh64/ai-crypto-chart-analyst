"""Phase 5.2.6 — Backtesting reporting & export."""

from app.replay.reporting.config import (
    DEFAULT_REPORT_CONFIG,
    DISCLAIMER,
    REPORT_VERSION,
    ReportConfig,
)
from app.replay.reporting.csv_export import render_csv
from app.replay.reporting.enums import EXPORT_KINDS, ExportKind
from app.replay.reporting.models import (
    BacktestReportSnapshot,
    ExportArtifact,
    ReportKeyMetric,
    ReportMetadata,
    ReportOpenTrade,
    ReportSummary,
    ReportTradeDetail,
)
from app.replay.reporting.pdf_export import render_pdf
from app.replay.reporting.report_builder import build_report
from app.replay.reporting.validation import (
    ReportError,
    build_export_filename,
    content_fingerprint,
    safe_filename_component,
)

__all__ = [
    "BacktestReportSnapshot",
    "DEFAULT_REPORT_CONFIG",
    "DISCLAIMER",
    "EXPORT_KINDS",
    "ExportArtifact",
    "ExportKind",
    "REPORT_VERSION",
    "ReportConfig",
    "ReportError",
    "ReportKeyMetric",
    "ReportMetadata",
    "ReportOpenTrade",
    "ReportSummary",
    "ReportTradeDetail",
    "build_export_filename",
    "build_report",
    "content_fingerprint",
    "render_csv",
    "render_pdf",
    "safe_filename_component",
]
