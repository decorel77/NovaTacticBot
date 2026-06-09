"""
Guardrail enforcement module.

Called at startup by run_tacticbot.py to verify no banned packages
are importable from the current Python environment path.

ADVISORY_ONLY = True is the permanent state of NovaTacticBot.
"""

from __future__ import annotations

import importlib.util
import logging
import sys

logger = logging.getLogger(__name__)

ADVISORY_ONLY: bool = True

# Packages that must never be importable in a TacticBot process
_BANNED_PACKAGES: list[str] = [
    "ib_insync",
    "ibapi",
    "alpaca_trade_api",
    "alpaca",
    "ccxt",
    "robin_stocks",
    "tastytrade",
    "tda",
    "schwab",
]

# Modules that TacticBot code must never import
_BANNED_MODULES: list[str] = [
    "socket",       # no network connections
    "subprocess",   # no shell execution
    "os.system",    # no shell execution
    "ftplib",
    "smtplib",
    "imaplib",
]


class GuardrailViolation(RuntimeError):
    """Raised when a hard guardrail is violated."""


def check_broker_imports() -> None:
    """Raise GuardrailViolation if any banned broker package is importable."""
    violations: list[str] = []
    for package in _BANNED_PACKAGES:
        spec = importlib.util.find_spec(package)
        if spec is not None:
            violations.append(package)
    if violations:
        raise GuardrailViolation(
            f"GUARDRAIL VIOLATION — banned broker packages found in environment: "
            f"{violations}. NovaTacticBot must not run in an environment with "
            f"broker access. Remove these packages or use a clean virtualenv."
        )
    logger.info("Guardrail check passed — no broker packages detected.")


def assert_advisory_only() -> None:
    """Log confirmation that ADVISORY_ONLY mode is active."""
    if not ADVISORY_ONLY:
        raise GuardrailViolation("ADVISORY_ONLY has been set to False. This is not permitted.")
    logger.info("ADVISORY_ONLY = True confirmed.")


def run_all_checks() -> None:
    """Run all guardrail checks. Call once at startup."""
    assert_advisory_only()
    check_broker_imports()
    logger.info("All guardrail checks passed.")
