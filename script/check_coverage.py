"""Check the test coverage of every module against the quality scale.

Silver's test-coverage rule asks for above 95 % in every module of the
integration, Bronze's config-flow-test-coverage for all of the config flow.
Reads the report that ``pytest --cov --cov-report=json`` writes.

Usage: python script/check_coverage.py [coverage.json]
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

MINIMUM = 95.0
FULLY_COVERED = {"custom_components/cfos_powerbrain/config_flow.py"}


def main(report: Path) -> int:
    """Print every module below its threshold; return the exit code."""
    files = json.loads(report.read_text())["files"]
    failures = []
    for name, data in sorted(files.items()):
        covered = data["summary"]["percent_covered"]
        if name in FULLY_COVERED:
            if covered < 100:
                failures.append(f"{name}: {covered:.1f} %, needs 100 %")
        elif covered <= MINIMUM:
            failures.append(f"{name}: {covered:.1f} %, needs above {MINIMUM:.0f} %")
    for failure in failures:
        print(failure)
    if not failures:
        print(f"Coverage: all {len(files)} modules meet the quality scale")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")))
