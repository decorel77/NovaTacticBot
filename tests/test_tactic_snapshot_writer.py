"""Tests for tactic_snapshot_writer.py (MASTER-021)."""
import json
from pathlib import Path

import pytest

from core.tactic_analytics_engine import AnalyticsResult, EdgeErosionWarning, RecommendationQuality
from utils.tactic_snapshot_writer import (
    TacticSnapshot,
    TacticSnapshotWriter,
    snapshot_from_result,
)


def _make_result() -> AnalyticsResult:
    from core.tactic_analytics_engine import StrategyStats, RegimeStats
    r = AnalyticsResult()
    s = StrategyStats(strategy_id="PUT_SELL")
    s.trade_outcomes = 10
    s.wins = 7
    s.win_rate = 0.7
    r.strategy_stats["PUT_SELL"] = s
    reg = RegimeStats(regime="BULL")
    reg.trade_outcomes = 8
    r.regime_stats["BULL"] = reg
    r.data_quality.total_events = 20
    r.recommendation_quality.avg_score = 0.65
    return r


def test_snapshot_from_result_ok():
    result = _make_result()
    snap = snapshot_from_result(result)
    assert snap.status == "OK"
    assert snap.event_count == 20
    assert snap.top_strategy == "PUT_SELL"
    assert snap.top_regime_fit == "BULL"
    assert snap.recommendation_quality_score == pytest.approx(0.65)


def test_snapshot_from_result_empty():
    snap = snapshot_from_result(AnalyticsResult())
    assert snap.status == "EMPTY"
    assert snap.event_count == 0


def test_edge_erosion_captured():
    r = _make_result()
    r.edge_erosion.warnings.append(
        EdgeErosionWarning(strategy_id="PUT_SELL", baseline_win_rate=0.7, rolling_win_rate=0.5, drop_pp=0.2)
    )
    snap = snapshot_from_result(r)
    assert "PUT_SELL" in snap.edge_erosion_warnings


def test_writer_roundtrip(tmp_path):
    snap = TacticSnapshot(event_count=5, top_strategy="X")
    writer = TacticSnapshotWriter(tmp_path / "result_snapshot.json")
    writer.write(snap)
    data = writer.read()
    assert data is not None
    assert data["event_count"] == 5
    assert data["top_strategy"] == "X"
    assert data["schema_version"] == "1.0"
    assert data["phase"] == "ANALYTICS"


def test_no_broker_imports():
    import utils.tactic_snapshot_writer as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "ibapi" not in src
    assert "import broker" not in src.lower()
