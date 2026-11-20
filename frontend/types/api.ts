export type HealthStatus = "ok" | "degraded" | "unavailable";

export interface ComponentStatus {
  name: string;
  status: HealthStatus;
  detail?: string | null;
}

export interface HealthResponse {
  status: HealthStatus;
  service: string;
  version: string;
  environment: string;
  timestamp: string;
  components: ComponentStatus[];
}

export type ExchangeId = "binance" | "bybit";
export type MarketType = "spot" | "usdt_m_futures" | "linear_perpetual";
export type Timeframe = "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d";

export interface MarketSelection {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
}

export interface ExchangeInfo {
  id: ExchangeId;
  name: string;
  market_types: MarketType[];
  status: HealthStatus;
}

export interface ExchangesResponse {
  exchanges: ExchangeInfo[];
  default_symbols: string[];
  timeframes: Timeframe[];
}

export interface TradingPair {
  symbol: string;
  base: string;
  quote: string;
  exchange: ExchangeId;
  market_type: MarketType;
  native_symbol: string;
  active: boolean;
}

export interface MarketsResponse {
  exchange: ExchangeId;
  market_type: MarketType;
  count: number;
  pairs: TradingPair[];
  last_updated: string;
  data_source: string;
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  is_closed: boolean;
  close_time?: string | null;
  quote_volume?: number | null;
  trades?: number | null;
}

export interface CandlesResponse {
  exchange: ExchangeId;
  market_type: MarketType;
  symbol: string;
  timeframe: Timeframe;
  count: number;
  candles: Candle[];
  latest_price?: number | null;
  last_updated: string;
  updated_at?: string | null;
  data_source: string;
}

export interface Ticker {
  symbol: string;
  exchange: ExchangeId;
  market_type: MarketType;
  last: number;
  bid?: number | null;
  ask?: number | null;
  high_24h?: number | null;
  low_24h?: number | null;
  volume_24h?: number | null;
  change_pct_24h?: number | null;
  updated_at: string;
}

export interface TickerResponse {
  ticker: Ticker;
  last_updated: string;
  data_source: string;
}

export type IndicatorStatus = "ready" | "warming_up" | "insufficient_data" | "error";

export type IndicatorId =
  | "ema_9"
  | "ema_20"
  | "ema_50"
  | "ema_100"
  | "ema_200"
  | "sma_20"
  | "sma_50"
  | "sma_200"
  | "rsi_14"
  | "macd"
  | "stoch_rsi"
  | "atr_14"
  | "bollinger"
  | "volume_sma_20"
  | "obv"
  | "relative_volume";

export interface IndicatorLatest {
  status: IndicatorStatus;
  is_forming: boolean;
  timestamp?: string | null;
  warmup_required: number;
  samples_used: number;
  params: Record<string, unknown>;
  value?: number | null;
  fields: Record<string, number | null>;
  detail?: string | null;
}

export interface IndicatorPoint {
  timestamp: string;
  values: Record<string, number | null>;
  is_closed: boolean;
}

export interface IndicatorSeriesResult {
  indicator: IndicatorId;
  params: Record<string, unknown>;
  warmup_required: number;
  status: IndicatorStatus;
  points: IndicatorPoint[];
  latest: IndicatorLatest;
}

export interface IndicatorsResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  timeframe: Timeframe;
  calculated_at: string;
  include_forming: boolean;
  closed_candles_used: number;
  data_source: string;
  indicators: Record<string, IndicatorLatest>;
  series: Record<string, IndicatorSeriesResult>;
  available_indicators: string[];
  metadata: Record<string, unknown>;
}

export type StructureBias = "undefined" | "bullish" | "bearish";
export type SwingKind = "high" | "low";
export type StructureLabel = "HH" | "LH" | "HL" | "LL";
export type StructureDirection = "bullish" | "bearish";

export interface SwingPoint {
  event_key: string;
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  timeframe: Timeframe;
  kind: SwingKind;
  price: number;
  candle_timestamp: string;
  confirmation_timestamp: string;
  confirmed: boolean;
  classification?: StructureLabel | null;
  previous_swing_key?: string | null;
  previous_swing_price?: number | null;
  config_version: string;
  candle_index: number;
}

export interface StructureBreakEvent {
  event_key: string;
  break_kind: "bos" | "choch";
  direction: StructureDirection;
  broken_level: number;
  broken_swing_key: string;
  /** Original swing candle timestamp for swing→break BOS segments. */
  broken_swing_timestamp?: string | null;
  close_price: number;
  candle_timestamp: string;
  confirmation_timestamp: string;
  previous_bias: StructureBias;
  new_bias: StructureBias;
  config_version: string;
  segment_start?: string | null;
  segment_end?: string | null;
  segment_active?: boolean;
}

export interface AmbiguousDualBreak {
  event_key: string;
  candle_timestamp: string;
  confirmation_timestamp: string;
  close_price: number;
  swing_high_level: number;
  swing_low_level: number;
  swing_high_key: string;
  swing_low_key: string;
  high: number;
  low: number;
  bias_unchanged: StructureBias;
  config_version: string;
}

export interface CHoCHEvent {
  event_key: string;
  direction: StructureDirection;
  broken_level: number;
  broken_swing_key: string;
  close_price: number;
  candle_timestamp: string;
  confirmation_timestamp: string;
  previous_bias: StructureBias;
  new_bias: StructureBias;
  config_version: string;
  structure_break_key: string;
}

export interface MSSEvent {
  event_key: string;
  direction: StructureDirection;
  choch_event_key: string;
  broken_level: number;
  close_price: number;
  candle_timestamp: string;
  confirmation_timestamp: string;
  body_size: number;
  atr_value: number;
  displacement_mult: number;
  previous_bias: StructureBias;
  new_bias: StructureBias;
  config_version: string;
}

