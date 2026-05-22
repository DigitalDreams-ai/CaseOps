#!/usr/bin/env python3
"""Nightly pre-compute scheduler. Run as a service/task.

Schedule: Weekdays at 6 AM MST

Usage:
  python nightly_scheduler.py

On Windows, schedule via Task Scheduler:
  - Trigger: Daily, 6:00 AM MST (UTC-7), Mon-Fri only
  - Action: Run python.exe C:\path\to\nightly_scheduler.py
  - Run with highest privileges: No
  - Run whether user is logged in or not: Yes
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import schedule

# Setup logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "nightly_precompute.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def run_precompute():
    """Run the nightly pre-computation."""
    try:
        logger.info("Starting nightly pre-computation...")
        from run_pipeline import run_nightly_precompute

        completed, failed = run_nightly_precompute()
        logger.info(f"Pre-computation complete: {completed} succeeded, {failed} failed")
    except Exception as e:
        logger.error(f"Pre-computation failed: {e}", exc_info=True)


def main():
    """Schedule and run jobs."""
    logger.info("Nightly scheduler started")

    # Schedule job: weekdays at 6 AM MST
    schedule.every().monday.at("06:00").do(run_precompute)
    schedule.every().tuesday.at("06:00").do(run_precompute)
    schedule.every().wednesday.at("06:00").do(run_precompute)
    schedule.every().thursday.at("06:00").do(run_precompute)
    schedule.every().friday.at("06:00").do(run_precompute)

    logger.info("Scheduler armed. Waiting for next scheduled run...")

    # Keep scheduler running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
        sys.exit(0)
