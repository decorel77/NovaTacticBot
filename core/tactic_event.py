"""
Universal Tactical Event — the single data type that flows through TacticBot.
All adapters produce lists of TacticalEvent. All analytics consume them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utcnow() -> datetime:
    """Naive UTC 'now' — behaviour-identical to the deprecated ``datetime.utcnow()``
    (scheduled for removal), but without the deprecation warning. Kept naive so the
    serialized ``timestamp`` isoformat contract is byte-identical (no ``+00:00``)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Enumerations (plain strings to avoid import friction across bots) ──────────

class SourceBot:
    NOVA_BOT_V2 = "NovaBotV2"
    NOVA_BOT_V2_OPTIONS = "NovaBotV2Options"
    MARKET_REGIME_BOT = "MarketRegimeBot"
    NOVA_ALLOCATION_BOT = "NovaAllocationBot"
    NOVA_BRIDGE = "NovaBridge"
    UNKNOWN = "UNKNOWN"


class EventType:
    TRADE_OUTCOME = "TRADE_OUTCOME"
    RECOMMENDATION = "RECOMMENDATION"
    REJECTION = "REJECTION"
    REGIME_CHANGE = "REGIME_CHANGE"
    ALLOCATION_CHANGE = "ALLOCATION_CHANGE"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class Regime:
    BULL = "BULL"
    BEAR = "BEAR"
    NORMAL = "NORMAL"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"
    UNKNOWN = "UNKNOWN"


class Outcome:
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    PARTIAL = "PARTIAL"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class TacticalEvent:
    """Universal tactical event — contract version 1.0."""

    source_bot: str
    event_type: str
    strategy_id: str

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=_utcnow)

    regime: Optional[str] = None
    score: Optional[float] = None          # 0.0 – 1.0
    expected_rr: Optional[float] = None
    realized_pnl: Optional[float] = None
    outcome: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    CONTRACT_VERSION: str = field(default="1.0", init=False, repr=False)

    # ── Validation ─────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if not self.source_bot:
            raise ValueError("source_bot is required")
        if not self.event_type:
            raise ValueError("event_type is required")
        if not self.strategy_id:
            raise ValueError("strategy_id is required")
        if self.score is not None and not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be in [0.0, 1.0], got {self.score}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def is_trade_outcome(self) -> bool:
        return self.event_type == EventType.TRADE_OUTCOME

    def is_rejection(self) -> bool:
        return self.event_type == EventType.REJECTION

    def is_win(self) -> bool:
        return self.outcome == Outcome.WIN

    def is_loss(self) -> bool:
        return self.outcome == Outcome.LOSS

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source_bot": self.source_bot,
            "event_type": self.event_type,
            "strategy_id": self.strategy_id,
            "regime": self.regime,
            "score": self.score,
            "expected_rr": self.expected_rr,
            "realized_pnl": self.realized_pnl,
            "outcome": self.outcome,
            "metadata": self.metadata,
            "contract_version": self.CONTRACT_VERSION,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TacticalEvent":
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=ts or _utcnow(),
            source_bot=data["source_bot"],
            event_type=data["event_type"],
            strategy_id=data["strategy_id"],
            regime=data.get("regime"),
            score=data.get("score"),
            expected_rr=data.get("expected_rr"),
            realized_pnl=data.get("realized_pnl"),
            outcome=data.get("outcome"),
            metadata=data.get("metadata", {}),
        )
