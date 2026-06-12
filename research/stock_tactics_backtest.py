"""Offline stock-tactics backtest harness (NEXT-015).

A deterministic, fixture-driven research harness for evaluating simple long-only
stock tactics over daily OHLC bars. It is RESEARCH-ONLY and completely separate
from any live path:

  - it reads only in-memory data or local JSON fixtures,
  - it places no orders and connects to no broker,
  - it imports no broker / order / live-cycle / network modules,
  - it is not wired into the NovaTacticBot advisory runner,
  - its output is always flagged ``research_only=True`` /
    ``broker_execution="disabled"`` and ``data_is_real=False`` unless the caller
    explicitly documents a real historical fixture.

Backtest convention (intentionally simple and explicit; see
``docs/NEXT_015_stock_tactics_backtest_harness.md``):

  - One price series per symbol, daily bars, strictly increasing dates.
  - Entry: at the OPEN of the first bar AFTER the signal bar (no same-bar
    look-ahead). A signal on the last bar is skipped (no entry bar).
  - Exit: at the CLOSE of the bar held ``holding_period_days`` bars after entry
    (the entry bar counts as bar 1), or earlier if a stop-loss / take-profit
    level is crossed. Within a bar a stop is assumed hit before a target
    (conservative).
  - max_drawdown: worst low-vs-entry excursion over the holding window.

Everything is pure arithmetic over the inputs: given the same fixture it always
produces the same numbers. No wall-clock, no randomness, no I/O during compute.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PriceBar:
    date: str  # ISO date "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class TacticSignal:
    signal_date: str
    symbol: str
    direction: str = "long"  # this harness models long-only stock tactics


@dataclass(frozen=True)
class BacktestConfig:
    holding_period_days: int = 5      # number of bars to hold (entry bar = bar 1)
    take_profit_pct: float | None = None   # e.g. 0.10 for +10%
    stop_loss_pct: float | None = None     # e.g. 0.05 for -5%


@dataclass(frozen=True)
class TradeResult:
    signal_date: str
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_reason: str          # "holding_period" | "take_profit" | "stop_loss" | "end_of_data"
    holding_period_days: int  # number of bars held (entry bar inclusive)
    return_pct: float
    win: bool
    max_drawdown_pct: float


@dataclass(frozen=True)
class BacktestSummary:
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_return_pct: float
    cumulative_return_pct: float     # compounded over trades, sequentially
    avg_holding_period_days: float
    max_drawdown_pct: float          # worst single-trade drawdown
    expectancy_pct: float            # mean return per trade


@dataclass(frozen=True)
class BacktestReport:
    research_only: bool
    broker_execution: str
    data_is_real: bool
    input_source: str
    symbol: str
    config: dict[str, Any]
    trades: tuple[TradeResult, ...]
    summary: BacktestSummary | None
    skipped: tuple[str, ...] = ()       # per-signal skip reasons (non-fatal)
    errors: tuple[str, ...] = ()        # dataset-level fatal errors (fail closed)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------- #
# Validation (fail closed)
# --------------------------------------------------------------------------- #
def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def validate_bars(bars: Sequence[PriceBar]) -> list[str]:
    """Return a list of dataset-level errors. Empty list means the bars are sane."""
    errors: list[str] = []
    if not bars:
        return ["no price bars provided"]
    prev_date: str | None = None
    for i, bar in enumerate(bars):
        loc = f"bar[{i}] {bar.date}"
        for name in ("open", "high", "low", "close"):
            v = getattr(bar, name)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errors.append(f"{loc}: {name} is not a number ({v!r})")
            elif v <= 0:
                errors.append(f"{loc}: {name} must be positive (got {v})")
        if bar.high < bar.low:
            errors.append(f"{loc}: high {bar.high} < low {bar.low}")
        if not (bar.low <= bar.open <= bar.high):
            errors.append(f"{loc}: open {bar.open} outside [low, high]")
        if not (bar.low <= bar.close <= bar.high):
            errors.append(f"{loc}: close {bar.close} outside [low, high]")
        if prev_date is not None and bar.date <= prev_date:
            errors.append(f"{loc}: date not strictly increasing (after {prev_date})")
        prev_date = bar.date
    return errors


# --------------------------------------------------------------------------- #
# Core backtest
# --------------------------------------------------------------------------- #
def _simulate_trade(
    bars: Sequence[PriceBar],
    entry_index: int,
    signal: TacticSignal,
    config: BacktestConfig,
) -> TradeResult:
    entry_bar = bars[entry_index]
    entry_price = entry_bar.open
    tp_price = entry_price * (1 + config.take_profit_pct) if config.take_profit_pct is not None else None
    sl_price = entry_price * (1 - config.stop_loss_pct) if config.stop_loss_pct is not None else None

    last_index = min(entry_index + config.holding_period_days - 1, len(bars) - 1)
    worst_low = entry_bar.low
    exit_index = last_index
    exit_price = bars[last_index].close
    exit_reason = "holding_period" if last_index == entry_index + config.holding_period_days - 1 else "end_of_data"

    for idx in range(entry_index, last_index + 1):
        bar = bars[idx]
        worst_low = min(worst_low, bar.low)
        # Conservative intrabar ordering: assume the stop is reached before the target.
        if sl_price is not None and bar.low <= sl_price:
            exit_index, exit_price, exit_reason = idx, sl_price, "stop_loss"
            break
        if tp_price is not None and bar.high >= tp_price:
            exit_index, exit_price, exit_reason = idx, tp_price, "take_profit"
            break

    return_pct = _round((exit_price - entry_price) / entry_price * 100.0)
    max_drawdown_pct = _round((worst_low - entry_price) / entry_price * 100.0)
    return TradeResult(
        signal_date=signal.signal_date,
        symbol=signal.symbol,
        entry_date=entry_bar.date,
        entry_price=_round(entry_price),
        exit_date=bars[exit_index].date,
        exit_price=_round(exit_price),
        exit_reason=exit_reason,
        holding_period_days=exit_index - entry_index + 1,
        return_pct=return_pct,
        win=return_pct > 0,
        max_drawdown_pct=max_drawdown_pct,
    )


def summarize(trades: Sequence[TradeResult]) -> BacktestSummary | None:
    if not trades:
        return None
    n = len(trades)
    wins = sum(1 for t in trades if t.win)
    returns = [t.return_pct for t in trades]
    cumulative = 1.0
    for r in returns:
        cumulative *= (1 + r / 100.0)
    avg_return = sum(returns) / n
    return BacktestSummary(
        trades=n,
        wins=wins,
        losses=n - wins,
        win_rate=_round(wins / n),
        avg_return_pct=_round(avg_return),
        cumulative_return_pct=_round((cumulative - 1.0) * 100.0),
        avg_holding_period_days=_round(sum(t.holding_period_days for t in trades) / n),
        max_drawdown_pct=_round(min(t.max_drawdown_pct for t in trades)),
        expectancy_pct=_round(avg_return),
    )


def run_backtest(
    bars: Sequence[PriceBar],
    signals: Sequence[TacticSignal],
    config: BacktestConfig | None = None,
    *,
    symbol: str,
    input_source: str = "fixture",
    data_is_real: bool = False,
) -> BacktestReport:
    """Run the deterministic backtest. Fails closed on invalid data.

    ``data_is_real`` defaults to False and should only be set True by a caller
    that is explicitly using a documented real historical fixture. Even then the
    harness never touches a broker and ``broker_execution`` stays "disabled".
    """
    cfg = config or BacktestConfig()
    config_dict = asdict(cfg)

    errors = validate_bars(bars)
    if cfg.holding_period_days < 1:
        errors.append(f"holding_period_days must be >= 1 (got {cfg.holding_period_days})")
    for opt_name in ("take_profit_pct", "stop_loss_pct"):
        val = getattr(cfg, opt_name)
        if val is not None and (not isinstance(val, (int, float)) or isinstance(val, bool) or val <= 0):
            errors.append(f"{opt_name} must be a positive fraction or None (got {val!r})")

    if errors:
        # Fail closed: never fabricate trades from invalid/fake data.
        return BacktestReport(
            research_only=RESEARCH_ONLY,
            broker_execution=BROKER_EXECUTION,
            data_is_real=False,
            input_source=input_source,
            symbol=symbol,
            config=config_dict,
            trades=(),
            summary=None,
            errors=tuple(errors),
        )

    date_to_index = {bar.date: i for i, bar in enumerate(bars)}
    trades: list[TradeResult] = []
    skipped: list[str] = []

    for sig in signals:
        if sig.symbol != symbol:
            skipped.append(f"{sig.signal_date}: signal symbol {sig.symbol!r} != series symbol {symbol!r}")
            continue
        if sig.direction != "long":
            skipped.append(f"{sig.signal_date}: unsupported direction {sig.direction!r} (long-only harness)")
            continue
        if sig.signal_date not in date_to_index:
            skipped.append(f"{sig.signal_date}: signal date not found in price series")
            continue
        entry_index = date_to_index[sig.signal_date] + 1
        if entry_index >= len(bars):
            skipped.append(f"{sig.signal_date}: no entry bar after signal (last bar)")
            continue
        trades.append(_simulate_trade(bars, entry_index, sig, cfg))

    return BacktestReport(
        research_only=RESEARCH_ONLY,
        broker_execution=BROKER_EXECUTION,
        data_is_real=bool(data_is_real),
        input_source=input_source,
        symbol=symbol,
        config=config_dict,
        trades=tuple(trades),
        summary=summarize(trades),
        skipped=tuple(skipped),
    )


# --------------------------------------------------------------------------- #
# Fixture loading + rendering (research convenience only)
# --------------------------------------------------------------------------- #
def load_dataset(path: str | Path) -> tuple[list[PriceBar], list[TacticSignal], str, dict[str, Any]]:
    """Load a JSON dataset: {symbol, bars:[...], signals:[...], meta:{...}}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    symbol = str(data["symbol"])
    bars = [
        PriceBar(date=str(b["date"]), open=float(b["open"]), high=float(b["high"]),
                 low=float(b["low"]), close=float(b["close"]))
        for b in data.get("bars", [])
    ]
    signals = [
        TacticSignal(signal_date=str(s["signal_date"]), symbol=str(s.get("symbol", symbol)),
                     direction=str(s.get("direction", "long")))
        for s in data.get("signals", [])
    ]
    meta = dict(data.get("meta", {}))
    return bars, signals, symbol, meta