export interface MarketStructureSnapshot {
  bias: StructureBias;
  latest_swing_high?: SwingPoint | null;
  latest_swing_low?: SwingPoint | null;
  /** Latest unbroken confirmed Swing High (bullish break target). */
  active_unbroken_swing_high?: number | null;
  /** Latest unbroken confirmed Swing Low (bearish break target). */
  active_unbroken_swing_low?: number | null;
  /** Legacy alias of active_unbroken_swing_high. */
  active_bullish_level?: number | null;
  /** Legacy alias of active_unbroken_swing_low. */
  active_bearish_level?: number | null;
  last_bos_key?: string | null;
  last_choch_key?: string | null;
  last_mss_key?: string | null;
  last_ambiguous_dual_break_key?: string | null;
  closed_candles_used: number;
  config_version: string;
  calculated_at: string;
}

export interface MarketStructureResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  timeframe: Timeframe;
  calculated_at: string;
  data_source: string;
  include_unconfirmed: boolean;
  config: Record<string, unknown>;
  snapshot: MarketStructureSnapshot;
  swings: SwingPoint[];
  unconfirmed_swings: SwingPoint[];
  bos_events: StructureBreakEvent[];
  choch_events: CHoCHEvent[];
  mss_events: MSSEvent[];
  ambiguous_dual_breaks: AmbiguousDualBreak[];
  metadata: Record<string, unknown>;
}

export type LiquidityType = "bsl" | "ssl";
export type LiquiditySourceType = "swing" | "eqh" | "eql";
export type LiquidityStatus = "active" | "swept" | "broken" | "invalidated";
/** @deprecated Side label — prefer liquidity_type + reaction_hint */
export type SweepDirection = "bullish_side" | "bearish_side";
/** Contextual ICT reaction only — not a trade signal */
export type ReactionHint = "bullish" | "bearish";

export interface LiquiditySwingContribution {
  swing_key: string;
  price: number;
  candle_timestamp: string;
  confirmation_timestamp: string;
}

export interface EqualExtremeCluster {
  event_key: string;
  kind: "eqh" | "eql";
  /** Representative median (backward-compatible) */
  level: number;
  representative_level?: number;
  min_price?: number;
  max_price?: number;
  price_range?: number;
  members: LiquiditySwingContribution[];
  member_count: number;
  first_detection_timestamp: string;
  latest_confirmation_timestamp: string;
  config_version: string;
  tolerance_used: number;
  atr_available: boolean;
}

export interface LiquidityLevel {
  event_key: string;
  liquidity_type: LiquidityType;
  source_type: LiquiditySourceType;
  price: number;
  status: LiquidityStatus;
  source_swing_keys: string[];
  source_swings: LiquiditySwingContribution[];
  cluster_key?: string | null;
  detection_timestamp: string;
  latest_confirmation_timestamp: string;
  status_changed_timestamp?: string | null;
  config_version: string;
  segment_start?: string | null;
  segment_end?: string | null;
  segment_active?: boolean;
}

export interface LiquiditySweep {
  event_key: string;
  /** @deprecated Prefer liquidity_type + reaction_hint */
  direction: SweepDirection;
  /** Contextual only — not a guaranteed reversal / trade signal */
  reaction_hint?: ReactionHint | null;
  liquidity_level_key: string;
  liquidity_type: LiquidityType;
  level_price: number;
  wick_extreme: number;
  close_price: number;
  penetration: number;
  candle_timestamp: string;
  confirmation_timestamp: string;
  confirmed: boolean;
  config_version: string;
}

export interface LiquiditySnapshot {
  config_version: string;
  closed_candles_used: number;
  active_bsl_count: number;
  active_ssl_count: number;
  eqh_count: number;
  eql_count: number;
  sweep_count: number;
  candle_range_start?: string | null;
  candle_range_end?: string | null;
  calculated_at: string;
}

export interface LiquidityResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  timeframe: Timeframe;
  calculated_at: string;
  data_source: string;
  include_unconfirmed: boolean;
  config: Record<string, unknown>;
  snapshot: LiquiditySnapshot;
  eqh_clusters: EqualExtremeCluster[];
  eql_clusters: EqualExtremeCluster[];
  bsl_levels: LiquidityLevel[];
  ssl_levels: LiquidityLevel[];
  sweeps: LiquiditySweep[];
  provisional_sweeps: LiquiditySweep[];
  ambiguous_crosses: unknown[];
  metadata: Record<string, unknown>;
}

export type ZoneSide = "bullish" | "bearish";
export type ObStatus = "active" | "partially_mitigated" | "mitigated" | "invalidated";
export type FvgStatus = "active" | "partially_filled" | "filled" | "invalidated";

export interface OrderBlock {
  event_key: string;
  side: ZoneSide;
  status: ObStatus;
  zone_low: number;
  zone_high: number;
  boundary_method: string;
  source_candle_timestamp: string;
  source_structure_kind: "bos" | "mss";
  source_structure_event_key: string;
  structure_candle_timestamp: string;
  detection_timestamp: string;
  first_mitigation_timestamp?: string | null;
  full_mitigation_timestamp?: string | null;
  invalidation_timestamp?: string | null;
  config_version: string;
  confirmed: boolean;
  segment_start?: string | null;
  segment_end?: string | null;
  segment_active?: boolean;
}

