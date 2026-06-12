"""
NovaBotV2 Trade-Outcome Adapter for NovaTacticBot (NEXT-008 / NEXT-009).

Reads NovaBotV2's append-only ``data/results/trade_events.jsonl`` and converts
completed-trade events into ``TRADE_OUTCOME`` TacticalEvents so that the
statistical floor (QA-016) and the strategy-outcome correlation diagnostic
(QA-019) finally have a real stock-side outcome stream to consume.

This is distinct from ``adapters/nova_botv2_adapter.py`` (NovaBotV2Adapter),
which reads worker *state* from result_snapshot.json and emits SYSTEM_EVENTs.
This adapter reads trade *outcomes*.

Provenance (NEXT-009): every emitted event carries ``metadata["data_is_real"]``,
derived from the source event's ``execution_mode``:
  - "LIVE" / "LIVE_RECONCILED"  -> real broker fill        -> data_is_real = True
  - "DRY_RUN" / "SIMULATED" / "" / anything else (fail closed) -> data_is_real = False
The adapter does NOT drop simulated events — it annotates them, so diagnostics
can see everything while QA-016/QA-019 filter on data_is_real. Fail-closed: any
unknown/missing execution mode is treated as NOT real.

Hard safety: READ-ONLY. No writes to NovaBotV2. No broker access. ADVISORY_ONLY.
This module is intentionally NOT wired into tools/run_tacticbot.py — it is
adapter/contract prep per the NEXT queue and stays out of the default runtime
until its preconditions (advisory cadence, review) are met.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from adapters.base_adapter import BaseAdapter
from core.tactic_event import EventType, Outcome, SourceBot, TacticalEvent

logger = logging.getLogger(__name__)

_NOVA_ROOT = Path(__file__).resolve().parents[3]  # C:\NovaGPT
DEFAULT_SOURCE_DIR = _NOVA_ROOT / "Apps" / "NovaBotV2" / "data" / "results"
_EVENTS_FILE = "trade_events.jsonl"

# The events log grows unbounded; cap how much we are willing to read. The newest
# events are at the end of the file, so when capping we keep the TAIL.
MAX_EVENTS_BYTES = 16 * 1024 * 1024  # 16 MB

# Event types that represent a realised, closed trade with a PnL number.
_OUTCOME_EVENT_TYPES = frozenset({"SELL_EXECUTED"})

# execution_mode values that mean a real broker fill. Everything else fails closed.
_REAL_EXECUTION_MODES = frozenset({"LIVE", "LIVE_RECONCILED"})

# PnL source fields in preference order (net-of-fees first).
_PNL_FIELDS = ("netto_pnl", "pnl_abs", "profit_abs", "realized_pnl")


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # guard NaN


def _parse_timestamp(raw: Any) -> Optional[datetime]:
    text = _safe_str(raw)
    if not text:
        return None
    for parse in (
        lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S"),
        datetime.fromisoformat,
    ):
        try:
            return parse(text)
        except ValueError:
            continue
    return None


def _derive_data_is_real(execution_mode: str) -> bool:
    """Fail-closed provenance: only explicit real broker fills are real."""
    return execution_mode.strip().upper() in _REAL_EXECUTION_MODES


def _derive_outcome(pnl: Optional[float]) -> str:
    if pnl is None:
        return Outcome.PENDING
    if pnl > 0:
        return Outcome.WIN
    if pnl < 0:
        return Outcome.LOSS
    return Outcome.BREAKEVEN


def _first_pnl(data: dict[str, Any]) -> Optional[float]:
    for field in _PNL_FIELDS:
        value = _to_float(data.get(field))
        if value is not None:
            return value
    return None


class NovaBotV2TradeAdapter(BaseAdapter):
    """Read-only adapter for NovaBotV2 trade_events.jsonl trade outcomes."""

    SOURCE_BOT = SourceBot.NOVA_BOT_V2

    def __init__(
        self,
        source_dir: Optional[str | Path] = None,
        *,
        deduplicate: bool = True,
        max_bytes: int = MAX_EVENTS_BYTES,
    ) -> None:
        super().__init__(source_dir or DEFAULT_SOURCE_DIR)
        self.deduplicate = deduplicate
        self.max_bytes = max_bytes

    def _read_lines(self, path: Path) -> list[str]:
        """Read the events file read-only, keeping only the tail within max_bytes."""
        try:
            with path.open("rb") as fh:
                fh.seek(0, 2)
                size = fh.tell()
                if size > self.max_bytes:
                    fh.seek(size - self.max_bytes)
                    # Drop the first (probably partial) line after a mid-file seek.
                    raw = fh.read().decode("utf-8", errors="replace")
                    return raw.splitlines()[1:]
                fh.seek(0)
                return fh.read().decode("utf-8", errors="replace").splitlines()
        except OSError as exc:
            self._record_error(f"could not read {path.name}: {exc}")
            return []

    def _event_from_line(self, line: str) -> Optional[TacticalEvent]:
        line = line.strip()
        if not line:
            return None
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            self._record_error("skipped unparseable JSONL line")
            return None
        if not isinstance(record, dict):
            return None
        if _safe_str(record.get("event_type")) not in _OUTCOME_EVENT_TYPES:
            return None

        data = record.get("data")
        if not isinstance(data, dict):
            self._record_error("outcome event missing data block")
            return None

        execution_mode = _safe_str(data.get("execution_mode"))
        data_is_real = _derive_data_is_real(execution_mode)
        pnl = _first_pnl(data)
        outcome = _derive_outcome(pnl)
        strategy_id = (
            _safe_str(data.get("strategy"))
            or _safe_str(data.get("setup_type"))
            or "UNKNOWN"
        )
        timestamp = (
            _parse_timestamp(data.get("timestamp"))
            or _parse_timestamp(record.get("timestamp"))
            or datetime.utcnow()
        )

        metadata = {
            "ticker": _safe_str(data.get("ticker")),
            "sell_reason": _safe_str(data.get("sell_reason")) or _safe_str(data.get("reason")),
            "setup_type": _safe_str(data.get("setup_type")),
            "execution_mode": execution_mode,
            "data_is_real": data_is_real,
            "currency": _safe_str(data.get("currency")),
            "quantity": _to_float(data.get("quantity")),
            "price": _to_float(data.get("price")),
            "pnl_pct": _to_float(data.get("pnl_pct")) or _to_float(data.get("netto_pnl_pct")),
            "cycle_id": _safe_str(data.get("cycle_id")),
            "session_id": _safe_str(data.get("session_id")),
            "trade_id": _safe_str(data.get("trade_id")),
            "exec_ids": _safe_str(data.get("exec_ids")),
            "broker_source": _safe_str(data.get("broker_source")),
        }

        try:
            return TacticalEvent(
                source_bot=self.SOURCE_BOT,
                event_type=EventType.TRADE_OUTCOME,
                strategy_id=strategy_id,
                timestamp=timestamp,
                realized_pnl=pnl,
                outcome=outcome,
                metadata=metadata,
            )
        except ValueError as exc:
            self._record_error(f"invalid outcome event: {exc}")
            return None

    @staticmethod
    def _dedup_key(event: TacticalEvent) -> Optional[tuple[str, str]]:
        """Stable identity for a closed trade: (trade_id, exec_ids) when both known.

        NovaBotV2 reconciliation can log the same broker fill more than once (e.g.
        a second line once the commission report arrives). Collapsing on the
        broker identity keeps outcome analytics from double-counting one trade.
        Returns None when identity is unknown — those events are never merged.
        """
        trade_id = _safe_str(event.metadata.get("trade_id"))
        exec_ids = _safe_str(event.metadata.get("exec_ids"))
        if trade_id and exec_ids:
            return (trade_id, exec_ids)
        return None

    def _load_from_source(self) -> None:
        path = self.source_dir / _EVENTS_FILE  # type: ignore[operator]
        if not path.exists():
            self._record_error(f"{_EVENTS_FILE} not found in {self.source_dir}")
            return

        deduped: dict[tuple[str, str], TacticalEvent] = {}
        for line in self._read_lines(path):
            event = self._event_from_line(line)
            if event is None:
                continue
            key = self._dedup_key(event) if self.deduplicate else None
            if key is None:
                self._add_event(event)
            else:
                # Keep the last (most-reconciled) occurrence of a trade.
                if key in deduped:
                    self._events.remove(deduped[key])
                deduped[key] = event
                self._add_event(event)
