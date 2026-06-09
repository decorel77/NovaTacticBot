"""Tests for AnalyticsBaselineWriter (TACTIC-HA-004)."""
import json
from pathlib import Path

import pytest

from core.tactic_event import EventType, Outcome, TacticalEvent
from core.tactic_analytics_engine import TacticAnalyticsEngine
from utils.analytics_baseline_writer import (
    AnalyticsBaselineWriter,
    BaselineSnapshot,
    snapshot_from_result,
)


def _make_event(strategy_id: str, outcome: str, regime: str = "BULL") -> TacticalEvent:
    return TacticalEvent(
        event_id=f"e-{strategy_id}-{outcome}",
        event_type=EventType.TRADE_OUTCOME,
        source_bot="test",
        strategy_id=strategy_id,
        outcome=outcome,
        regime=regime,
        realized_pnl=1.0 if outcome == Outcome.WIN else -1.0,
    )


@pytest.fixture()
def tmp_file(tmp_path: Path) -> Path:
    return tmp_path / "analytics_baseline.json"


@pytest.fixture()
def simple_result():
    events = [
        _make_event("strat_a", Outcome.WIN),
        _make_event("strat_a", Outcome.WIN),
        _make_event("strat_a", Outcome.LOSS),
        _make_event("strat_b", Outcome.WIN, regime="BEAR"),
    ]

    return TacticAnalyticsEngine().run(events)


def test_append_creates_file(tmp_file: Path, simple_result) -> None:
    writer = AnalyticsBaselineWriter(baseline_file=tmp_file)
    writer.append(snapshot_from_result(simple_result))
    assert tmp_file.exists()


def test_append_stores_list(tmp_file: Path, simple_result) -> None:
    writer = AnalyticsBaselineWriter(baseline_file=tmp_file)
    writer.append(snapshot_from_result(simple_result))
    data = json.loads(tmp_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1


def test_multiple_appends(tmp_file: Path, simple_result) -> None:
    writer = AnalyticsBaselineWriter(baseline_file=tmp_file)
    writer.append(snapshot_from_result(simple_result))
    writer.append(snapshot_from_result(simple_result))
    assert len(writer.read_all()) == 2


def test_overall_win_rate(tmp_file: Path, simple_result) -> None:
    snap = snapshot_from_result(simple_result)
    assert snap.overall_win_rate == pytest.approx(3 / 4)


def test_strategy_win_rates(tmp_file: Path, simple_result) -> None:
    snap = snapshot_from_result(simple_result)
    assert snap.strategy_win_rates["strat_a"] == pytest.approx(2 / 3)
    assert snap.strategy_win_rates["strat_b"] == pytest.approx(1.0)


def test_regime_distribution(tmp_file: Path, simple_result) -> None:
    snap = snapshot_from_result(simple_result)
    assert "BULL" in snap.regime_distribution
    assert "BEAR" in snap.regime_distribution


def test_schema_version(tmp_file: Path, simple_result) -> None:
    writer = AnalyticsBaselineWriter(baseline_file=tmp_file)
    writer.append(snapshot_from_result(simple_result))
    data = writer.read_all()[0]
    assert data["schema_version"] == "1.0"


def test_latest_returns_last(tmp_file: Path, simple_result) -> None:
    writer = AnalyticsBaselineWriter(baseline_file=tmp_file)
    snap1 = snapshot_from_result(simple_result, run_id="run-001")
    snap2 = snapshot_from_result(simple_result, run_id="run-002")
    writer.append(snap1)
    writer.append(snap2)
    assert writer.latest()["run_id"] == "run-002"


def test_latest_none_when_empty(tmp_file: Path) -> None:
    writer = AnalyticsBaselineWriter(baseline_file=tmp_file)
    assert writer.latest() is None


def test_no_broker_imports() -> None:
    import importlib
    mod = importlib.import_module("utils.analytics_baseline_writer")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "ib_insync" not in src
    assert "ibapi" not in src
