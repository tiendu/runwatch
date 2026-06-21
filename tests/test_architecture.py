from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "runwatch"
DOMAIN_PREFIXES = (
    "runwatch.checks",
    "runwatch.exporters",
    "runwatch.installation",
    "runwatch.targets",
    "runwatch.templates",
)
APPLICATION_PREFIXES = ("runwatch.cli", "runwatch.commands", "runwatch.main")


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


def test_domain_modules_do_not_import_application_layer() -> None:
    violations: list[str] = []
    for path in ROOT.rglob("*.py"):
        module = _module_name(path)
        if not module.startswith(DOMAIN_PREFIXES):
            continue
        for imported in _imports(path):
            if imported.startswith(APPLICATION_PREFIXES):
                violations.append(f"{module} imports {imported}")

    assert violations == []


def test_only_main_imports_cli() -> None:
    importers = {
        _module_name(path) for path in ROOT.rglob("*.py") if "runwatch.cli" in _imports(path)
    }

    assert importers == {"runwatch.main"}


def test_internal_module_graph_has_no_cycles() -> None:
    paths = {_module_name(path): path for path in ROOT.rglob("*.py")}
    edges: dict[str, set[str]] = defaultdict(set)

    for module, path in paths.items():
        for imported in _imports(path):
            candidate = imported
            while candidate not in paths and "." in candidate:
                candidate = candidate.rsplit(".", 1)[0]
            if candidate in paths and candidate != module:
                edges[module].add(candidate)

    visited: set[str] = set()
    active: list[str] = []

    def visit(module: str) -> None:
        if module in active:
            cycle = [*active[active.index(module) :], module]
            raise AssertionError("import cycle: " + " -> ".join(cycle))
        if module in visited:
            return
        active.append(module)
        for dependency in edges[module]:
            visit(dependency)
        active.pop()
        visited.add(module)

    for module in paths:
        visit(module)


def test_cli_commands_match_registered_handlers() -> None:
    import argparse

    from runwatch.cli import build_parser
    from runwatch.commands import COMMAND_HANDLERS

    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )

    assert set(subparsers.choices) == set(COMMAND_HANDLERS)
