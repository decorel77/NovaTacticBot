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
class AnalyticsResult:
    strategy_stats: dict[str, StrategyStats] = field(default_factory=dict)
    regime_stats: dict[str, RegimeStats] = field(default_factory=dict)
    rejection_stats: RejectionStats = field(default_factory=RejectionStats)
    recommendation_quality: RecommendationQuality = field(default_factory=RecommendationQuality)
    data_quality: DataQuality = field(default_factory=DataQuality)
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

        if result.rejection_stats.rejection_rate is not None:
            rr = result.rejection_stats.rejection_rate
            if rr > 0.5:
                obs.append(
                    f"Rejection rate is {rr:.0%} — more than half of actionable signals are filtered."
                )