def report_to_dict(report: BacktestReport) -> dict[str, Any]:
    return asdict(report)


def render_report_text(report: BacktestReport) -> str:
    lines = [
        "STOCK-TACTICS OFFLINE BACKTEST (RESEARCH ONLY)",
        "",
        f"research_only: {report.research_only}",
        f"broker_execution: {report.broker_execution}",
        f"data_is_real: {report.data_is_real}",
        f"input_source: {report.input_source}",
        f"symbol: {report.symbol}",
        f"config: {report.config}",
        "",
    ]
    if report.errors:
        lines.append("ERRORS (failed closed, no trades evaluated):")
        lines.extend(f"  - {e}" for e in report.errors)
        return "\n".join(lines).rstrip() + "\n"

    lines.append(f"trades: {len(report.trades)}")
    for t in report.trades:
        lines.append(
            f"  {t.entry_date} {t.symbol} entry={t.entry_price} exit={t.exit_price} "
            f"({t.exit_reason}) hold={t.holding_period_days}b return={t.return_pct}% "
            f"dd={t.max_drawdown_pct}% {'WIN' if t.win else 'LOSS'}"
        )
    if report.skipped:
        lines.append("skipped signals:")
        lines.extend(f"  - {s}" for s in report.skipped)
    s = report.summary
    if s is not None:
        lines.extend([
            "",
            "summary:",
            f"  trades={s.trades} wins={s.wins} losses={s.losses} win_rate={s.win_rate}",
            f"  avg_return_pct={s.avg_return_pct} cumulative_return_pct={s.cumulative_return_pct}",
            f"  avg_holding_period_days={s.avg_holding_period_days} "
            f"max_drawdown_pct={s.max_drawdown_pct} expectancy_pct={s.expectancy_pct}",
        ])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline RESEARCH-ONLY stock-tactics backtest (no broker, no orders)"
    )
    parser.add_argument("dataset", help="path to a JSON dataset fixture")
    parser.add_argument("--holding-days", type=int, default=5)
    parser.add_argument("--take-profit", type=float, default=None)
    parser.add_argument("--stop-loss", type=float, default=None)
    args = parser.parse_args(argv)

    bars, signals, symbol, meta = load_dataset(args.dataset)
    cfg = BacktestConfig(
        holding_period_days=args.holding_days,
        take_profit_pct=args.take_profit,
        stop_loss_pct=args.stop_loss,
    )
    report = run_backtest(
        bars, signals, cfg, symbol=symbol,
        input_source=str(meta.get("input_source", "fixture")),
        data_is_real=False,  # CLI never asserts realness; fixtures are research-only
    )
    print(render_report_text(report), end="")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
