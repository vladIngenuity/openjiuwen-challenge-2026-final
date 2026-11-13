#!/usr/bin/env python3
"""Generate a source-linked inventory of every project Python function."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "run_agent.py", *sorted((ROOT / "harness").rglob("*.py")),
           *sorted((ROOT / "tools").rglob("*.py"))]


def first_sentence(node: ast.AST) -> str:
    doc = ast.get_docstring(node) or ""
    if not doc:
        return "Описание в docstring отсутствует; сигнатура и реализация доступны по ссылке."
    return " ".join(doc.strip().splitlines()[0].split()).replace("|", "\\|")


def inventory(path: Path) -> list[tuple[str, int, str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    entries: list[tuple[str, int, str, str]] = []

    class Collector(ast.NodeVisitor):
        scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._function(node)

        def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            name = ".".join([*self.scope, node.name])
            if isinstance(node, ast.AsyncFunctionDef):
                name = "async " + name
            signature = "(" + ast.unparse(node.args) + ")"
            if node.returns is not None:
                signature += " -> " + ast.unparse(node.returns)
            entries.append((name, node.lineno, signature, first_sentence(node)))
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

    Collector().visit(tree)
    return sorted(entries, key=lambda entry: entry[1])


def render() -> str:
    lines = [
        "# Справочник функций исходного кода",
        "",
        "Сгенерировано по AST текущего checkout. Охват: `run_agent.py`, `harness/**/*.py`,",
        "`tools/**/*.py` (включая функции командных инструментов и вложенные функции).",
        "Сигнатуры и строки исходника точные; описание берётся из первой строки docstring.",
        "Отсутствующий docstring указан явно, чтобы не выдавать догадку за контракт.",
        "Внешние зависимости, тесты, сгенерированные корпуса и старые резервные копии",
        "в справочник не входят. Ссылка на строку ведёт к определению в GitHub.",
        "",
    ]
    count = 0
    for path in SOURCES:
        if not path.is_file():
            continue
        entries = inventory(path)
        if not entries:
            continue
        relative = path.relative_to(ROOT).as_posix()
        lines += [f"## `{relative}`", ""]
        for name, line, signature, summary in entries:
            target = f"../../{relative}#L{line}"
            lines.append(f"- [`{name}{signature}`]({target}) — {summary}")
            count += 1
        lines.append("")
    lines.insert(8, f"Всего определений: **{count}**.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if catalog is stale")
    args = parser.parse_args()
    target = ROOT / "docs" / "project" / "FUNCTIONS.md"
    content = render()
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            parser.error("FUNCTIONS.md is stale; regenerate with tools/document_api.py")
        print("function catalog current")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"wrote {target}")


if __name__ == "__main__":
    main()
