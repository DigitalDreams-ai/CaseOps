import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import caseops_paths


class GlobalQueueTests(unittest.TestCase):
    def test_global_queue_skips_escalated_to_engineering(self):
        rows = [
            {"Key": "OPEN-1", "Status": "Open"},
            {"Key": "ENG-1", "Status": "Escalated to Engineering"},
            {"Key": "DONE-1", "Status": "Open"},
        ]

        def detail_for(key):
            if key == "DONE-1":
                return True, "complete"
            return False, "incomplete; next STEP_5 (Retrieve relevant Production metadata, pending)"

        messages = []
        with (
            patch.object(app, "_read_manifest", return_value=rows),
            patch.object(app, "_global_issue_queue_detail", side_effect=lambda key: detail_for(key)),
            patch.object(app, "_log_emit_line", side_effect=lambda _run_key, msg: messages.append(msg)),
        ):
            queued = app._select_global_issue_queue("__global__")

        self.assertEqual(queued, ["OPEN-1"])
        self.assertTrue(any("skipped 1 issue(s) already Escalated to Engineering" in msg for msg in messages))
        self.assertTrue(any("1 escalated skipped" in msg for msg in messages))

    def test_queue_incomplete_summary_bucket_groups_next_steps(self):
        detail = "stalled/no progress in pass 3; incomplete; next STEP_9 (Deploy and test in Sandbox, stale)"
        self.assertEqual(
            app._queue_incomplete_summary_bucket(detail),
            "STEP_9 Deploy and test in Sandbox (stale)",
        )

    def test_ready_to_deploy_flag_requires_validated_confirmed_production_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {
                    "path": "support_resolvable",
                    "confidence": "high",
                    "reason": "Fixture routing.",
                },
                "deliverable": {
                    "type": "metadata",
                    "production_deploy_required": "yes",
                    "production_deploy_method": "standard release process",
                },
            }
            with (
                patch.object(app, "OUTPUTS", Path(tmp)),
                patch.object(app, "_read_pipeline_state", return_value=state),
                patch.object(app, "_test_report_is_data_only", return_value=False),
                patch.object(app, "_test_report_confirms_fix", return_value=True),
                patch.object(app, "_calculate_pipeline_state", return_value=app.PipelineState.VALIDATED),
            ):
                flags = app._pipeline_file_flags("OPEN-1", "Open")

        self.assertEqual(flags["production_deploy_required"], "yes")
        self.assertTrue(flags["has_confirmed_solution"])
        self.assertTrue(flags["is_ready_to_deploy"])

    def test_issue_tag_contract_has_one_primary_and_no_internal_validated_tag(self):
        flags = {
            "pipeline_state": app.PipelineState.VALIDATED.value,
            "is_ready_to_deploy": True,
            "is_data_only": False,
            "is_blocked": False,
            "needs_escalation": False,
            "is_jira_escalated_any": False,
            "has_stale_pipeline_step": False,
            "has_failed_validation": False,
            "has_similar_issues": True,
            "has_generated_files": False,
            "needs_customer_reply": False,
        }

        contract = app._derive_issue_tag_contract("Open", flags, has_new_comments=True)

        self.assertEqual(contract["primary_tag"], "ready to deploy")
        self.assertEqual(contract["condition_tags"], ["new comments", "similar issues"])
        self.assertIn("ready to deploy", contract["tags"])
        self.assertNotIn("validated", contract["tags"])

    def test_issue_tag_contract_accounts_for_partial_and_engineering_states(self):
        partial = app._derive_issue_tag_contract(
            "Open",
            {
                "pipeline_state": app.PipelineState.ANALYZED.value,
                "is_ready_to_deploy": False,
                "is_data_only": False,
                "is_blocked": False,
                "needs_escalation": False,
                "is_jira_escalated_any": False,
                "has_stale_pipeline_step": True,
            },
        )
        engineering = app._derive_issue_tag_contract(
            "Open",
            {
                "pipeline_state": app.PipelineState.ENGINEERING_HANDOFF.value,
                "is_ready_to_deploy": False,
                "is_data_only": False,
                "is_blocked": False,
                "needs_escalation": True,
                "is_jira_escalated_any": False,
            },
        )

        self.assertEqual(partial["primary_tag"], "analyzed")
        self.assertEqual(partial["condition_tags"], ["partial run", "stale"])
        self.assertEqual(engineering["primary_tag"], "needs engineering")
        self.assertNotIn("needs escalation", engineering["tags"])

    def test_issue_tag_contract_primary_tags_are_exclusive_and_complete(self):
        base = {
            "pipeline_state": app.PipelineState.UNTRIAGED.value,
            "is_ready_to_deploy": False,
            "is_data_only": False,
            "is_blocked": False,
            "needs_escalation": False,
            "is_jira_escalated_any": False,
        }
        cases = [
            ("Closed", {**base}, "closed"),
            ("Escalated to Engineering", {**base}, "escalated to engineering"),
            ("Open", {**base, "is_blocked": True}, "blocked"),
            ("Open", {**base, "needs_escalation": True}, "needs engineering"),
            ("Open", {**base, "is_data_only": True}, "data only"),
            ("Open", {**base, "pipeline_state": app.PipelineState.VALIDATED.value, "is_ready_to_deploy": True}, "ready to deploy"),
            ("Open", {**base, "pipeline_state": app.PipelineState.VALIDATED.value}, "complete no deploy"),
            ("Open", {**base, "pipeline_state": app.PipelineState.ANALYZED.value}, "analyzed"),
            ("Open", {**base, "pipeline_state": app.PipelineState.INVESTIGATING.value}, "in progress"),
            ("Open", {**base}, "not triaged"),
        ]

        for status, flags, expected in cases:
            with self.subTest(expected=expected):
                contract = app._derive_issue_tag_contract(status, flags)
                self.assertEqual(contract["primary_tag"], expected)
                self.assertEqual(contract["tags"][0], expected)

    def test_issue_tag_contract_covers_all_condition_tags_without_legacy_synonyms(self):
        flags = {
            "pipeline_state": app.PipelineState.ANALYZED.value,
            "is_ready_to_deploy": False,
            "is_data_only": False,
            "is_blocked": False,
            "needs_escalation": False,
            "is_jira_escalated_any": False,
            "has_stale_pipeline_step": True,
            "has_failed_validation": True,
            "has_similar_issues": True,
            "has_generated_files": True,
            "needs_customer_reply": True,
        }

        contract = app._derive_issue_tag_contract("Open", flags, has_new_comments=True)

        self.assertEqual(contract["primary_tag"], "analyzed")
        self.assertEqual(
            contract["condition_tags"],
            [
                "new comments",
                "partial run",
                "stale",
                "failed validation",
                "similar issues",
                "generated files",
                "customer reply needed",
            ],
        )
        legacy_tags = {
            "validated",
            "needs escalation",
            "no support solution",
            "no solution identified",
            "pipeline complete",
            "ready deploy",
            "deploy ready",
            "production deploy",
            "engineering handoff",
            "jira escalated",
            "escalated to eng",
        }
        self.assertFalse(legacy_tags.intersection(contract["tags"]))

    def test_legacy_escalated_status_aliases_normalize_to_one_canonical_tag(self):
        for status in ("Escalated to Engineering", "Escalated to Eng", "Jira Escalated"):
            with self.subTest(status=status):
                self.assertEqual(app._disposition(status), "escalated")
                contract = app._derive_issue_tag_contract(
                    status,
                    {
                        "pipeline_state": app.PipelineState.UNTRIAGED.value,
                        "is_ready_to_deploy": False,
                        "is_data_only": False,
                        "is_blocked": False,
                        "needs_escalation": False,
                        "is_jira_escalated_any": True,
                    },
                )
                self.assertEqual(contract["tags"], ["escalated to engineering"])

    def test_issue_apis_return_backend_tag_contract(self):
        flags = {
            "pipeline_state": app.PipelineState.VALIDATED.value,
            "is_ready_to_deploy": True,
            "is_data_only": False,
            "is_blocked": False,
            "needs_escalation": False,
            "is_jira_escalated": False,
            "is_jira_escalated_any": False,
            "has_stale_pipeline_step": False,
            "has_failed_validation": False,
            "has_similar_issues": False,
            "has_generated_files": True,
            "needs_customer_reply": False,
        }
        row = {
            "Key": "OPEN-1",
            "Status": "Open",
            "Assignee": "Tester",
            "Summary": "Fixture issue",
            "Updated": "2026-06-08T00:00:00.000+0000",
            "Due": "",
            "Priority": "Medium",
            "HasNewComments": "true",
        }

        with (
            patch.object(app, "_read_manifest", return_value=[row]),
            patch.object(app, "_pipeline_file_flags", return_value=flags),
            patch.object(app, "_available_tabs", return_value=[]),
            patch.object(app, "read_issue_cluster_context", return_value={"issue": "OPEN-1", "cluster_id": ""}),
            patch.object(app, "_get_issue_reporter", return_value=""),
        ):
            client = app.app.test_client()
            issues_payload = client.get("/api/issues").get_json()
            issue_payload = client.get("/api/issue/OPEN-1").get_json()

        for payload in (issues_payload[0], issue_payload):
            self.assertEqual(payload["primary_tag"], "ready to deploy")
            self.assertEqual(payload["condition_tags"], ["new comments", "generated files"])
            self.assertEqual(payload["tags"], ["ready to deploy", "new comments", "generated files"])

    def test_default_env_file_ignores_removed_jira_env_alias(self):
        with patch.dict(os.environ, {"CASEOPS_JIRA_ENV_FILE": "/legacy/.env.jira"}, clear=True):
            self.assertEqual(
                caseops_paths.default_jira_env_file(),
                str(caseops_paths.PROJECT_ROOT / ".env"),
            )
        with patch.dict(os.environ, {"CASEOPS_ENV_FILE": "/data/.env", "CASEOPS_JIRA_ENV_FILE": "/legacy/.env.jira"}, clear=True):
            self.assertEqual(caseops_paths.default_jira_env_file(), "/data/.env")

if __name__ == "__main__":
    unittest.main()
