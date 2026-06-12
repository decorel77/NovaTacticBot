# NEXT-015 — Offline Stock-Tactics Backtest Harness

**Module:** `research/stock_tactics_backtest.py` (+ `research/__init__.py`)
**Status:** research-only, not wired into the advisory runner.
**Tests:** `tests/test_stock_tactics_backtest.py`, fixtures in `tests/fixtures/backtest/`.

## What this is

A deterministic, fixture-driven harness for evaluating simple **long-only** stock
tactics over daily OHLC bars. Given a price series and a list of signal dates, it
computes per-trade outcomes and summary statistics:

- signal date, symbol, setup label, entry date/price, exit date/price, exit reason,
- holding period (bars), return %, win/loss,
- per-trade max drawdown (worst low-vs-entry excursion),
- summary: trade count, win rate, average return, compounded cumulative return,
  average holding period, worst drawdown, expectancy,
- `summary_by_setup`: the same summary metrics grouped per normalized setup
  label (sorted keys, deterministic).

## Per-setup / strategy labels (added 2026-06-12)

Signals may carry an optional `setup_type` (JSON keys `setup_type` or
`SetupType`). Labels are normalized (trim + uppercase) and validated against
the labels the NovaBotV2 stock pipeline actually produces:

| Label | Source |
|---|---|
| `RSI_CROSS_UP` | `detect_setup` family (NovaBotV2 `utils/signal_setup_utils.py`) |
| `TREND_PULLBACK` | `detect_setup` family |
| `TREND_CONTINUATION` | `detect_setup` family |
| `OVERSOLD_REBOUND` | `detect_setup` family |
| `BREAKOUT` | observed strategy label in the real NovaBotV2 `trade_events.jsonl` outcome stream |
| `UNKNOWN` | fail-closed sentinel |

**Fail-closed rule:** a missing/empty label is an explicit `UNKNOWN`; a
non-empty label outside the table (e.g. `DIP_BUY`, `MYSTERY_SETUP`) also maps
to `UNKNOWN` **and** is recorded in the report's `notes` — per-setup statistics
can never be attributed to a setup family that does not exist. The rendered
report prints the per-setup block with an inline warning that small samples
are not evidence of edge.

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

- **Per-setup labels exist, but real labeled samples do not (yet).** The
  per-setup breakdown ("sample sizes per setup") is implemented and pinned by
  tests, but every checked-in fixture is synthetic and the only real outcome
  stream currently has **1 unique deduplicated trade** (NEXT-016 soak, paused
  while `\NovaBot_Main` is disabled). Per-setup win rates on n<30 samples are
  noise — the rendered report says so explicitly.
- **Label provenance is declarative.** The harness trusts the `setup_type` on
  the input signal; it does not (and cannot, offline) re-derive the setup from
  the bars. Garbage labels fail closed to UNKNOWN, but a *wrong* known label
  is undetectable here.
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

1. ~~Add an optional `setup_type`/`strategy` label to `TacticSignal` and a
   per-label summary breakdown, so reports satisfy "sample sizes per setup".~~
   ✅ DONE 2026-06-12 (this revision; see "Per-setup / strategy labels").
2. Build a documented **real historical fixture** (clearly labelled
   `data_is_real: true`, with source and date range) and produce a first dated
   in-sample report for the NovaBotV2 setup families using the live
   TP/SL parameters exported from config — read-only export, no runtime import.
3. Split that fixture into calibration vs holdout windows for an explicit
   in-sample / out-of-sample comparison (walk-forward can come later,
   aligned with NEXT-014's regime-calibration harness pattern).
4. Only after per-setup sample sizes are ≥30 real outcomes per family should
   any conclusion feed back into tactic confidence discussions (NEXT-016 gate).

## How this later feeds dashboard / TacticBot reporting

The intended (NOT yet wired) consumption path, all read-only:

- The per-setup labels here use the **same vocabulary** as NovaTacticBot's
  outcome stream: `NovaBotV2TradeAdapter` already derives `strategy_id` from
  `strategy`/`setup_type` on real trade events, so backtest setup families and
  real-outcome setup families will be directly comparable per label.
- Once real per-setup sample sizes pass the ≥30 deduplicated-outcomes gate
  (NEXT-016), TacticBot's report generator (QA-016 statistical floor /
  NEXT-020) can show backtest expectancy *next to* real expectancy per setup —
  with the backtest column clearly marked research-only.
- Any Bridge/dashboard surfacing would consume the JSON report
  (`report_to_dict`, includes `summary_by_setup`) as a static research
  artifact; the harness itself stays out of every runtime cycle, and nothing
  in this step wires it anywhere.
