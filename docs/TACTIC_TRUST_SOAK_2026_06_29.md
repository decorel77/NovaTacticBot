# TacticBot edge / soak tracking study (TACTIC-TRUST-001) — 2026-06-29

**Card:** TACTIC-TRUST-001 (VERIFY) from `NOVA_MASTER_TODO_ROADMAP_2026_06_29.md` §4c.
**Type:** research / reporting only — **DIAGNOSTIC-ONLY, NOT WIRED.** No live
trading, no broker, no real data, no execution wiring, no production behaviour
change. Runs under the broker-free pytest venv (`requirements.txt` = pytest only;
TacticBot source is pure-stdlib + advisory).
**Artifacts:** `research/tactic_trust_soak.py`, `tests/test_tactic_trust_soak.py`
(6 tests green), this report.

**Question:** *what is TacticBot's trust state, and what is still missing before any
tactic could be labelled STRONG?* This continues the evidence/soak tracking by
joining the two existing advisory pieces — the offline backtest harness
(`research/stock_tactics_backtest.py`, NEXT-015) and the statistical evidence floor
(`core/statistical_floor.py`, QA-016) — into one soak report.

---

## 1. Method

1. Generate a deterministic synthetic uptrend bar series + evenly spaced long
   signals (`research/tactic_trust_soak.generate_synthetic_backtest_inputs`).
2. Run the production backtest harness (`run_backtest`, next-bar-open entry, 5-bar
   hold, no look-ahead) → `BacktestSummary` (trades, win-rate, expectancy).
3. Turn the summary into a `TacticalSignalEvidence` (sample_size, win_rate,
   edge = expectancy%/100 as a decimal, `data_is_real=False` because it is
   synthetic) and evaluate it through `evaluate_statistical_floor`.
4. Report the **soak progress** (samples vs the 30-floor) and the **floor verdict**
   (strength + refusal reasons).

The statistical floor's bar for STRONG: **≥30 samples · confidence ≥0.70 ·
win-rate ≥0.55 · edge ≥0.02 · real data · verified known regime · fresh.** Any
miss → `DIAGNOSTIC_ONLY` (fail-closed).

## 2. Results (synthetic)

| Scenario | trades | win-rate | edge | sample-floor met? | strength | refusal reasons |
|---|---|---|---|---|---|---|
| few samples | 8 | 1.00 | 0.0147 | no | DIAGNOSTIC_ONLY | `sample_size_below_floor:8<30`, `edge_below_floor`, `data_not_real`, `regime_not_verified` |
| enough samples, modest edge | 40 | 0.925 | 0.0157 | yes | DIAGNOSTIC_ONLY | `edge_below_floor`, `data_not_real`, `regime_not_verified` |
| enough samples, strong edge | 40 | 1.00 | 0.0536 | yes | DIAGNOSTIC_ONLY | **`data_not_real`, `regime_not_verified`** (only) |

## 3. Findings

1. **The trust gate is enforced and visible.** A tactic is `DIAGNOSTIC_ONLY` until
   it clears every floor criterion. The soak report makes the *remaining* blockers
   explicit (sample size, edge, real-data, regime verification).
2. **Synthetic data can never earn STRONG.** Even the best synthetic case — 40
   samples, 100% win-rate, 5.4% edge, all numeric floors cleared — stays
   `DIAGNOSTIC_ONLY`, because the irreducible blockers `data_not_real` +
   `regime_not_verified` remain. This is the correct, honest ceiling: research data
   informs design, it does not grant trust.
3. **The ~1/30 trust posture is structural, not incidental.** Below 30 real samples
   a tactic is gated on sample size; the soak `samples_remaining` quantifies the
   distance to even the *first* gate. Real edge (≥2%) and a verified regime are
   additional, independent gates on top.
4. **The machinery stays unwired.** `statistical_floor` and `stock_tactics_backtest`
   import no broker/live/order module and are not called by the runner or snapshot
   writer; this study composes them in `research/` only and is likewise unwired
   (`wired_into_execution=False`).

## 4. Limitations / honest caveats

- **Synthetic only.** The win-rates/edges here are properties of a constructed
  uptrend; they are **not** evidence of a real tactical edge. Real-data soak +
  approval is **HUMAN_GATED** (the same harness can be pointed at an approved real
  fixture with `data_is_real=True` once provisioned — only a human may set that).
- **No costs/slippage** in the backtest edge (signal alignment, not a tradable P&L).
- **Diagnostic-only by design.** Nothing here may be wired into execution; doing so
  is out of scope and HUMAN_GATED.

## 5. Verdict

**TacticBot remains correctly `DIAGNOSTIC_ONLY`.** The soak machinery now reports,
in one place, both *how much* evidence has accumulated and *which* fail-closed gates
remain — and confirms that no amount of synthetic success can lift a tactic to
STRONG. Advancing trust requires a HUMAN_GATED real-data soak that clears the sample,
edge, real-data, and verified-regime floors together. Until then the gate holds and
the modules stay unwired.

**Reproduce:** `Apps/NovaTacticBot/.venv/Scripts/python -m pytest
tests/test_tactic_trust_soak.py -q` (broker-free venv; no real data; no writes).