export interface FairValueGap {
  event_key: string;
  side: ZoneSide;
  status: FvgStatus;
  zone_low: number;
  zone_high: number;
  gap_size: number;
  candle1_timestamp: string;
  candle2_timestamp: string;
  candle3_timestamp: string;
  detection_timestamp: string;
  first_touch_timestamp?: string | null;
  max_fill_pct: number;
  full_fill_timestamp?: string | null;
  invalidation_timestamp?: string | null;
  config_version: string;
  confirmed: boolean;
  segment_start?: string | null;
  segment_end?: string | null;
  segment_active?: boolean;
}

export interface ObFvgSnapshot {
  config_version: string;
  closed_candles_used: number;
  active_ob_count: number;
  active_fvg_count: number;
  bullish_ob_count: number;
  bearish_ob_count: number;
  bullish_fvg_count: number;
  bearish_fvg_count: number;
  candle_range_start?: string | null;
  candle_range_end?: string | null;
  calculated_at: string;
}

export interface ObFvgResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  timeframe: Timeframe;
  calculated_at: string;
  data_source: string;
  include_unconfirmed: boolean;
  config: Record<string, unknown>;
  snapshot: ObFvgSnapshot;
  bullish_order_blocks: OrderBlock[];
  bearish_order_blocks: OrderBlock[];
  bullish_fvgs: FairValueGap[];
  bearish_fvgs: FairValueGap[];
  provisional_order_blocks: OrderBlock[];
  provisional_fvgs: FairValueGap[];
  metadata: Record<string, unknown>;
}

export type MtfDataQuality =
  | "ok"
  | "insufficient"
  | "stale"
  | "gaps"
  | "error"
  | "unavailable";

export type MtfOverallStatus = "ready" | "partial" | "unavailable";

export interface MtfTimeframeSeries {
  timeframe: Timeframe;
  purpose: string;
  duration_minutes: number;
  latest_candle_time?: string | null;
  latest_closed_candle_time?: string | null;
  latest_price?: number | null;
  candles_count: number;
  closed_candles_count: number;
  is_ready: boolean;
  is_stale: boolean;
  has_data_gaps: boolean;
  data_quality: MtfDataQuality;
  status_detail?: string | null;
  last_updated?: string | null;
  gap_count: number;
}

export interface MtfSyncMetadata {
  as_of: string;
  note: string;
  latest_closed_by_timeframe: Record<string, string | null>;
  forming_by_timeframe: Record<string, string | null>;
  aligned: boolean;
}

export interface MultiTimeframeSnapshot {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  calculated_at: string;
  config_version: string;
  overall_status: MtfOverallStatus;
  ready_timeframes: Timeframe[];
  unavailable_timeframes: Timeframe[];
  timeframes: MtfTimeframeSeries[];
  sync: MtfSyncMetadata;
  metadata: Record<string, unknown>;
}

export interface MultiTimeframeResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  calculated_at: string;
  data_source: string;
  config: Record<string, unknown>;
  snapshot: MultiTimeframeSnapshot;
  timeframes: MtfTimeframeSeries[];
  sync: MtfSyncMetadata;
  metadata: Record<string, unknown>;
}

export type PreliminaryAssessment =
  | "bullish_confluence"
  | "bearish_confluence"
  | "mixed"
  | "insufficient_evidence"
  | "data_unavailable";

export type EvidenceDirection = "bullish" | "bearish" | "neutral";

export interface ConfluenceEvidence {
  evidence_id: string;
  evidence_type: string;
  category: string;
  timeframe: Timeframe;
  direction: EvidenceDirection;
  strength: number;
  confidence: number;
  source_event_key: string;
  source_timestamp?: string | null;
  is_confirmed: boolean;
  is_active: boolean;
  explanation: string;
  excluded?: boolean;
  exclusion_reason?: string | null;
}

export interface ConfluenceConflict {
  conflict_type: string;
  severity: "low" | "medium" | "high" | "critical";
  affected_timeframes: Timeframe[];
  bullish_evidence_ids: string[];
  bearish_evidence_ids: string[];
  description: string;
  resolution_status: string;
}

export interface ConfluenceCategoryScore {
  category: string;
  weight: number;
  bullish_contribution: number;
  bearish_contribution: number;
  bullish_unit: number;
  bearish_unit: number;
}

export interface ConfluenceDataQuality {
  overall: string;
  is_analysis_complete: boolean;
  timeframes_used: Timeframe[];
  timeframes_unavailable: Timeframe[];
  timeframes_stale: Timeframe[];
  limitations: string[];
}

export interface ConfluenceResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  calculated_at: string;
  data_source: string;
  config: Record<string, unknown>;
  bullish_score: number;
  bearish_score: number;
  category_scores: ConfluenceCategoryScore[];
  evidence: ConfluenceEvidence[];
  excluded_evidence: ConfluenceEvidence[];
  conflicts: ConfluenceConflict[];
  preliminary_assessment: PreliminaryAssessment;
  assessment_strength: "strong" | "moderate" | "none";
  data_quality: ConfluenceDataQuality;
  summary: string;
  configuration_version: string;
  analysis_timestamp: string;
  metadata: Record<string, unknown>;
}

export type PlanStatus = "eligible" | "blocked" | "invalid";
export type PlanDirection = "bullish" | "bearish";

export interface TradePlanEntry {
  entry_low: number;
  entry_high: number;
  entry_reference_price: number;
  entry_type: string;
  entry_source: string;
  source_event_key: string;
  timeframe: string;
  entry_explanation: string;
  price_inside_zone: boolean;
}

export interface TradePlanStopLoss {
  stop_loss_price: number;
  stop_loss_source: string;
  stop_loss_distance: number;
  stop_loss_distance_pct: number;
  atr_value?: number | null;
  buffer_value: number;
  invalidation_explanation: string;
  source_event_key?: string | null;
}

