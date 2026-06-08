"""Shared local paths for CaseOps helper scripts."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def default_jira_env_file() -> str:
    """Return the env file path used by local helper scripts."""
    return os.environ.get("CASEOPS_ENV_FILE") or str(PROJECT_ROOT / ".env")


def default_jira_dir(*, for_write: bool = False) -> Path:
    """Return the default local Jira output directory."""
    path = Path(os.environ.get("CASEOPS_JIRA_OUT_DIR") or PROJECT_ROOT / "outputs" / "jira")
    if for_write:
        path.mkdir(parents=True, exist_ok=True)
    return path
