/**
 * Draws translucent price×time zones (Order Blocks / FVGs) on the candle series.
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

export interface ZoneDrawSpec {
  id: string;
  start: UTCTimestamp;
  end: UTCTimestamp;
  priceHigh: number;
  priceLow: number;
  fillColor: string;
  strokeColor: string;
  dashed?: boolean;
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

class ZoneRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly _chart: IChartApi,
    private readonly _series: ISeriesApi<"Candlestick">,
    private readonly _zones: readonly ZoneDrawSpec[],
  ) {}

  draw(target: BitmapTarget): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const hr = scope.horizontalPixelRatio;
      const vr = scope.verticalPixelRatio;
      const timeScale = this._chart.timeScale();

      for (const z of this._zones) {
        if (z.end < z.start || z.priceHigh <= z.priceLow) continue;
        const x1 = timeScale.timeToCoordinate(z.start as Time);
        const x2 = timeScale.timeToCoordinate(z.end as Time);
        const y1 = this._series.priceToCoordinate(z.priceHigh);
        const y2 = this._series.priceToCoordinate(z.priceLow);
        if (x1 === null || x2 === null || y1 === null || y2 === null) continue;

        const bx1 = Math.round(Math.min(x1, x2) * hr);
        const bx2 = Math.round(Math.max(x1, x2) * hr);
        const by1 = Math.round(Math.min(y1, y2) * vr);
        const by2 = Math.round(Math.max(y1, y2) * vr);
        if (bx2 - bx1 < 1 || by2 - by1 < 1) continue;

        ctx.save();
        ctx.fillStyle = z.fillColor;
        ctx.fillRect(bx1, by1, bx2 - bx1, by2 - by1);
        ctx.strokeStyle = z.strokeColor;
        ctx.lineWidth = Math.max(1, Math.round(1 * vr));
        if (z.dashed) ctx.setLineDash([5 * hr, 4 * hr]);
        else ctx.setLineDash([]);
        ctx.strokeRect(bx1, by1, bx2 - bx1, by2 - by1);
        ctx.restore();
      }
    });
  }
}

class ZonePaneView implements IPrimitivePaneView {
  private _zones: readonly ZoneDrawSpec[] = [];

  constructor(
    private readonly _chart: IChartApi,
    private readonly _series: ISeriesApi<"Candlestick">,
  ) {}

  setZones(zones: readonly ZoneDrawSpec[]): void {
    this._zones = zones;
  }

  renderer(): IPrimitivePaneRenderer | null {
    if (!this._zones.length) return null;
    return new ZoneRenderer(this._chart, this._series, this._zones);
  }

  zOrder(): "bottom" {
    return "bottom";
  }
}

export class ZonePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApi | null = null;
  private _series: ISeriesApi<"Candlestick"> | null = null;
  private _views: ZonePaneView[] = [];
  private _zones: ZoneDrawSpec[] = [];
  private _requestUpdate: (() => void) | null = null;

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart;
    this._series = param.series as ISeriesApi<"Candlestick">;
    this._requestUpdate = param.requestUpdate;
    const view = new ZonePaneView(this._chart, this._series);
    view.setZones(this._zones);
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
    for (const v of this._views) v.setZones(this._zones);
  }

  setZones(zones: ZoneDrawSpec[]): void {
    this._zones = zones;
    for (const v of this._views) v.setZones(zones);
    this._requestUpdate?.();
  }
}
