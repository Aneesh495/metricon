import json
from pathlib import Path

root = Path(".metricon/verification/browser")
report = json.loads((root / "playwright.json").read_text())
tests = []


def collect(suite):
    for spec in suite.get("specs", []):
        tests.append(
            {
                "name": spec["title"],
                "passed": spec["ok"],
                "results": [
                    result["status"] for test in spec["tests"] for result in test["results"]
                ],
            }
        )
    for child in suite.get("suites", []):
        collect(child)


for suite in report["suites"]:
    collect(suite)
result = {
    "passed": bool(tests) and all(test["passed"] for test in tests),
    "workflows": tests,
    "stats": report["stats"],
}
(root / "e2e.json").write_text(json.dumps(result, indent=2) + "\n")
if not result["passed"]:
    raise SystemExit(1)
