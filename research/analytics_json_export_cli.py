"""Offline, synthetic-only CLI for research/analytics_json_export.py (TACTIC-RP-002).

Loads a **synthetic** events fixture, runs the analytics engine, and prints the
JSON export to **stdout**. It:

  - writes nothing by default (stdout only),
  - never asserts realness (``data_is_real`` is always ``false``),
  - reads **no** real bot directory (there is no ``--nova-botv2-dir`` option),
  - imports no broker / order / live-cycle / scheduler / network module,
  - is **not** wired into ``tools/run_tacticbot.py`` or any scheduler,
  - **fails closed** (exit 2) on a missing/malformed/invalid fixture.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from core.tactic_analytics_engine import TacticAnalyticsEngine
from core.tactic_event import TacticalEvent
from research.analytics_json_export import to_json


def load_events_fixture(path: str | Path) -> list[TacticalEvent]:
    """Load a synthetic events fixture: a list, or ``{"events": [...]}``.

    Raises on malformed input so the CLI can fail closed; never reads a real
    runtime directory.
    """
    data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("events", []) if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise ValueError("fixture must be a list of events or {'events': [...]}")
    return [TacticalEvent.from_dict(e) for e in raw]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Offline RESEARCH-ONLY JSON analytics export (no broker, no orders, no "
            "real data). Loads a SYNTHETIC events fixture and prints JSON to stdout; "
            "data_is_real is always false."
        )
    )
    parser.add_argument("input", help="path to a synthetic events fixture JSON")
    parser.add_argument("--no-indent", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)

    try:
        events = load_events_fixture(args.input)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"[research] failed closed: cannot load fixture: {exc}", file=sys.stderr)
        return 2

    result = TacticAnalyticsEngine().run(events)
    indent = None if args.no_indent else 2
    # The CLI never asserts realness: data_is_real is always false.
    print(to_json(result, data_is_real=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
