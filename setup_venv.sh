#!/usr/bin/env bash
# Create the isolated, broker-FREE virtualenv for NovaTacticBot (REPAIR-011).
#
# NovaTacticBot is ADVISORY-ONLY. It must never run where a broker /
# order-execution library is importable. This script builds a local .venv from
# requirements.txt, then PROVES the env is broker-free by asserting ib_insync
# (and friends) cannot be imported. Installs only into the repo-local .venv;
# never installs globally.
#
# Usage: ./setup_venv.sh [path-to-base-python]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
BASE_PYTHON="${1:-python3}"

echo "== NovaTacticBot advisory venv setup (REPAIR-011) =="
echo "Repo:  $REPO_ROOT"
echo "Venv:  $VENV_DIR"

# 1. Create the venv (idempotent).
if [ ! -f "$VENV_DIR/pyvenv.cfg" ]; then
    echo "Creating virtualenv..."
    "$BASE_PYTHON" -m venv "$VENV_DIR"
else
    echo "Reusing existing virtualenv."
fi

# venv python lives in Scripts/ on Windows-style layouts, bin/ elsewhere.
if [ -x "$VENV_DIR/bin/python" ]; then
    VENV_PYTHON="$VENV_DIR/bin/python"
else
    VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
fi

# 2. Install ONLY this repo's pinned requirements into the venv.
echo "Installing requirements (broker-free)..."
"$VENV_PYTHON" -m pip install --upgrade pip >/dev/null
"$VENV_PYTHON" -m pip install -r "$REPO_ROOT/requirements.txt"

# 3. HARD PROOF: the advisory env must not import any broker library.
echo "Verifying broker-free guarantee..."
"$VENV_PYTHON" "$REPO_ROOT/tools/verify_broker_free.py"

echo ""
echo "Done. Run NovaTacticBot inside this venv, e.g.:"
echo "    $VENV_PYTHON tools/run_tacticbot.py --nova-options-dir C:/NovaGPT/Apps/NovaBotV2Options"
echo "    $VENV_PYTHON -m pytest -q"
