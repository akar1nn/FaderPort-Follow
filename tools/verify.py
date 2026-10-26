"""Run automated checks and record their limits separately from hardware QA."""

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from FaderPort_Follow import __version__


def main():
    (ROOT / "tmp").mkdir(exist_ok=True)
    syntax_ok = True
    for source in (ROOT / "FaderPort_Follow").glob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source), feature_version=(3, 7))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "version": __version__,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "runtime_python_3_7_syntax": syntax_ok,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "passed": result.wasSuccessful(),
        "limitations": ["Live framework entrypoint tests use stubs",
                        "This runner does not validate actual Live loading or physical hardware"],
    }
    destination = ROOT / "docs" / "validation-results.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
