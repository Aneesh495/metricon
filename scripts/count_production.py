"""Audit authored production lines; tests, docs, generated assets and configuration excluded."""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_lines(path: Path) -> int:
    source = path.read_text()
    excluded = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            expression = body[0].value
            if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
                excluded.update(range(body[0].lineno, body[0].end_lineno + 1))
    lines = set()
    ignored = {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.ENCODING,
    }
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in ignored:
            lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines - excluded)


def typescript_lines(path: Path) -> int:
    # Authored TS/TSX contains no block comments or template literals containing comments.
    # Keep physical production lines, including multiline contracts and JSX markup.
    source = path.read_text()
    without_blocks = re.sub(
        r"/\*.*?\*/", lambda match: "\n" * match.group().count("\n"), source, flags=re.S
    )
    return sum(
        bool(line.strip()) and not line.lstrip().startswith("//")
        for line in without_blocks.splitlines()
    )


def main() -> None:
    verification = {"campaigns.py", "benchmark.py", "workloads.py", "acceptance.py", "evidence.py"}
    paths = sorted(
        path
        for path in (ROOT / "src/metricon").rglob("*.py")
        if not (path.parent.name == "evaluation" and path.name in verification)
    )
    paths += sorted(
        path
        for path in (ROOT / "web/src").rglob("*")
        if path.suffix in {".ts", ".tsx"} and not path.name.endswith((".test.ts", ".test.tsx"))
    )
    counts = {
        path.relative_to(ROOT).as_posix(): python_lines(path)
        if path.suffix == ".py"
        else typescript_lines(path)
        for path in paths
    }
    modules = {}
    for name, count in counts.items():
        module = (
            "/".join(name.split("/")[:3])
            if name.startswith("src/")
            else "/".join(name.split("/")[:3])
        )
        modules[module] = modules.get(module, 0) + count
    test_paths = [
        *(ROOT / "tests").rglob("*.py"),
        *(ROOT / "web/src").rglob("*.test.ts"),
        *(ROOT / "web/e2e").rglob("*.ts"),
    ]
    test_counts = {
        path.relative_to(ROOT).as_posix(): python_lines(path)
        if path.suffix == ".py"
        else typescript_lines(path)
        for path in test_paths
    }
    result = {
        "method": "Nonblank, noncomment physical lines in reusable Python and authored TS/TSX. Python docstrings excluded. No formatting expansion is counted separately.",
        "exclusions": "Tests, docs, config, scripts, CSS, copied UI, fixtures, datasets, generated assets, notebooks, dependencies and lockfiles.",
        "files": counts,
        "modules": modules,
        "test_files": test_counts,
        "test_total": sum(test_counts.values()),
        "include_paths": ["src/metricon/**/*.py", "web/src/**/*.ts", "web/src/**/*.tsx"],
        "verification_exclusions": sorted(verification),
        "total": sum(counts.values()),
        "minimum": 10000,
        "target": [12000, 17000],
        "minimum_met": sum(counts.values()) >= 10000,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