export interface TradePlanTarget {
  index: number;
  label: string;
  price: number;
  source: string;
  source_event_key?: string | null;
  distance: number;
  distance_pct: number;
  risk_reward_ratio: number;
  explanation: string;
}

export interface TradePlanRisk {
  risk_distance: number;
  risk_distance_pct: number;
  reward_distances: number[];
  primary_rr?: number | null;
  minimum_required_rr: number;
  meets_minimum_rr: boolean;
}

export interface TradePlanSizing {
  account_balance: number;
  risk_percent: number;
  risk_amount: number;
  position_size?: number | null;
  position_notional?: number | null;
  estimated_loss_at_sl?: number | null;
  contract_multiplier?: number | null;
  sizing_available: boolean;
  sizing_explanation: string;
  is_hypothetical: boolean;
}

export interface TradePlanValidation {
  is_valid: boolean;
  validation_errors: string[];
  warnings: string[];
  blocking_reasons: string[];
}

export interface TradePlanEligibility {
  is_eligible: boolean;
  direction?: PlanDirection | null;
  blocking_reasons: string[];
  notes?: string[];
}

export interface TradePlanDataQuality {
  overall: string;
  is_analysis_complete: boolean;
  timeframes_used: string[];
  timeframes_unavailable: string[];
  timeframes_stale: string[];
  limitations: string[];
  current_price?: number | null;
  atr_available: boolean;
}

export interface TradePlanResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  plan_id: string;
  direction?: PlanDirection | null;
  plan_status: PlanStatus;
  entry?: TradePlanEntry | null;
  stop_loss?: TradePlanStopLoss | null;
  take_profit_targets: TradePlanTarget[];
  risk?: TradePlanRisk | null;
  position_sizing?: TradePlanSizing | null;
  validation: TradePlanValidation;
  eligibility: TradePlanEligibility;
  supporting_evidence_ids: string[];
  conflict_ids: string[];
  invalidation_conditions: string[];
  explanations: string[];
  configuration_version: string;
  analysis_timestamp: string;
  data_quality: TradePlanDataQuality;
  confluence_assessment?: string | null;
  confluence_assessment_strength?: string | null;
  bullish_score?: number | null;
  bearish_score?: number | null;
  spot_short_warning?: string | null;
  analysis_only_disclaimer: string;
  config: Record<string, unknown>;
  data_source: string;
  metadata: Record<string, unknown>;
}

export type FinalDecision = "LONG" | "SHORT" | "WAIT" | "NO TRADE";
export type SetupLifecycle =
  | "setup_detected"
  | "awaiting_confirmation"
  | "entry_confirmed"
  | "invalidated"
  | "expired";

export interface DecisionConfluenceScores {
  bullish_score: number;
  bearish_score: number;
  preliminary_assessment?: string | null;
  assessment_strength?: string | null;
}

export interface DecisionEntryConfirmation {
  status: string;
  is_confirmed: boolean;
  confirmation_type?: string | null;
  source_event_key?: string | null;
  timeframe?: string | null;
  direction?: string | null;
  explanation: string;
  evidence_ids?: string[];
  blocking_reasons?: string[];
}

export interface DecisionDataQuality {
  overall: string;
  is_analysis_complete: boolean;
  timeframes_used: string[];
  timeframes_unavailable: string[];
  timeframes_stale: string[];
  limitations: string[];
  current_price?: number | null;
}

export interface DecisionResponse {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  decision_id: string;
  decision: FinalDecision;
  decision_reason: string;
  direction?: PlanDirection | null;
  lifecycle: SetupLifecycle;
  confluence_scores: DecisionConfluenceScores;
  trade_plan_status?: string | null;
  trade_plan_id?: string | null;
  entry_confirmation: DecisionEntryConfirmation;
  entry_zone_summary?: Record<string, unknown> | null;
  stop_loss_price?: number | null;
  take_profit_prices: number[];
  primary_rr?: number | null;
  risk_amount?: number | null;
  position_size?: number | null;
  price_inside_entry_zone?: boolean | null;
  supporting_evidence: string[];
  blocking_conditions: string[];
  conflict_ids: string[];
  data_quality: DecisionDataQuality;
  spot_restriction?: string | null;
  analysis_only_disclaimer: string;
  configuration_version: string;
  analysis_timestamp: string;
  setup_detected_at?: string | null;
  expires_at?: string | null;
  config: Record<string, unknown>;
  data_source: string;
  metadata: Record<string, unknown>;
}

/* ─── Phase 5.1 Historical Replay ─── */

export type ReplaySpeed = "1x" | "2x" | "5x" | "10x" | "50x" | "100x" | "max";
export type ReplayStatus =
  | "created"
  | "loading"
  | "ready"
  | "running"
  | "paused"
  | "completed"
  | "stopped"
  | "error";

export interface TimeframeReplayState {
  timeframe: Timeframe;
  closed_candles: Candle[];
  closed_count: number;
  forming_candle: Candle | null;
  latest_closed_open_time?: string | null;
  latest_closed_close_time?: string | null;
  latest_price?: number | null;
  is_ready: boolean;
  data_quality: "ok" | "insufficient" | "gaps" | "empty";
  gap_count: number;
}

export interface ReplaySnapshot {
  session_id: string;
  replay_timestamp: string;
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  event_index: number;
  event_count: number;
  progress_pct: number;
  status: ReplayStatus;
  speed: ReplaySpeed;
  timeframes: Record<string, TimeframeReplayState>;
  gaps: Array<{
    timeframe: Timeframe;
    after_open: string;
    before_open: string;
    missing_estimate: number;
  }>;
  data_quality: "ok" | "partial" | "insufficient" | "empty";
  limitations: string[];
  config_version: string;
  timestamp_convention: string;
}

