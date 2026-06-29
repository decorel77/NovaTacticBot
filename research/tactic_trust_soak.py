"""TacticBot edge / soak tracking study (TACTIC-TRUST-001).

RESEARCH / REPORTING ONLY — DIAGNOSTIC-ONLY, NOT WIRED.

Continues the TacticBot trust tracking by joining the two existing advisory
pieces — the offline backtest harness (`research/stock_tactics_backtest.py`,
NEXT-015) and the evidence gate (`core/statistical_floor.py`, QA-016) — into one
soak report: run a deterministic synthetic backtest, turn its summary into a
`TacticalSignalEvidence`, and ask the statistical floor whether the tactic has
accumulated enough trustworthy evidence to be labelled STRONG.

The whole point is to make the **fail-closed trust gate visible**: a tactic stays
`DIAGNOSTIC_ONLY` until it clears the floor (>=30 real samples, win-rate >=0.55,
edge >=0.02, real data, verified regime, fresh). Synthetic data can therefore
**never** be approved (`data_not_real`), which is the honest result — this study
shows the soak *progress* and *what is still missing*, it does not (and must not)
grant trust.

Boundaries (binding): imports only the stdlib + in-repo research/core modules; no
broker/live/order import, no network, no real data, no writes. It is **not wired**
into the runner, snapshot writer, or any execution path — exactly like the modules
it composes. Mirrors REGIME-TRUST-001's synthetic-study pattern.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from core.statistical_floor import (
    StatisticalFloorConfig,
    TacticalSignalEvidence,
    evaluate_statistical_floor,
)
from research.stock_tactics_backtest import (
    BacktestConfig,
    PriceBar,
    TacticSignal,
    run_backtest,
)

PRODUCER = "NovaTacticBot.research.tactic_trust_soak"
SOAK_SCHEMA_VERSION = "tactic_trust_soak.v1"

_SETUP = "TREND_CONTINUATION"
_SYMBOL = "SYN"


def generate_synthetic_backtest_inputs(
    *, n_signals: int, drift: float = 0.002, noise: float = 0.006, seed: int = 7
) -> tuple[list[PriceBar], list[TacticSignal]]:
    """Build a deterministic synthetic uptrend bar series + evenly spaced signals.

    A mild positive drift makes a long-only tactic show a positive edge, so the
    soak's *only* remaining blocker is the honest one (synthetic data + sample
    accumulation), not a broken setup. Entry is next-bar-open, hold 5 bars, so we
    pad enough trailing bars after the last signal.
    """
    import datetime as _dt

    spacing = 3
    bars_needed = spacing * n_signals + 8
    rng = random.Random(seed)
    base = _dt.date(2025, 1, 1)
    price = 100.0
    bars: list[PriceBar] = []
    for i in range(bars_needed):
        drift_step = price * (1.0 + drift)
        op = round(drift_step + rng.uniform(-noise, noise) * price, 2)
        cl = round(op * (1.0 + drift) + rng.uniform(-noise, noise) * price, 2)
        hi = round(max(op, cl) * (1.0 + abs(rng.uniform(0, noise))), 2)
        lo = round(min(op, cl) * (1.0 - abs(rng.uniform(0, noise))), 2)
        bars.append(PriceBar(date=(base + _dt.timedelta(days=i)).isoformat(),
                              open=op, high=hi, low=lo, close=max(cl, 0.01)))
        price = max(cl, 1.0)
    signals = [
        TacticSignal(signal_date=bars[i * spacing].date, symbol=_SYMBOL,
                     direction="long", setup_type=_SETUP)
        for i in range(n_signals)
    ]
    return bars, signals


def build_tactic_trust_soak(
    *,
    n_signals: int,
    drift: float = 0.002,
    noise: float = 0.006,
    synthetic_confidence: float = 0.75,
    generated_at: str | None = None,
    config: StatisticalFloorConfig | None = None,
) -> dict[str, Any]:
    """Run the synthetic backtest, feed the evidence gate, and report the soak state."""
    cfg = config or StatisticalFloorConfig()
    bars, signals = generate_synthetic_backtest_inputs(
        n_signals=n_signals, drift=drift, noise=noise
    )
    report = run_backtest(bars, signals, BacktestConfig(holding_period_days=5),
                          symbol=_SYMBOL, input_source="synthetic_uptrend", data_is_real=False)
    summary = report.summary

    now = (datetime.fromisoformat(generated_at) if generated_at
           else datetime.now(timezone.utc))
    # The backtest reports expectancy as a PERCENT (e.g. 2.5 == 2.5%); the floor's
    # `edge` is a DECIMAL fraction (min_edge 0.02 == 2%). Convert percent -> decimal.
    edge_decimal = (summary.expectancy_pct / 100.0) if summary else None
    evidence = TacticalSignalEvidence(
        signal_id="soak-syn-1",
        strategy_id=_SETUP,
        sample_size=(summary.trades if summary else 0),
        confidence=synthetic_confidence,
        win_rate=(summary.win_rate if summary else None),
        edge=edge_decimal,
        produced_at=now.isoformat(),
        fresh_until=None,
        data_is_real=False,  # synthetic — the floor MUST refuse STRONG on this
        regime="BULL",
        regime_verified=False,
        exposure_increasing=True,
        input_source="synthetic_uptrend",
    )
    floor = evaluate_statistical_floor(evidence, now=now, config=cfg)

    sample_size = summary.trades if summary else 0
    return {
        "schema_version": SOAK_SCHEMA_VERSION,
        "producer": PRODUCER,
        "research_only": True,
        "not_for_live_trading": True,
        "diagnostic_only": True,
        "wired_into_execution": False,
        "data_is_real": False,
        "honesty_note": (
            "Synthetic data: the statistical floor can NEVER approve STRONG here "
            "(data_not_real). This study shows soak progress + remaining blockers; "
            "it grants no trust. Real-data approval is HUMAN_GATED."
        ),
        "backtest_summary": (
            {
                "trades": summary.trades,
                "win_rate": summary.win_rate,
                "avg_return_pct": summary.avg_return_pct,
                "expectancy_pct": summary.expectancy_pct,
                "max_drawdown_pct": summary.max_drawdown_pct,
            }
            if summary else None
        ),
        "soak_progress": {
            "sample_size": sample_size,
            "min_sample_size": cfg.min_sample_size,
            "sample_floor_met": sample_size >= cfg.min_sample_size,
            "samples_remaining": max(0, cfg.min_sample_size - sample_size),
        },
        "floor_verdict": floor.to_dict(),
    }
