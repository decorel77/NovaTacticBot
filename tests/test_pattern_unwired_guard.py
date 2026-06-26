"""PATTERN-009: repo-wide guard that the research pattern modules stay UNWIRED
from every runner / scheduler / live-order path.

The per-module ``SafetyTests`` in ``test_pattern_recognition`` /
``test_pattern_outcome_bridge`` / ``test_pattern_report`` each check only the
single ``tools/run_tacticbot.py`` file. This guard instead scans **all** Python
files in the live/operational directories (``tools/``, ``workflow/``, ``core/``,
``adapters/``) via the AST and asserts none of them import the research
package — so a future scheduler, order path, or adapter that imported a pattern
prototype would fail here, in CI, broker-free, rather than silently wiring an
unvalidated research signal into the live path.

Pure: parses source only, imports nothing from the scanned files, touches no
broker / network / data. Research stays research-only by policy; promoting it is
a separate HUMAN_GATED decision that must update this guard deliberately.
"""
import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Directories that may run, schedule, or place orders. Research must never be
# imported here.
LIVE_DIRS = ("tools", "workflow", "core", "adapters")

# The research-only modules that must stay unwired (leaf module names). The whole
# ``research`` package is unwired by policy; these are called out for clear
# failure messages.
FORBIDDEN_RESEARCH_MODULES = frozenset({
    "pattern_recognition",
    "pattern_outcome_bridge",
    "pattern_report",
    "research_indicators",
})
FORBIDDEN_TOP_PACKAGE = "research"


def _imported_modules(source: str):
    """Yield the dotted module path of every import in ``source`` (AST-based)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None
        elif isinstance(node, ast.ImportFrom):
            # level>0 is a relative import; module may be None for "from . import x"
            module = node.module or ""
            for alias in node.names:
                yield module, alias.name


def _live_py_files():
    for d in LIVE_DIRS:
        directory = REPO / d
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


class PatternModulesUnwiredGuard(unittest.TestCase):
    def test_live_dirs_exist_and_are_scanned(self):
        # Guard against a vacuous pass: the scan must actually cover files.
        files = list(_live_py_files())
        self.assertGreaterEqual(len(files), 5, "expected to scan the live dirs")

    def test_no_live_file_imports_a_research_module(self):
        offenders = []
        for path in _live_py_files():
            source = path.read_text(encoding="utf-8")
            for module, name in _imported_modules(source):
                top = module.split(".")[0] if module else ""
                leaf = module.split(".")[-1] if module else ""
                hits_package = top == FORBIDDEN_TOP_PACKAGE
                hits_module = (
                    leaf in FORBIDDEN_RESEARCH_MODULES
                    or (name in FORBIDDEN_RESEARCH_MODULES)
                )
                if hits_package or hits_module:
                    offenders.append(
                        f"{path.relative_to(REPO)} imports "
                        f"{module or '.'}{'.' + name if name else ''}"
                    )
        self.assertEqual(
            offenders,
            [],
            "research pattern modules must stay unwired from live paths:\n"
            + "\n".join(offenders),
        )

    def test_runner_entrypoint_has_no_pattern_reference(self):
        # Belt-and-suspenders: the runner must not even name the modules in a
        # dynamic import / string. Plain substring scan of the entrypoint.
        runner = REPO / "tools" / "run_tacticbot.py"
        if runner.is_file():
            text = runner.read_text(encoding="utf-8")
            for mod in FORBIDDEN_RESEARCH_MODULES:
                with self.subTest(module=mod):
                    self.assertNotIn(mod, text)


if __name__ == "__main__":
    unittest.main()
