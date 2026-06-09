"""
Tactical Analytics Engine — pure analysis over TacticalEvent lists.

Responsibilities:
  - strategy comparison
  - win rate by strategy and regime
  - recommendation quality scoring
  - rejection analysis
  - outcome distribution

No recommendations. No optimization. No writes. No broker calls.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from core.tactic_event import EventType, Outcome, TacticalEvent


# ── Result containers ──────────────────────────────────────────────────────────

@dataclass
class StrategyStats:
    strategy_id: str
    total_events: int = 0
    trade_outcomes: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    total_pnl: float = 0.0
    avg_score: Optional[float] = None
    avg_expected_rr: Optional[float] = None
    win_rate: Optional[float] = None
    avg_realized_pnl: Optional[float] = None
    regimes: dict[str, int] = field(default_factory=dict)

    def finalize(self) -> None:
        if self.trade_outcomes > 0:
            self.win_rate = self.wins / self.trade_outcomes
            self.avg_realized_pnl = self.total_pnl / self.trade_outcomes


@dataclass
class RegimeStats:
    regime: str
    total_events: int = 0
    trade_outcomes: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    win_rate: Optional[float] = None
    avg_pnl: Optional[float] = None
    strategies: dict[str, int] = field(default_factory=dict)

    def finalize(self) -> None:
        if self.trade_outcomes > 0:
            self.win_rate = self.wins / self.trade_outcomes
            self.avg_pnl = self.total_pnl / self.trade_outcomes


@dataclass
class RejectionStats:
    total_rejections: int = 0
    by_strategy: dict[str, int] = field(default_factory=dict)
    by_regime: dict[str, int] = field(default_factory=dict)
    rejection_rate: Optional[float] = None  # rejections / (rejections + outcomes)


@dataclass
class RecommendationQuality:
    total_recommendations: int = 0
    scored_recommendations: int = 0
    avg_score: Optional[float] = None
    score_vs_outcome: list[dict[str, Any]] = field(default_factory=list)
    high_score_win_rate: Optional[float] = None   # score >= 0.7
    low_score_win_rate: Optional[float] = None    # score < 0.5


@dataclass
class DataQuality:
    total_events: int = 0
    missing_regime: int = 0
    missing_score: int = 0
    missing_pnl: int = 0
    missing_outcome: int = 0
    malformed_events: int = 0
    source_bot_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class SymbolConcentration:
    """How often each symbol appears across all events."""
    by_symbol: dict[str, int] = field(default_factory=dict)       # total events
    outcomes_by_symbol: dict[str, int] = field(default_factory=dict)  # TRADE_OUTCOME count
    rejections_by_symbol: dict[str, int] = field(default_factory=dict)
    pnl_by_symbol: dict[str, float] = field(default_factory=dict)
    top_symbols: list[str] = field(default_factory=list)          # sorted by total events


@dataclass
class ConfidenceBucket:
    label: str
    min_score: float
    max_score: float
    count: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: Optional[float] = None

    def finalize(self) -> None:
        total = self.wins + self.losses
        if total > 0:
            self.win_rate = self.wins / total


@dataclass
class ConfidenceDistribution:
    """Score distribution bucketed into ranges."""
    buckets: list[ConfidenceBucket] = field(default_factory=list)
    total_scored: int = 0
    avg_score: Optional[float] = None


@dataclass
class RollingWinRateWindow:
    """Win rate over the last N trade-outcome events (all strategies combined)."""
    window: int          # e.g. 10, 30, 100
    trades: int          # actual trades included (may be < window if fewer events)
    wins: int
    win_rate: Optional[float] = None

    def finalize(self) -> None:
        if self.trades > 0:
            self.win_rate = self.wins / self.trades


@dataclass
class RollingWinRates:
    """Rolling win rates over last-10, last-30, last-100 trade outcomes."""
    last_10: RollingWinRateWindow = field(
        default_factory=lambda: RollingWinRateWindow(window=10, trades=0, wins=0)
    )
    last_30: RollingWinRateWindow = field(
        default_factory=lambda: RollingWinRateWindow(window=30, trades=0, wins=0)
    )
    last_100: RollingWinRateWindow = field(
        default_factory=lambda: RollingWinRateWindow(window=100, trades=0, wins=0)
    )
    # Per-strategy rolling windows (last-10 only — most actionable)
    by_strategy_last_10: dict[str, RollingWinRateWindow] = field(default_factory=dict)


@dataclass
class CandidateRanking:
    """Ranked list of symbols by composite desirability score."""

    @dataclass
    class RankedCandidate:
        symbol: str
        strategy_id: str
        composite_score: float
        total_events: int
        win_rate: Optional[float]
        avg_pnl: Optional[float]
        avg_score: Optional[float]

    candidates: list["CandidateRanking.RankedCandidate"] = field(default_factory=list)


@dataclass
class StrategyStreakStats:
    strategy_id: str
    current_streak: int = 0           # positive = win streak, negative = loss streak
    max_win_streak: int = 0
    max_loss_streak: int = 0
    current_loss_streak: int = 0      # convenience: absolute value of current streak if losing
    flagged: bool = False             # True when current loss streak >= LOSS_STREAK_FLAG_THRESHOLD


LOSS_STREAK_FLAG_THRESHOLD = 3
EDGE_EROSION_THRESHOLD_PP = 0.10   # 10 percentage points below baseline triggers warning
REGIME_BIAS_MULTIPLIER = 2.0       # trade frequency > 2x expected base rate triggers flag


@dataclass
class RegimeBiasWarning:
    regime: str
    observed_rate: float    # fraction of trade outcomes in this regime
    expected_rate: float    # fraction of all events in this regime (base rate)
    multiplier: float       # observed / expected


@dataclass
class RegimeBiasAnalysis:
    """Detects systematic over-trading in specific market regimes."""
    warnings: list[RegimeBiasWarning] = field(default_factory=list)
    regime_trade_rates: dict[str, float] = field(default_factory=dict)
    regime_base_rates: dict[str, float] = field(default_factory=dict)


@dataclass
class EdgeErosionWarning:
    strategy_id: str
    baseline_win_rate: float        # overall historical win rate for this strategy
    rolling_win_rate: float         # current rolling-last-10 win rate
    drop_pp: float                  # baseline - rolling (in percentage points, positive = drop)


@dataclass
class EdgeErosionAnalysis:
    """Flags strategies whose recent win rate has eroded significantly vs their baseline."""
    warnings: list[EdgeErosionWarning] = field(default_factory=list)
    healthy_strategies: list[str] = field(default_factory=list)


@dataclass
class StreakAnalysis:
    """Consecutive win/loss streak data per strategy."""
    by_strategy: dict[str, StrategyStreakStats] = field(default_factory=dict)
    flagged_strategies: list[str] = field(default_factory=list)


@dataclass
class AnalyticsResult:
    strategy_stats: dict[str, StrategyStats] = field(default_factory=dict)
    regime_stats: dict[str, RegimeStats] = field(default_factory=dict)
    rejection_stats: RejectionStats = field(default_factory=RejectionStats)
    recommendation_quality: RecommendationQuality = field(default_factory=RecommendationQuality)
    data_quality: DataQuality = field(default_factory=DataQuality)
    symbol_concentration: SymbolConcentration = field(default_factory=SymbolConcentration)
    confidence_distribution: ConfidenceDistribution = field(default_factory=ConfidenceDistribution)
    candidate_ranking: CandidateRanking = field(default_factory=CandidateRanking)
    rolling_win_rates: RollingWinRates = field(default_factory=RollingWinRates)
    streak_analysis: StreakAnalysis = field(default_factory=StreakAnalysis)
    edge_erosion: EdgeErosionAnalysis = field(default_factory=EdgeErosionAnalysis)
    regime_bias: RegimeBiasAnalysis = field(default_factory=RegimeBiasAnalysis)
    open_questions: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)


# ── Engine ─────────────────────────────────────────────────────────────────────

class TacticAnalyticsEngine:
    """
    Runs all analytics passes over a list of TacticalEvents.
    Returns an AnalyticsResult. Does not modify events or write files.
    """

    def run(self, events: list[TacticalEvent]) -> AnalyticsResult:
        result = AnalyticsResult()

        if not events:
            result.open_questions.append("No events loaded — is the adapter path configured correctly?")
            return result

        self._data_quality(events, result)
        self._strategy_analysis(events, result)
        self._regime_analysis(events, result)
        self._rejection_analysis(events, result)
        self._recommendation_quality(events, result)
        self._symbol_concentration(events, result)
        self._confidence_distribution(events, result)
        self._candidate_ranking(events, result)
        self._rolling_win_rates(events, result)
        self._streak_analysis(events, result)
        self._edge_erosion_analysis(result)
        self._regime_bias_analysis(events, result)
        self._generate_observations(result)

        return result

    # ── Passes ─────────────────────────────────────────────────────────────────

    def _data_quality(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        dq = result.data_quality
        dq.total_events = len(events)
        for e in events:
            dq.source_bot_counts[e.source_bot] = dq.source_bot_counts.get(e.source_bot, 0) + 1
            if e.regime is None:
                dq.missing_regime += 1
            if e.score is None:
                dq.missing_score += 1
            if e.realized_pnl is None:
                dq.missing_pnl += 1
            if e.outcome is None:
                dq.missing_outcome += 1

    def _strategy_analysis(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        buckets: dict[str, StrategyStats] = {}
        score_sums: dict[str, float] = defaultdict(float)
        score_counts: dict[str, int] = defaultdict(int)
        rr_sums: dict[str, float] = defaultdict(float)
        rr_counts: dict[str, int] = defaultdict(int)

        for e in events:
            sid = e.strategy_id
            if sid not in buckets:
                buckets[sid] = StrategyStats(strategy_id=sid)
            s = buckets[sid]
            s.total_events += 1

            if e.regime:
                s.regimes[e.regime] = s.regimes.get(e.regime, 0) + 1

            if e.score is not None:
                score_sums[sid] += e.score
                score_counts[sid] += 1

            if e.expected_rr is not None:
                rr_sums[sid] += e.expected_rr
                rr_counts[sid] += 1

            if e.event_type == EventType.TRADE_OUTCOME:
                s.trade_outcomes += 1
                if e.realized_pnl is not None:
                    s.total_pnl += e.realized_pnl
                if e.outcome == Outcome.WIN:
                    s.wins += 1
                elif e.outcome == Outcome.LOSS:
                    s.losses += 1
                elif e.outcome == Outcome.BREAKEVEN:
                    s.breakevens += 1

        for sid, s in buckets.items():
            if score_counts[sid]:
                s.avg_score = score_sums[sid] / score_counts[sid]
            if rr_counts[sid]:
                s.avg_expected_rr = rr_sums[sid] / rr_counts[sid]
            s.finalize()

        result.strategy_stats = buckets

    def _regime_analysis(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        buckets: dict[str, RegimeStats] = {}

        for e in events:
            regime = e.regime or "UNKNOWN"
            if regime not in buckets:
                buckets[regime] = RegimeStats(regime=regime)
            r = buckets[regime]
            r.total_events += 1
            r.strategies[e.strategy_id] = r.strategies.get(e.strategy_id, 0) + 1

            if e.event_type == EventType.TRADE_OUTCOME:
                r.trade_outcomes += 1
                if e.realized_pnl is not None:
                    r.total_pnl += e.realized_pnl
                if e.outcome == Outcome.WIN:
                    r.wins += 1
                elif e.outcome == Outcome.LOSS:
                    r.losses += 1

        for r in buckets.values():
            r.finalize()

        result.regime_stats = buckets

    def _rejection_analysis(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        rs = result.rejection_stats
        total_actionable = 0

        for e in events:
            if e.event_type == EventType.REJECTION:
                rs.total_rejections += 1
                rs.by_strategy[e.strategy_id] = rs.by_strategy.get(e.strategy_id, 0) + 1
                regime = e.regime or "UNKNOWN"
                rs.by_regime[regime] = rs.by_regime.get(regime, 0) + 1
            if e.event_type in (EventType.TRADE_OUTCOME, EventType.REJECTION):
                total_actionable += 1

        if total_actionable > 0:
            rs.rejection_rate = rs.total_rejections / total_actionable

    def _recommendation_quality(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        rq = result.recommendation_quality
        score_sum = 0.0
        high_score_wins = high_score_total = 0
        low_score_wins = low_score_total = 0

        for e in events:
            if e.event_type == EventType.RECOMMENDATION:
                rq.total_recommendations += 1

            if e.score is not None and e.event_type == EventType.TRADE_OUTCOME:
                rq.scored_recommendations += 1
                score_sum += e.score
                rq.score_vs_outcome.append({
                    "strategy_id": e.strategy_id,
                    "score": e.score,
                    "outcome": e.outcome,
                    "realized_pnl": e.realized_pnl,
                })
                if e.score >= 0.7:
                    high_score_total += 1
                    if e.outcome == Outcome.WIN:
                        high_score_wins += 1
                elif e.score < 0.5:
                    low_score_total += 1
                    if e.outcome == Outcome.WIN:
                        low_score_wins += 1

        if rq.scored_recommendations > 0:
            rq.avg_score = score_sum / rq.scored_recommendations
        if high_score_total > 0:
            rq.high_score_win_rate = high_score_wins / high_score_total
        if low_score_total > 0:
            rq.low_score_win_rate = low_score_wins / low_score_total

    def _symbol_concentration(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        sc = result.symbol_concentration
        for e in events:
            symbol = e.metadata.get("symbol") if e.metadata else None
            if not symbol:
                continue
            sc.by_symbol[symbol] = sc.by_symbol.get(symbol, 0) + 1
            if e.event_type == EventType.TRADE_OUTCOME:
                sc.outcomes_by_symbol[symbol] = sc.outcomes_by_symbol.get(symbol, 0) + 1
                if e.realized_pnl is not None:
                    sc.pnl_by_symbol[symbol] = sc.pnl_by_symbol.get(symbol, 0.0) + e.realized_pnl
            if e.event_type == EventType.REJECTION:
                sc.rejections_by_symbol[symbol] = sc.rejections_by_symbol.get(symbol, 0) + 1
        sc.top_symbols = sorted(sc.by_symbol, key=lambda s: -sc.by_symbol[s])

    def _confidence_distribution(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        cd = result.confidence_distribution
        ranges = [
            ("< 0.5", 0.0, 0.5),
            ("0.5–0.6", 0.5, 0.6),
            ("0.6–0.7", 0.6, 0.7),
            ("0.7–0.8", 0.7, 0.8),
            ("0.8–1.0", 0.8, 1.01),
        ]
        cd.buckets = [
            ConfidenceBucket(label=label, min_score=lo, max_score=hi)
            for label, lo, hi in ranges
        ]
        score_sum = 0.0
        count = 0
        for e in events:
            if e.score is None:
                continue
            cd.total_scored += 1
            score_sum += e.score
            count += 1
            for b in cd.buckets:
                if b.min_score <= e.score < b.max_score:
                    b.count += 1
                    if e.event_type == EventType.TRADE_OUTCOME:
                        if e.outcome == Outcome.WIN:
                            b.wins += 1
                        elif e.outcome == Outcome.LOSS:
                            b.losses += 1
                    break
        for b in cd.buckets:
            b.finalize()
        if count:
            cd.avg_score = score_sum / count

    def _candidate_ranking(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        # Build per (symbol, strategy) stats for ranking
        from collections import defaultdict
        key_events: dict[tuple, list] = defaultdict(list)
        for e in events:
            symbol = e.metadata.get("symbol") if e.metadata else None
            if symbol and e.strategy_id:
                key_events[(symbol, e.strategy_id)].append(e)

        candidates = []
        for (symbol, strat), evts in key_events.items():
            outcomes = [e for e in evts if e.event_type == EventType.TRADE_OUTCOME]
            wins = sum(1 for e in outcomes if e.outcome == Outcome.WIN)
            win_rate = wins / len(outcomes) if outcomes else None
            pnl_vals = [e.realized_pnl for e in outcomes if e.realized_pnl is not None]
            avg_pnl = sum(pnl_vals) / len(pnl_vals) if pnl_vals else None
            scores = [e.score for e in evts if e.score is not None]
            avg_score = sum(scores) / len(scores) if scores else None

            # Composite: avg_score * win_rate (penalize unknowns)
            wr_factor = win_rate if win_rate is not None else 0.5
            sc_factor = avg_score if avg_score is not None else 0.5
            composite = sc_factor * wr_factor

            candidates.append(
                CandidateRanking.RankedCandidate(
                    symbol=symbol,
                    strategy_id=strat,
                    composite_score=composite,
                    total_events=len(evts),
                    win_rate=win_rate,
                    avg_pnl=avg_pnl,
                    avg_score=avg_score,
                )
            )

        candidates.sort(key=lambda c: -c.composite_score)
        result.candidate_ranking.candidates = candidates

    def _rolling_win_rates(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        """Compute rolling win rates over last-10, last-30, last-100 trade outcomes."""
        # Only TRADE_OUTCOME events with a known outcome contribute
        outcomes = [
            e for e in events
            if e.event_type == EventType.TRADE_OUTCOME
            and e.outcome in (Outcome.WIN, Outcome.LOSS, Outcome.BREAKEVEN)
        ]
        # Sort by timestamp ascending so the last N are the most recent
        outcomes.sort(key=lambda e: e.timestamp)

        def _compute_window(n: int) -> RollingWinRateWindow:
            window_events = outcomes[-n:] if len(outcomes) >= n else outcomes
            wins = sum(1 for e in window_events if e.outcome == Outcome.WIN)
            w = RollingWinRateWindow(window=n, trades=len(window_events), wins=wins)
            w.finalize()
            return w

        result.rolling_win_rates.last_10 = _compute_window(10)
        result.rolling_win_rates.last_30 = _compute_window(30)
        result.rolling_win_rates.last_100 = _compute_window(100)

        # Per-strategy last-10
        strategies: dict[str, list[TacticalEvent]] = defaultdict(list)
        for e in outcomes:
            strategies[e.strategy_id].append(e)

        for sid, strat_events in strategies.items():
            last_10 = strat_events[-10:]
            wins = sum(1 for e in last_10 if e.outcome == Outcome.WIN)
            w = RollingWinRateWindow(window=10, trades=len(last_10), wins=wins)
            w.finalize()
            result.rolling_win_rates.by_strategy_last_10[sid] = w

    def _regime_bias_analysis(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        """Detect over-trading in specific regimes relative to base rate.

        Base rate = fraction of all events in a regime.
        Trade rate = fraction of TRADE_OUTCOME events in that regime.
        Flag when trade_rate / base_rate > REGIME_BIAS_MULTIPLIER.
        """
        rb = result.regime_bias
        total_events = len(events)
        if total_events == 0:
            return

        trade_outcomes = [e for e in events if e.event_type == EventType.TRADE_OUTCOME]
        total_trades = len(trade_outcomes)
        if total_trades == 0:
            return

        # Count all events per regime (base rate denominator)
        regime_event_counts: dict[str, int] = {}
        for e in events:
            regime = e.regime or "UNKNOWN"
            regime_event_counts[regime] = regime_event_counts.get(regime, 0) + 1

        # Count trade outcomes per regime
        regime_trade_counts: dict[str, int] = {}
        for e in trade_outcomes:
            regime = e.regime or "UNKNOWN"
            regime_trade_counts[regime] = regime_trade_counts.get(regime, 0) + 1

        for regime, event_count in regime_event_counts.items():
            base_rate = event_count / total_events
            trade_count = regime_trade_counts.get(regime, 0)
            trade_rate = trade_count / total_trades

            rb.regime_base_rates[regime] = base_rate
            rb.regime_trade_rates[regime] = trade_rate

            if base_rate > 0:
                multiplier = trade_rate / base_rate
                if multiplier > REGIME_BIAS_MULTIPLIER:
                    rb.warnings.append(RegimeBiasWarning(
                        regime=regime,
                        observed_rate=trade_rate,
                        expected_rate=base_rate,
                        multiplier=multiplier,
                    ))

    def _edge_erosion_analysis(self, result: AnalyticsResult) -> None:
        """Compare per-strategy rolling last-10 win rate against overall baseline.

        Flags EDGE_EROSION_WARNING when rolling rate is >= EDGE_EROSION_THRESHOLD_PP
        below the strategy's overall historical win rate.
        """
        ea = result.edge_erosion
        rolling_by_strat = result.rolling_win_rates.by_strategy_last_10

        for sid, s_stats in result.strategy_stats.items():
            baseline = s_stats.win_rate
            if baseline is None or sid not in rolling_by_strat:
                continue

            rolling_window = rolling_by_strat[sid]
            if rolling_window.win_rate is None or rolling_window.trades < 3:
                # Too few trades in rolling window — skip
                continue

            rolling = rolling_window.win_rate
            drop = baseline - rolling

            if drop >= EDGE_EROSION_THRESHOLD_PP:
                ea.warnings.append(EdgeErosionWarning(
                    strategy_id=sid,
                    baseline_win_rate=baseline,
                    rolling_win_rate=rolling,
                    drop_pp=drop,
                ))
            else:
                ea.healthy_strategies.append(sid)

    def _streak_analysis(self, events: list[TacticalEvent], result: AnalyticsResult) -> None:
        """Detect consecutive win/loss streaks per strategy. Flag loss streaks >= threshold."""
        from collections import defaultdict

        outcomes_by_strategy: dict[str, list[TacticalEvent]] = defaultdict(list)
        for e in events:
            if (
                e.event_type == EventType.TRADE_OUTCOME
                and e.outcome in (Outcome.WIN, Outcome.LOSS)
            ):
                outcomes_by_strategy[e.strategy_id].append(e)

        for sid, evts in outcomes_by_strategy.items():
            evts.sort(key=lambda e: e.timestamp)
            stats = StrategyStreakStats(strategy_id=sid)

            current = 0
            max_win = 0
            max_loss = 0

            for e in evts:
                if e.outcome == Outcome.WIN:
                    current = current + 1 if current > 0 else 1
                else:
                    current = current - 1 if current < 0 else -1

                if current > 0:
                    max_win = max(max_win, current)
                else:
                    max_loss = max(max_loss, abs(current))

            stats.current_streak = current
            stats.max_win_streak = max_win
            stats.max_loss_streak = max_loss
            stats.current_loss_streak = abs(current) if current < 0 else 0
            stats.flagged = stats.current_loss_streak >= LOSS_STREAK_FLAG_THRESHOLD

            result.streak_analysis.by_strategy[sid] = stats
            if stats.flagged:
                result.streak_analysis.flagged_strategies.append(sid)

    def _generate_observations(self, result: AnalyticsResult) -> None:
        obs = result.observations
        oq = result.open_questions
        dq = result.data_quality

        if dq.total_events == 0:
            return

        missing_pct = dq.missing_outcome / dq.total_events
        if missing_pct > 0.3:
            oq.append(
                f"{missing_pct:.0%} of events have no outcome — "
                "consider whether pending trades should be excluded from win-rate calculations."
            )

        for sid, s in result.strategy_stats.items():
            if s.win_rate is not None and s.win_rate < 0.35 and s.trade_outcomes >= 5:
                obs.append(
                    f"Strategy '{sid}' shows a win rate of {s.win_rate:.0%} "
                    f"over {s.trade_outcomes} trades."
                )
            if s.win_rate is not None and s.win_rate > 0.70 and s.trade_outcomes >= 5:
                obs.append(
                    f"Strategy '{sid}' shows a strong win rate of {s.win_rate:.0%} "
                    f"over {s.trade_outcomes} trades."
                )

        rq = result.recommendation_quality
        if (
            rq.high_score_win_rate is not None
            and rq.low_score_win_rate is not None
            and rq.high_score_win_rate < rq.low_score_win_rate
        ):
            oq.append(
                "High-score recommendations have a lower win rate than low-score recommendations. "
                "Score calibration may need review."
            )

        for w in result.regime_bias.warnings:
            obs.append(
                f"REGIME_BIAS: Regime '{w.regime}' has {w.multiplier:.1f}x expected trade frequency "
                f"(observed {w.observed_rate:.0%}, expected {w.expected_rate:.0%})."
            )

        for w in result.edge_erosion.warnings:
            obs.append(
                f"EDGE_EROSION_WARNING: Strategy '{w.strategy_id}' rolling win rate "
                f"{w.rolling_win_rate:.0%} is {w.drop_pp:.0%} below baseline {w.baseline_win_rate:.0%}."
            )

        for sid in result.streak_analysis.flagged_strategies:
            streak = result.streak_analysis.by_strategy[sid].current_loss_streak
            obs.append(
                f"Strategy '{sid}' has a current loss streak of {streak} "
                f"(threshold: {LOSS_STREAK_FLAG_THRESHOLD})."
            )

        if result.rejection_stats.rejection_rate is not None:
            rr = result.rejection_stats.rejection_rate
            if rr > 0.5:
                obs.append(
                    f"Rejection rate is {rr:.0%} — more than half of actionable signals are filtered."
                )