export interface ReplaySessionInfo {
  session_id: string;
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  start_time: string;
  end_time: string;
  timeframes: Timeframe[];
  status: ReplayStatus;
  speed: ReplaySpeed;
  event_index: number;
  event_count: number;
  replay_timestamp?: string | null;
  created_at: string;
  error?: string | null;
  config_version: string;
  data_quality: string;
  limitations: string[];
}

export interface ReplaySessionResponse {
  session: ReplaySessionInfo;
  snapshot: ReplaySnapshot;
}

export interface ReplayControlResponse {
  session_id: string;
  status: ReplayStatus;
  speed: ReplaySpeed;
  snapshot: ReplaySnapshot;
  message?: string | null;
}

export interface CreateReplaySessionRequest {
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  start_time: string;
  end_time: string;
  timeframes?: Timeframe[];
  speed?: ReplaySpeed;
}

/* ─── Phase 5.2.1 Historical Analysis ─── */

export interface HistoricalAnalysisSnapshot {
  session_id: string;
  replay_timestamp: string;
  event_index: number;
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  decision: FinalDecision | string;
  decision_reason: string;
  lifecycle_status: string;
  direction?: string | null;
  bullish_score: number;
  bearish_score: number;
  confluence_strength?: string | null;
  preliminary_assessment?: string | null;
  conflicts: string[];
  evidence_summary: string[];
  entry_zone?: Record<string, unknown> | null;
  stop_loss?: number | null;
  take_profit_levels: number[];
  risk_reward?: number | null;
  trade_plan_status?: string | null;
  hypothetical_plan_disclaimer: string;
  data_quality: string;
  data_ready: boolean;
  limitations: string[];
  analysis_versions: Record<string, string>;
  analysis_error?: string | null;
  config_version: string;
  analysis_timestamp: string;
  closed_candle_counts: Record<string, number>;
}

export interface ReplayAnalysisToggleResponse {
  session_id: string;
  analysis_enabled: boolean;
  snapshot: HistoricalAnalysisSnapshot | null;
  message?: string | null;
}

export interface ReplayAnalysisCurrentResponse {
  session_id: string;
  analysis_enabled: boolean;
  snapshot: HistoricalAnalysisSnapshot | null;
}

/* ─── Phase 5.2.2 Historical Trade Simulation ─── */

export type TradeLifecycleStatus =
  | "pending_entry"
  | "open"
  | "partially_closed"
  | "closed_tp"
  | "closed_sl"
  | "closed_expired"
  | "cancelled"
  | "rejected"
  | "ambiguous_execution";

export interface SimulationExecutionEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  price?: number | null;
  quantity?: number | null;
  remaining_quantity?: number | null;
  tp_index?: number | null;
  reason?: string | null;
  ambiguity_policy_applied?: string | null;
  candle_open_time?: string | null;
  metadata?: Record<string, unknown>;
}

export interface SimulatedTrade {
  trade_id: string;
  signal_key: string;
  replay_session_id: string;
  signal_id?: string | null;
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  direction: "LONG" | "SHORT";
  decision: string;
  decision_timestamp: string;
  decision_event_index: number;
  lifecycle_status: TradeLifecycleStatus;
  entry_zone?: Record<string, unknown> | null;
  entry_limit_price?: number | null;
  entry_price?: number | null;
  entry_timestamp?: string | null;
  exit_timestamp?: string | null;
  initial_stop_loss: number;
  current_stop_loss: number;
  take_profit_levels: number[];
  tp_allocations: number[];
  tp_filled: boolean[];
  original_quantity: number;
  remaining_quantity: number;
  executed_quantity: number;
  quantity_closed_tp: number;
  quantity_closed_sl: number;
  quantity_closed_expired: number;
  expires_at?: string | null;
  rejection_reason?: string | null;
  ambiguity_warnings: string[];
  realized_pnl_placeholder: null;
  risk_reward?: number | null;
  decision_reason?: string | null;
  execution_events: SimulationExecutionEvent[];
  config_version: string;
  created_at: string;
  updated_at: string;
}

export interface SimulationOverview {
  enabled: boolean;
  pending_count: number;
  open_count: number;
  partially_closed_count: number;
  closed_count: number;
  rejected_count: number;
  cancelled_count: number;
  ambiguous_count: number;
  total_trades: number;
  config: Record<string, unknown>;
  disclaimer: string;
  replay_timestamp?: string | null;
}

export interface SimulationSnapshot {
  session_id: string;
  enabled: boolean;
  overview: SimulationOverview;
  trades: SimulatedTrade[];
  recent_events: SimulationExecutionEvent[];
  config_version: string;
  disclaimer: string;
}

export interface ReplaySimulationToggleResponse {
  session_id: string;
  simulation_enabled: boolean;
  analysis_enabled: boolean;
  snapshot: SimulationSnapshot;
  message?: string | null;
}

export interface ReplaySimulationCurrentResponse {
  session_id: string;
  simulation_enabled: boolean;
  snapshot: SimulationSnapshot;
}

/* ─── Phase 5.2.3 Execution Costs ─── */

export interface LedgerEntry {
  execution_id: string;
  source_event_id: string;
  trade_id: string;
  replay_session_id: string;
  event_timestamp: string;
  exchange: ExchangeId;
  market_type: MarketType;
  symbol: string;
  direction: "LONG" | "SHORT";
  execution_role: "entry" | "exit";
  order_type_estimate: string;
  maker_taker: "maker" | "taker" | "unknown";
  maker_taker_estimated: boolean;
  executed_quantity: string | number;
  reference_price: string | number;
  execution_price: string | number;
  executed_notional: string | number;
  fee_rate: string | number;
  fee_amount: string | number;
  slippage_amount: string | number;
  spread_cost: string | number;
  gross_realized_pnl?: string | number | null;
  allocated_entry_fee?: string | number | null;
  net_realized_pnl?: string | number | null;
  cost_model_version: string;
  fee_config_source: string;
  fee_schedule_version: string;
  assumptions: string[];
  warnings: string[];
}

