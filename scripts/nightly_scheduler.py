#!/usr/bin/env python3
"""Nightly pre-compute scheduler. Run as a service/task.

Schedule: Weekdays at 6 AM MST

Usage:
  python nightly_scheduler.py                    # default instance only
  python nightly_scheduler.py --instances instance1 instance2  # multiple instances

On Windows, schedule via Task Scheduler:
  - Trigger: Daily, 6:00 AM MST (UTC-7), Mon-Fri only
  - Action: Run python.exe C:\path\to\nightly_scheduler.py --instances instance1 instance2
  - Run with highest privileges: No
  - Run whether user is logged in or not: Yes
"""

import argparse
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import schedule

# Add repo root to path so we can import from root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging (in root logs directory)
log_dir = PROJECT_ROOT / "logs"
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


def run_precompute_for_instance(instance: str | None = None):
    """Run nightly pre-computation for a specific instance."""
    try:
        from caseops_paths import default_jira_env_file
        from run_pipeline import run_nightly_precompute

        if instance:
            env_file = str(PROJECT_ROOT / instance / ".env.jira")
            outputs_dir = PROJECT_ROOT / instance / "outputs"
            label = f"[{instance}]"
        else:
            env_file = default_jira_env_file()
            outputs_dir = PROJECT_ROOT / "outputs"
            label = "[default]"

        logger.info(f"Starting nightly pre-computation {label}")
        completed, failed = run_nightly_precompute(outputs_dir=outputs_dir)
        logger.info(f"Pre-computation {label} complete: {completed} succeeded, {failed} failed")
    except Exception as e:
        label = f"[{instance}]" if instance else "[default]"
        logger.error(f"Pre-computation {label} failed: {e}", exc_info=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nightly scheduler for multi-instance CaseOps")
    parser.add_argument(
        "--instances",
        nargs="*",
        default=None,
        help="Instance names to process (e.g. instance1 instance2). If omitted, processes default only.",
    )
    return parser.parse_args()


def main():
    """Schedule and run jobs."""
    args = parse_args()

    # Determine which instances to process
    instances = args.instances if args.instances else [None]  # None = default instance
    logger.info(f"Nightly scheduler started. Instances: {instances or ['default']}")

    # Schedule job: weekdays at 6 AM MST for each instance
    for instance in instances:
        schedule.every().monday.at("06:00").do(run_precompute_for_instance, instance=instance)
        schedule.every().tuesday.at("06:00").do(run_precompute_for_instance, instance=instance)
        schedule.every().wednesday.at("06:00").do(run_precompute_for_instance, instance=instance)
        schedule.every().thursday.at("06:00").do(run_precompute_for_instance, instance=instance)
        schedule.every().friday.at("06:00").do(run_precompute_for_instance, instance=instance)
        label = f"[{instance}]" if instance else "[default]"
        logger.info(f"  Scheduled weekdays 06:00 MST for {label}")

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
