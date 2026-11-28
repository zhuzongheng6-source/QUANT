"""Run the same checks locally and in CI, using a fresh workspace for tests."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
FORMATTED_FILES = (
    "historical_checks.py",
    "test_backtest.py",
    "test_fixtures.py",
    "test_ledger_data.py",
    "test_workbench.py",
    "test_workspace.py",
    "tools",
)


def main():
    node = shutil.which("node")
    if node is None:
        print("缺少 Node，无法执行 JavaScript 检查和 CSV 一致性测试。", file=sys.stderr)
        return 2
    python = sys.executable
    commands = (
        (python, "-m", "pip", "check"),
        (python, "-m", "ruff", "check", "."),
        (python, "-m", "ruff", "format", "--check", *FORMATTED_FILES),
        (node, "--check", "docs/app.js"),
        (python, "-m", "unittest", "discover", "-v"),
        (python, "-m", "tools.benchmark"),
    )
    with TemporaryDirectory(prefix="quant-quality-") as workspace:
        env = {**os.environ, "QUANT_WORKSPACE_DIR": workspace}
        env.pop("QUANT_RUN_MANIFEST", None)
        for command in commands:
            print(subprocess.list2cmdline(command), flush=True)
            result = subprocess.run(command, cwd=ROOT, env=env, check=False)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
