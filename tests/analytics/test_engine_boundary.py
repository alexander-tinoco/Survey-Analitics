"""Enforce the boundary ADR 0001 depends on.

The analytics engine is framework-agnostic so its statistics can be tested in
milliseconds against hand-computed values, without a database. That property
is easy to state and easy to lose: one convenient ``from django.db import
models`` inside the engine and every test in it needs a database again.

A rule written in a document erodes. A rule that fails the build does not.
"""

import ast
import pkgutil
from pathlib import Path

import pytest

import apps.analytics.engine as engine_package

ENGINE_ROOT = Path(engine_package.__file__).parent

FORBIDDEN_ROOTS = {"django", "rest_framework", "celery", "apps"}


def engine_modules() -> list[Path]:
    """Every Python module inside the engine package."""
    return sorted(
        Path(module.module_finder.path) / f"{module.name}.py"
        for module in pkgutil.iter_modules([str(ENGINE_ROOT)])
    )


def imported_roots(source: str) -> set[str]:
    """Top-level packages a module imports."""
    roots: set[str] = set()

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])

    return roots


def test_the_engine_package_is_not_empty() -> None:
    """Guards the guard: an empty package would pass every check below."""
    assert engine_modules(), "No engine modules found — has the package moved?"


@pytest.mark.parametrize("module", engine_modules(), ids=lambda p: p.name)
def test_engine_module_imports_no_framework(module: Path) -> None:
    """The engine may import pandas, scipy and sklearn. Nothing else."""
    violations = imported_roots(module.read_text()) & FORBIDDEN_ROOTS

    assert not violations, (
        f"{module.name} imports {sorted(violations)}. The analytics engine must "
        "stay framework-agnostic (ADR 0001) — move the Django-aware part into "
        "apps/analytics/services/."
    )
