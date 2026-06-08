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
            ("Open", {**base, "pipeline_state": app.PipelineState.VALIDATED.value, "is_complete_no_deploy": True}, "complete no deploy"),
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

    def test_failed_validation_tag_ignores_historical_or_explanatory_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "OPEN-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Notes",
                        "Previous attempts were not fixed and were reverted.",
                        "This report explains why those tests failed before the current run.",
                        "No explicit failed verdict has been recorded for this run.",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(app, "OUTPUTS", Path(tmp)):
                self.assertFalse(app._test_report_indicates_failed_validation("OPEN-1"))

    def test_failed_validation_tag_uses_structured_report_verdicts(self):
        cases = {
            "FIELD-1": "Validation Status: failed\n",
            "FIELD-2": "Test Result: not fixed\n",
            "FIELD-3": "**Validation Status:** failed\n",
            "SECTION-1": "## Fixed?\nNo\n",
            "SECTION-2": "## Validation Result\nfailed\n",
            "TASK-1": "- [x] failed validation\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            for key, text in cases.items():
                (test_dir / f"{key}.md").write_text(text, encoding="utf-8")

            with patch.object(app, "OUTPUTS", Path(tmp)):
                for key in cases:
                    with self.subTest(key=key):
                        self.assertTrue(app._test_report_indicates_failed_validation(key))

    def test_confirmed_fix_wins_over_failed_validation_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "OPEN-1.md").write_text(
                "\n".join(
                    [
                        "## Fixed?",
                        "Yes, confirmed in Sandbox.",
                        "",
                        "## Notes",
                        "An earlier validation failed and was not fixed.",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(app, "OUTPUTS", Path(tmp)):
                self.assertTrue(app._test_report_confirms_fix("OPEN-1"))
                self.assertFalse(app._test_report_indicates_failed_validation("OPEN-1"))

    def test_canonical_validation_verdict_contract_controls_test_report_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "PASS-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: passed",
                        "- Fixed?: yes",
                        "- Production deploy required: yes",
                        "- Evidence: Sandbox validation run passed.",
                        "",
                        "Historical note: an earlier attempt failed validation.",
                    ]
                ),
                encoding="utf-8",
            )
            (test_dir / "FAIL-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: failed",
                        "- Fixed?: no",
                        "- Production deploy required: unknown",
                        "- Evidence: Acceptance criterion 2 did not pass.",
                    ]
                ),
                encoding="utf-8",
            )
            (test_dir / "PARTIAL-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: passed",
                        "- Fixed?: unknown",
                        "- Production deploy required: yes",
                        "- Evidence: Validation passed but fix confirmation is pending.",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(app, "OUTPUTS", Path(tmp)):
                self.assertTrue(app._test_report_confirms_fix("PASS-1"))
                self.assertFalse(app._test_report_indicates_failed_validation("PASS-1"))
                self.assertFalse(app._test_report_confirms_fix("FAIL-1"))
                self.assertTrue(app._test_report_indicates_failed_validation("FAIL-1"))
                self.assertFalse(app._test_report_confirms_fix("PARTIAL-1"))
                self.assertFalse(app._test_report_indicates_failed_validation("PARTIAL-1"))

    def test_blocked_validation_verdict_maps_to_blocked_primary_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "BLOCK-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: blocked",
                        "- Fixed?: unknown",
                        "- Production deploy required: unknown",
                        "- Evidence: Sandbox org permission is missing.",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(app, "OUTPUTS", Path(tmp)),
                patch.object(app, "_read_pipeline_state", return_value={}),
                patch.object(app, "_test_report_is_data_only", return_value=False),
                patch.object(app, "_calculate_pipeline_state", return_value=app.PipelineState.VALIDATED),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_issue_needs_customer_reply", return_value=False),
                patch.object(app, "_investigation_indicates_blocked", return_value=False),
            ):
                flags = app._pipeline_file_flags("BLOCK-1", "Open")
                contract = app._derive_issue_tag_contract("Open", flags)

            self.assertTrue(flags["is_blocked"])
            self.assertEqual(flags["test_report_verdict"]["validation_status"], "blocked")
            self.assertEqual(contract["primary_tag"], "blocked")

    def test_ready_to_deploy_uses_validation_verdict_deploy_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "DEPLOY-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: passed",
                        "- Fixed?: yes",
                        "- Production deploy required: yes",
                        "- Evidence: Sandbox validation passed.",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(app, "OUTPUTS", Path(tmp)),
                patch.object(app, "_read_pipeline_state", return_value={}),
                patch.object(app, "_test_report_is_data_only", return_value=False),
                patch.object(app, "_calculate_pipeline_state", return_value=app.PipelineState.VALIDATED),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_issue_needs_customer_reply", return_value=False),
                patch.object(app, "_investigation_indicates_blocked", return_value=False),
            ):
                flags = app._pipeline_file_flags("DEPLOY-1", "Open")
                contract = app._derive_issue_tag_contract("Open", flags)

            self.assertEqual(flags["production_deploy_required"], "yes")
            self.assertTrue(flags["is_ready_to_deploy"])
            self.assertEqual(contract["primary_tag"], "ready to deploy")

    def test_failed_verdict_does_not_become_complete_no_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "FAIL-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: failed",
                        "- Fixed?: no",
                        "- Production deploy required: no",
                        "- Evidence: Acceptance criterion failed.",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(app, "OUTPUTS", Path(tmp)),
                patch.object(app, "_read_pipeline_state", return_value={}),
                patch.object(app, "_test_report_is_data_only", return_value=False),
                patch.object(app, "_calculate_pipeline_state", return_value=app.PipelineState.VALIDATED),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_issue_needs_customer_reply", return_value=False),
                patch.object(app, "_investigation_indicates_blocked", return_value=False),
            ):
                flags = app._pipeline_file_flags("FAIL-1", "Open")
                contract = app._derive_issue_tag_contract("Open", flags)

            self.assertFalse(flags["is_complete_no_deploy"])
            self.assertTrue(flags["has_failed_validation"])
            self.assertEqual(contract["primary_tag"], "in progress")
            self.assertEqual(contract["condition_tags"], ["partial run", "failed validation"])

    def test_incomplete_contract_does_not_fall_through_to_legacy_failure_text(self):
        text = "\n".join(
            [
                "## Validation Verdict",
                "- Validation Status: not-run",
                "- Evidence: This action has not been executed.",
                "",
                "## Historical Notes",
                "Previous testing failed validation and was not fixed.",
                "- [x] failed validation",
            ]
        )

        verdict = app._parse_test_report_verdict_text(text)

        self.assertTrue(verdict["contract_present"])
        self.assertFalse(verdict["contract_complete"])
        self.assertFalse(app._structured_validation_verdict_failed(text))

    def test_complete_no_deploy_requires_confirmed_no_deploy_verdict_not_data_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "NODEPLOY-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: passed",
                        "- Fixed?: yes",
                        "- Production deploy required: no",
                        "- Evidence: Existing Production metadata already covers the fix.",
                    ]
                ),
                encoding="utf-8",
            )
            state = {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "support_resolvable"},
                "deliverable": {"type": "metadata_candidate", "production_deploy_required": "no"},
            }

            with (
                patch.object(app, "OUTPUTS", Path(tmp)),
                patch.object(app, "_read_pipeline_state", return_value=state),
                patch.object(app, "_test_report_is_data_only", return_value=False),
                patch.object(app, "_calculate_pipeline_state", return_value=app.PipelineState.VALIDATED),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_issue_needs_customer_reply", return_value=False),
                patch.object(app, "_investigation_indicates_blocked", return_value=False),
            ):
                flags = app._pipeline_file_flags("NODEPLOY-1", "Open")
                contract = app._derive_issue_tag_contract("Open", flags)

            self.assertFalse(flags["is_data_only"])
            self.assertTrue(flags["is_complete_no_deploy"])
            self.assertEqual(contract["primary_tag"], "complete no deploy")

    def test_data_only_requires_data_or_admin_action_evidence_and_confirmed_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "DATA-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: passed",
                        "- Fixed?: yes",
                        "- Production deploy required: n/a",
                        "- Evidence: Operator completed and verified the data correction.",
                    ]
                ),
                encoding="utf-8",
            )
            state = {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "support_resolvable"},
                "deliverable": {
                    "type": "admin_action",
                    "production_deploy_required": "n/a",
                    "no_deploy_reason": "Existing permission set assignment.",
                },
            }

            with (
                patch.object(app, "OUTPUTS", Path(tmp)),
                patch.object(app, "_read_pipeline_state", return_value=state),
                patch.object(app, "_test_report_is_data_only", return_value=False),
                patch.object(app, "_calculate_pipeline_state", return_value=app.PipelineState.VALIDATED),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_issue_needs_customer_reply", return_value=False),
                patch.object(app, "_investigation_indicates_blocked", return_value=False),
            ):
                flags = app._pipeline_file_flags("DATA-1", "Open")
                contract = app._derive_issue_tag_contract("Open", flags)

            self.assertTrue(flags["is_data_only"])
            self.assertFalse(flags["is_complete_no_deploy"])
            self.assertEqual(contract["primary_tag"], "data only")

    def test_unexecuted_operator_action_verdict_stays_in_progress_not_data_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "TODO-1.md").write_text(
                "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: not-run",
                        "- Fixed?: unknown",
                        "- Production deploy required: n/a",
                        "- Evidence: Operator action has not been executed by CaseOps.",
                    ]
                ),
                encoding="utf-8",
            )
            state = {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "support_resolvable"},
                "deliverable": {
                    "type": "admin_action",
                    "production_deploy_required": "n/a",
                    "no_deploy_reason": "Operator action not executed.",
                },
            }

            with (
                patch.object(app, "OUTPUTS", Path(tmp)),
                patch.object(app, "_read_pipeline_state", return_value=state),
                patch.object(app, "_test_report_is_data_only", return_value=False),
                patch.object(app, "_calculate_pipeline_state", return_value=app.PipelineState.VALIDATED),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_issue_needs_customer_reply", return_value=False),
                patch.object(app, "_investigation_indicates_blocked", return_value=False),
            ):
                flags = app._pipeline_file_flags("TODO-1", "Open")
                contract = app._derive_issue_tag_contract("Open", flags)

            self.assertFalse(flags["is_data_only"])
            self.assertFalse(flags["is_complete_no_deploy"])
            self.assertEqual(contract["primary_tag"], "in progress")

    def test_test_report_file_api_returns_parsed_validation_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_dir = Path(tmp) / "test-reports"
            test_dir.mkdir(parents=True)
            (test_dir / "OPEN-1.md").write_text(
                "\n".join(
                    [
                        "# Test Report",
                        "",
                        "## Validation Verdict",
                        "- Validation Status: passed",
                        "- Fixed?: yes",
                        "- Production deploy required: no",
                        "- Evidence: Acceptance criteria passed in Sandbox.",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(app, "OUTPUTS", Path(tmp)):
                payload = app.app.test_client().get("/api/issue/OPEN-1/file/test_report").get_json()

            self.assertEqual(payload["test_report_verdict"]["validation_status"], "passed")
            self.assertEqual(payload["test_report_verdict"]["fixed"], "yes")
            self.assertEqual(payload["test_report_verdict"]["production_deploy_required"], "no")

    def test_available_tabs_include_all_generated_markdown_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            for ftype, rel in app.FILE_LOCATIONS.items():
                path = outputs / rel.format(key="OPEN-1")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# {ftype}\n", encoding="utf-8")

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "read_issue_cluster_context", return_value={}),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
            ):
                tabs = app._available_tabs("OPEN-1")

        self.assertEqual(
            [tab["id"] for tab in tabs],
            [
                "jira_summary",
                "investigation",
                "hypothesis",
                "internal_notes",
                "jira_message",
                "test_report",
                "eng_handoff",
                "closed_resolved",
            ],
        )

    def test_no_deploy_operator_report_allows_step10_drafts_without_terminal_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            files = {
                "jira/summary/OPEN-1.md": "# Jira Summary\n",
                "investigations/OPEN-1.md": (
                    "## Problem Location\n"
                    "Specific artifact: PermissionSetAssignment for an existing permission set.\n"
                    "Failure point: user is missing the existing permission assignment.\n"
                    "Root cause: missing assignment.\n"
                    "Support-resolvable classification complete.\n"
                ),
                "hypothesis/OPEN-1.md": (
                    "## Hypothesis\n"
                    "Problem focus: missing existing permission set assignment.\n"
                    "Root cause hypothesis: missing existing permission assignment.\n"
                ),
                "test-reports/OPEN-1.md": "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: not-run",
                        "- Fixed?: unknown",
                        "- Production deploy required: n/a",
                        "- Evidence: Operator action has not been executed by CaseOps.",
                    ]
                ),
            }
            for name, text in files.items():
                path = outputs / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            prod_org = app._safe_path_component(os.environ.get("CASEOPS_PRODUCTION_READ_ORG") or "production", "production")
            api_version_raw = os.environ.get("CASEOPS_SALESFORCE_API_VERSION") or os.environ.get("SF_API_VERSION") or "v66.0"
            api_version = app._safe_path_component(api_version_raw if str(api_version_raw).startswith("v") else f"v{api_version_raw}", "v66.0")
            raw_metadata = outputs / "metadata-cache" / "production" / prod_org / api_version / "raw" / "OPEN-1" / "fixture.txt"
            raw_metadata.parent.mkdir(parents=True, exist_ok=True)
            raw_metadata.write_text("metadata evidence", encoding="utf-8")
            state = {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "support_resolvable", "confidence": "high"},
                "deliverable": {
                    "type": "admin_action",
                    "production_deploy_required": "n/a",
                    "no_deploy_reason": "Existing permission set assignment by operator.",
                },
                "signatures": {},
            }

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "_read_pipeline_state", return_value=state),
                patch.object(app, "_latest_issue_summary_path", return_value=None),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
            ):
                plan = app._build_pipeline_resume_plan("OPEN-1", status="Open")
                flags = app._pipeline_file_flags("OPEN-1", "Open")
                contract = app._derive_issue_tag_contract("Open", flags)

        step9 = next(step for step in plan["steps"] if step["step"] == 9)
        step10 = next(step for step in plan["steps"] if step["step"] == 10)
        self.assertEqual(step9["status"], "complete")
        self.assertIn("operator action report", step9["reason"])
        self.assertEqual(step10["status"], "pending")
        self.assertEqual(plan["quality_gates"]["step_9_test_report"], "operator_action_pending")
        self.assertEqual(contract["primary_tag"], "in progress")
        self.assertIn("partial run", contract["condition_tags"])

    def test_bulk_pipeline_state_repair_repairs_only_stale_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            state_dir = outputs / "pipeline-state"
            state_dir.mkdir(parents=True)
            (state_dir / "STALE-1.json").write_text(
                '{"steps":[{"step":9,"name":"Deploy and test in Sandbox","status":"stale"}]}',
                encoding="utf-8",
            )
            (state_dir / "CURRENT-1.json").write_text(
                '{"steps":[{"step":9,"name":"Deploy and test in Sandbox","status":"complete"}]}',
                encoding="utf-8",
            )
            calls = []

            def repair_key(key, row=None, *, emit_manifest=True):
                calls.append((key, emit_manifest))
                return {
                    "ok": True,
                    "key": key,
                    "plan_path": f"pipeline-state/{key}.json",
                    "next_step": {"step": 10, "name": "Draft internal notes and Jira message"},
                }

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "_read_manifest", return_value=[
                    {"Key": "STALE-1", "Status": "Open"},
                    {"Key": "CURRENT-1", "Status": "Open"},
                ]),
                patch.object(app, "_repair_pipeline_state_key", side_effect=repair_key),
                patch.object(app, "manifest_changed") as manifest_changed_mock,
            ):
                payload = app.app.test_client().post("/api/pipeline-state/repair-all", json={"scope": "stale"}).get_json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["repaired_count"], 1)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(calls, [("STALE-1", False)])
        manifest_changed_mock.assert_called_once_with(["STALE-1"])

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
