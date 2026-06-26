# NovaTacticBot Pattern Recognition — Lookahead-Bias Audit (PATTERN-004)

Task: `PATTERN-004`
Status: read-only audit + synthetic pinning tests (no detector behaviour changed)
Repo: `Apps/NovaTacticBot`
Evidence date: 2026-06-26 (Europe/Brussels) — **line numbers dated; re-verify at HEAD.**
HEAD at audit: `1808448`

> This audit reads code only. No detector logic was changed — per the card, any
> bug fix would be a separate, explicitly named card. The findings below are
> pinned by `tests/test_pattern_recognition.py` (`LookaheadWindowLocalityTests`,
> `LookaheadFutureIndependenceTests`) so a future refactor that introduced
> lookahead would fail the suite.

## What "lookahead bias" means here

A detector has lookahead bias if its verdict about the decision bar uses data
from a **later** bar than the decision bar. In this research stack the decision
bar is always **the last bar of the input window** ("now"); a detector must use
only bars up to and including it.

## Per-detector finding (`research/pattern_recognition.py`)

Every price detector takes a `Sequence[PatternBar]`, slices a **bounded trailing
window** from the end, and evaluates the last bar relative to the prior bars in
that window. None reference an index beyond the last element. Verdict: **no
lookahead** for all eight.

| Detector | Window slice | Decision bar | No-lookahead reasoning |
|---|---|---|---|
| `breakout_after_consolidation` (`:270`) | `bars[-(cw+1):-1]` (range) + `bars[-1]` | last bar | range built from bars strictly before the last; breakout tested on the last close only |
| `volume_spike` (`:319`) | `bars[-(vw+1):-1]` baseline + `bars[-1]` | last bar | baseline excludes the last bar; ratio uses the last bar vs the trailing baseline |
| `trend_continuation` (`:357`) | `bars[-(tw+1):]` | last bar | net return / consistency / last-move all from the trailing window only |
| `mean_reversion_candidate` (`:409`) | `bars[-lookback:]` | last bar | mean/stdev over the trailing window; z-score of the last close |
| `gap_continuation_risk` (`:458`) | `bars[-2:]` | last bar | gap is last.open vs prev.close; fill/close use the last bar's own H/L/C |
| `failed_breakout` (`:510`) | `bars[-(cw+2):-2]` base + `bars[-2]`,`bars[-1]` | last bar | base high from bars before the poke; failure tested on the last close |
| `higher_high_higher_low` (`:557`) | `bars[-max(4,tw):]` split in halves | last bar | both halves lie within the trailing window |
| `drawdown_recovery` (`:607`) | `bars[-lookback:]` | last bar | peak/trough/recovery computed by a single forward pass over the trailing window |

The outcome detector `win_loss_clusters` (`:666`) operates on labeled outcomes,
not price bars; it sorts deterministically by `(date, original_index)` (`:686`)
and computes streaks — no price bar, so no price-lookahead surface.

## Harness finding (`research/stock_tactics_backtest.py`)

The backtest is where same-bar lookahead would normally creep in. It is clean:

- **Entry is the bar AFTER the signal**: `entry_index = date_to_index[signal_date] + 1`
  (`:331`); entry price is that bar's **open** (`:195-196`). No same-bar fill.
- **A signal on the last bar is skipped**: `if entry_index >= len(bars): skip
  "no entry bar after signal"` (`:332-334`).
- The **outcome** legitimately uses the holding window (entry..exit, `:200-215`).
  This is the realized result, not a feature — forward-looking *outcomes* are
  correct; forward-looking *signals* would be the bug, and the signals are
  supplied externally by `signal_date`, never computed from future bars here.

These conventions are documented in the module docstring (`:15-28`) and already
pinned by `tests/test_stock_tactics_backtest.py` ("no entry bar after signal";
"stop assumed hit before target" same-bar ordering). No change made to that file.

## Pinning tests added (`tests/test_pattern_recognition.py`)

- `LookaheadWindowLocalityTests` — prepending older bars before the window does
  not change any detector's verdict (per-detector + full-scan), proving each uses
  only its trailing window and cannot reach into history; also asserts detectors
  do not mutate their input.
- `LookaheadFutureIndependenceTests` — a detector's decision *as of* bar k
  (computed from `bars[:k+1]`) is identical when the tail of the full series is
  mutated to extreme values, and the verdict for a 6-bar window is reproducible
  after an extreme 7th (future) bar is appended and sliced back.

## Conclusion

No lookahead bias found in the eight price detectors or in the backtest entry
convention. All findings are pinned by synthetic, broker-free tests. Any future
behavioural fix (none needed today) must be a separate, named card per
`PATTERN-004`'s contract.
