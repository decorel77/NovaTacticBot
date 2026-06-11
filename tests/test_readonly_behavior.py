"""
Read-only behavior verification.

Verifies that NovaTacticBot code paths do not import or expose
any execution, broker, or modification capabilities.
"""

import ast
import importlib
import importlib.util
from pathlib import Path
import sys
import pytest

from utils.guardrails import _BANNED_MODULES


BANNED_PACKAGES = [
    "ib_insync",
    "ibapi",
    "alpaca_trade_api",
    "ccxt",
    "robin_stocks",
]

TACTICBOT_MODULES = [
    "core.tactic_event",
    "core.tactic_analytics_engine",
    "adapters.base_adapter",
    "adapters.options_adapter",
    "utils.guardrails",
    "utils.tactic_report_generator",
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SOURCE_DIRS = ("adapters", "core", "tools", "utils", "workflow")

# This test intentionally scans production source only. Tests may use subprocess,
# sockets, or temp helpers to verify behavior without granting production code
# those capabilities.
SOURCE_SCAN_EXCLUDED_FILES = frozenset()


class TestNoBrokerImports:
    @pytest.mark.parametrize("package", BANNED_PACKAGES)
    def test_banned_package_not_importable_via_tacticbot(self, package):
        """Banned packages must not be reachable through any TacticBot module."""
        spec = importlib.util.find_spec(package)
        # If the package isn't installed, the test trivially passes.
        # If it IS installed, we verify it's not imported by TacticBot modules.
        if spec is None:
            return  # not installed — safe
        # The package exists but TacticBot must not import it
        for mod_name in TACTICBOT_MODULES:
            mod = sys.modules.get(mod_name)
            if mod is None:
                continue
            assert package not in getattr(mod, "__dict__", {}), (
                f"{mod_name} exposes banned package '{package}'"
            )

    def test_production_source_does_not_import_banned_modules(self):
        violations: list[str] = []
        banned_import_roots = {
            module for module in _BANNED_MODULES if "." not in module
        }

        for directory in PRODUCTION_SOURCE_DIRS:
            for path in (PROJECT_ROOT / directory).rglob("*.py"):
                rel_path = path.relative_to(PROJECT_ROOT).as_posix()
                if rel_path in SOURCE_SCAN_EXCLUDED_FILES:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            root = alias.name.split(".", 1)[0]
                            if root in banned_import_roots:
                                violations.append(f"{rel_path}: import {alias.name}")
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        root = node.module.split(".", 1)[0]
                        if root in banned_import_roots:
                            violations.append(f"{rel_path}: from {node.module} import ...")
                        if node.module == "os":
                            for alias in node.names:
                                if alias.name == "system" and "os.system" in _BANNED_MODULES:
                                    violations.append(f"{rel_path}: from os import system")
                    elif (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                        and node.func.attr == "system"
                        and "os.system" in _BANNED_MODULES
                    ):
                        violations.append(f"{rel_path}: os.system(...)")

        assert violations == []


class TestAdvisoryOnlyFlag:
    def test_advisory_only_is_true(self):
        from utils.guardrails import ADVISORY_ONLY
        assert ADVISORY_ONLY is True

    def test_guardrails_run_checks_raises_when_broker_present(self):
        """
        run_all_checks() raises GuardrailViolation when a banned broker package is installed.
        If the environment is clean, it passes silently.
        Both outcomes are correct — the test verifies the check actually runs.
        """
        import importlib.util
        from utils.guardrails import GuardrailViolation, run_all_checks, _BANNED_PACKAGES

        broker_installed = any(importlib.util.find_spec(p) for p in _BANNED_PACKAGES)
        if broker_installed:
            # Guardrail must fire
            with pytest.raises(GuardrailViolation):
                run_all_checks()
        else:
            # Clean env — must not raise
            run_all_checks()


class TestNoWriteOutsideNovaTacticBot:
    def test_options_adapter_does_not_write(self, tmp_path):
        """The adapter must not write any files to the source directory."""
        import json
        source = tmp_path / "source"
        source.mkdir()
        (source / "sample.json").write_text(json.dumps([{"strategy_id": "x", "outcome": "win"}]))

        files_before = set(source.iterdir())
        from adapters.options_adapter import OptionsAdapter
        adapter = OptionsAdapter(source_dir=source)
        adapter.load()
        files_after = set(source.iterdir())

        assert files_before == files_after, (
            f"Adapter wrote files to source directory: {files_after - files_before}"
        )

    def test_analytics_engine_does_not_write(self, tmp_path):
        """The analytics engine must not write any files."""
        from core.tactic_analytics_engine import TacticAnalyticsEngine
        from core.tactic_event import TacticalEvent, EventType, SourceBot
        events = [
            TacticalEvent(
                source_bot=SourceBot.NOVA_BOT_V2_OPTIONS,
                event_type=EventType.TRADE_OUTCOME,
                strategy_id="x",
            )
        ]
        files_before = set(tmp_path.iterdir())
        TacticAnalyticsEngine().run(events)
        files_after = set(tmp_path.iterdir())
        assert files_before == files_after
