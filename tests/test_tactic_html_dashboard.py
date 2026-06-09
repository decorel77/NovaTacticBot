"""Tests for tactic_html_dashboard.py (MASTER-015)."""
from pathlib import Path

from core.tactic_analytics_engine import AnalyticsResult, StrategyStats
from workflow.tactic_html_dashboard import TacticHtmlDashboard, render


def _make_result():
    r = AnalyticsResult()
    s = StrategyStats(strategy_id="PUT_SELL", trade_outcomes=10, wins=6)
    s.win_rate = 0.6
    r.strategy_stats["PUT_SELL"] = s
    return r


def test_render_returns_html():
    html = render(AnalyticsResult())
    assert "<!DOCTYPE html>" in html
    assert "NovaTacticBot Analytics Dashboard" in html


def test_render_contains_sections():
    html = render(_make_result())
    assert "Strategy Performance" in html
    assert "Regime Breakdown" in html
    assert "Edge Erosion" in html
    assert "Recommendation Quality" in html


def test_strategy_in_output():
    html = render(_make_result())
    assert "PUT_SELL" in html


def test_writer_creates_file(tmp_path):
    dashboard = TacticHtmlDashboard(tmp_path / "dashboard.html")
    out = dashboard.write(_make_result())
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


def test_no_broker_imports():
    import workflow.tactic_html_dashboard as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "ibapi" not in src
    assert "import broker" not in src.lower()
