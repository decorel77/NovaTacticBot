"""
NovaBotV2Options Real-Data Adapter — READ-ONLY

Reads the live NovaBotV2Options directory structure and converts it
into universal TacticalEvents.

Source files consumed (all read-only):
  data/logs/decision_audit_trail.jsonl   — primary signal/decision events
  data/logs/options_events.jsonl         — chain-level rejection events
  data/reports/recommendation_accuracy.json  — realized PnL cross-reference
  data/reports/strategy_performance.json     — supplementary strategy stats
  data/reports/regime_performance.json       — supplementary regime stats

No broker access. No scheduler access. No writes to NovaBotV2Options.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from adapters.base_adapter import BaseAdapter
from core.tactic_event import EventType, Outcome, Regime, SourceBot, TacticalEvent

logger = logging.getLogger(__name__)

# ── Regime mapping — NovaBotV2Options uses SIDEWAYS; contract uses NORMAL ──────

_REGIME_MAP: dict[str, str] = {
    "BULL": Regime.BULL,
    "BEAR": Regime.BEAR,
    "NORMAL": Regime.NORMAL,
    "SIDEWAYS": Regime.NORMAL,  # NovaBotV2Options term for neutral market
    "HIGH_VOL": Regime.HIGH_VOL,
    "LOW_VOL": Regime.LOW_VOL,
    "STRESSED": Regime.HIGH_VOL,
    "ELEVATED": Regime.HIGH_VOL,
}


# ── Diagnostics container ──────────────────────────────────────────────────────

@dataclass
class AdapterDiagnostics:
    """Tracks what was found, parsed, and skipped during a load."""

    source_dir: str = ""
    files_found: list[str] = field(default_factory=list)
    files_missing: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    events_parsed: int = 0
    records_skipped: int = 0
    schema_mismatches: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    source_breakdown: dict[str, int] = field(default_factory=dict)

    def record_found(self, filename: str) -> None:
        self.files_found.append(filename)

    def record_missing(self, filename: str) -> None:
        self.files_missing.append(filename)

    def record_mismatch(self, detail: str) -> None:
        self.schema_mismatches.append(detail)


# ── Adapter ────────────────────────────────────────────────────────────────────

class NovaBotV2OptionsAdapter(BaseAdapter):
    """
    Reads the real NovaBotV2Options directory and produces TacticalEvents.

    Pass source_dir pointing at the root of the NovaBotV2Options repository
    (i.e. the directory that contains data/logs/ and data/reports/).

    All file reads are performed on local copies. No network calls.
    No writes to the source directory.
    """

    SOURCE_BOT = SourceBot.NOVA_BOT_V2_OPTIONS

    # Expected files relative to source_dir
    _AUDIT_TRAIL = "data/logs/decision_audit_trail.jsonl"
    _EVENTS_LOG = "data/logs/options_events.jsonl"
    _REC_ACCURACY = "data/reports/recommendation_accuracy.json"
    _STRATEGY_PERF = "data/reports/strategy_performance.json"
    _REGIME_PERF = "data/reports/regime_performance.json"

    def __init__(self, source_dir: Optional[str | Path] = None) -> None:
        super().__init__(source_dir)
        self.diagnostics = AdapterDiagnostics(
            source_dir=str(source_dir) if source_dir else ""
        )
        # Pre-computed supplementary data loaded alongside events
        self.strategy_performance: dict[str, Any] = {}
        self.regime_performance: dict[str, Any] = {}

    def _load_from_source(self) -> None:
        assert self.source_dir is not None
        diag = self.diagnostics

        # Cross-reference: recommendation_accuracy → signal_id → realized_pnl / outcome
        rec_lookup = self._load_recommendation_accuracy(diag)

        # Primary: decision_audit_trail.jsonl
        self._load_audit_trail(diag, rec_lookup)

        # Secondary: chain-level options_events.jsonl
        self._load_options_events(diag)

        # Supplementary (not converted to events, stored for report enrichment)
        self._load_strategy_performance(diag)
        self._load_regime_performance(diag)

        diag.events_parsed = len(self._events)

    # ── Loader: recommendation accuracy cross-reference ────────────────────────

    def _load_recommendation_accuracy(
        self, diag: AdapterDiagnostics
    ) -> dict[str, dict[str, Any]]:
        """Returns a dict keyed by signal_id for PnL cross-referencing."""
        path = self.source_dir / self._REC_ACCURACY  # type: ignore[operator]
        if not path.exists():
            diag.record_missing(self._REC_ACCURACY)
            return {}
        diag.record_found(self._REC_ACCURACY)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            self._record_error(f"recommendation_accuracy.json parse error: {e}")
            diag.parse_errors.append(str(e))
            return {}
        lookup: dict[str, dict[str, Any]] = {}
        for rec in data.get("recommendations", []):
            sid = rec.get("signal_id", "")
            if sid:
                lookup[sid] = rec
        return lookup

    # ── Loader: decision_audit_trail.jsonl ─────────────────────────────────────

    def _load_audit_trail(
        self,
        diag: AdapterDiagnostics,
        rec_lookup: dict[str, dict[str, Any]],
    ) -> None:
        path = self.source_dir / self._AUDIT_TRAIL  # type: ignore[operator]
        if not path.exists():
            diag.record_missing(self._AUDIT_TRAIL)
            return
        diag.record_found(self._AUDIT_TRAIL)

        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                diag.parse_errors.append(f"audit_trail line {i}: {e}")
                diag.records_skipped += 1
                continue

            event = self._audit_record_to_event(record, rec_lookup, diag)
            if event is not None:
                self._add_event(event)
                source = "audit_trail"
                diag.source_breakdown[source] = diag.source_breakdown.get(source, 0) + 1

    def _audit_record_to_event(
        self,
        record: dict[str, Any],
        rec_lookup: dict[str, dict[str, Any]],
        diag: AdapterDiagnostics,
    ) -> Optional[TacticalEvent]:
        strategy_id = record.get("strategy_id")
        if not strategy_id:
            diag.record_mismatch(f"audit trail record missing strategy_id: {record.get('signal_id', '?')}")
            diag.records_skipped += 1
            return None

        final_decision = str(record.get("final_decision", "")).upper()
        signal_id_pre = record.get("signal_id", "")
        has_outcome = (
            signal_id_pre in rec_lookup
            and rec_lookup[signal_id_pre].get("outcome_pnl") is not None
        )

        if final_decision == "ACCEPTED" and has_outcome:
            # Paper trade completed — we have a realized PnL
            event_type = EventType.TRADE_OUTCOME
        elif final_decision == "ACCEPTED":
            # Paper position still open / pending
            event_type = EventType.RECOMMENDATION
        elif final_decision in ("REJECTED", "SKIPPED"):
            event_type = EventType.REJECTION
        else:
            event_type = EventType.RECOMMENDATION
            if final_decision:
                diag.record_mismatch(
                    f"Unknown final_decision '{final_decision}' for signal {record.get('signal_id', '?')}"
                )

        raw_regime = str(record.get("regime", "")).upper()
        regime = _REGIME_MAP.get(raw_regime)

        score = _safe_float(record.get("score"))
        rr = record.get("risk_reward_result", {})
        expected_rr = _safe_float(rr.get("risk_reward_ratio")) if rr.get("is_valid") else None

        # Cross-reference realized PnL from recommendation_accuracy
        signal_id = record.get("signal_id", "")
        realized_pnl: Optional[float] = None
        outcome: Optional[str] = None

        if signal_id and signal_id in rec_lookup:
            acc = rec_lookup[signal_id]
            realized_pnl = _safe_float(acc.get("outcome_pnl"))
            outcome_win = acc.get("outcome_win")
            if outcome_win is True:
                outcome = Outcome.WIN
            elif outcome_win is False:
                outcome = Outcome.LOSS
            elif realized_pnl is not None:
                outcome = Outcome.WIN if realized_pnl > 0 else Outcome.LOSS
        elif event_type == EventType.RECOMMENDATION:
            outcome = Outcome.PENDING

        # Carry useful NovaBotV2Options-specific fields into metadata
        metadata: dict[str, Any] = {
            "signal_id": signal_id,
            "symbol": record.get("symbol"),
            "cycle_id": record.get("cycle_id"),
            "iv_rank": record.get("iv_rank"),
            "dte": record.get("dte"),
            "delta": record.get("delta"),
            "rejection_codes": record.get("reason_codes", []),
            "human_explanation": record.get("human_explanation"),
            "advisory_only": record.get("advisory_only", True),
        }
        if raw_regime and regime is None:
            metadata["original_regime"] = raw_regime

        try:
            return TacticalEvent(
                source_bot=self.SOURCE_BOT,
                event_type=event_type,
                strategy_id=strategy_id,
                regime=regime,
                score=score,
                expected_rr=expected_rr,
                realized_pnl=realized_pnl,
                outcome=outcome,
                metadata=metadata,
            )
        except Exception as e:
            diag.parse_errors.append(f"TacticalEvent construction failed for {signal_id}: {e}")
            diag.records_skipped += 1
            return None

    # ── Loader: options_events.jsonl (chain rejections) ────────────────────────

    def _load_options_events(self, diag: AdapterDiagnostics) -> None:
        path = self.source_dir / self._EVENTS_LOG  # type: ignore[operator]
        if not path.exists():
            diag.record_missing(self._EVENTS_LOG)
            return
        diag.record_found(self._EVENTS_LOG)

        chain_reject_count = 0
        seen_contracts: set[str] = set()  # deduplicate same-contract rejections

        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                diag.parse_errors.append(f"options_events line {i}: {e}")
                diag.records_skipped += 1
                continue

            decision = str(record.get("decision", "")).upper()
            if decision != "REJECT":
                continue  # Only handle rejections from this log

            option_contract = record.get("option_contract", "")
            rejection_reason = record.get("rejection_reason", "chain_filter")
            symbol = record.get("symbol", "UNKNOWN")

            # Create one representative event per unique contract, not one per log line
            # The log has many repeat entries for the same contract on the same day
            contract_key = option_contract
            if contract_key in seen_contracts:
                diag.records_skipped += 1
                continue
            seen_contracts.add(contract_key)

            try:
                event = TacticalEvent(
                    source_bot=self.SOURCE_BOT,
                    event_type=EventType.REJECTION,
                    strategy_id=f"chain_filter_{symbol}",
                    regime=None,
                    metadata={
                        "option_contract": option_contract,
                        "symbol": symbol,
                        "rejection_reason": rejection_reason,
                        "module": record.get("module", ""),
                        "chain_level": True,
                        "raw_count_in_log": None,  # actual count tracked below
                    },
                )
                self._add_event(event)
                chain_reject_count += 1
                source = "chain_rejections"
                diag.source_breakdown[source] = diag.source_breakdown.get(source, 0) + 1
            except Exception as e:
                diag.parse_errors.append(f"Chain event construction failed: {e}")
                diag.records_skipped += 1

        # Record total raw log lines vs deduplicated
        if chain_reject_count:
            logger.info(
                "NovaBotV2OptionsAdapter: %d unique chain contracts rejected "
                "(deduplicated from options_events.jsonl)",
                chain_reject_count,
            )

    # ── Loader: supplementary strategy performance ─────────────────────────────

    def _load_strategy_performance(self, diag: AdapterDiagnostics) -> None:
        path = self.source_dir / self._STRATEGY_PERF  # type: ignore[operator]
        if not path.exists():
            diag.record_missing(self._STRATEGY_PERF)
            return
        diag.record_found(self._STRATEGY_PERF)
        try:
            self.strategy_performance = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            diag.parse_errors.append(f"strategy_performance.json: {e}")

    # ── Loader: supplementary regime performance ───────────────────────────────

    def _load_regime_performance(self, diag: AdapterDiagnostics) -> None:
        path = self.source_dir / self._REGIME_PERF  # type: ignore[operator]
        if not path.exists():
            diag.record_missing(self._REGIME_PERF)
            return
        diag.record_found(self._REGIME_PERF)
        try:
            self.regime_performance = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            diag.parse_errors.append(f"regime_performance.json: {e}")


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
