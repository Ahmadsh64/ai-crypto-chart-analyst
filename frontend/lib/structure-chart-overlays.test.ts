import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyLabelCollisionPolicy,
  assertNoDuplicateAnnotationIds,
  buildCandleTimeSet,
  collectAnnotationPrices,
  dedupePriceMarkers,
  mapBosMarkers,
  mapBosSegments,
  mapChochMarkers,
  mapChochSegments,
  mapMssMarkers,
  mapSwingMarkers,
  resolveBrokenSwingTimestamp,
  selectRecentSegments,
  snapToCandleTime,
  toSegmentDrawSpecs,
  toUtcTimestamp,
  type BosSegmentPoints,
} from "./structure-chart-overlays";
import {
  buildCandleLookup,
  candleChangePct,
  lookupCandleAtTimeSec,
} from "./ohlc-crosshair";
import { VISUAL_FIXTURE } from "./chart-visual-fixture";

const baseSwing = {
  exchange: "binance" as const,
  symbol: "BTC/USDT",
  market_type: "spot" as const,
  timeframe: "1h" as const,
  confirmed: true,
  config_version: "ms-v1.0.0-balanced",
  candle_index: 3,
  confirmation_timestamp: "2024-01-01T03:00:00.000Z",
  previous_swing_key: null,
  previous_swing_price: null,
};

const swingOpts = {
  showSwings: true,
  showHh: true,
  showHl: true,
  showLh: true,
  showLl: true,
};

