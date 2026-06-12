# NEXT-015 — Offline Stock-Tactics Backtest Harness

**Module:** `research/stock_tactics_backtest.py` (+ `research/__init__.py`)
**Status:** research-only, not wired into the advisory runner.
**Tests:** `tests/test_stock_tactics_backtest.py`, fixtures in `tests/fixtures/backtest/`.

## What this is

A deterministic, fixture-driven harness for evaluating simple **long-only** stock
tactics over daily OHLC bars. Given a price series and a list of signal dates, it
computes per-trade outcomes and summary statistics:

- signal date, symbol, entry date/price, exit date/price, exit reason,
- holding period (bars), return %, win/loss,
- per-trade max drawdown (worst low-vs-entry excursion),
- summary: trade count, win rate, average return, compounded cumulative return,
  average holding period, worst drawdown, expectancy.

## Backtest convention

- **One symbol per series**, daily bars, **strictly increasing dates**.
- **Entry** at the **open of the first bar after the signal bar** — no same-bar
  look-ahead. A signal on the last bar is skipped (no entry bar).
- **Exit** at the **close of the bar held `holding_period_days` bars** after entry
  (entry bar counts as bar 1), or earlier if a stop-loss / take-profit level is
  crossed. Within a single bar a stop is assumed reached **before** a target
  (conservative).
- **max_drawdown** is the worst `(low - entry) / entry` over the holding window.

The computation is pure arithmetic: the same fixture always yields the same
numbers. There is no wall-clock, no randomness, and no I/O during compute.

## Provenance / safety flags

Every report carries:

- `research_only: true`
- `broker_execution: "disabled"`
- `data_is_real: false` — and it **stays false** unless a caller explicitly passes
  `data_is_real=True` while using a documented real historical fixture. The CLI
  never asserts realness; all checked-in fixtures are synthetic.

Invalid or fake data **fails closed**: bad OHLC (non-positive prices,
`high < low`, open/close outside `[low, high]`), non-increasing dates, or a bad
config produce a report with `errors`, **no trades**, `summary: None`, and
`data_is_real: false`. The harness never fabricates trades from invalid data.

## How this differs from live trading

This is a **research / sanity tool, not a trading system**:

- It **places no orders** and **connects to no broker** (no `ib_insync`/`ibapi`/
  etc.); it imports no network/subprocess/order/live-cycle modules. A test
  asserts the module imports none of the guardrail's banned broker packages.
- It is **not wired** into the NovaTacticBot advisory runner or any scheduler.
- It models an idealised fill (entry at next open, clean stop/target prices) with
  **no slippage, no commissions, no partial fills, no liquidity limits, and no
  position sizing / capital model**. Real results will be worse.
- Backtests on synthetic or in-sample data are **not** evidence of live edge.
  Results must be labelled in-sample vs out-of-sample; the checked-in fixtures are
  synthetic and exist only to pin the maths.
- It does **not** read or write any live NovaBotV2 state, snapshot, `.env`,
  live-arm token, or scheduled task.

## Usage (offline only)

```bash
# from the NovaTacticBot repo root, using its broker-free venv
.\.venv\Scripts\python.exe -m research.stock_tactics_backtest tests/fixtures/backtest/sample_mixed.json --holding-days 2
```

Programmatic:

```python
from research.stock_tactics_backtest import load_dataset, run_backtest, BacktestConfig

bars, signals, symbol, meta = load_dataset("tests/fixtures/backtest/sample_uptrend.json")
report = run_backtest(bars, signals, BacktestConfig(holding_period_days=3), symbol=symbol)
# report.data_is_real is False; report.broker_execution == "disabled"
```

## Validation status (2026-06-12 review)

Reviewed against the NEXT-015 acceptance criteria:

- **Offline / deterministic / not runtime-wired:** confirmed. The module is
  referenced only by its own tests and this doc — no adapter, runner, workflow,
  or tool imports it. `SafetyTests` pins the broker/network/runtime import ban.
- **Reported metrics:** sample size (`trades`), win rate, expectancy
  (`expectancy_pct`, currently identical to `avg_return_pct`), compounded
  cumulative return, average holding period, and per-trade max adverse excursion
  (`max_drawdown_pct`, worst low-vs-entry). All pinned by exact-value tests.
- **Test coverage:** 18 deterministic tests including exit rules (holding period,
  stop, target, end-of-data), the conservative stop-before-target intrabar
  assumption when both levels are crossed in one bar, determinism, five
  fail-closed cases, signal skipping, and import-safety guardrails.

## Known limitations

- **No per-setup / strategy labels.** `TacticSignal` carries no setup-family or
  strategy tag, so the summary cannot break down win rate / expectancy *per
  setup* — which the NEXT-015 acceptance ("sample sizes per setup") ultimately
  wants. This is the main remaining gap.
- **Single-trade drawdown only.** `max_drawdown_pct` is per-trade max adverse
  excursion; there is no equity-curve / portfolio-level drawdown because there
  is no capital or position-sizing model.
- **Idealised fills.** No slippage, commissions, partial fills, or liquidity
  limits; stops/targets fill exactly at their level. Real results will be worse.
- **Long-only, one symbol per series, daily bars.** Non-long signals and
  symbol mismatches are skipped (recorded in `skipped`), never simulated.
- **All checked-in fixtures are synthetic.** They pin the arithmetic; they say
  nothing about live edge. Any real-data run must label its fixture as real
  historical data explicitly and state in-sample vs out-of-sample.

## Next research steps (offline only; no runtime wiring)

1. Add an optional `setup_type`/`strategy` label to `TacticSignal` and a
   per-label summary breakdown, so reports satisfy "sample sizes per setup".
2. Build a documented **real historical fixture** (clearly labelled
   `data_is_real: true`, with source and date range) and produce a first dated
   in-sample report for the three NovaBotV2 setup families using the live
   TP/SL parameters exported from config — read-only export, no runtime import.
3. Split that fixture into calibration vs holdout windows for an explicit
   in-sample / out-of-sample comparison (walk-forward can come later,
   aligned with NEXT-014's regime-calibration harness pattern).
4. Only after per-setup sample sizes are ≥30 real outcomes per family should
   any conclusion feed back into tactic confidence discussions (NEXT-016 gate).
