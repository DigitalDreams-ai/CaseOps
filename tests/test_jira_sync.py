import csv
import tempfile
import unittest
from pathlib import Path

import jira_sync


class JiraSyncManifestTests(unittest.TestCase):
    def test_closed_issue_refresh_updates_manifest_status_without_raw_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            jira_dir = Path(tmp)
            manifest_path = jira_dir / "manifest.csv"
            raw_dir = jira_dir / "raw"
            summary_dir = jira_dir / "summary"
            raw_dir.mkdir()
            summary_dir.mkdir()

            old_row = {
                "Key": "ISSUE-1",
                "Status": "In Progress",
                "Assignee": "Frodo",
                "Summary": "Old summary",
                "Updated": "2026-06-08T18:07:04.871-0400",
                "Due": "",
                "Priority": "Medium",
                "RawPath": "/data/outputs/jira/raw/ISSUE-1.json",
                "SummaryPath": "/data/outputs/jira/summary/ISSUE-1.md",
                "AttachmentCount": "2",
                "FormCount": "1",
                "CommentCount": "5",
                "HasNewComments": "false",
                "EscalationReady": "",
            }
            jira_sync.write_manifest(manifest_path, [old_row])

            issue = {
                "fields": {
                    "status": {"name": "Resolved"},
                    "assignee": {"displayName": "Frodo"},
                    "summary": "Current summary",
                    "updated": "2026-06-08T19:00:00.000-0400",
                    "priority": {"name": "Medium"},
                }
            }
            row = jira_sync.skipped_status_manifest_row(
                "ISSUE-1",
                issue,
                old_row,
                raw_dir,
                summary_dir,
            )
            jira_sync.write_manifest(manifest_path, [row])

            rows = list(csv.DictReader(manifest_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Status"], "Resolved")
            self.assertEqual(rows[0]["Summary"], "Current summary")
            self.assertEqual(rows[0]["RawPath"], old_row["RawPath"])
            self.assertEqual(rows[0]["CommentCount"], "5")
            self.assertFalse(jira_sync.manifest_status_is_active(rows[0]["Status"]))


if __name__ == "__main__":
    unittest.main()