describe("structure-chart-overlays alignment", () => {
  it("converts ISO timestamps to UTC seconds (not milliseconds)", () => {
    const t = toUtcTimestamp("2024-06-01T03:00:00.000Z");
    assert.equal(t, 1717210800);
    assert.ok(t < 1e12, "must be seconds-scale for Lightweight Charts");
  });

  it("pins swing markers to exact prices with atPrice positions", () => {
    const swings = [
      {
        ...baseSwing,
        event_key: "swing:high:1",
        kind: "high",
        price: 150.5,
        candle_timestamp: "2024-01-01T01:00:00.000Z",
        classification: "HH",
      },
      {
        ...baseSwing,
        event_key: "swing:low:1",
        kind: "low",
        price: 110.25,
        candle_timestamp: "2024-01-01T02:00:00.000Z",
        classification: "HL",
      },
    ];
    const markers = mapSwingMarkers(swings as never, swingOpts);
    assert.equal(markers.length, 2);
    assert.equal(markers[0].price, 150.5);
    assert.equal(markers[0].position, "atPriceTop");
    assert.equal(markers[0].time, toUtcTimestamp("2024-01-01T01:00:00.000Z"));
    assert.equal(markers[1].price, 110.25);
    assert.equal(markers[1].position, "atPriceBottom");
  });

  it("honors independent HH/HL/LH/LL toggles", () => {
    const swings = [
      {
        ...baseSwing,
        event_key: "hh",
        kind: "high",
        price: 1,
        candle_timestamp: "2024-01-01T01:00:00.000Z",
        classification: "HH",
      },
      {
        ...baseSwing,
        event_key: "ll",
        kind: "low",
        price: 2,
        candle_timestamp: "2024-01-01T02:00:00.000Z",
        classification: "LL",
      },
    ];
    const onlyHh = mapSwingMarkers(swings as never, {
      ...swingOpts,
      showHh: true,
      showHl: false,
      showLh: false,
      showLl: false,
    });
    assert.equal(onlyHh.length, 1);
    assert.equal(onlyHh[0].text, "HH");
  });

  it("maps BOS segments from original swing timestamp to breakout candle", () => {
    const events = [
      {
        event_key: "bos:1",
        break_kind: "bos",
        direction: "bullish",
        broken_level: 130,
        broken_swing_key: "sh1",
        broken_swing_timestamp: "2024-01-01T04:00:00.000Z",
        close_price: 131,
        candle_timestamp: "2024-01-01T10:00:00.000Z",
        confirmation_timestamp: "2024-01-01T10:00:00.000Z",
        previous_bias: "undefined",
        new_bias: "bullish",
        config_version: "ms-v1.0.0-balanced",
        segment_active: false,
      },
    ];
    const segs: BosSegmentPoints[] = mapBosSegments(events as never, []);
    assert.equal(segs.length, 1);
    assert.equal(segs[0].points[0].time, toUtcTimestamp("2024-01-01T04:00:00.000Z"));
    assert.equal(segs[0].points[1].time, toUtcTimestamp("2024-01-01T10:00:00.000Z"));
    assert.equal(segs[0].points[0].value, 130);
    assert.equal(segs[0].price, 130);
  });

  it("snaps BOS endpoints onto candle open times", () => {
    const candleTimes = buildCandleTimeSet([
      "2024-01-01T04:00:00.000Z",
      "2024-01-01T10:00:00.000Z",
    ]);
    const events = [
      {
        event_key: "bos:1",
        break_kind: "bos",
        direction: "bullish",
        broken_level: 130,
        broken_swing_key: "sh1",
        broken_swing_timestamp: "2024-01-01T04:00:00Z",
        close_price: 131,
        candle_timestamp: "2024-01-01T10:00:00Z",
        confirmation_timestamp: "2024-01-01T10:00:00Z",
        previous_bias: "undefined",
        new_bias: "bullish",
        config_version: "ms-v1.0.0-balanced",
      },
    ];
    const segs = mapBosSegments(events as never, [], candleTimes);
    assert.equal(segs[0].start, toUtcTimestamp("2024-01-01T04:00:00.000Z"));
    assert.equal(segs[0].end, toUtcTimestamp("2024-01-01T10:00:00.000Z"));
    assert.equal(
      snapToCandleTime("2024-01-01T04:00:00Z", candleTimes),
      toUtcTimestamp("2024-01-01T04:00:00.000Z"),
    );
  });

  it("drops BOS segments whose endpoints are outside the candle series", () => {
    const candleTimes = buildCandleTimeSet(["2024-01-01T10:00:00.000Z"]);
    const events = [
      {
        event_key: "bos:old",
        break_kind: "bos",
        direction: "bullish",
        broken_level: 130,
        broken_swing_key: "sh1",
        broken_swing_timestamp: "2023-01-01T04:00:00.000Z",
        close_price: 131,
        candle_timestamp: "2023-01-01T10:00:00.000Z",
        confirmation_timestamp: "2023-01-01T10:00:00.000Z",
        previous_bias: "undefined",
        new_bias: "bullish",
        config_version: "ms-v1.0.0-balanced",
      },
    ];
    assert.equal(mapBosSegments(events as never, [], candleTimes).length, 0);
  });

  it("resolves swing timestamp via broken_swing_key when API field missing", () => {
    const swings = [
      {
        ...baseSwing,
        event_key: "sh1",
        kind: "high",
        price: 130,
        candle_timestamp: "2024-01-01T04:00:00.000Z",
      },
    ];
    const ts = resolveBrokenSwingTimestamp(
      {
        broken_swing_timestamp: null,
        broken_swing_key: "sh1",
        candle_timestamp: "2024-01-01T10:00:00.000Z",
      },
      swings as never,
    );
    assert.equal(ts, "2024-01-01T04:00:00.000Z");
  });

  it("places BOS labels at breakout candle and broken_level with distinct colors", () => {
    const markers = mapBosMarkers(
      [
        {
          event_key: "bos:1",
          break_kind: "bos",
          direction: "bearish",
          broken_level: 100.5,
          broken_swing_key: "sl1",
          broken_swing_timestamp: "2024-01-01T02:00:00.000Z",
          close_price: 99,
          candle_timestamp: "2024-01-01T08:00:00.000Z",
          confirmation_timestamp: "2024-01-01T08:00:00.000Z",
          previous_bias: "bullish",
          new_bias: "bearish",
          config_version: "ms-v1.0.0-balanced",
        },
      ] as never,
      true,
    );
    assert.equal(markers[0].price, 100.5);
    assert.equal(markers[0].time, toUtcTimestamp("2024-01-01T08:00:00.000Z"));
    assert.equal(markers[0].color, "#dc2626");
    assert.notEqual(markers[0].color, mapChochMarkers([], true)[0]?.color);
  });

  it("distinguishes CHoCH colors from BOS", () => {
    const bos = mapBosMarkers(
      [
        {
          event_key: "b",
          break_kind: "bos",
          direction: "bullish",
          broken_level: 1,
          broken_swing_key: "x",
          close_price: 2,
          candle_timestamp: "2024-01-01T01:00:00.000Z",
          confirmation_timestamp: "2024-01-01T01:00:00.000Z",
          previous_bias: "undefined",
          new_bias: "bullish",
          config_version: "v",
        },
      ] as never,
      true,
    );
    const choch = mapChochMarkers(
      [
        {
          event_key: "c",
          direction: "bullish",
          broken_level: 1,
          broken_swing_key: "x",
          close_price: 2,
          candle_timestamp: "2024-01-01T01:00:00.000Z",
          confirmation_timestamp: "2024-01-01T01:00:00.000Z",
          previous_bias: "bearish",
          new_bias: "bullish",
          config_version: "v",
          structure_break_key: "c",
        },
      ] as never,
      true,
    );
    assert.notEqual(bos[0].color, choch[0].color);
    assert.equal(bos[0].text, "BOS↑");
    assert.equal(choch[0].text, "CHoCH↑");
  });

  it("strips older label text without moving price coordinates", () => {
    const markers = [];
    for (let i = 0; i < 12; i++) {
      markers.push({
        id: `m${i}`,
        time: (1000 + i) as never,
        position: "atPriceTop" as const,
        shape: "arrowDown" as const,
        color: "#fff",
        text: "HH",
        price: 100 + i,
        kind: "swing" as const,
      });
    }
    const managed = applyLabelCollisionPolicy(markers, {
      maxLabeledPerCategory: 3,
      hideOlderLabels: true,
    });
    const withText = managed.filter((m) => m.text);
    const without = managed.filter((m) => !m.text);
    assert.equal(withText.length, 4); // swing floor is max(4, maxLabeledPerCategory)
    assert.equal(without.length, 8);
    for (let i = 0; i < 12; i++) {
      assert.equal(managed[i].price, markers[i].price);
      assert.equal(managed[i].time, markers[i].time);
    }
  });

  it("selectRecentSegments keeps newest ends without changing prices", () => {
    const segs = [
      { id: "a", end: 1 as never, price: 10 },
      { id: "b", end: 5 as never, price: 20 },
      { id: "c", end: 3 as never, price: 30 },
    ];
    const picked = selectRecentSegments(segs, 2, true);
    assert.equal(picked.length, 2);
    assert.deepEqual(
      picked.map((s) => s.id).sort(),
      ["b", "c"],
    );
    assert.equal(picked.find((s) => s.id === "b")!.price, 20);
  });

  it("prevents duplicate annotation keys after remapping (WS reconnect)", () => {
    const once = dedupePriceMarkers([
      ...mapBosMarkers(VISUAL_FIXTURE.bosEvents, true),
      ...mapBosMarkers(VISUAL_FIXTURE.bosEvents, true),
    ]);
    assert.equal(assertNoDuplicateAnnotationIds(once).length, 0);
  });

  it("draw specs keep exact broken_level and finite swing→break span", () => {
    const segs = mapBosSegments(VISUAL_FIXTURE.bosEvents, VISUAL_FIXTURE.swings);
    const specs = toSegmentDrawSpecs(segs);
    assert.equal(specs.length, 2);
    for (const spec of specs) {
      const src = VISUAL_FIXTURE.bosEvents.find((e) => e.event_key === spec.id)!;
      assert.equal(spec.price, src.broken_level);
      assert.equal(spec.start, toUtcTimestamp(src.broken_swing_timestamp!));
      assert.equal(spec.end, toUtcTimestamp(src.candle_timestamp));
      assert.ok(spec.end >= spec.start);
      assert.notEqual(spec.price, src.close_price);
    }
  });
});

