/**
 * Draws horizontal structure segments in the candlestick series coordinate space.
 *
 * X: chart.timeScale().timeToCoordinate (same bar slots as OHLC)
 * Y: candlestickSeries.priceToCoordinate (main price scale — never a side scale)
 */

import type {
  IChartApi,
  ISeriesApi,
  ISeriesPrimitive,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  SeriesAttachedParameter,
  Time,
  UTCTimestamp,
} from "lightweight-charts";

export interface StructureSegmentDrawSpec {
  id: string;
  start: UTCTimestamp;
  end: UTCTimestamp;
  price: number;
  color: string;
  lineWidth: number;
  dashed: boolean;
}

type BitmapTarget = {
  useBitmapCoordinateSpace: (
    fn: (scope: {
      context: CanvasRenderingContext2D;
      horizontalPixelRatio: number;
      verticalPixelRatio: number;
    }) => void,
  ) => void;
};

class StructureSegmentRenderer implements IPrimitivePaneRenderer {
  private readonly _segments: readonly StructureSegmentDrawSpec[];
  private readonly _chart: IChartApi;
  private readonly _series: ISeriesApi<"Candlestick">;

  constructor(
    chart: IChartApi,
    series: ISeriesApi<"Candlestick">,
    segments: readonly StructureSegmentDrawSpec[],
  ) {
    this._chart = chart;
    this._series = series;
    this._segments = segments;
  }

  draw(target: BitmapTarget): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hr = scope.horizontalPixelRatio;
      const vr = scope.verticalPixelRatio;
      const timeScale = this._chart.timeScale();

      for (const seg of this._segments) {
        if (seg.end < seg.start) continue;
        const x1 = timeScale.timeToCoordinate(seg.start as Time);
        const x2 = timeScale.timeToCoordinate(seg.end as Time);
        const y = this._series.priceToCoordinate(seg.price);
        if (x1 === null || x2 === null || y === null) continue;

        const bx1 = Math.round(Math.min(x1, x2) * hr);
        const bx2 = Math.round(Math.max(x1, x2) * hr);
        const by = Math.round(y * vr);
        if (bx2 - bx1 < 1) continue;

        ctx.save();
        ctx.strokeStyle = seg.color;
        ctx.lineWidth = Math.max(1, Math.round(seg.lineWidth * vr));
        if (seg.dashed) ctx.setLineDash([6 * hr, 4 * hr]);
        else ctx.setLineDash([]);

        ctx.beginPath();
        ctx.moveTo(bx1, by);
        ctx.lineTo(bx2, by);
        ctx.stroke();

        // Endpoint ticks at swing / breakout bar centers.
        const tick = Math.round(4 * vr);
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(bx1, by - tick);
        ctx.lineTo(bx1, by + tick);
        ctx.moveTo(bx2, by - tick);
        ctx.lineTo(bx2, by + tick);
        ctx.stroke();
        ctx.restore();
      }
    });
  }
}

class StructureSegmentPaneView implements IPrimitivePaneView {
  private readonly _chart: IChartApi;
  private readonly _series: ISeriesApi<"Candlestick">;
  private _segments: readonly StructureSegmentDrawSpec[] = [];

  constructor(chart: IChartApi, series: ISeriesApi<"Candlestick">) {
    this._chart = chart;
    this._series = series;
  }

  setSegments(segments: readonly StructureSegmentDrawSpec[]): void {
    this._segments = segments;
  }

  renderer(): IPrimitivePaneRenderer | null {
    if (!this._segments.length) return null;
    return new StructureSegmentRenderer(this._chart, this._series, this._segments);
  }

  zOrder(): "top" {
    return "top";
  }
}

/** One primitive attached to the candlestick series. */
export class StructureSegmentPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApi | null = null;
  private _series: ISeriesApi<"Candlestick"> | null = null;
  private _views: StructureSegmentPaneView[] = [];
  private _segments: StructureSegmentDrawSpec[] = [];
  private _requestUpdate: (() => void) | null = null;

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart;
    this._series = param.series as ISeriesApi<"Candlestick">;
    this._requestUpdate = param.requestUpdate;
    const view = new StructureSegmentPaneView(this._chart, this._series);
    view.setSegments(this._segments);
    this._views = [view];
    this._requestUpdate();
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._views = [];
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._views;
  }

  updateAllViews(): void {
    for (const v of this._views) v.setSegments(this._segments);
  }

  setSegments(segments: StructureSegmentDrawSpec[]): void {
    this._segments = segments;
    for (const v of this._views) v.setSegments(segments);
    this._requestUpdate?.();
  }

  getCoordinateSpaceSeries(): ISeriesApi<"Candlestick"> | null {
    return this._series;
  }

  getChart(): IChartApi | null {
    return this._chart;
  }

  getSegments(): readonly StructureSegmentDrawSpec[] {
    return this._segments;
  }
}
