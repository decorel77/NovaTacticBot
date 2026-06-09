"""
Base adapter — all source-bot adapters inherit from this class.

Adapters are READ-ONLY. They:
  - read files from a configured source directory
  - convert native bot output into TacticalEvent objects
  - never write to source bot directories
  - never connect to brokers
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from core.tactic_event import TacticalEvent

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Abstract base for all NovaTacticBot source adapters."""

    SOURCE_BOT: str = "UNKNOWN"

    def __init__(self, source_dir: Optional[str | Path] = None) -> None:
        self.source_dir: Optional[Path] = Path(source_dir) if source_dir else None
        self._events: list[TacticalEvent] = []
        self._load_errors: list[str] = []

    # ── Public interface ───────────────────────────────────────────────────────

    def load(self) -> list[TacticalEvent]:
        """Load and return all tactical events from the source directory."""
        self._events.clear()
        self._load_errors.clear()

        if self.source_dir is None:
            logger.warning("%s: no source_dir configured — returning empty", self.__class__.__name__)
            return []

        if not self.source_dir.exists():
            logger.warning("%s: source_dir does not exist: %s", self.__class__.__name__, self.source_dir)
            return []

        self._load_from_source()
        logger.info(
            "%s: loaded %d events (%d errors)",
            self.__class__.__name__, len(self._events), len(self._load_errors),
        )
        return list(self._events)

    @property
    def load_errors(self) -> list[str]:
        return list(self._load_errors)

    # ── Abstract ───────────────────────────────────────────────────────────────

    @abstractmethod
    def _load_from_source(self) -> None:
        """
        Subclasses implement source-specific reading logic here.
        Append to self._events. Record errors in self._load_errors.
        Never write to any file. Never call broker APIs.
        """

    # ── Helpers for subclasses ─────────────────────────────────────────────────

    def _record_error(self, message: str) -> None:
        self._load_errors.append(message)
        logger.warning("%s: %s", self.__class__.__name__, message)

    def _add_event(self, event: TacticalEvent) -> None:
        self._events.append(event)