describe("deterministic visual fixture", () => {
  it("maps swing prices exactly from fixture", () => {
    const markers = mapSwingMarkers(VISUAL_FIXTURE.swings, swingOpts);
    const sh = markers.find((m) => m.text === "HH");
    const sl = markers.find((m) => m.text === "LL");
    assert.ok(sh);
    assert.ok(sl);
    assert.equal(sh!.price, VISUAL_FIXTURE.swings[0].price);
    assert.equal(sl!.price, VISUAL_FIXTURE.swings[1].price);
  });

  it("maps BOS segment start/end/price exactly with candle snap", () => {
    const candleTimes = buildCandleTimeSet(VISUAL_FIXTURE.candles.map((c) => c.timestamp));
    const segs = mapBosSegments(VISUAL_FIXTURE.bosEvents, VISUAL_FIXTURE.swings, candleTimes);
    assert.equal(segs.length, 2);
    for (const seg of segs) {
      const src = VISUAL_FIXTURE.bosEvents.find((e) => e.event_key === seg.id)!;
      assert.equal(seg.price, src.broken_level);
      assert.equal(seg.start, toUtcTimestamp(src.broken_swing_timestamp!));
      assert.equal(seg.end, toUtcTimestamp(src.candle_timestamp));
      assert.ok(candleTimes.has(Number(seg.start)));
      assert.ok(candleTimes.has(Number(seg.end)));
    }
  });

  it("anchors CHoCH/MSS to broken_level at confirmation timestamps", () => {
    const choch = mapChochMarkers(VISUAL_FIXTURE.chochEvents, true);
    const mss = mapMssMarkers(VISUAL_FIXTURE.mssEvents, true);
    assert.equal(choch.length, 2);
    for (const m of choch) {
      const src = VISUAL_FIXTURE.chochEvents.find((e) => e.event_key === m.id)!;
      assert.equal(m.price, src.broken_level);
      assert.equal(m.time, toUtcTimestamp(src.candle_timestamp));
    }
    for (const m of mss) {
      const src = VISUAL_FIXTURE.mssEvents.find((e) => e.event_key === m.id)!;
      assert.equal(m.price, src.broken_level);
    }
  });

  it("OHLC crosshair lookup returns exact candle values", () => {
    const lookup = buildCandleLookup(VISUAL_FIXTURE.candles);
    const target = VISUAL_FIXTURE.candles[3]!;
    const sec = Math.floor(new Date(target.timestamp).getTime() / 1000);
    const hit = lookupCandleAtTimeSec(lookup, sec)!;
    assert.equal(hit.open, target.open);
    assert.equal(hit.high, target.high);
    assert.equal(hit.low, target.low);
    assert.equal(hit.close, target.close);
    assert.equal(hit.changePct, candleChangePct(target.open, target.close));
  });

  it("annotation prices stay stable across remaps (zoom/scroll/WS)", () => {
    const candleTimes = buildCandleTimeSet(VISUAL_FIXTURE.candles.map((c) => c.timestamp));
    const mapOnce = () => {
      const markers = applyLabelCollisionPolicy(
        dedupePriceMarkers([
          ...mapSwingMarkers(VISUAL_FIXTURE.swings, swingOpts),
          ...mapBosMarkers(VISUAL_FIXTURE.bosEvents, true),
          ...mapChochMarkers(VISUAL_FIXTURE.chochEvents, true),
        ]),
        { maxLabeledPerCategory: 8, hideOlderLabels: true },
      );
      const segs = mapBosSegments(VISUAL_FIXTURE.bosEvents, VISUAL_FIXTURE.swings, candleTimes);
      return { markers, segs, prices: collectAnnotationPrices(markers, segs) };
    };
    const a = mapOnce();
    const b = mapOnce();
    assert.deepEqual(
      a.markers.map((m) => ({ id: m.id, t: m.time, p: m.price, text: m.text })),
      b.markers.map((m) => ({ id: m.id, t: m.time, p: m.price, text: m.text })),
    );
    assert.deepEqual(
      a.segs.map((s) => ({ id: s.id, start: s.start, end: s.end, price: s.price })),
      b.segs.map((s) => ({ id: s.id, start: s.start, end: s.end, price: s.price })),
    );
  });

  it("maps CHoCH segments snapped to candle times", () => {
    const candleTimes = buildCandleTimeSet(VISUAL_FIXTURE.candles.map((c) => c.timestamp));
    const segs = mapChochSegments(VISUAL_FIXTURE.chochEvents, VISUAL_FIXTURE.swings, true, candleTimes);
    assert.equal(segs.length, 2);
    for (const seg of segs) {
      assert.ok(candleTimes.has(Number(seg.start)));
      assert.ok(candleTimes.has(Number(seg.end)));
    }
  });
});
