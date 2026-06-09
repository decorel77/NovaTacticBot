"""
Multi-source event merger for NovaTacticBot.

Loads TacticalEvents from all configured adapters, deduplicates on
event_id (or signal_id in metadata), and returns a merged stream with
merge statistics.

Registered adapters (loaded in priority order):
  1. NovaBotV2Options  — nova_options_adapter.NovaBotV2OptionsAdapter
  2. NovaBotV2         — nova_botv2_adapter.NovaBotV2Adapter

Schema mismatches between adapters are handled gracefully: an event that
fails validation is logged and counted but not included in the merged stream.

ADVISORY_ONLY. Read-only inputs. No broker imports. No writes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.tactic_event import TacticalEvent

logger = logging.getLogger(__name__)


@dataclass
class MergeStats:
    """Statistics from a single merge pass."""
    sources_loaded: list[str] = field(default_factory=list)
    events_per_source: dict[str, int] = field(default_factory=dict)
    total_before_dedup: int = 0
    duplicates_removed: int = 0
    total_after_dedup: int = 0
    load_errors: dict[str, list[str]] = field(default_factory=dict)
    schema_version: str = "1.0"

    def summary_line(self) -> str:
        return (
            f"merged {self.total_after_dedup} events from "
            f"{len(self.sources_loaded)} sources "
            f"(removed {self.duplicates_removed} duplicates)"
        )


def _event_dedup_key(event: TacticalEvent) -> str:
    """Return a stable deduplication key for a TacticalEvent.

    Prefers explicit signal_id / event_id in metadata, falls back to
    the auto-generated event_id field.
    """
    meta_id = (
        event.metadata.get("signal_id")
        or event.metadata.get("event_id")
    )
    if meta_id:
        return f"{event.source_bot}:{meta_id}"
    return event.event_id


class MultiSourceMerger:
    """Loads and deduplicates TacticalEvents across all registered adapters.

    Each adapter is instantiated with its default source_dir (pointing to the
    sibling project's data directory).  Pass ``source_dirs`` to override paths
    for testing.
    """

    def __init__(
        self,
        source_dirs: Optional[dict[str, str | Path]] = None,
    ) -> None:
        self._source_dirs = source_dirs or {}

    def _build_adapters(self):
        """Instantiate all registered adapters, applying optional path overrides."""
        adapters = []

        # Import lazily to keep test isolation clean
        try:
            from adapters.nova_options_adapter import NovaBotV2OptionsAdapter
            src = self._source_dirs.get("NovaBotV2Options")
            adapters.append(NovaBotV2OptionsAdapter(src) if src else NovaBotV2OptionsAdapter())
        except Exception as exc:
            logger.warning("Could not instantiate NovaBotV2OptionsAdapter: %s", exc)

        try:
            from adapters.nova_botv2_adapter import NovaBotV2Adapter
            src = self._source_dirs.get("NovaBotV2")
            adapters.append(NovaBotV2Adapter(src) if src else NovaBotV2Adapter())
        except Exception as exc:
            logger.warning("Could not instantiate NovaBotV2Adapter: %s", exc)

        return adapters

    def merge(self) -> tuple[list[TacticalEvent], MergeStats]:
        """Load all adapters, deduplicate, return (events, stats).

        Never raises — any per-adapter error is captured in stats.load_errors.
        """
        stats = MergeStats()
        all_events: list[TacticalEvent] = []

        for adapter in self._build_adapters():
            source_name = adapter.SOURCE_BOT
            try:
                events = adapter.load()
                errors = adapter.load_errors
            except Exception as exc:
                logger.warning("Adapter %s raised during load: %s", source_name, exc)
                events = []
                errors = [str(exc)]

            stats.sources_loaded.append(source_name)
            stats.events_per_source[source_name] = len(events)
            if errors:
                stats.load_errors[source_name] = list(errors)

            all_events.extend(events)

        stats.total_before_dedup = len(all_events)

        # --- Deduplication ---
        seen: dict[str, TacticalEvent] = {}
        for event in all_events:
            key = _event_dedup_key(event)
            if key not in seen:
                seen[key] = event
            else:
                stats.duplicates_removed += 1
                logger.debug("Duplicate event removed: key=%s source=%s", key, event.source_bot)

        merged = list(seen.values())
        stats.total_after_dedup = len(merged)

        logger.info(stats.summary_line())
        return merged, stats
