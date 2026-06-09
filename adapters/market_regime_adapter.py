"""
MarketRegimeBot Read-Only Adapter for NovaTacticBot.

Reads MarketRegimeBot's data/system/regime_export.json (schema regime_export.v1)
and converts the regime classification into a TacticalEvent of type REGIME_CHANGE.

Fields consumed:
  market_regime, confidence, risk_level, volatility_env,
  input_source, generated_at, reason, dry_run

Mapping to TacticalEvent contract v1.0:
  source_bot    = SourceBot.MARKET_REGIME_BOT
  event_type    = EventType.REGIME_CHANGE
  strategy_id   = "regime_{market_regime.lower()}"
  regime        = market_regime (via Regime.* constants)
  score         = confidence / 100.0
  metadata      = all export fields for downstream analytics

Falls closed: any missing file, bad schema, or parse error → empty list.
No broker imports. No writes. ADVISORY_ONLY.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from adapters.base_adapter import BaseAdapter
from core.tactic_event import EventType, SourceBot, TacticalEvent

logger = logging.getLogger(__name__)

_NOVA_ROOT = Path(__file__).resolve().parents[3]  # C:\NovaGPT

DEFAULT_SOURCE_DIR = _NOVA_ROOT / "Apps" / "MarketRegimeBot" / "data" / "system"
_EXPORT_FILE = "regime_export.json"
_SNAPSHOT_FILE = "result_snapshot.json"  # fallback if export not present

MAX_EXPORT_BYTES = 65536
EXPECTED_SCHEMA_VERSION = "regime_export.v1"

# Valid market_regime values from regime_export schema
_VALID_REGIMES = frozenset({
    "BULL", "BEAR", "SIDEWAYS", "HIGH_VOLATILITY",
    "RISK_ON", "RISK_OFF", "UNKNOWN",
})

# Allowlist: only these resolved paths may be read
ALLOWED_SOURCE_DIRS = frozenset({
    DEFAULT_SOURCE_DIR.resolve(),
})


def _map_regime(market_regime: str) -> Optional[str]:
    """Map a MarketRegimeBot regime string to a TacticalEvent Regime constant."""
    mapping = {
        "BULL": "BULL",
        "BEAR": "BEAR",
        "SIDEWAYS": "NORMAL",
        "HIGH_VOLATILITY": "HIGH_VOL",
        "RISK_ON": "BULL",
        "RISK_OFF": "BEAR",
        "UNKNOWN": "UNKNOWN",
    }
    return mapping.get(market_regime, "UNKNOWN")


class MarketRegimeBotAdapter(BaseAdapter):
    """Read-only adapter for MarketRegimeBot regime_export.json."""

    SOURCE_BOT = SourceBot.MARKET_REGIME_BOT

    def __init__(
        self,
        source_dir: Optional[str | Path] = None,
        *,
        allowed_dirs: Optional[frozenset] = None,
    ) -> None:
        super().__init__(source_dir or DEFAULT_SOURCE_DIR)
        self._allowed_dirs = allowed_dirs if allowed_dirs is not None else ALLOWED_SOURCE_DIRS

    def _load_from_source(self) -> None:
        resolved_dir = self.source_dir.resolve()

        # Allowlist check
        if resolved_dir not in self._allowed_dirs:
            self._record_error(
                f"MarketRegimeBot source dir not on allowlist: {resolved_dir}"
            )
            return

        # Prefer regime_export.json; fall back to result_snapshot.json
        export_path = self.source_dir / _EXPORT_FILE
        snapshot_path = self.source_dir / _SNAPSHOT_FILE

        if export_path.exists():
            self._load_export(export_path)
        elif snapshot_path.exists():
            self._load_legacy_snapshot(snapshot_path)
        else:
            self._record_error(
                f"MarketRegimeBot: neither {_EXPORT_FILE} nor {_SNAPSHOT_FILE} found in {self.source_dir}"
            )

    def _load_export(self, export_path: Path) -> None:
        """Load from regime_export.json (schema regime_export.v1)."""
        try:
            size = export_path.stat().st_size
        except OSError as exc:
            self._record_error(f"Cannot stat regime_export.json: {exc}")
            return

        if size > MAX_EXPORT_BYTES:
            self._record_error(
                f"regime_export.json too large ({size} > {MAX_EXPORT_BYTES})"
            )
            return

        try:
            payload: dict[str, Any] = json.loads(
                export_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            self._record_error(f"regime_export.json invalid JSON: {exc}")
            return
        except OSError as exc:
            self._record_error(f"regime_export.json unreadable: {exc}")
            return

        if not isinstance(payload, dict):
            self._record_error("regime_export.json is not a JSON object")
            return

        # Schema version check (warn, not fail)
        schema = payload.get("schema_version", "")
        if schema != EXPECTED_SCHEMA_VERSION:
            logger.warning(
                "MarketRegimeBotAdapter: unexpected schema_version %r (expected %r)",
                schema, EXPECTED_SCHEMA_VERSION,
            )

        event = self._event_from_export(payload, str(export_path))
        if event is not None:
            self._add_event(event)

    def _load_legacy_snapshot(self, snapshot_path: Path) -> None:
        """Load from result_snapshot.json when regime_export.json is absent."""
        try:
            size = snapshot_path.stat().st_size
        except OSError as exc:
            self._record_error(f"Cannot stat result_snapshot.json: {exc}")
            return

        if size > MAX_EXPORT_BYTES:
            self._record_error(
                f"result_snapshot.json too large ({size} > {MAX_EXPORT_BYTES})"
            )
            return

        try:
            payload: dict[str, Any] = json.loads(
                snapshot_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError) as exc:
            self._record_error(f"result_snapshot.json unreadable: {exc}")
            return

        if not isinstance(payload, dict):
            self._record_error("result_snapshot.json is not a JSON object")
            return

        # Map result_snapshot schema to the same event builder
        mapped = {
            "market_regime": payload.get("market_regime", "UNKNOWN"),
            "confidence": payload.get("confidence", 0),
            "risk_level": payload.get("risk_level", "UNKNOWN"),
            "volatility_env": payload.get("volatility_env", "UNKNOWN"),
            "input_source": payload.get("input_source", "result_snapshot"),
            "reason": payload.get("reason", []),
            "generated_at": "",
        }
        event = self._event_from_export(mapped, str(snapshot_path))
        if event is not None:
            self._add_event(event)

    def _event_from_export(
        self, payload: dict[str, Any], source_file: str
    ) -> Optional[TacticalEvent]:
        """Convert a regime export payload to a TacticalEvent."""
        market_regime = str(payload.get("market_regime") or "UNKNOWN").upper()
        if market_regime not in _VALID_REGIMES:
            market_regime = "UNKNOWN"

        confidence_raw = payload.get("confidence", 0)
        try:
            confidence = int(confidence_raw)
            confidence = max(0, min(100, confidence))
        except (TypeError, ValueError):
            confidence = 0

        score = round(confidence / 100.0, 4)
        risk_level = str(payload.get("risk_level") or "UNKNOWN")
        volatility_env = str(payload.get("volatility_env") or "UNKNOWN")
        input_source = str(payload.get("input_source") or "unknown")
        generated_at = str(payload.get("generated_at") or "")
        reason = list(payload.get("reason") or [])

        mapped_regime = _map_regime(market_regime)
        strategy_id = f"regime_{market_regime.lower()}"

        metadata: dict[str, Any] = {
            "market_regime": market_regime,
            "confidence": confidence,
            "risk_level": risk_level,
            "volatility_env": volatility_env,
            "input_source": input_source,
            "generated_at": generated_at,
            "reason": reason,
            "source_file": source_file,
            "dry_run": payload.get("dry_run", True),
            "read_only": True,
            "report_only": True,
        }

        try:
            return TacticalEvent(
                source_bot=self.SOURCE_BOT,
                event_type=EventType.REGIME_CHANGE,
                strategy_id=strategy_id,
                regime=mapped_regime,
                score=score,
                metadata=metadata,
            )
        except Exception as exc:
            self._record_error(
                f"Failed to build TacticalEvent from MarketRegimeBot export: {exc}"
            )
            return None
