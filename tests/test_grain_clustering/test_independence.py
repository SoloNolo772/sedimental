"""
Unit tests for script independence from the main application.

Validates requirements 11.1, 11.2, 11.4 by AST-parsing grain_clustering.py
directly, so these checks work regardless of the runtime environment.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Approved top-level package names (requirement 11.1).
_APPROVED_TOP_LEVEL = {
    "numpy",
    "pandas",
    "sklearn",       # scikit-learn installs as 'sklearn'
    "matplotlib",
}

# Standard library module names are determined at runtime via sys.stdlib_module_names
# (Python 3.10+).  For older Pythons we fall back to a hand-curated set that is a
# superset of what grain_clustering.py actually uses.
try:
    _STDLIB_MODULES: frozenset[str] = frozenset(sys.stdlib_module_names)  # type: ignore[attr-defined]
except AttributeError:
    # Fallback for Python < 3.10 – covers everything grain_clustering.py imports.
    _STDLIB_MODULES = frozenset(
        {
            "__future__",
            "argparse",
            "ast",
            "builtins",
            "collections",
            "contextlib",
            "copy",
            "csv",
            "datetime",
            "functools",
            "io",
            "itertools",
            "logging",
            "math",
            "operator",
            "os",
            "pathlib",
            "re",
            "shutil",
            "statistics",
            "string",
            "struct",
            "subprocess",
            "sys",
            "tempfile",
            "threading",
            "time",
            "traceback",
            "typing",
            "unittest",
            "warnings",
        }
    )


def _parse_script() -> ast.Module:
    """Parse grain_clustering.py and return the AST module node."""
    script_path = Path(__file__).parent.parent.parent / "analysis" / "grain_clustering.py"
    source = script_path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(script_path))


def _top_level_module(name: str) -> str:
    """Return the top-level package name from a dotted module path."""
    return name.split(".")[0]


def _collect_imports(tree: ast.Module) -> list[str]:
    """Return the top-level package names of every import in the AST.

    Only considers top-level (module-scope) statements so that local imports
    inside functions are also checked.  Both ``import X`` and ``from X import Y``
    forms are handled.
    """
    top_level_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_names.append(_top_level_module(alias.name))
        elif isinstance(node, ast.ImportFrom):
            # ``from . import foo`` has module == None; treat as relative (local).
            if node.module is not None:
                top_level_names.append(_top_level_module(node.module))
    return top_level_names


# ---------------------------------------------------------------------------
# 11.4 – if __name__ == "__main__" guard
# ---------------------------------------------------------------------------


def test_script_has_main_guard() -> None:
    """grain_clustering.py must contain an ``if __name__ == "__main__":`` guard.

    Requirement 11.4.
    """
    tree = _parse_script()

    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        # Match: __name__ == "__main__"
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
        ):
            found = True
            break

    assert found, (
        'grain_clustering.py is missing the ``if __name__ == "__main__":`` guard '
        "(requirement 11.4)."
    )


# ---------------------------------------------------------------------------
# 11.2 – no project-internal (sedimental) imports
# ---------------------------------------------------------------------------


def test_no_project_internal_imports() -> None:
    """grain_clustering.py must not import from the ``sedimental`` package.

    Checks for both ``import sedimental`` and ``from sedimental import …``
    forms (requirement 11.2).
    """
    tree = _parse_script()

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _top_level_module(alias.name) == "sedimental":
                    violations.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _top_level_module(module) == "sedimental":
                violations.append(f"from {module} import …")

    assert not violations, (
        "grain_clustering.py contains project-internal import(s) "
        f"(requirement 11.2): {violations}"
    )


# ---------------------------------------------------------------------------
# 11.1 – only approved imports (stdlib + numpy, pandas, sklearn, matplotlib)
# ---------------------------------------------------------------------------


def test_only_approved_imports() -> None:
    """All imports in grain_clustering.py must come from stdlib or approved packages.

    Approved third-party packages: numpy, pandas, sklearn (scikit-learn),
    matplotlib (requirement 11.1).
    """
    tree = _parse_script()

    violations: list[str] = []
    for top_level_name in _collect_imports(tree):
        if top_level_name in _STDLIB_MODULES:
            continue
        if top_level_name in _APPROVED_TOP_LEVEL:
            continue
        violations.append(top_level_name)

    assert not violations, (
        "grain_clustering.py imports from unapproved package(s) "
        f"(requirement 11.1): {violations}. "
        f"Approved packages: stdlib + {sorted(_APPROVED_TOP_LEVEL)}"
    )