export interface SessionCostSummary {
  session_id: string;
  enabled: boolean;
  cost_model_version: string;
  fee_config_source: string;
  fee_schedule_version: string;
  gross_realized_pnl: string | number;
  total_entry_fees: string | number;
  total_exit_fees: string | number;
  total_fees: string | number;
  total_slippage: string | number;
  total_spread_cost: string | number;
  total_costs: string | number;
  net_realized_pnl: string | number;
  trade_count: number;
  ledger_entry_count: number;
  assumptions: string[];
  warnings: string[];
  disclaimer: string;
  config: Record<string, unknown>;
  replay_timestamp?: string | null;
}

export interface TradeCostSummary {
  trade_id: string;
  session_id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  lifecycle_status: string;
  total_executed_quantity: string | number;
  remaining_open_quantity: string | number;
  total_gross_realized_pnl: string | number;
  total_entry_fees: string | number;
  total_exit_fees: string | number;
  total_fees: string | number;
  total_slippage: string | number;
  total_spread_cost: string | number;
  total_costs: string | number;
  net_realized_pnl: string | number;
  cost_model_version: string;
  fee_config_source: string;
  assumptions: string[];
  warnings: string[];
  ledger_entry_count: number;
}

export interface CostSnapshot {
  session_id: string;
  enabled: boolean;
  summary: SessionCostSummary;
  trades: TradeCostSummary[];
  recent_ledger: LedgerEntry[];
  cost_model_version: string;
  disclaimer: string;
}

export interface ExecutionCostConfigPublic {
  config_version?: string;
  enabled?: boolean;
  maker_fee_rate?: string | number | null;
  taker_fee_rate?: string | number | null;
  fee_currency?: string;
  fee_source?: string;
  fee_schedule_version?: string;
  slippage_policy?: string;
  slippage_bps?: string | number;
  slippage_percentage?: string | number;
  spread_policy?: string;
  spread_bps?: string | number;
  spread_percentage?: string | number;
  maker_taker_fallback?: string;
  contract_multiplier?: string | number;
  disclaimer?: string;
}

export interface ReplayCostToggleResponse {
  session_id: string;
  costs_enabled: boolean;
  simulation_enabled: boolean;
  analysis_enabled: boolean;
  snapshot: CostSnapshot;
  message?: string | null;
}

export interface ReplayCostCurrentResponse {
  session_id: string;
  costs_enabled: boolean;
  snapshot: CostSnapshot;
}

/* ─── Phase 5.2.4 Performance Analytics ─── */

export type MetricAvailability = "available" | "unavailable" | "infinite";

export interface MetricValue {
  value: string | number | null;
  availability: MetricAvailability;
  label?: string | null;
}

export interface TradeStatistics {
  total_simulated_trades: number;
  completed_trades: number;
  open_trades: number;
  partially_closed_trades: number;
  winning_trades: number;
  losing_trades: number;
  break_even_trades: number;
  win_rate: MetricValue;
  loss_rate: MetricValue;
  average_winning_trade: MetricValue;
  average_losing_trade: MetricValue;
  largest_winning_trade: MetricValue;
  largest_losing_trade: MetricValue;
}

export interface ProfitabilityMetrics {
  total_gross_realized_pnl: string | number;
  total_net_realized_pnl: string | number;
  total_trading_fees: string | number;
  total_slippage: string | number;
  total_spread_costs: string | number;
  total_execution_costs: string | number;
  average_net_pnl_per_completed: MetricValue;
  profit_factor: MetricValue;
  gross_profit: string | number;
  gross_loss: string | number;
}

export interface RiskRewardMetrics {
  average_r_multiple: MetricValue;
  median_r_multiple: MetricValue;
  best_r_multiple: MetricValue;
  worst_r_multiple: MetricValue;
  avg_win_loss_ratio: MetricValue;
  r_multiple_sample_count: number;
  missing_risk_metadata_count: number;
}

export interface ReturnMetrics {
  initial_equity: string | number | null;
  current_equity: MetricValue;
  ending_equity: MetricValue;
  total_return_pct: MetricValue;
  average_trade_return_pct: MetricValue;
  best_trade_return_pct: MetricValue;
  worst_trade_return_pct: MetricValue;
}

export interface EquityPoint {
  timestamp: string;
  trade_id: string;
  event_id?: string | null;
  net_pnl_change: string | number;
  cumulative_net_pnl: string | number;
  equity?: string | number | null;
  completed_trade_count: number;
  curve: string;
}

export interface EquityCurve {
  mode: string;
  points: EquityPoint[];
  available: boolean;
  unavailable_reason?: string | null;
  initial_equity?: string | number | null;
  ending_equity?: string | number | null;
  cumulative_net_pnl: string | number;
}

export interface DrawdownPoint {
  timestamp: string;
  equity?: string | number | null;
  peak_equity?: string | number | null;
  drawdown: string | number;
  drawdown_pct?: string | number | null;
}

export interface DrawdownSummary {
  available: boolean;
  unavailable_reason?: string | null;
  absolute_drawdown: string | number;
  drawdown_pct: MetricValue;
  max_drawdown: string | number;
  max_drawdown_pct: MetricValue;
  peak_timestamp?: string | null;
  trough_timestamp?: string | null;
  recovery_timestamp?: string | null;
  current_drawdown: string | number;
  current_drawdown_pct: MetricValue;
  series: DrawdownPoint[];
}

