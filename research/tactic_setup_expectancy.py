"""Expectancy-by-setup soak breakdown (TACTIC-TRUST-002).

RESEARCH / REPORTING ONLY — DIAGNOSTIC-ONLY, NOT WIRED.

TACTIC-TRUST-001 (`tactic_trust_soak`) ran one synthetic soak for a single setup
and showed the fail-closed trust gate refuses STRONG on synthetic data. This
follow-up answers the localisation question the ~1/30-edge finding raised: **where
would an edge concentrate across setups?** It runs an independent deterministic
synthetic backtest per known setup family — each given a distinct, *documented*
synthetic drift profile so the breakdown spreads — and reports per-setup
expectancy / win-rate, then feeds each through the same statistical floor to prove
every setup stays DIAGNOSTIC_ONLY (synthetic ⇒ never STRONG).

The drift profiles are **modelling choices for a diagnostic study, NOT measured
real edges**: some setups carry a positive synthetic drift, one is flat, one is
negative, purely so the per-setup expectancy table is informative about *which*
family the harness would surface an edge for. Real-data trust remains BLOCKED /
HUMAN_GATED.

Boundaries (binding): imports only the stdlib + in-repo research/core modules
(reusing the TACTIC-TRUST-001 generator and the QA-016 statistical floor); no
broker/live/order import, no network, no real data, no writes. Not wired into the
runner, snapshot writer, or any execution path.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from core.statistical_floor import (
    StatisticalFloorConfig,
    TacticalSignalEvidence,
    evaluate_statistical_floor,
)
from research.stock_tactics_backtest import (
    KNOWN_SETUP_LABELS,
    BacktestConfig,
    run_backtest,
)
from research.tactic_trust_soak import generate_synthetic_backtest_inputs

PRODUCER = "NovaTacticBot.research.tactic_setup_expectancy"
SCHEMA_VERSION = "tactic_setup_expectancy.v1"

_SYMBOL = "SYN"

# Per-setup synthetic drift profiles (deterministic). Chosen to SPREAD expectancy
# so the breakdown localises where a (synthetic) edge would concentrate: positive
# for trend/breakout families, flat for RSI cross, negative for a long-into-
# weakness rebound. These are MODELLING CHOICES for a diagnostic study — not
# measured real edges.
SETUP_PROFILES: dict[str, dict[str, float | int]] = {
    "TREND_CONTINUATION": {"drift": 0.004, "noise": 0.006, "seed": 11},
    "BREAKOUT": {"drift": 0.003, "noise": 0.006, "seed": 13},
    "TREND_PULLBACK": {"drift": 0.002, "noise": 0.006, "seed": 17},
    "RSI_CROSS_UP": {"drift": 0.0, "noise": 0.008, "seed": 19},
    "OVERSOLD_REBOUND": {"drift": -0.002, "noise": 0.006, "seed": 23},
}

# Fail-closed at import: never attribute statistics to a setup family the harness
# does not actually recognise.
assert set(SETUP_PROFILES) <= set(KNOWN_SETUP_LABELS), (
    "SETUP_PROFILES must be a subset of KNOWN_SETUP_LABELS"
)


def build_setup_expectancy(
    setup: str,
    *,
    n_signals: int,
    profile: dict[str, float | int],
    synthetic_confidence: float = 0.75,
    now: datetime,
    config: StatisticalFloorConfig,
) -> dict[str, Any]:
    """Run one synthetic backtest for ``setup`` and return its expectancy row."""
    bars, signals = generate_synthetic_backtest_inputs(
        n_signals=n_signals,
        drift=float(profile["drift"]),
        noise=float(profile["noise"]),
        seed=int(profile["seed"]),
    )
    signals = [replace(s, setup_type=setup) for s in signals]
    report = run_backtest(
        bars, signals, BacktestConfig(holding_period_days=5),
        symbol=_SYMBOL, input_source="synthetic_setup", data_is_real=False,
    )
    summary = report.summary
    edge_decimal = (summary.expectancy_pct / 100.0) if summary else None
    evidence = TacticalSignalEvidence(
        signal_id=f"setup-soak-{setup}",
        strategy_id=setup,
        sample_size=(summary.trades if summary else 0),
        confidence=synthetic_confidence,
        win_rate=(summary.win_rate if summary else None),
        edge=edge_decimal,
        produced_at=now.isoformat(),
        fresh_until=None,
        data_is_real=False,  # synthetic — the floor MUST refuse STRONG
        regime="BULL",
        regime_verified=False,
        exposure_increasing=True,
        input_source="synthetic_setup",
    )
    floor = evaluate_statistical_floor(evidence, now=now, config=config)
    return {
        "setup": setup,
        "drift": round(float(profile["drift"]), 6),
        "trades": (summary.trades if summary else 0),
        "win_rate": (summary.win_rate if summary else None),
        "avg_return_pct": (summary.avg_return_pct if summary else None),
        "expectancy_pct": (summary.expectancy_pct if summary else None),
        "max_drawdown_pct": (summary.max_drawdown_pct if summary else None),
        "edge_decimal": (round(edge_decimal, 6) if edge_decimal is not None else None),
        "floor_approved": floor.approved,
        "floor_verdict": floor.to_dict(),
    }


def run_setup_expectancy_study(
    *,
    n_signals: int = 40,
    synthetic_confidence: float = 0.75,
    generated_at: str | None = None,
    config: StatisticalFloorConfig | None = None,
) -> dict[str, Any]:
    """Build the per-setup expectancy table + an edge-concentration summary."""
    cfg = config or StatisticalFloorConfig()
    now = (datetime.fromisoformat(generated_at) if generated_at
           else datetime.now(timezone.utc))

    rows = [
        build_setup_expectancy(
            setup, n_signals=n_signals, profile=profile,
            synthetic_confidence=synthetic_confidence, now=now, config=cfg,
        )
        for setup, profile in SETUP_PROFILES.items()
    ]

    ranked = sorted(
        rows, key=lambda r: (r["expectancy_pct"] is None, -(r["expectancy_pct"] or 0.0))
    )
    positive = [r["setup"] for r in rows
                if r["expectancy_pct"] is not None and r["expectancy_pct"] > 0]
    negative = [r["setup"] for r in rows
                if r["expectancy_pct"] is not None and r["expectancy_pct"] < 0]
    any_approved = any(r["floor_approved"] for r in rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "research_only": True,
        "not_for_live_trading": True,
        "diagnostic_only": True,
        "wired_into_execution": False,
        "data_is_real": False,
        "honesty_note": (
            "Synthetic per-setup drift profiles localise where an edge WOULD "
            "concentrate; they are not measured real edges. The statistical floor "
            "refuses STRONG for every setup (data_not_real), so this grants no "
            "trust. Real-data approval is HUMAN_GATED."
        ),
        "n_signals_per_setup": n_signals,
        "min_sample_size": cfg.min_sample_size,
        "edge_concentration": {
            "ranked_by_expectancy": [r["setup"] for r in ranked],
            "best_setup": ranked[0]["setup"] if ranked else None,
            "worst_setup": ranked[-1]["setup"] if ranked else None,
            "positive_expectancy_setups": positive,
            "negative_expectancy_setups": negative,
            "any_setup_approved_strong": any_approved,  # must be False (synthetic)
        },
        "per_setup": rows,
    }
