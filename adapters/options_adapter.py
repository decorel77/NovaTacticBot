"""
NovaBotV2Options Adapter — READ-ONLY

Reads NovaBotV2Options output and converts it into universal TacticalEvents.

Supported source formats:
  - JSON report files  (*.json in source_dir)
  - CSV export files   (*.csv in source_dir)
  - Log files          (*.log in source_dir, best-effort parsing)

No broker access. No scheduler access. No execution access.
"""

from __future__ import annotations

import csv
import json
import logging
import math
from pathlib import Path
from typing import Any

from adapters.base_adapter import BaseAdapter
from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent

logger = logging.getLogger(__name__)


# ── Field mappings from NovaBotV2Options native format ────────────────────────

_OUTCOME_MAP: dict[str, str] = {
    "win": Outcome.WIN,
    "profit": Outcome.WIN,
    "loss": Outcome.LOSS,
    "breakeven": Outcome.BREAKEVEN,
    "be": Outcome.BREAKEVEN,
    "partial": Outcome.PARTIAL,
    "expired": Outcome.EXPIRED,
    "pending": Outcome.PENDING,
}

_REGIME_MAP: dict[str, str] = {
    "bull": Regime.BULL,
    "bear": Regime.BEAR,
    "normal": Regime.NORMAL,
    "neutral": Regime.NORMAL,
    "high_vol": Regime.HIGH_VOL,
    "highvol": Regime.HIGH_VOL,
    "low_vol": Regime.LOW_VOL,
    "lowvol": Regime.LOW_VOL,
}

_EVENT_TYPE_MAP: dict[str, str] = {
    "trade_outcome": EventType.TRADE_OUTCOME,
    "trade": EventType.TRADE_OUTCOME,
    "outcome": EventType.TRADE_OUTCOME,
    "recommendation": EventType.RECOMMENDATION,
    "signal": EventType.RECOMMENDATION,
    "rejection": EventType.REJECTION,
    "rejected": EventType.REJECTION,
}


class OptionsAdapter(BaseAdapter):
    """
    Adapter for NovaBotV2Options.

    Reads JSON reports, CSV exports, and log files from source_dir.
    All reads are performed on local files — no broker connection required.
    """

    SOURCE_BOT = SourceBot.NOVA_BOT_V2_OPTIONS

    def _load_from_source(self) -> None:
        assert self.source_dir is not None  # guaranteed by base.load()

        json_files = list(self.source_dir.glob("*.json"))
        csv_files = list(self.source_dir.glob("*.csv"))
        log_files = list(self.source_dir.glob("*.log"))

        logger.info(
            "OptionsAdapter: found %d JSON, %d CSV, %d log files in %s",
            len(json_files), len(csv_files), len(log_files), self.source_dir,
        )

        for path in json_files:
            self._load_json(path)
        for path in csv_files:
            self._load_csv(path)
        for path in log_files:
            self._load_log(path)

    # ── JSON loader ────────────────────────────────────────────────────────────

    def _load_json(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._record_error(f"JSON parse error in {path.name}: {e}")
            return

        records: list[dict[str, Any]] = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Support {"events": [...]} or {"trades": [...]} wrapper
            for key in ("events", "trades", "outcomes", "records"):
                if key in data and isinstance(data[key], list):
                    records = data[key]
                    break
            if not records:
                records = [data]

        for i, record in enumerate(records):
            try:
                event = self._record_to_event(record)
                if event:
                    self._add_event(event)
            except Exception as e:
                self._record_error(f"{path.name}[{i}]: {e}")

    # ── CSV loader ─────────────────────────────────────────────────────────────

    def _load_csv(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    try:
                        event = self._record_to_event(dict(row))
                        if event:
                            self._add_event(event)
                    except Exception as e:
                        self._record_error(f"{path.name} row {i + 2}: {e}")
        except Exception as e:
            self._record_error(f"CSV read error in {path.name}: {e}")

    # ── Log loader (best-effort JSON-line parsing) ─────────────────────────────

    def _load_log(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or not line.startswith("{"):
                        continue
                    try:
                        record = json.loads(line)
                        event = self._record_to_event(record)
                        if event:
                            self._add_event(event)
                    except Exception as e:
                        self._record_error(f"{path.name} line {i}: {e}")
        except Exception as e:
            self._record_error(f"Log read error in {path.name}: {e}")

    # ── Record → TacticalEvent ─────────────────────────────────────────────────

    def _record_to_event(self, record: dict[str, Any]) -> TacticalEvent | None:
        # strategy_id — try multiple field names
        strategy_id = (
            record.get("strategy_id")
            or record.get("strategy")
            or record.get("tactic")
            or record.get("trade_type")
            or "unknown"
        )

        # event_type
        raw_type = str(record.get("event_type", record.get("type", "trade_outcome"))).lower()
        event_type = _EVENT_TYPE_MAP.get(raw_type, EventType.TRADE_OUTCOME)

        # regime
        raw_regime = record.get("regime", record.get("market_regime", ""))
        regime = _REGIME_MAP.get(str(raw_regime).lower()) if raw_regime else None

        # outcome
        raw_outcome = record.get("outcome", record.get("result", ""))
        outcome = _OUTCOME_MAP.get(str(raw_outcome).lower()) if raw_outcome else None

        # numeric fields — tolerant parsing
        score = _to_float(record.get("score") or record.get("confidence"))
        expected_rr = _to_float(record.get("expected_rr") or record.get("rr") or record.get("risk_reward"))
        realized_pnl = _to_float(record.get("realized_pnl") or record.get("pnl") or record.get("profit_loss"))

        # Carry unrecognised fields into metadata
        known = {
            "strategy_id", "strategy", "tactic", "trade_type",
            "event_type", "type", "regime", "market_regime",
            "outcome", "result", "score", "confidence",
            "expected_rr", "rr", "risk_reward",
            "realized_pnl", "pnl", "profit_loss",
            "event_id", "timestamp",
        }
        metadata = {k: v for k, v in record.items() if k not in known}
        if "source_bot" in record:
            metadata["original_source_bot"] = record["source_bot"]

        return TacticalEvent(
            source_bot=self.SOURCE_BOT,
            event_type=event_type,
            strategy_id=str(strategy_id),
            regime=regime,
            score=score,
            expected_rr=expected_rr,
            realized_pnl=realized_pnl,
            outcome=outcome,
            metadata=metadata,
        )


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # A non-finite (NaN/+-Infinity, e.g. a bare ``Infinity`` parsed by json.loads
    # from an upstream record) must not leak into TacticalEvent.expected_rr /
    # realized_pnl: those are NOT range-checked at construction and would poison
    # the analytics sums (total_pnl, avg_expected_rr) downstream. Fail closed.
    if not math.isfinite(number):
        return None
    return number