export interface GroupPerformanceRow {
  key: string;
  completed_trades: number;
  win_rate: MetricValue;
  net_pnl: string | number;
  profit_factor: MetricValue;
  average_net_trade: MetricValue;
  average_r_multiple: MetricValue;
}

export interface PerformanceGroups {
  by_symbol: GroupPerformanceRow[];
  by_timeframe: GroupPerformanceRow[];
  by_direction: GroupPerformanceRow[];
  by_period: GroupPerformanceRow[];
  by_exit_type: GroupPerformanceRow[];
  timeframe_unavailable_reason?: string | null;
  warnings: string[];
}

export interface AnalyticsTradeRow {
  trade_id: string;
  symbol: string;
  direction: string;
  lifecycle_status: string;
  analytics_class: string;
  exit_type: string;
  net_realized_pnl?: string | number | null;
  gross_realized_pnl?: string | number | null;
  r_multiple?: string | number | null;
  entry_timestamp?: string | null;
  exit_timestamp?: string | null;
  included_in_completed_stats: boolean;
}

export interface PerformanceSummary {
  session_id: string;
  enabled: boolean;
  analytics_version: string;
  cost_model_version?: string | null;
  replay_timestamp?: string | null;
  event_index?: number | null;
  quote_currency: string;
  initial_equity?: string | number | null;
  initial_equity_source: string;
  trade_stats: TradeStatistics;
  profitability: ProfitabilityMetrics;
  risk_reward: RiskRewardMetrics;
  returns: ReturnMetrics;
  drawdown: DrawdownSummary;
  included_completed_trades: number;
  excluded_open_trades: number;
  excluded_partial_trades: number;
  assumptions: string[];
  warnings: string[];
  disclaimer: string;
  filter_context: Record<string, unknown>;
  config: Record<string, unknown>;
}

export interface AnalyticsSnapshot {
  session_id: string;
  enabled: boolean;
  analytics_version: string;
  summary: PerformanceSummary;
  equity_completed: EquityCurve;
  equity_cashflow: EquityCurve;
  drawdown: DrawdownSummary;
  groups: PerformanceGroups;
  completed_trades: AnalyticsTradeRow[];
  disclaimer: string;
}

export interface AnalyticsConfigPublic {
  config_version?: string;
  enabled?: boolean;
  initial_equity?: string | number | null;
  quote_currency?: string;
  include_closed_only_for_stats?: boolean;
  include_partial_realized_in_cashflow?: boolean;
  equity_curve_mode?: string;
  drawdown_mode?: string;
  time_group_period?: string;
  display_timezone?: string;
  disclaimer?: string;
}

export interface ReplayAnalyticsToggleResponse {
  session_id: string;
  analytics_enabled: boolean;
  costs_enabled: boolean;
  simulation_enabled: boolean;
  analysis_enabled: boolean;
  snapshot?: AnalyticsSnapshot | null;
  message?: string | null;
}

export interface ReplayAnalyticsCurrentResponse {
  session_id: string;
  analytics_enabled: boolean;
  snapshot: AnalyticsSnapshot;
}

/* ─── Phase 5.2.6 Backtesting Reporting ─── */

export interface ReportKeyMetric {
  key: string;
  label: string;
  value?: string | number | null;
  availability: MetricAvailability;
  unit?: string;
}

export interface ReportMetadata {
  report_id: string;
  report_version: string;
  session_id: string;
  generated_at: string;
  replay_timestamp?: string | null;
  event_index?: number | null;
  event_count?: number | null;
  exchange: ExchangeId;
  symbol: string;
  market_type: MarketType;
  timeframes: Timeframe[];
  replay_start?: string | null;
  replay_end?: string | null;
  status?: string | null;
  data_quality?: string | null;
  initial_equity?: string | number | null;
  initial_equity_source?: string | null;
  quote_currency: string;
  disclaimer: string;
  filter_context: Record<string, unknown>;
  cost_model_version?: string | null;
  analytics_version?: string | null;
}

export interface ReportSummary {
  completed_trade_count: number;
  total_simulated_trades: number;
  winning_trades: number;
  losing_trades: number;
  break_even_trades: number;
  partially_closed_trades: number;
  open_trades: number;
  excluded_open_trades: number;
  excluded_partial_trades: number;
  win_rate: MetricValue;
  profit_factor: MetricValue;
  average_net_pnl_per_completed: MetricValue;
  average_r_multiple: MetricValue;
  gross_pnl: string | number;
  net_pnl: string | number;
  total_fees: string | number;
  total_slippage: string | number;
  total_spread_cost: string | number;
  total_execution_costs: string | number;
  initial_equity?: string | number | null;
  ending_equity: MetricValue;
  current_equity: MetricValue;
  total_return_pct: MetricValue;
  max_drawdown: string | number;
  max_drawdown_pct: MetricValue;
  current_drawdown: string | number;
  recovery_timestamp?: string | null;
  peak_timestamp?: string | null;
  trough_timestamp?: string | null;
  key_metrics: ReportKeyMetric[];
}

export interface ReportTradeDetail {
  trade_id: string;
  symbol: string;
  direction: string;
  lifecycle_status: string;
  analytics_class: string;
  exit_type: string;
  included_in_completed_stats: boolean;
  entry_timestamp?: string | null;
  exit_timestamp?: string | null;
  entry_price?: string | number | null;
  average_exit_price?: string | number | null;
  average_exit_price_source?: string;
  original_quantity?: string | number | null;
  executed_quantity?: string | number | null;
  remaining_quantity?: string | number | null;
  initial_stop_loss?: string | number | null;
  current_stop_loss?: string | number | null;
  take_profit_levels: Array<string | number>;
  gross_realized_pnl?: string | number | null;
  net_realized_pnl?: string | number | null;
  fees?: string | number | null;
  slippage?: string | number | null;
  spread_cost?: string | number | null;
  r_multiple?: string | number | null;
}

