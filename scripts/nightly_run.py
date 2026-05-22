#!/usr/bin/env python3
"""Wrapper for nightly pre-computation. Called by Windows Task Scheduler."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from run_pipeline import run_nightly_precompute, default_jira_env_file

if __name__ == "__main__":
    # Step 1: Sync fresh Jira data with --incremental flag
    print("Nightly: syncing fresh Jira data...")
    env_file = default_jira_env_file()
    sync_cmd = [sys.executable, str(PROJECT_ROOT / "jira_sync.py"), "--env-file", str(env_file), "--incremental"]
    result = subprocess.run(sync_cmd, capture_output=False)
    if result.returncode != 0:
        print(f"ERROR: jira_sync.py failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Pre-compute investigation records from fresh manifest
    print("\nNightly: pre-computing investigation records...")
    completed, failed = run_nightly_precompute()
    print(f"\nNightly pre-compute: {completed} completed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
