"""Resolve the installed code and this user's private data independently."""

import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
WORKSPACE_ENV = "QUANT_WORKSPACE_DIR"


def workspace_root():
    configured = os.environ.get(WORKSPACE_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    if any((CODE_ROOT / name).is_dir() for name in ("data", "projects", "reports")):
        # Preserve in-place installations created before workspace separation.
        return CODE_ROOT
    return (Path.home() / "QUANT-Workspace").resolve()


WORKSPACE_ROOT = workspace_root()
DATA = WORKSPACE_ROOT / "data"
PROJECTS = WORKSPACE_ROOT / "projects"
REPORTS = WORKSPACE_ROOT / "reports"
