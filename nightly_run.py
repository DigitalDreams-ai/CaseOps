#!/usr/bin/env python3
"""Wrapper for nightly pre-computation. Called by Windows Task Scheduler."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from run_pipeline import run_nightly_precompute

if __name__ == "__main__":
    completed, failed = run_nightly_precompute()
    print(f"\nNightly pre-compute: {completed} completed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
