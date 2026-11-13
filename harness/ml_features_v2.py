
"""Public-only structural features for ML Scheduler v2.

No reference answers, hidden tests, task IDs or post-execution results.
"""
from __future__ import annotations

import ast
import csv
import io
import math
import re
from collections.abc import Mapping


FEATURE_NAMES = (
    "log_instruction_words",
    "log_numeric_literals",
    "log_constraint_markers",
    "log_operation_markers",
    "log_question_marks",
    "log_code_functions",
    "log_code_branches",
    "log_code_loops",
    "log_code_ast_nodes",
    "log_public_tests",
    "log_table_rows",
    "log_table_columns",
    "log_document_count",
    "log_document_words",
)


def _log(count: int) -> float:
    return math.log1p(max(0, count))


def extract(instruction: str,
            workspace: Mapping[str, str]) -> list[float]:
    """Extract deterministic features from public task inputs."""
    text = instruction.lower()

    words = re.findall(r"\b\w+\b", text)
    numeric = re.findall(
        r"(?<!\w)[+-]?\d+(?:\.\d+)?(?!\w)", text
    )

    constraints = re.findall(
        r"\b(?:must|exactly|at least|at most|"
        r"only|except|without|не менее|не более|"
        r"ровно|только|кроме)\b", text
    )

    operations = re.findall(
        r"\b(?:sum|count|sort|filter|group|join|"
        r"minimum|maximum|average|calculate|"
        r"сумм|сортир|фильтр|найти|вычисл)\w*",
        text
    )

    functions = branches = loops = nodes = tests = 0
    table_rows = table_columns = 0
    documents = document_words = 0

    for name, content in sorted(workspace.items()):
        if not isinstance(content, str):
            continue

        lower = name.lower()

        if lower.endswith(".py"):
            try:
                tree = ast.parse(content)
            except (SyntaxError, ValueError):
                continue

            for node in ast.walk(tree):
                nodes += 1
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    functions += 1
                    if node.name.startswith("test_"):
                        tests += 1
                elif isinstance(
                    node, (ast.If, ast.IfExp, ast.Match)
                ):
                    branches += 1
                elif isinstance(
                    node, (ast.For, ast.AsyncFor, ast.While)
                ):
                    loops += 1

        elif lower.endswith(".csv"):
            try:
                rows = list(csv.reader(io.StringIO(content)))
                table_rows += max(0, len(rows) - 1)
                table_columns += max(
                    (len(row) for row in rows), default=0
                )
            except csv.Error:
                pass

        elif lower.endswith((".txt", ".md", ".json")):
            documents += 1
            document_words += len(re.findall(r"\b\w+\b", content))

    values = (
        len(words),
        len(numeric),
        len(constraints),
        len(operations),
        instruction.count("?"),
        functions,
        branches,
        loops,
        nodes,
        tests,
        table_rows,
        table_columns,
        documents,
        document_words,
    )

    return [_log(value) for value in values]
