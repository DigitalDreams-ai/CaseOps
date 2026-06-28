import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import knowledge_service


class KnowledgeServiceTests(unittest.TestCase):
    def test_seed_core_knowledge_preserves_runtime_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            runtime_file = outputs / "org-knowledge" / "run-rules.md"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_text("operator edit\n", encoding="utf-8")

            knowledge_service.ensure_knowledge_defaults(outputs)

            self.assertEqual(runtime_file.read_text(encoding="utf-8"), "operator edit\n")
            self.assertTrue((outputs / "org-knowledge" / "index.json").exists())
            self.assertTrue((outputs / "org-knowledge" / "org-profile" / "README.md").exists())
            self.assertTrue((outputs / "org-knowledge" / "signals").is_dir())
            self.assertTrue((outputs / "org-knowledge" / "pending-lessons").is_dir())

    def test_selection_diagnostics_include_layer_type_and_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)

            selections = knowledge_service.select_knowledge(
                outputs,
                "OPEN-1",
                {"Summary": "Permission set FLS access issue", "Status": "Open"},
                "",
            )
            diagnostics = knowledge_service.selection_diagnostics(selections)

        paths = {item["path"] for item in diagnostics}
        self.assertIn("run-rules.md", paths)
        self.assertTrue(any(item["layer"] == "core" for item in diagnostics))
        self.assertTrue(any(item["knowledge_type"] in {"helper_contract", "gotcha", "query_pattern"} for item in diagnostics))
        self.assertTrue(any(item["reasons"] for item in diagnostics))

    def test_signal_redacts_secret_like_values_and_validates_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)

            signal = knowledge_service.write_signal(
                outputs,
                issue_key="OPEN-1",
                run_id="OPEN-1",
                source_step="STEP_5",
                signal_type="helper_failure",
                topic="share-objects",
                summary="helper failed with access_token=secret-token-value",
                evidence=["frontdoor.jsp?sid=00D0b000000vHFc!AQEAQSecretSecretSecretSecret"],
                helper_available="sobject-fields",
            )

            saved = json.loads(
                (outputs / "org-knowledge" / "signals" / f"{signal['signal_id']}.json").read_text(encoding="utf-8")
            )

        self.assertNotIn("secret-token-value", json.dumps(saved))
        self.assertIn("[REDACTED]", json.dumps(saved))

    def test_manual_auditor_creates_pending_lessons_without_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            for key in ("OPEN-1", "OPEN-2"):
                knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="STEP_5",
                    signal_type="invalid_query_field",
                    topic="share-objects",
                    summary="SOQL queried invalid UserShare.Name field.",
                    evidence=["No such column 'Name' on entity 'UserShare'"],
                    helper_available="sobject-fields",
                )

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))
            accepted = list((outputs / "org-knowledge" / "accepted-lessons").glob("*.json"))
            second = knowledge_service.run_manual_audit(outputs, min_recurrence=2)

        self.assertEqual(summary["candidates_created"], 1)
        self.assertEqual(len(pending), 1)
        self.assertEqual(accepted, [])
        self.assertEqual(second["candidates_created"], 0)

    def test_manual_auditor_does_not_process_below_threshold_singletons(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            knowledge_service.write_signal(
                outputs,
                issue_key="OPEN-1",
                run_id="OPEN-1",
                source_step="STEP_5",
                signal_type="invalid_query_field",
                topic="share-objects",
                summary="SOQL queried invalid UserShare.Name field.",
                evidence=["No such column 'Name' on entity 'UserShare'"],
                helper_available="sobject-fields",
            )

            first = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            state_after_first = json.loads(
                (outputs / "org-knowledge" / "audit-reports" / "knowledge-auditor-state.json").read_text(encoding="utf-8")
            )
            knowledge_service.write_signal(
                outputs,
                issue_key="OPEN-2",
                run_id="OPEN-2",
                source_step="STEP_5",
                signal_type="invalid_query_field",
                topic="share-objects",
                summary="SOQL queried invalid UserShare.Name field.",
                evidence=["No such column 'Name' on entity 'UserShare'"],
                helper_available="sobject-fields",
            )
            second = knowledge_service.run_manual_audit(outputs, min_recurrence=2)

        self.assertEqual(first["candidates_created"], 0)
        self.assertEqual(state_after_first["processed_signal_ids"], [])
        self.assertEqual(second["candidates_created"], 1)
        self.assertEqual(second["signals_consumed"], 2)

    def test_accepted_lessons_are_selected_but_pending_and_rejected_are_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            base = {
                "schema_version": 1,
                "candidate_id": "lesson-access-1",
                "source_signal_ids": ["sig-1"],
                "affected_issue_keys": ["OPEN-1"],
                "topic": "share-objects",
                "trigger": "UserShare Name field failed",
                "lesson": "Describe UserShare before querying fields.",
                "evidence": ["No such column Name"],
                "recommended_file": "local-gotchas/access-and-visibility.md",
                "knowledge_type": "query_pattern",
                "org_specific": False,
                "confidence": "high",
                "recurrence_count": 2,
                "risk": "low",
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "accepted",
                "keywords": ["UserShare"],
            }
            accepted_json = outputs / "org-knowledge" / "accepted-lessons" / "lesson-access-1.json"
            accepted_md = outputs / "org-knowledge" / "accepted-lessons" / "lesson-access-1.md"
            accepted_json.parent.mkdir(parents=True, exist_ok=True)
            accepted_json.write_text(json.dumps(base), encoding="utf-8")
            accepted_md.write_text("# Accepted\nDescribe UserShare before querying fields.\n", encoding="utf-8")
            pending = dict(base, candidate_id="lesson-access-2", status="pending")
            rejected = dict(base, candidate_id="lesson-access-3", status="rejected")
            (outputs / "org-knowledge" / "pending-lessons" / "lesson-access-2.json").write_text(json.dumps(pending), encoding="utf-8")
            (outputs / "org-knowledge" / "rejected-lessons" / "lesson-access-3.json").write_text(json.dumps(rejected), encoding="utf-8")

            selections = knowledge_service.select_knowledge(
                outputs,
                "OPEN-1",
                {"Summary": "UserShare access issue", "Status": "Open"},
                "",
            )

        rels = {item.rel_path for item in selections}
        self.assertIn("accepted-lessons/lesson-access-1.md", rels)
        self.assertNotIn("pending-lessons/lesson-access-2.json", rels)
        self.assertNotIn("rejected-lessons/lesson-access-3.json", rels)

    def test_review_actions_accept_reject_retire_and_convert_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            candidate = {
                "schema_version": 1,
                "candidate_id": "lesson-review-1",
                "source_signal_ids": ["sig-1", "sig-2"],
                "affected_issue_keys": ["OPEN-1", "OPEN-2"],
                "topic": "deploy",
                "trigger": "Repeated helper failure",
                "lesson": "Use deploy-mdapi after source tracking failures.",
                "evidence": ["NothingToDeploy"],
                "recommended_file": "local-gotchas/deploy-and-sandbox.md",
                "knowledge_type": "deploy_pattern",
                "org_specific": False,
                "confidence": "medium",
                "recurrence_count": 2,
                "risk": "low",
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "pending",
            }
            pending_path = outputs / "org-knowledge" / "pending-lessons" / "lesson-review-1.json"
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.write_text(json.dumps(candidate), encoding="utf-8")

            helper = knowledge_service.convert_to_helper_work_item(outputs, "lesson-review-1")
            accepted = knowledge_service.accept_lesson(outputs, "lesson-review-1")
            retired = knowledge_service.retire_lesson(outputs, "lesson-review-1", reason="replaced by helper")

            pending_path_2 = outputs / "org-knowledge" / "pending-lessons" / "lesson-review-2.json"
            pending_2 = dict(candidate, candidate_id="lesson-review-2")
            pending_path_2.write_text(json.dumps(pending_2), encoding="utf-8")
            rejected = knowledge_service.reject_lesson(outputs, "lesson-review-2", reason="too broad")

        self.assertEqual(helper["source_candidate_id"], "lesson-review-1")
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(retired["status"], "retired")
        self.assertEqual(rejected["status"], "rejected")

    def test_guardrail_command_classification(self):
        legacy = knowledge_service.classify_guardrail_command("sfdx force:source:deploy -p force-app")
        manifest = knowledge_service.classify_guardrail_command("sf project deploy start --manifest package.xml")
        usershare = knowledge_service.classify_guardrail_command("sf data query --query 'SELECT Id, Name FROM UserShare'")

        self.assertFalse(legacy["ok"])
        self.assertTrue(any(item["rule"] == "routine_manifest_deploy" for item in manifest["findings"]))
        self.assertFalse(usershare["ok"])

    def test_knowledge_review_api_accepts_pending_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            candidate = {
                "schema_version": 1,
                "candidate_id": "lesson-api-1",
                "source_signal_ids": ["sig-1", "sig-2"],
                "affected_issue_keys": ["OPEN-1", "OPEN-2"],
                "topic": "share-objects",
                "trigger": "Repeated invalid field",
                "lesson": "Describe share objects before querying fields.",
                "evidence": ["No such column Name"],
                "recommended_file": "local-gotchas/access-and-visibility.md",
                "knowledge_type": "query_pattern",
                "org_specific": False,
                "confidence": "medium",
                "recurrence_count": 2,
                "risk": "low",
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "pending",
            }
            pending = outputs / "org-knowledge" / "pending-lessons" / "lesson-api-1.json"
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(json.dumps(candidate), encoding="utf-8")

            with patch.object(app, "OUTPUTS", outputs):
                client = app.app.test_client()
                review_before = client.get("/api/knowledge/review")
                accepted = client.post("/api/knowledge/review/lesson-api-1/accept", json={})
                review_after = client.get("/api/knowledge/review")

        self.assertEqual(review_before.status_code, 200)
        self.assertEqual(len(review_before.get_json()["items"]["pending_lessons"]), 1)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["item"]["status"], "accepted")
        self.assertEqual(len(review_after.get_json()["items"]["pending_lessons"]), 0)
        self.assertEqual(len(review_after.get_json()["items"]["accepted_lessons"]), 1)

    def test_issue_detail_exposes_selected_knowledge_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(
                    app,
                    "_read_manifest",
                    return_value=[{
                        "Key": "OPEN-1",
                        "Status": "Open",
                        "Summary": "Custom field picklist value is not visible on layout",
                        "Assignee": "CaseOps User",
                    }],
                ),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_read_pipeline_state", return_value={}),
            ):
                client = app.app.test_client()
                issue_payload = client.get("/api/issue/OPEN-1").get_json()
                diagnostics = client.get("/api/knowledge/diagnostics/OPEN-1").get_json()

        self.assertIn("caseops_knowledge", [tab["id"] for tab in issue_payload["tabs"]])
        selected_paths = {item["path"] for item in diagnostics["selected"]}
        self.assertIn("run-rules.md", selected_paths)
        self.assertIn("query-patterns/custom-field.md", selected_paths)
        self.assertTrue(any("matched keywords" in " ".join(item["reasons"]) for item in diagnostics["selected"]))

    def test_guardrail_check_api(self):
        response = app.app.test_client().post(
            "/api/knowledge/guardrail-check",
            json={"command": "sfdx force:source:deploy -p force-app"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["result"]["ok"])

        missing = app.app.test_client().post(
            "/api/knowledge/guardrail-check",
            json={"command": ""},
        )

        self.assertEqual(missing.status_code, 400)
        self.assertFalse(missing.get_json()["ok"])

    def test_pipeline_failure_artifact_writes_knowledge_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            log_dir = outputs / "pipeline-logs"
            log_dir.mkdir(parents=True)
            log_path = log_dir / "OPEN-1.jsonl"
            log_path.write_text(
                "\n".join([
                    json.dumps({"ts": "2026-06-26T12:00:00+00:00", "text": "STEP_5 OPEN-1"}),
                    json.dumps({"ts": "2026-06-26T12:02:00+00:00", "text": "[Bash] python scripts/sf_caseops_helper.py query-data --org prod --soql 'SELECT Id FROM Case'"}),
                    json.dumps({"ts": "2026-06-26T12:03:00+00:00", "text": '{"failure_class":"invalid_field","retryable":false}'}),
                ])
                + "\n",
                encoding="utf-8",
            )

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "OUTPUTS_PIPELINE_LOGS", log_dir),
                patch.object(app, "_log_emit_line"),
            ):
                app._write_pipeline_failure_artifact(
                    "OPEN-1",
                    "OPEN-1",
                    failure_class="claude_exit_failure",
                    reason="failed",
                    retryable=False,
                    next_action="inspect helper failure",
                )

            signals = list((outputs / "org-knowledge" / "signals").glob("*.json"))
            self.assertEqual(len(signals), 1)
            saved = json.loads(signals[0].read_text(encoding="utf-8"))

        self.assertEqual(saved["signal_type"], "helper_failure")


if __name__ == "__main__":
    unittest.main()
