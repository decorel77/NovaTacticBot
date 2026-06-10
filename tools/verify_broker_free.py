"""Assert the current interpreter is broker-free (REPAIR-011).

NovaTacticBot is advisory-only and must run in an environment where no broker /
order-execution library can be imported. This script is the operational proof:
it exits 0 when the environment is clean and exits 1 (listing offenders) when any
banned broker package is importable.

Used by setup_venv.ps1 / setup_venv.sh after building the isolated venv, and
runnable on its own:

    .venv/Scripts/python.exe tools/verify_broker_free.py
"""

from __future__ import annotations

import importlib.util
import sys

# Mirrors utils.guardrails._BANNED_PACKAGES (kept in sync deliberately; this
# script must stay dependency-free so it can run before the package is importable).
BANNED_PACKAGES: list[str] = [
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


def find_broker_packages() -> list[str]:
    return [p for p in BANNED_PACKAGES if importlib.util.find_spec(p) is not None]


def main() -> int:
    found = find_broker_packages()
    if found:
        sys.stderr.write(
            "BROKER LIB PRESENT IN ADVISORY ENV: "
            + ", ".join(found)
            + "\nNovaTacticBot must run in a broker-free virtualenv.\n"
        )
        return 1
    sys.stdout.write("OK: advisory environment is broker-free\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
