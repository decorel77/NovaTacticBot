"""Source provenance assessment for data_is_real (POST-005).

data_is_real previously became true whenever ANY source directory was passed on
the CLI, so a dummy dir full of fixture files was reported as real data. This
module derives data_is_real from trusted adapter provenance instead:

  - Generic source directories (--source-dir) are untrusted: always false.
  - The trusted NovaBotV2Options source (--nova-options-dir) may be real ONLY if
    all of the following hold:
      1. the source path exists,
      2. the expected adapter input files exist (decision audit trail),
      3. the source's own result_snapshot.json carries real-data flags
         (data_is_real true, or the REPAIR-006 portfolio_fidelity_source marker)
         and still declares broker execution disabled,
      4. the source snapshot is fresh enough (default 36h, daily cadence + slack).
  - Mixing a generic dir into a trusted run taints the event set: false.
  - Unknown stays unknown: any unreadable/missing evidence fails closed to false.

READ-ONLY and side-effect free: only existence checks and JSON reads.
No broker access, no writes, no network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

TRUSTED_SOURCE_NOVA_OPTIONS = "NovaBotV2Options"
GENERIC_SOURCE = "generic_source_dir"
MIXED_SOURCE = "NovaBotV2Options+generic_source_dir"
NO_SOURCE = "none"

# Primary adapter input proving the trusted source has actual signal data.
REQUIRED_TRUSTED_FILES = ("data/logs/decision_audit_trail.jsonl",)
SOURCE_SNAPSHOT_RELPATH = "data/system/result_snapshot.json"
DEFAULT_MAX_SOURCE_AGE_HOURS = 36.0


@dataclass(frozen=True)
class SourceProvenance:
    """Outcome of a provenance assessment: the value plus why."""

    data_is_real: bool
    input_source: str
    reasons: tuple[str, ...]


def _parse_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        ts = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def assess_nova_options_source(
    source_dir: str | Path,
    *,
    now: Optional[datetime] = None,
    max_age_hours: float = DEFAULT_MAX_SOURCE_AGE_HOURS,
) -> SourceProvenance:
    """Assess the trusted NovaBotV2Options directory. Fails closed to false."""
    root = Path(source_dir)
    if not root.is_dir():
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                (f"source dir missing: {root}",))

    missing = [rel for rel in REQUIRED_TRUSTED_FILES if not (root / rel).is_file()]
    if missing:
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                tuple(f"expected adapter input missing: {rel}" for rel in missing))

    snap_path = root / SOURCE_SNAPSHOT_RELPATH
    if not snap_path.is_file():
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                (f"source snapshot missing: {SOURCE_SNAPSHOT_RELPATH}",))
    try:
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                (f"source snapshot unreadable: {type(exc).__name__}",))
    if not isinstance(snapshot, dict):
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                ("source snapshot is not a JSON object",))

    # Advisory posture: the trusted source must still declare broker execution
    # disabled; an absent flag is unverified, not trusted.
    if snapshot.get("broker_execution_enabled") is not False:
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                ("source snapshot does not declare broker_execution_enabled false",))

    # Real-data flags: canonical data_is_real, or the REPAIR-006 marker proving
    # the snapshot carries the persisted advisory-ledger portfolio truth (the
    # plain dry-run overwrite lacks it).
    has_real_flag = (
        snapshot.get("data_is_real") is True
        or "portfolio_fidelity_source" in snapshot
    )
    if not has_real_flag:
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                ("source snapshot lacks real-data flags "
                                 "(dry-run zeros overwrite? see POST-006)",))

    produced = _parse_utc(snapshot.get("updated_at_utc") or snapshot.get("produced_at"))
    if produced is None:
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                ("source snapshot has no parseable freshness timestamp",))
    reference = now or datetime.now(timezone.utc)
    age_hours = (reference - produced).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        return SourceProvenance(False, TRUSTED_SOURCE_NOVA_OPTIONS,
                                (f"source snapshot stale: {age_hours:.1f}h old "
                                 f"(max {max_age_hours:.0f}h)",))

    return SourceProvenance(True, TRUSTED_SOURCE_NOVA_OPTIONS,
                            ("trusted NovaBotV2Options source verified: inputs present, "
                             f"real-data flags set, snapshot {age_hours:.1f}h old",))


def derive_run_provenance(
    nova_options_dir: str | Path | None,
    source_dir: str | Path | None,
    *,
    now: Optional[datetime] = None,
    max_age_hours: float = DEFAULT_MAX_SOURCE_AGE_HOURS,
) -> SourceProvenance:
    """Derive (input_source, data_is_real) for a run from its CLI sources.

    Generic input can never be real; a generic dir mixed into a trusted run
    taints the merged event set, so the run reports false as well.
    """
    if nova_options_dir and source_dir:
        trusted = assess_nova_options_source(
            nova_options_dir, now=now, max_age_hours=max_age_hours
        )
        return SourceProvenance(
            False,
            MIXED_SOURCE,
            trusted.reasons + ("generic source dir mixed in: merged events are not "
                               "purely trusted, data_is_real forced false",),
        )
    if nova_options_dir:
        return assess_nova_options_source(
            nova_options_dir, now=now, max_age_hours=max_age_hours
        )
    if source_dir:
        return SourceProvenance(
            False, GENERIC_SOURCE,
            ("generic/untrusted source dir: provenance unverifiable, data_is_real false",),
        )
    return SourceProvenance(False, NO_SOURCE, ("no source directory provided",))
