import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import knowledge_service


class KnowledgeServiceTests(unittest.TestCase):
    def test_invalid_salesforce_query_classification_wins_over_production_wording(self):
        failure_class = knowledge_service.classify_failure_class(
            "invalid_query_type",
            "salesforce-query",
            "Repeated Salesforce INVALID_TYPE errors while querying optional metadata in Production.",
        )

        self.assertEqual(failure_class, "invalid_salesforce_assumption")

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

    def test_manual_auditor_derives_signals_from_pipeline_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            logs = outputs / "pipeline-logs"
            logs.mkdir(parents=True)
            for key in ("OPEN-1", "OPEN-2"):
                record = {
                    "ts": "2026-06-28T17:00:00+00:00",
                    "run_key": key,
                    "kind": "line",
                    "text": 'Tool warning: command returned exit code 1. {"name":"INVALID_TYPE","errorCode":"INVALID_TYPE"}',
                }
                (logs / f"{key}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            signals = list((outputs / "org-knowledge" / "signals").glob("*.json"))
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))
            helpers = list((outputs / "org-knowledge" / "helper-work-items").glob("*.json"))
            second = knowledge_service.run_manual_audit(outputs, min_recurrence=2)

        self.assertEqual(summary["log_signals_created"], 2)
        self.assertEqual(summary["signals_reviewed"], 2)
        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(summary["helper_only_groups"], 1)
        self.assertEqual(len(signals), 2)
        self.assertEqual(pending, [])
        self.assertEqual(len(helpers), 1)
        self.assertEqual(second["log_signals_created"], 0)
        self.assertEqual(second["candidates_created"], 0)

    def test_manual_auditor_reports_scope_and_global_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            logs = outputs / "pipeline-logs"
            logs.mkdir(parents=True)
            issue_record = {
                "ts": "2026-06-28T17:00:00+00:00",
                "run_key": "OPEN-1",
                "kind": "line",
                "text": 'Tool warning: command returned exit code 1. {"name":"INVALID_TYPE","errorCode":"INVALID_TYPE"}',
            }
            global_record = {
                "ts": "2026-06-28T17:01:00+00:00",
                "run_key": "__global__",
                "kind": "line",
                "text": 'Tool warning: command returned exit code 1. {"name":"INVALID_TYPE","errorCode":"INVALID_TYPE"}',
            }
            (logs / "OPEN-1.jsonl").write_text(json.dumps(issue_record) + "\n", encoding="utf-8")
            (logs / "__global__.jsonl").write_text(json.dumps(global_record) + "\n", encoding="utf-8")

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)

        self.assertEqual(summary["issue_logs_scanned"], 1)
        self.assertEqual(summary["global_logs_scanned"], 1)
        self.assertEqual(summary["global_logs_excluded_reason"], "")
        self.assertIn("signals_considered", summary)
        self.assertIn("signals_skipped", summary)
        self.assertEqual(summary["redaction_status"], "not_needed")

    def test_low_and_report_only_findings_do_not_create_pending_lessons(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            for key in ("OPEN-1", "OPEN-2"):
                knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="STEP_5",
                    signal_type="missing_file_or_directory",
                    topic="mixed-missing-files",
                    summary="No such file or directory appeared in a broad context.",
                    evidence=["No such file or directory"],
                )

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))

        self.assertEqual(summary["suppressed_groups"], 1)
        self.assertEqual(pending, [])

    def test_decision_artifact_schema_redacts_or_blocks_unsafe_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)

            artifact = knowledge_service.write_decision_artifact(
                outputs,
                issue_key="OPEN-1",
                decision_type="helper_failure",
                belief="Helper failed and needs developer review.",
                evidence=["access_token=secret-value"],
                action_or_refusal="Created a helper work item.",
                next_need="Developer reviews helper output.",
                failure_class="helper_failure",
                source="unit-test",
            )
            stored = json.loads(
                (outputs / "org-knowledge" / "decision-artifacts" / f"{artifact['artifact_id']}.json").read_text(encoding="utf-8")
            )

        self.assertEqual(stored["schema_version"], 1)
        self.assertEqual(stored["redaction_status"], "redacted")
        self.assertIn("[REDACTED]", json.dumps(stored))
        self.assertNotIn("secret-value", json.dumps(stored))

    def test_manual_auditor_routes_invalid_type_to_helper_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            for key in ("OPEN-1", "OPEN-2", "OPEN-3"):
                knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="LOG",
                    signal_type="invalid_query_type",
                    topic="salesforce-query",
                    summary="Salesforce query or metadata command hit an invalid type error.",
                    evidence=['{"name":"INVALID_TYPE"}'],
                )

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))
            helper = json.loads(next((outputs / "org-knowledge" / "helper-work-items").glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(summary["helper_only_groups"], 1)
        self.assertEqual(summary["helper_work_items_created"], 1)
        self.assertEqual(pending, [])
        self.assertIn("verify an object or metadata type exists", helper["lesson"])
        self.assertIn("INVALID_TYPE", helper["evidence"][0] if helper["evidence"] else "INVALID_TYPE")

    def test_manual_auditor_routes_json_decode_to_helper_work_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            for key in ("OPEN-1", "OPEN-2"):
                knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="LOG",
                    signal_type="json_decode_error",
                    topic="salesforce-cli-output",
                    summary="A command expected JSON output but received non-JSON output.",
                    evidence=["json.decoder.JSONDecodeError: Expecting value: line 1 column 1"],
                )

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))
            helpers = list((outputs / "org-knowledge" / "helper-work-items").glob("*.json"))
            second = knowledge_service.run_manual_audit(outputs, min_recurrence=2)

        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(summary["helper_only_groups"], 1)
        self.assertEqual(summary["helper_work_items_created"], 1)
        self.assertEqual(pending, [])
        self.assertEqual(len(helpers), 1)
        self.assertEqual(second["helper_work_items_created"], 0)

    def test_manual_auditor_normalizes_legacy_helper_work_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            signal = knowledge_service.write_signal(
                outputs,
                issue_key="OPEN-1",
                run_id="OPEN-1",
                source_step="LOG",
                signal_type="invalid_query_type",
                topic="salesforce-query",
                summary="Salesforce INVALID_TYPE occurred while querying an optional object.",
                evidence=["INVALID_TYPE"],
            )
            helper = {
                "schema_version": 1,
                "work_item_id": "helper-legacy-invalid-type",
                "source_candidate_id": "lesson-legacy-invalid_query_type",
                "source_signal_ids": [signal["signal_id"]],
                "affected_issue_keys": ["OPEN-1"],
                "topic": "salesforce-query",
                "summary": "Evaluate helper support for INVALID_TYPE.",
                "lesson": "Verify object existence before retrying.",
                "evidence": ["INVALID_TYPE"],
                "status": "pending",
                "created_at": "2026-06-28T00:00:00+00:00",
            }
            helper_path = outputs / "org-knowledge" / "helper-work-items" / "helper-legacy-invalid-type.json"
            helper_path.write_text(json.dumps(helper), encoding="utf-8")

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            updated = json.loads(helper_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["helper_work_items_refined"], 1)
        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(updated["route"], "helper_work_item")
        self.assertEqual(updated["failure_class"], "invalid_salesforce_assumption")
        self.assertEqual(updated["quality"], "high")
        self.assertEqual(updated["redaction_status"], "not_needed")

    def test_manual_auditor_suppresses_broad_missing_file_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            for key in ("OPEN-1", "OPEN-2"):
                knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="LOG",
                    signal_type="missing_file_or_directory",
                    topic="filesystem",
                    summary="Pipeline command referenced a missing file, directory, or command.",
                    evidence=["ls: cannot access path: No such file or directory"],
                )

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))

        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(summary["suppressed_groups"], 1)
        self.assertEqual(summary["signals_consumed"], 2)
        self.assertEqual(pending, [])

    def test_manual_auditor_routes_invalid_sfdx_workspace_to_helper_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            for key in ("OPEN-1", "OPEN-2"):
                knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="LOG",
                    signal_type="invalid_sfdx_workspace",
                    topic="deploy-command",
                    summary="Salesforce CLI command ran outside a valid Salesforce DX project workspace.",
                    evidence=["InvalidProjectWorkspaceError: /app does not contain a valid Salesforce DX project."],
                )

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))
            helper = json.loads(next((outputs / "org-knowledge" / "helper-work-items").glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(summary["helper_only_groups"], 1)
        self.assertEqual(summary["helper_work_items_created"], 1)
        self.assertEqual(pending, [])
        self.assertIn("workspace-init", helper["lesson"])
        self.assertIn("InvalidProjectWorkspaceError", helper["evidence"][0] if helper["evidence"] else "InvalidProjectWorkspaceError")

    def test_manual_auditor_refines_existing_pending_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            signal_a = knowledge_service.write_signal(
                outputs,
                issue_key="OPEN-1",
                run_id="OPEN-1",
                source_step="LOG",
                signal_type="invalid_query_type",
                topic="salesforce-query",
                summary="Salesforce query or metadata command hit an invalid type error.",
                evidence=['{"name":"INVALID_TYPE"}'],
            )
            signal_b = knowledge_service.write_signal(
                outputs,
                issue_key="OPEN-2",
                run_id="OPEN-2",
                source_step="LOG",
                signal_type="invalid_query_type",
                topic="salesforce-query",
                summary="Salesforce query or metadata command hit an invalid type error.",
                evidence=['{"name":"INVALID_TYPE"}'],
            )
            old_candidate = {
                "schema_version": 1,
                "candidate_id": "lesson-old-invalid-query-type",
                "source_signal_ids": [signal_a["signal_id"], signal_b["signal_id"]],
                "affected_issue_keys": ["OPEN-1", "OPEN-2"],
                "topic": "salesforce-query",
                "trigger": "Repeated invalid query type signal for salesforce-query.",
                "lesson": "Salesforce query or metadata command hit an invalid type error.",
                "evidence": ['{"name":"INVALID_TYPE"}'],
                "recommended_file": "local-gotchas/access-and-visibility.md",
                "knowledge_type": "query_pattern",
                "org_specific": False,
                "confidence": "medium",
                "recurrence_count": 2,
                "risk": "low",
                "keywords": ["UserShare"],
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "pending",
            }
            pending_path = outputs / "org-knowledge" / "pending-lessons" / "lesson-old-invalid-query-type.json"
            pending_path.write_text(json.dumps(old_candidate), encoding="utf-8")

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))
            helpers = list((outputs / "org-knowledge" / "helper-work-items").glob("*.json"))
            rejected = json.loads(next((outputs / "org-knowledge" / "rejected-lessons").glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(summary["pending_lessons_converted_to_helper"], 1)
        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(pending, [])
        self.assertEqual(len(helpers), 1)
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["refinement_action"], "helper_work_item")

    def test_manual_auditor_converts_existing_json_decode_pending_to_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            source_ids = []
            for key in ("OPEN-1", "OPEN-2"):
                signal = knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="LOG",
                    signal_type="json_decode_error",
                    topic="salesforce-cli-output",
                    summary="A command expected JSON output but received non-JSON output.",
                    evidence=["json.decoder.JSONDecodeError: Expecting value"],
                )
                source_ids.append(signal["signal_id"])
            candidate = {
                "schema_version": 1,
                "candidate_id": "lesson-old-json-decode",
                "source_signal_ids": source_ids,
                "affected_issue_keys": ["OPEN-1", "OPEN-2"],
                "topic": "salesforce-cli-output",
                "trigger": "Repeated json decode error signal for salesforce-cli-output.",
                "lesson": "A command expected JSON output but received non-JSON output.",
                "evidence": ["json.decoder.JSONDecodeError: Expecting value"],
                "recommended_file": "lessons-learned/general.md",
                "knowledge_type": "lesson_learned",
                "org_specific": False,
                "confidence": "medium",
                "recurrence_count": 2,
                "risk": "low",
                "keywords": ["UserShare"],
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "pending",
            }
            (outputs / "org-knowledge" / "pending-lessons" / "lesson-old-json-decode.json").write_text(json.dumps(candidate), encoding="utf-8")

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            pending = list((outputs / "org-knowledge" / "pending-lessons").glob("*.json"))
            helpers = list((outputs / "org-knowledge" / "helper-work-items").glob("*.json"))
            rejected = list((outputs / "org-knowledge" / "rejected-lessons").glob("*.json"))

        self.assertEqual(summary["pending_lessons_converted_to_helper"], 1)
        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(pending, [])
        self.assertEqual(len(helpers), 1)
        self.assertEqual(len(rejected), 1)

    def test_manual_auditor_refines_existing_accepted_lessons(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            source_ids = []
            for key in ("OPEN-1", "OPEN-2"):
                signal = knowledge_service.write_signal(
                    outputs,
                    issue_key=key,
                    run_id=key,
                    source_step="LOG",
                    signal_type="invalid_sfdx_workspace",
                    topic="deploy-command",
                    summary="Salesforce CLI command ran outside a valid Salesforce DX project workspace.",
                    evidence=["InvalidProjectWorkspaceError: /app does not contain a valid Salesforce DX project."],
                )
                source_ids.append(signal["signal_id"])
            accepted = {
                "schema_version": 1,
                "candidate_id": "lesson-old-sfdx-workspace",
                "source_signal_ids": source_ids,
                "affected_issue_keys": ["OPEN-1", "OPEN-2"],
                "topic": "deploy-command",
                "trigger": "Repeated invalid sfdx workspace signal for deploy-command.",
                "lesson": "Salesforce CLI command ran outside a valid Salesforce DX project workspace.",
                "evidence": ["InvalidProjectWorkspaceError"],
                "recommended_file": "local-gotchas/deploy-and-sandbox.md",
                "knowledge_type": "deploy_pattern",
                "org_specific": False,
                "confidence": "medium",
                "recurrence_count": 2,
                "risk": "low",
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "accepted",
            }
            accepted_path = outputs / "org-knowledge" / "accepted-lessons" / "lesson-old-sfdx-workspace.json"
            accepted_path.write_text(json.dumps(accepted), encoding="utf-8")

            summary = knowledge_service.run_manual_audit(outputs, min_recurrence=2)
            accepted_remaining = list((outputs / "org-knowledge" / "accepted-lessons").glob("*.json"))
            retired = json.loads(next((outputs / "org-knowledge" / "rejected-lessons").glob("*.json")).read_text(encoding="utf-8"))
            helpers = list((outputs / "org-knowledge" / "helper-work-items").glob("*.json"))

        self.assertEqual(summary["accepted_lessons_refined"], 0)
        self.assertEqual(summary["accepted_lessons_retired"], 1)
        self.assertEqual(summary["candidates_created"], 0)
        self.assertEqual(accepted_remaining, [])
        self.assertEqual(len(helpers), 1)
        self.assertEqual(retired["status"], "retired")
        self.assertEqual(retired["refinement_action"], "helper_work_item")

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
                "keywords": ["UserShare"],
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "pending",
            }
            pending_path = outputs / "org-knowledge" / "pending-lessons" / "lesson-review-1.json"
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.write_text(json.dumps(candidate), encoding="utf-8")

            helper = knowledge_service.convert_to_helper_work_item(outputs, "lesson-review-1")
            with self.assertRaises(FileNotFoundError):
                knowledge_service.accept_lesson(outputs, "lesson-review-1")
            rejected_converted = outputs / "org-knowledge" / "rejected-lessons" / "lesson-review-1.json"
            self.assertTrue(rejected_converted.exists())

            pending_path_2 = outputs / "org-knowledge" / "pending-lessons" / "lesson-review-2.json"
            pending_2 = dict(candidate, candidate_id="lesson-review-2")
            pending_path_2.write_text(json.dumps(pending_2), encoding="utf-8")
            rejected = knowledge_service.reject_lesson(outputs, "lesson-review-2", reason="too broad")

        self.assertEqual(helper["source_candidate_id"], "lesson-review-1")
        self.assertEqual(rejected["status"], "rejected")

    def test_helper_work_item_lifecycle_requires_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            knowledge_service.ensure_knowledge_defaults(outputs)
            candidate = {
                "schema_version": 1,
                "candidate_id": "lesson-helper-lifecycle",
                "source_signal_ids": ["sig-1", "sig-2"],
                "affected_issue_keys": ["OPEN-1", "OPEN-2"],
                "topic": "salesforce-query",
                "trigger": "Repeated INVALID_TYPE",
                "lesson": "Verify object existence before retrying broad Salesforce queries.",
                "evidence": ["INVALID_TYPE"],
                "recommended_file": "query-patterns/object-existence.md",
                "knowledge_type": "helper_contract",
                "org_specific": False,
                "confidence": "medium",
                "recurrence_count": 2,
                "risk": "low",
                "keywords": ["INVALID_TYPE"],
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "pending",
                "route": "helper_work_item",
                "quality": "high",
                "quality_reason": "Repeated helper failure.",
                "failure_class": "invalid_salesforce_assumption",
                "redaction_status": "not_needed",
            }
            pending_path = outputs / "org-knowledge" / "pending-lessons" / "lesson-helper-lifecycle.json"
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.write_text(json.dumps(candidate), encoding="utf-8")

            helper = knowledge_service.convert_to_helper_work_item(outputs, "lesson-helper-lifecycle")
            accepted = knowledge_service.update_helper_work_item_status(
                outputs,
                helper["work_item_id"],
                "accepted_for_work",
                reason="valid platform gap",
            )
            with self.assertRaises(ValueError):
                knowledge_service.update_helper_work_item_status(outputs, helper["work_item_id"], "verified", reference="test")
            with self.assertRaises(ValueError):
                knowledge_service.update_helper_work_item_status(outputs, helper["work_item_id"], "implemented")
            implemented = knowledge_service.update_helper_work_item_status(
                outputs,
                helper["work_item_id"],
                "implemented",
                reference="scripts/sf_caseops_helper.py in 0.1.56",
            )
            verified = knowledge_service.update_helper_work_item_status(
                outputs,
                helper["work_item_id"],
                "verified",
                reference="tests.test_knowledge_service",
            )
            retired = knowledge_service.update_helper_work_item_status(
                outputs,
                helper["work_item_id"],
                "retired",
                reason="covered by core helper guardrail",
            )
            decisions = list((outputs / "org-knowledge" / "decision-artifacts").glob("*helper_work_item_status_changed*.json"))

        self.assertEqual(accepted["status"], "accepted_for_work")
        self.assertEqual(implemented["implementation_reference"], "scripts/sf_caseops_helper.py in 0.1.56")
        self.assertEqual(verified["status"], "verified")
        self.assertEqual(retired["retirement_reason"], "covered by core helper guardrail")
        self.assertGreaterEqual(len(decisions), 4)

    def test_guardrail_command_classification(self):
        legacy = knowledge_service.classify_guardrail_command("sfdx force:source:deploy -p force-app")
        manifest = knowledge_service.classify_guardrail_command("sf project deploy start --manifest package.xml")
        usershare = knowledge_service.classify_guardrail_command("sf data query --query 'SELECT Id, Name FROM UserShare'")
        raw_retrieve = knowledge_service.classify_guardrail_command(
            "sf project retrieve start --metadata Flow:Example --target-org prod"
        )
        raw_deploy = knowledge_service.classify_guardrail_command(
            "sf project deploy start --source-dir candidate --target-org sandbox"
        )
        raw_query = knowledge_service.classify_guardrail_command(
            "sf data query --query 'SELECT Id FROM Missing_Object__c'"
        )

        self.assertFalse(legacy["ok"])
        self.assertTrue(any(item["rule"] == "routine_manifest_deploy" for item in manifest["findings"]))
        self.assertFalse(usershare["ok"])
        self.assertFalse(raw_retrieve["ok"])
        self.assertTrue(any(item["rule"] == "raw_project_retrieve_without_helper" for item in raw_retrieve["findings"]))
        self.assertFalse(raw_deploy["ok"])
        self.assertTrue(any(item["rule"] == "raw_project_deploy_without_helper" for item in raw_deploy["findings"]))
        self.assertTrue(raw_query["ok"])
        self.assertTrue(any(item["rule"] == "raw_soql_without_helper" for item in raw_query["findings"]))

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
                "keywords": ["UserShare"],
                "created_at": "2026-06-27T00:00:00+00:00",
                "status": "pending",
            }
            pending = outputs / "org-knowledge" / "pending-lessons" / "lesson-api-1.json"
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(json.dumps(candidate), encoding="utf-8")

            with patch.object(app, "OUTPUTS", outputs):
                client = app.app.test_client()
                review_before = client.get("/api/knowledge/review")
                accepted = client.post(
                    "/api/knowledge/review/lesson-api-1/accept",
                    json={
                        "edit": {
                            "lesson": "Describe share objects before querying fields, then query only returned fields.",
                            "confidence": "high",
                            "knowledge_type": "query_pattern",
                            "keywords": ["UserShare", "describe"],
                        },
                    },
                )
                review_after = client.get("/api/knowledge/review")

        self.assertEqual(review_before.status_code, 200)
        self.assertEqual(len(review_before.get_json()["items"]["pending_lessons"]), 1)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["item"]["status"], "accepted")
        self.assertEqual(
            accepted.get_json()["item"]["lesson"],
            "Describe share objects before querying fields.",
        )
        self.assertEqual(accepted.get_json()["item"]["confidence"], "medium")
        self.assertEqual(accepted.get_json()["item"]["keywords"], ["UserShare"])
        self.assertEqual(len(review_after.get_json()["items"]["pending_lessons"]), 0)
        self.assertEqual(len(review_after.get_json()["items"]["accepted_lessons"]), 1)

    def test_knowledge_review_api_updates_helper_work_item_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            helper = {
                "schema_version": 1,
                "work_item_id": "helper-api-1",
                "source_candidate_id": "lesson-api-1",
                "source_signal_ids": ["sig-1"],
                "affected_issue_keys": ["OPEN-1"],
                "topic": "deploy-command",
                "summary": "Evaluate helper work.",
                "lesson": "Run deploy commands inside an issue-scoped workspace.",
                "evidence": ["InvalidProjectWorkspaceError"],
                "failure_class": "bad_context",
                "route": "helper_work_item",
                "quality": "high",
                "quality_reason": "Repeated helper failure.",
                "redaction_status": "not_needed",
                "status": "pending",
                "created_at": "2026-06-27T00:00:00+00:00",
            }
            path = outputs / "org-knowledge" / "helper-work-items" / "helper-api-1.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(helper), encoding="utf-8")

            with patch.object(app, "OUTPUTS", outputs):
                client = app.app.test_client()
                accepted = client.post(
                    "/api/knowledge/helper-work/helper-api-1/status",
                    json={"status": "accepted_for_work", "reason": "will fix"},
                )
                missing_ref = client.post(
                    "/api/knowledge/helper-work/helper-api-1/status",
                    json={"status": "implemented"},
                )
                implemented = client.post(
                    "/api/knowledge/helper-work/helper-api-1/status",
                    json={"status": "implemented", "reference": "commit abc123"},
                )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["item"]["status"], "accepted_for_work")
        self.assertEqual(missing_ref.status_code, 400)
        self.assertEqual(implemented.status_code, 200)
        self.assertEqual(implemented.get_json()["item"]["implementation_reference"], "commit abc123")

    def test_review_items_separate_active_and_retired_helper_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            helper_dir = outputs / "org-knowledge" / "helper-work-items"
            helper_dir.mkdir(parents=True, exist_ok=True)
            base = {
                "schema_version": 1,
                "source_candidate_id": "lesson-helper",
                "source_signal_ids": ["sig-1"],
                "affected_issue_keys": ["OPEN-1"],
                "topic": "deploy-command",
                "summary": "Evaluate helper work.",
                "lesson": "Run deploy commands inside an issue-scoped workspace.",
                "evidence": ["InvalidProjectWorkspaceError"],
                "failure_class": "bad_context",
                "route": "helper_work_item",
                "quality": "high",
                "quality_reason": "Repeated helper failure.",
                "redaction_status": "not_needed",
                "created_at": "2026-06-27T00:00:00+00:00",
            }
            active = dict(base, work_item_id="helper-active", status="pending")
            retired = dict(
                base,
                work_item_id="helper-retired",
                status="retired",
                retired_at="2026-06-30T00:00:00+00:00",
                retirement_reason="Covered by core helper behavior.",
            )
            (helper_dir / "helper-active.json").write_text(json.dumps(active), encoding="utf-8")
            (helper_dir / "helper-retired.json").write_text(json.dumps(retired), encoding="utf-8")

            items = knowledge_service.list_review_items(outputs)

        self.assertEqual([item["work_item_id"] for item in items["helper_work_items"]], ["helper-active"])
        self.assertEqual([item["work_item_id"] for item in items["retired_helper_work_items"]], ["helper-retired"])

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
