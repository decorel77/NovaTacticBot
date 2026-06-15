"""Research-only JSON serializer for RegimeStrategyFit (TACTIC-RA-003 export layer).

The structured-export sibling of ``research/regime_strategy_fit_report.py`` and a
mirror of ``research/analytics_json_export.py``: pure, deterministic, ASCII-safe
serialization of a ``RegimeStrategyFit`` into a dict / JSON string.

RESEARCH / DIAGNOSTIC-ONLY. This module:

  - computes nothing; it only serializes an already-built ``RegimeStrategyFit``,
  - performs no I/O during compute (returns a dict / string),
  - imports no broker / order / live-cycle / scheduler / network / subprocess
    module,
  - is NOT wired into ``tools/run_tacticbot.py`` or any scheduler,
  - REFLECTS ``data_is_real`` and ``status`` verbatim from the fit and never
    upgrades them; a withheld (below-floor) cell serializes its ``win_rate`` as
    ``null`` (``INSUFFICIENT_SAMPLE``), never a fabricated number,
  - emits ASCII-safe JSON (``ensure_ascii=True``).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from research.regime_strategy_fit import RegimeStrategyFit

SCHEMA_VERSION: str = "1.0"


def fit_to_dict(
    fit: RegimeStrategyFit,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Serialize a ``RegimeStrategyFit`` into a plain JSON-safe dict.

    The returned dict has two top-level keys:

      - ``meta``: schema version plus provenance flags reflected **verbatim** from
        the fit (``research_only``, ``diagnostic_only``, ``broker_execution``,
        ``data_is_real``, ``status``, ``min_sample``). Nothing here is invented.
      - ``fit``: the full ``RegimeStrategyFit`` via ``dataclasses.asdict`` (every
        nested value is a primitive; a withheld cell keeps ``win_rate: null``).
    """
    if not isinstance(fit, RegimeStrategyFit):
        raise TypeError(
            f"fit_to_dict requires a RegimeStrategyFit, got {type(fit).__name__}"
        )

    meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_only": fit.research_only,
        "diagnostic_only": fit.diagnostic_only,
        "broker_execution": fit.broker_execution,
        "data_is_real": bool(fit.data_is_real),  # reflected, never upgraded
        "status": fit.status,
        "min_sample": fit.min_sample,
    }
    if generated_at is not None:
        meta["generated_at"] = generated_at

    return {"meta": meta, "fit": asdict(fit)}


def to_json(
    fit: RegimeStrategyFit,
    *,
    generated_at: str | None = None,
    indent: int | None = 2,
) -> str:
    """Serialize a ``RegimeStrategyFit`` to a deterministic, ASCII-safe JSON string.

    ``sort_keys=True`` makes the output byte-stable for a given fit, and
    ``ensure_ascii=True`` keeps it printable on any codepage.
    """
    return json.dumps(
        fit_to_dict(fit, generated_at=generated_at),
        indent=indent,
        sort_keys=True,
        ensure_ascii=True,
    )
