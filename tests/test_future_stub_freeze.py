"""REPAIR-012 — freeze invariants for the NovaTacticBot future-ecosystem bot stubs.

LoggingBot / ResearchBot / NewsBot / MacroBot / TaxBot are planning-only stubs
(NOVA_FUTURE_BOTS_ASSESSMENT.md: DO NOT BUILD YET). These tests lock them so they
cannot accidentally look executable, dispatchable, or integrated before a deliberate
human promotion. The frozen set is pinned exactly: promotion requires editing BOTH
the task queue AND this test in the same change.
"""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_QUEUE_PATH = PROJECT_ROOT / "data" / "system" / "task_queue.json"
ADAPTERS_DIR = PROJECT_ROOT / "adapters"

# The exact set of frozen future-ecosystem bot stubs (REPAIR-012).
EXPECTED_FROZEN_IDS = frozenset(
    {
        "TACTIC-FUTURE-001",  # LoggingBot
        "TACTIC-FUTURE-002",  # ResearchBot
        "TACTIC-FUTURE-003",  # NewsBot
        "TACTIC-FUTURE-004",  # MacroBot
        "TACTIC-FUTURE-005",  # TaxBot
    }
)
FROZEN_PHASE = "FUTURE_ECOSYSTEM"
# Substrings that would indicate a (premature) adapter/module for a frozen bot.
FUTURE_BOT_KEYWORDS = ("logging", "research", "news", "macro", "tax")


def _load_tasks():
    return json.loads(TASK_QUEUE_PATH.read_text(encoding="utf-8"))


def _frozen():
    return [t for t in _load_tasks() if t.get("frozen") is True]


def test_frozen_set_is_exactly_the_future_ecosystem_stubs():
    """The frozen set is pinned. Promotion must be a deliberate, reviewed edit."""
    actual = {t["id"] for t in _frozen()}
    assert actual == set(EXPECTED_FROZEN_IDS)


def test_every_future_ecosystem_task_is_frozen():
    """A newly-added future-bot stub cannot slip into the queue unfrozen."""
    for t in _load_tasks():
        if t.get("phase") == FROZEN_PHASE:
            assert t.get("frozen") is True, f"{t['id']} unfrozen"
            assert t["id"] in EXPECTED_FROZEN_IDS


@pytest.mark.parametrize("task_id", sorted(EXPECTED_FROZEN_IDS))
def test_frozen_task_carries_explicit_non_dispatch_attributes(task_id):
    task = {t["id"]: t for t in _load_tasks()}[task_id]
    assert str(task["status"]).upper() == "FUTURE"
    assert task.get("allowed_under_current_architecture") is False
    assert task.get("broker_execution") is False
    assert task.get("runtime_effect") is False
    fz = task.get("freeze")
    assert isinstance(fz, dict)
    assert fz.get("classification") == "future"
    assert fz.get("dispatchable") is False
    assert fz.get("executable") is False
    assert fz.get("broker_access") is False
    assert fz.get("live_trading") is False
    assert fz.get("human_promotion_required") is True
    assert "NOVA_FUTURE_BOTS_ASSESSMENT.md" in str(fz.get("assessment_ref"))
    assert str(fz.get("promotion_note")).strip()


def test_frozen_tasks_never_actionable():
    """Frozen => never TODO/DONE; cannot enter the actionable/done counts."""
    actionable = {"TODO", "DONE", "IN_PROGRESS"}
    for t in _frozen():
        assert str(t["status"]).upper() not in actionable


def test_no_adapter_or_module_exists_for_a_frozen_future_bot():
    """Non-executable: no source adapter exists for any frozen future bot."""
    existing = [p.name.lower() for p in ADAPTERS_DIR.glob("*.py")]
    for name in existing:
        for kw in FUTURE_BOT_KEYWORDS:
            assert kw not in name, f"unexpected future-bot adapter present: {name}"
