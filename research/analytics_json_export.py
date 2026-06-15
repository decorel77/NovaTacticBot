"""Research-only JSON serializer for AnalyticsResult (TACTIC-RP-002).

Pure, deterministic, ASCII-safe serialization of a ``TacticAnalyticsEngine``
``AnalyticsResult`` into a structured dict / JSON string, mirroring the fields
the Markdown report (``utils/tactic_report_generator.py``) renders. It is the
structured-export sibling of the Markdown generator.

RESEARCH / DIAGNOSTIC-ONLY. This module:

  - computes nothing new; it only serializes an already-computed
    ``AnalyticsResult`` (no analytics, no recommendations, no optimization),
  - performs no I/O during compute (it returns a dict / string; callers persist
    if and where they choose),
  - imports no broker / order / live-cycle / scheduler / network / subprocess
    module,
  - is NOT wired into ``tools/run_tacticbot.py`` or any scheduler,
  - PROPAGATES ``data_is_real`` verbatim from the caller and never invents
    realness (it defaults to ``False`` and is only ``True`` if the caller says so),
  - emits ASCII-safe JSON (``ensure_ascii=True``) so it renders on any console
    codepage and in redirected pipelines.

Placed under ``research/`` (not ``utils/``) so it is unambiguously offline,
research-only, and unwired; the original TACTIC-RP-002 card named
``utils/tactic_json_exporter.py``.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from core.tactic_analytics_engine import AnalyticsResult

SCHEMA_VERSION: str = "1.0"
RESEARCH_ONLY: bool = True
BROKER_EXECUTION: str = "disabled"


def result_to_dict(
    result: AnalyticsResult,
    *,
    data_is_real: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Serialize an ``AnalyticsResult`` into a plain JSON-safe dict.

    The returned dict has two top-level keys:

      - ``meta``: schema version + research/diagnostic provenance flags. The
        ``data_is_real`` value is taken verbatim from the caller (default
        ``False``) and is never inferred from the data.
      - ``analytics``: the full ``AnalyticsResult`` rendered via
        ``dataclasses.asdict`` (every nested field is a primitive — the
        ``Outcome``/``EventType``/``Regime`` "enums" are plain strings — so the
        output is JSON-safe without custom encoders).
    """
    if not isinstance(result, AnalyticsResult):
        raise TypeError(
            f"result_to_dict requires an AnalyticsResult, got {type(result).__name__}"
        )

    meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_only": RESEARCH_ONLY,
        "diagnostic_only": True,
        "broker_execution": BROKER_EXECUTION,
        "data_is_real": bool(data_is_real),  # propagated, never invented
    }
    if generated_at is not None:
        meta["generated_at"] = generated_at

    return {"meta": meta, "analytics": asdict(result)}


def to_json(
    result: AnalyticsResult,
    *,
    data_is_real: bool = False,
    generated_at: str | None = None,
    indent: int | None = 2,
) -> str:
    """Serialize an ``AnalyticsResult`` to a deterministic, ASCII-safe JSON string.

    ``sort_keys=True`` makes the output byte-stable for a given result, and
    ``ensure_ascii=True`` keeps it printable on any codepage (e.g. the en-dash in
    confidence-bucket labels is escaped rather than emitted raw).
    """
    return json.dumps(
        result_to_dict(result, data_is_real=data_is_real, generated_at=generated_at),
        indent=indent,
        sort_keys=True,
        ensure_ascii=True,
    )