export interface ReportOpenTrade {
  trade_id: string;
  symbol: string;
  direction: string;
  lifecycle_status: string;
  analytics_class: string;
  entry_timestamp?: string | null;
  entry_price?: string | number | null;
  original_quantity?: string | number | null;
  remaining_quantity?: string | number | null;
  executed_quantity?: string | number | null;
  initial_stop_loss?: string | number | null;
  current_stop_loss?: string | number | null;
  take_profit_levels: Array<string | number>;
  unrealized_note: string;
}

export interface ReportEquitySection {
  completed: EquityCurve;
  cashflow: EquityCurve;
}

export interface ReportDrawdownSection {
  summary: DrawdownSummary;
  points: DrawdownPoint[];
}

export interface BacktestReportSnapshot {
  metadata: ReportMetadata;
  summary: ReportSummary;
  performance_summary: PerformanceSummary;
  equity: ReportEquitySection;
  drawdown: ReportDrawdownSection;
  groups: PerformanceGroups;
  completed_trades: ReportTradeDetail[];
  completed_trade_total: number;
  completed_trades_truncated: boolean;
  open_trades: ReportOpenTrade[];
  open_trade_total: number;
  open_trades_truncated: boolean;
  limitations: string[];
  assumptions: string[];
  disclaimer: string;
}

export interface ReplayReportResponse {
  session_id: string;
  analytics_enabled: boolean;
  report: BacktestReportSnapshot;
}

export type ReportCsvKind = "summary" | "trades" | "equity" | "drawdown";

/* ─── Phase 5.4 AI Vision / Explainer ─── */

export type AiStatus =
  | "OK"
  | "AI_UNAVAILABLE"
  | "TIMEOUT"
  | "RATE_LIMITED"
  | "INVALID_MODEL_RESPONSE"
  | "INSUFFICIENT_DATA"
  | "VALIDATION_ERROR"
  | "ERROR"
  | string;

export type VisionObservationCategory =
  | "TREND"
  | "SUPPORT"
  | "RESISTANCE"
  | "CANDLE_PATTERN"
  | "INDICATOR"
  | "PRICE_ZONE"
  | "ANNOTATION"
  | "OTHER";

export interface VisionObservation {
  observation_id: string;
  category: VisionObservationCategory;
  description: string;
  confidence: number;
  visible: boolean;
  evidence_description: string;
  uncertainty_reason?: string | null;
}

export interface VisionImageMetadata {
  content_type: string;
  width: number;
  height: number;
  size_bytes: number;
  format: string;
}

export interface VisionResult {
  status: AiStatus;
  image_metadata?: VisionImageMetadata | null;
  detected_timeframe?: string | null;
  detected_symbol?: string | null;
  detected_chart_type?: string | null;
  observations: VisionObservation[];
  visible_price_labels: string[];
  visible_indicators: string[];
  unreadable_fields: string[];
  limitations: string[];
  message?: string | null;
}

export interface VisionComparisonSummary {
  status:
    | "CONSISTENT"
    | "PARTIALLY_CONSISTENT"
    | "CONFLICTING"
    | "INSUFFICIENT_VISUAL_DATA"
    | "SKIPPED"
    | string;
  notes: string[];
  disagreements: string[];
}

export interface AnalysisExplanation {
  status: AiStatus;
  summary: string;
  decision_explanation: string;
  market_context: string;
  bullish_evidence: string[];
  bearish_evidence: string[];
  supporting_factors: string[];
  conflicting_factors: string[];
  entry_explanation: string;
  stop_loss_explanation: string;
  take_profit_explanations: string[];
  risk_notes: string[];
  missing_confirmations: string[];
  data_limitations: string[];
  vision_comparison?: VisionComparisonSummary | null;
  disclaimer: string;
  message?: string | null;
  validation_warnings: string[];
}

export interface AnalysisSnapshot {
  exchange: string;
  symbol: string;
  market_type: string;
  analysis_timestamp: string;
  data_freshness: string;
  decision: string;
  decision_reason: string;
  lifecycle?: string | null;
  direction?: string | null;
  confluence_bullish?: number | null;
  confluence_bearish?: number | null;
  preliminary_assessment?: string | null;
  conflicts: string[];
  supporting_evidence: string[];
  blocking_conditions: string[];
  trade_plan_status?: string | null;
  plan_id?: string | null;
  decision_id?: string | null;
  entry_reference_price?: number | null;
  entry_low?: number | null;
  entry_high?: number | null;
  stop_loss_price?: number | null;
  take_profit_prices: number[];
  primary_rr?: number | null;
  price_inside_entry_zone?: boolean | null;
  spot_restriction?: string | null;
  analysis_only_disclaimer: string;
}

export interface AiAnalyzeResponse {
  status: AiStatus;
  request_id: string;
  exchange: ExchangeId;
  market_type: MarketType;
  symbol: string;
  timeframe?: string | null;
  decision: DecisionResponse;
  trade_plan: TradePlanResponse;
  snapshot: AnalysisSnapshot;
  explanation?: AnalysisExplanation | null;
  message?: string | null;
}

export interface AiVisionAnalyzeResponse {
  status: AiStatus;
  request_id: string;
  vision: VisionResult;
}

export interface AiCompareResponse {
  status: string;
  request_id: string;
  comparison: VisionComparisonSummary;
  snapshot_decision: string;
  notes: string[];
}

