#!/usr/bin/env python3
"""Lightweight Jira comments poller. Updates manifest.csv every 10 minutes with new comment counts."""

import csv
import os
import sys
import time
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).parent.parent))

from jira_sync import JiraClient

POLL_INTERVAL = 600  # 10 minutes in seconds
MANIFEST_LOCK = Lock()


def load_manifest(manifest_path: Path) -> dict[str, dict[str, str]]:
    """Load manifest.csv into memory."""
    manifest = {}
    if not manifest_path.exists():
        return manifest
    try:
        with manifest_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("Key"):
                    manifest[row["Key"]] = row
    except Exception as e:
        print(f"Error reading manifest: {e}", flush=True)
    return manifest


def save_manifest(manifest_path: Path, manifest: dict[str, dict[str, str]]) -> None:
    """Save manifest.csv from memory."""
    if not manifest:
        return
    fieldnames = [
        "Key",
        "Status",
        "Summary",
        "Updated",
        "Due",
        "Priority",
        "RawPath",
        "SummaryPath",
        "AttachmentCount",
        "FormCount",
        "CommentCount",
        "HasNewComments",
        "EscalationReady",
    ]
    try:
        with manifest_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(manifest.values())
    except Exception as e:
        print(f"Error writing manifest: {e}", flush=True)


def poll_comments(client: JiraClient, issues: list[str], manifest: dict[str, dict[str, str]]) -> int:
    """Fetch comment counts for issues. Return count of updated rows."""
    if not issues:
        return 0

    updates = 0
    for key in issues:
        try:
            comments = client.get_paginated(f"/rest/api/3/issue/{key}/comment", "comments")
            new_count = len(comments)
            old_row = manifest.get(key, {})
            old_count = int(old_row.get("CommentCount", "0") or "0")

            # Update if count changed
            if new_count != old_count:
                manifest[key]["CommentCount"] = str(new_count)
                manifest[key]["HasNewComments"] = "true" if new_count > old_count else old_row.get(
                    "HasNewComments", "false"
                )
                updates += 1
        except Exception as e:
            print(f"Error fetching comments for {key}: {str(e)[:100]}", flush=True)

    return updates


def main() -> int:
    """Run comment poller loop."""
    # Load env
    env_file = Path(__file__).parent.parent / ".env.jira"
    if not env_file.exists():
        print("ERROR: .env.jira not found", file=sys.stderr, flush=True)
        return 1

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ[key] = value

    # Validate Jira auth
    if not os.environ.get("JIRA_BASE_URL"):
        print("ERROR: JIRA_BASE_URL not set in .env.jira", file=sys.stderr, flush=True)
        return 1

    client = JiraClient(
        base_url=os.environ.get("JIRA_BASE_URL", ""),
        email=os.environ.get("JIRA_EMAIL", ""),
        api_token=os.environ.get("JIRA_API_TOKEN", ""),
    )

    jira_dir = Path(__file__).parent.parent / "caseops" / "data" / "jira"
    manifest_path = jira_dir / "manifest.csv"

    print(f"[Comments Poller] Starting (poll interval: {POLL_INTERVAL}s)", flush=True)
    print(f"[Comments Poller] Manifest: {manifest_path}", flush=True)

    iteration = 0
    while True:
        try:
            iteration += 1
            with MANIFEST_LOCK:
                manifest = load_manifest(manifest_path)
                if not manifest:
                    print(f"[{iteration}] No issues in manifest yet", flush=True)
                    time.sleep(POLL_INTERVAL)
                    continue

                issues = list(manifest.keys())
                updates = poll_comments(client, issues, manifest)
                if updates > 0:
                    save_manifest(manifest_path, manifest)
                    print(f"[{iteration}] Updated {updates}/{len(issues)} issues", flush=True)
                else:
                    print(f"[{iteration}] No updates ({len(issues)} issues)", flush=True)
        except KeyboardInterrupt:
            print("\n[Comments Poller] Interrupted by user", flush=True)
            return 0
        except Exception as e:
            print(f"[{iteration}] Error: {str(e)[:100]}", flush=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
