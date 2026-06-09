"""Tests for utils/multi_source_merger.py.

Uses lightweight stub adapters to avoid touching real sibling project paths.
Verifies: event collection, deduplication, stats, error isolation, and
fail-closed behaviour.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.tactic_event import EventType, SourceBot, TacticalEvent
from utils.multi_source_merger import MergeStats, MultiSourceMerger, _event_dedup_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    source_bot: str = SourceBot.NOVA_BOT_V2_OPTIONS,
    event_type: str = EventType.TRADE_OUTCOME,
    strategy_id: str = "MOMENTUM",
    event_id: str | None = None,
    signal_id: str | None = None,
) -> TacticalEvent:
    event = TacticalEvent(
        source_bot=source_bot,
        event_type=event_type,
        strategy_id=strategy_id,
    )
    if event_id:
        object.__setattr__(event, "event_id", event_id) if hasattr(event, "__setattr__") else None
        event.event_id = event_id
    if signal_id:
        event.metadata["signal_id"] = signal_id
    return event


class _StubAdapter:
    """Minimal adapter stub that returns a fixed list of events."""

    SOURCE_BOT = SourceBot.NOVA_BOT_V2_OPTIONS

    def __init__(self, events=None, errors=None, source_bot=None):
        self._events = events or []
        self._errors = errors or []
        if source_bot:
            self.SOURCE_BOT = source_bot

    def load(self):
        return list(self._events)

    @property
    def load_errors(self):
        return list(self._errors)


class _RaisingAdapter:
    SOURCE_BOT = "RaisingBot"

    def load(self):
        raise RuntimeError("adapter exploded")

    @property
    def load_errors(self):
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMergeStats(unittest.TestCase):
    def test_summary_line(self):
        stats = MergeStats(
            sources_loaded=["A", "B"],
            total_after_dedup=10,
            duplicates_removed=2,
        )
        line = stats.summary_line()
        self.assertIn("10", line)
        self.assertIn("2 sources", line)

    def test_schema_version(self):
        self.assertEqual(MergeStats().schema_version, "1.0")


class TestEventDedupKey(unittest.TestCase):
    def test_uses_signal_id_when_present(self):
        e = _make_event(signal_id="SIG-001")
        key = _event_dedup_key(e)
        self.assertIn("SIG-001", key)

    def test_uses_event_id_when_no_signal_id(self):
        e = _make_event()
        key = _event_dedup_key(e)
        self.assertIn(e.event_id, key)

    def test_key_includes_source_bot_for_signal_id(self):
        e = _make_event(signal_id="SIG-999")
        key = _event_dedup_key(e)
        self.assertIn(e.source_bot, key)


class TestMultiSourceMerger(unittest.TestCase):
    def _merger_with_adapters(self, adapters):
        merger = MultiSourceMerger()
        merger._build_adapters = lambda: adapters
        return merger

    def test_empty_adapters_returns_empty_list(self):
        merger = self._merger_with_adapters([])
        events, stats = merger.merge()
        self.assertEqual(events, [])
        self.assertEqual(stats.total_after_dedup, 0)

    def test_single_adapter_events_returned(self):
        e1 = _make_event()
        e2 = _make_event()
        merger = self._merger_with_adapters([_StubAdapter([e1, e2])])
        events, stats = merger.merge()
        self.assertEqual(len(events), 2)

    def test_two_adapters_events_merged(self):
        e1 = _make_event(source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        e2 = _make_event(source_bot=SourceBot.NOVA_BOT_V2)
        a1 = _StubAdapter([e1], source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        a2 = _StubAdapter([e2], source_bot=SourceBot.NOVA_BOT_V2)
        merger = self._merger_with_adapters([a1, a2])
        events, stats = merger.merge()
        self.assertEqual(len(events), 2)
        self.assertEqual(stats.total_before_dedup, 2)

    def test_duplicate_signal_ids_removed(self):
        e1 = _make_event(signal_id="SIG-001", source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        e2 = _make_event(signal_id="SIG-001", source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        a = _StubAdapter([e1, e2], source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        merger = self._merger_with_adapters([a])
        events, stats = merger.merge()
        self.assertEqual(len(events), 1)
        self.assertEqual(stats.duplicates_removed, 1)

    def test_different_sources_same_signal_id_not_deduped(self):
        e1 = _make_event(signal_id="SIG-001", source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        e2 = _make_event(signal_id="SIG-001", source_bot=SourceBot.NOVA_BOT_V2)
        a1 = _StubAdapter([e1], source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        a2 = _StubAdapter([e2], source_bot=SourceBot.NOVA_BOT_V2)
        merger = self._merger_with_adapters([a1, a2])
        events, stats = merger.merge()
        # Different source bots → different keys → no dedup
        self.assertEqual(len(events), 2)

    def test_sources_listed_in_stats(self):
        a1 = _StubAdapter(source_bot="BotA")
        a2 = _StubAdapter(source_bot="BotB")
        merger = self._merger_with_adapters([a1, a2])
        _, stats = merger.merge()
        self.assertIn("BotA", stats.sources_loaded)
        self.assertIn("BotB", stats.sources_loaded)

    def test_events_per_source_counted(self):
        e1 = _make_event()
        e2 = _make_event()
        a = _StubAdapter([e1, e2], source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        merger = self._merger_with_adapters([a])
        _, stats = merger.merge()
        self.assertEqual(stats.events_per_source[SourceBot.NOVA_BOT_V2_OPTIONS], 2)

    def test_load_errors_captured_in_stats(self):
        a = _StubAdapter(errors=["read error"], source_bot="BotX")
        merger = self._merger_with_adapters([a])
        _, stats = merger.merge()
        self.assertIn("BotX", stats.load_errors)
        self.assertIn("read error", stats.load_errors["BotX"])

    def test_raising_adapter_does_not_propagate(self):
        merger = self._merger_with_adapters([_RaisingAdapter()])
        events, stats = merger.merge()
        self.assertEqual(events, [])
        self.assertIn("RaisingBot", stats.load_errors)

    def test_stats_before_dedup_correct(self):
        events = [_make_event() for _ in range(5)]
        a = _StubAdapter(events, source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        merger = self._merger_with_adapters([a])
        _, stats = merger.merge()
        self.assertEqual(stats.total_before_dedup, 5)

    def test_no_duplicates_leaves_all_events(self):
        events = [_make_event() for _ in range(4)]
        a = _StubAdapter(events, source_bot=SourceBot.NOVA_BOT_V2_OPTIONS)
        merger = self._merger_with_adapters([a])
        result, stats = merger.merge()
        self.assertEqual(stats.duplicates_removed, 0)
        self.assertEqual(len(result), 4)


class TestNoBrokerImports(unittest.TestCase):
    def test_no_broker_imports_in_merger(self):
        import ast, pathlib
        src = pathlib.Path(__file__).parent.parent / "utils" / "multi_source_merger.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        broker_modules = {"ib_insync", "ibapi", "TWS"}
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        self.assertFalse(imports & broker_modules)


if __name__ == "__main__":
    unittest.main()
