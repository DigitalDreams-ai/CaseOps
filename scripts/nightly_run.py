#!/usr/bin/env python3
"""Wrapper for nightly pre-computation. Called by Windows Task Scheduler.

Usage:
  python nightly_run.py                          # default instance (outputs/)
  python nightly_run.py --instance instance2     # instance2 (instance2/outputs/)
  python nightly_run.py --env-file .env.jira.custom --outputs-dir custom/outputs
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from caseops_paths import default_jira_env_file
from run_pipeline import run_nightly_precompute

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nightly pre-computation wrapper")
    parser.add_argument(
        "--instance",
        help="Instance name (e.g. instance2) — determines env file and outputs dir",
    )
    parser.add_argument(
        "--env-file",
        help="Override .env.jira file path",
    )
    parser.add_argument(
        "--outputs-dir",
        help="Override outputs directory",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    # Determine env_file and outputs_dir from instance or explicit args
    if args.env_file:
        env_file = args.env_file
    elif args.instance:
        env_file = str(PROJECT_ROOT / f"{args.instance}" / ".env.jira")
    else:
        env_file = default_jira_env_file()

    if args.outputs_dir:
        outputs_dir = Path(args.outputs_dir)
    elif args.instance:
        outputs_dir = PROJECT_ROOT / args.instance / "outputs"
    else:
        outputs_dir = PROJECT_ROOT / "outputs"

    jira_dir = outputs_dir / "jira"

    # Step 1: Sync fresh Jira data with --incremental flag
    print(f"Nightly [{args.instance or 'default'}]: syncing fresh Jira data...")
    print(f"  env_file: {env_file}")
    print(f"  outputs_dir: {outputs_dir}")
    sync_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "jira_sync.py"),
        "--env-file", str(env_file),
        "--out-dir", str(jira_dir),
        "--incremental"
    ]
    result = subprocess.run(sync_cmd, capture_output=False)
    if result.returncode != 0:
        print(f"ERROR: jira_sync.py failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Pre-compute investigation records from fresh manifest
    print(f"\nNightly [{args.instance or 'default'}]: pre-computing investigation records...")
    completed, failed = run_nightly_precompute(outputs_dir=outputs_dir)
    print(f"\nNightly pre-compute: {completed} completed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
