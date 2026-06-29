import csv
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
                "ExternalCommentCount": "4",
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
            self.assertEqual(rows[0]["ExternalCommentCount"], "4")
            self.assertFalse(jira_sync.manifest_status_is_active(rows[0]["Status"]))

    def test_manifest_removes_issue_that_is_no_longer_assigned(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.csv"
            old_row = {
                "Key": "ISSUE-1",
                "Status": "In Progress",
                "Assignee": "Sean",
                "Summary": "Old summary",
                "Updated": "2026-06-08T18:07:04.871-0400",
                "Due": "",
                "Priority": "Medium",
                "RawPath": "/data/outputs/jira/raw/ISSUE-1.json",
                "SummaryPath": "/data/outputs/jira/summary/ISSUE-1.md",
                "AttachmentCount": "2",
                "FormCount": "1",
                "CommentCount": "5",
                "ExternalCommentCount": "4",
                "HasNewComments": "false",
                "EscalationReady": "",
            }
            jira_sync.write_manifest(manifest_path, [old_row])

            jira_sync.write_manifest(manifest_path, [], remove_keys={"ISSUE-1"})

            rows = list(csv.DictReader(manifest_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(rows, [])

    def test_not_assigned_exclusion_applies_to_default_queue_only(self):
        issue = {
            "fields": {
                "assignee": {
                    "displayName": "Other Person",
                    "emailAddress": "other@example.com",
                    "accountId": "other-account",
                }
            }
        }
        with patch.dict("os.environ", {"CASEOPS_DEFAULT_ASSIGNEE": "sean@example.com"}, clear=False):
            default_args = argparse.Namespace(jql=None)
            custom_args = argparse.Namespace(jql='assignee = "Other Person"')

            self.assertTrue(jira_sync.should_exclude_not_assigned(default_args, issue))
            self.assertFalse(jira_sync.should_exclude_not_assigned(custom_args, issue))

    def test_not_assigned_exclusion_accepts_email_display_name_or_account_id(self):
        args = argparse.Namespace(jql=None)
        issue = {
            "fields": {
                "assignee": {
                    "displayName": "Sean Bingham",
                    "emailAddress": "sean@example.com",
                    "accountId": "abc123",
                }
            }
        }

        for configured in ["sean@example.com", "Sean Bingham", "abc123"]:
            with self.subTest(configured=configured):
                with patch.dict("os.environ", {"CASEOPS_DEFAULT_ASSIGNEE": configured}, clear=False):
                    self.assertFalse(jira_sync.should_exclude_not_assigned(args, issue))

    def test_not_assigned_archive_is_written_outside_active_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir = Path(tmp) / "not-assigned"
            issue = {
                "fields": {
                    "status": {"name": "In Progress"},
                    "assignee": {"displayName": "Other Person"},
                    "summary": "Moved to another operator",
                    "updated": "2026-06-08T19:00:00.000-0400",
                }
            }
            with patch.dict("os.environ", {"CASEOPS_DEFAULT_ASSIGNEE": "Sean Bingham"}, clear=False):
                jira_sync.archive_not_assigned_issue(
                    key="ISSUE-1",
                    issue=issue,
                    old_row={},
                    archive_dir=archive_dir,
                )

            archive_text = (archive_dir / "ISSUE-1.md").read_text(encoding="utf-8")
            self.assertIn("Not Assigned Archive - ISSUE-1", archive_text)
            self.assertIn("Current Jira assignee: Other Person", archive_text)
            self.assertIn("removed from `outputs/jira/manifest.csv`", archive_text)

    def test_external_comment_count_ignores_current_operator_identities(self):
        comments = [
            {"author": {"emailAddress": "sean@example.com", "displayName": "Different Name"}},
            {"author": {"displayName": "Sean Bingham"}},
            {"author": {"accountId": "operator-account"}},
            {"author": {"emailAddress": "other@example.com", "displayName": "Other Person"}},
        ]

        with patch.dict(
            "os.environ",
            {
                "JIRA_EMAIL": "sean@example.com",
                "CASEOPS_EXAMPLE_ASSIGNEE_NAME": "Sean Bingham",
                "CASEOPS_DEFAULT_ASSIGNEE": "operator-account",
            },
            clear=False,
        ):
            self.assertEqual(jira_sync.external_comment_count(comments), 1)

    def test_self_only_new_comment_does_not_set_new_comments_flag(self):
        comments = [
            {"author": {"emailAddress": "sean@example.com"}, "body": "older self comment"},
            {"author": {"emailAddress": "sean@example.com"}, "body": "new self comment"},
        ]
        old_row = {
            "CommentCount": "1",
            "ExternalCommentCount": "0",
            "HasNewComments": "false",
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"JIRA_EMAIL": "sean@example.com"}, clear=False):
                total, external, flag = jira_sync.comment_tracking_for_manifest(
                    "ISSUE-1",
                    comments,
                    old_row,
                    Path(tmp) / "raw",
                )

        self.assertEqual(total, 2)
        self.assertEqual(external, 0)
        self.assertEqual(flag, "false")

    def test_external_new_comment_sets_new_comments_flag(self):
        comments = [
            {"author": {"emailAddress": "sean@example.com"}, "body": "self comment"},
            {"author": {"emailAddress": "other@example.com"}, "body": "external comment"},
        ]
        old_row = {
            "CommentCount": "1",
            "ExternalCommentCount": "0",
            "HasNewComments": "false",
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"JIRA_EMAIL": "sean@example.com"}, clear=False):
                _, external, flag = jira_sync.comment_tracking_for_manifest(
                    "ISSUE-1",
                    comments,
                    old_row,
                    Path(tmp) / "raw",
                )

        self.assertEqual(external, 1)
        self.assertEqual(flag, "true")

    def test_legacy_manifest_backfills_external_count_from_old_raw_bundle(self):
        old_comments = [
            {"author": {"emailAddress": "sean@example.com"}, "body": "self comment"},
            {"author": {"emailAddress": "other@example.com"}, "body": "old external comment"},
        ]
        current_comments = [
            *old_comments,
            {"author": {"emailAddress": "another@example.com"}, "body": "new external comment"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            raw_dir.mkdir()
            raw_path = raw_dir / "ISSUE-1.json"
            raw_path.write_text(json.dumps({"comments": old_comments}), encoding="utf-8")
            old_row = {
                "CommentCount": "2",
                "RawPath": str(raw_path),
                "HasNewComments": "false",
            }

            with patch.dict("os.environ", {"JIRA_EMAIL": "sean@example.com"}, clear=False):
                _, external, flag = jira_sync.comment_tracking_for_manifest(
                    "ISSUE-1",
                    current_comments,
                    old_row,
                    raw_dir,
                )

        self.assertEqual(external, 2)
        self.assertEqual(flag, "true")


if __name__ == "__main__":
    unittest.main()
