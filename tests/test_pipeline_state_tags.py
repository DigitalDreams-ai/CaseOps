import json
import tempfile
import unittest
import os
import threading
import time
import subprocess
from unittest.mock import patch
from typing import Any
from datetime import datetime, timezone, timedelta
from pathlib import Path

import app


class PipelineStateTagTests(unittest.TestCase):
    def setUp(self):
        self._old_outputs = app.OUTPUTS
        self._old_cache = dict(app.investigation_cache)
        self._old_pipeline_logs = getattr(app, "OUTPUTS_PIPELINE_LOGS", None)
        self.tempdir = tempfile.TemporaryDirectory()
        app.OUTPUTS = Path(self.tempdir.name)
        app.OUTPUTS_PIPELINE_LOGS = app.OUTPUTS / "pipeline-logs"
        app.investigation_cache.clear()
        for rel in app.FILE_LOCATIONS.values():
            (app.OUTPUTS / rel.format(key="HEAL-1")).parent.mkdir(parents=True, exist_ok=True)
        (app.OUTPUTS / "generated-files").mkdir(parents=True, exist_ok=True)
        (app.OUTPUTS / "pipeline-state").mkdir(parents=True, exist_ok=True)
        app.OUTPUTS_PIPELINE_LOGS.mkdir(parents=True, exist_ok=True)

        metadata_dirs = app._metadata_workspace_dirs()
        for path in metadata_dirs.values():
            if "metadata-workspace.json" in str(path):
                continue
            path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        app.OUTPUTS = self._old_outputs
        app.OUTPUTS_PIPELINE_LOGS = self._old_pipeline_logs
        app.investigation_cache.clear()
        app.investigation_cache.update(self._old_cache)
        self.tempdir.cleanup()

    def _write_state(self, key, payload):
        path = app.OUTPUTS / "pipeline-state" / f"{key}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _write_artifact(self, key, location, text):
        path = app.OUTPUTS / app.FILE_LOCATIONS[location].format(key=key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_metadata_workspace(self, key, manifest_text: str, raw_dir_text: str = "metadata") -> None:
        metadata_dirs = app._metadata_workspace_dirs()
        sandbox_dir = metadata_dirs["sandbox_work"] / key
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        (sandbox_dir / "metadata-workspace.json").write_text(manifest_text, encoding="utf-8")

        raw_metadata_dir = metadata_dirs["raw_prod"] / key
        raw_metadata_dir.mkdir(parents=True, exist_ok=True)
        (raw_metadata_dir / "sample.md").write_text(raw_dir_text, encoding="utf-8")

    def test_generated_files_add_issue_tab_and_payload(self):
        key = "HEAL-1"
        generated_dir = app.OUTPUTS / "generated-files" / key
        generated_dir.mkdir(parents=True, exist_ok=True)
        generated_file = generated_dir / "SF_Users_Frozen_Inactive.xlsx"
        generated_file.write_bytes(b"fake workbook")

        tabs = app._available_tabs(key)
        self.assertIn({"id": "generated_files", "label": "Generated Files"}, tabs)

        payload = app._generated_files_payload(key)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["filename"], "SF_Users_Frozen_Inactive.xlsx")
        self.assertEqual(payload[0]["path"], "SF_Users_Frozen_Inactive.xlsx")
        self.assertIn(f"/files/generated/{key}/SF_Users_Frozen_Inactive.xlsx", payload[0]["url"])

    def test_generated_file_route_is_issue_scoped(self):
        key = "HEAL-1"
        generated_dir = app.OUTPUTS / "generated-files" / key
        generated_dir.mkdir(parents=True, exist_ok=True)
        generated_file = generated_dir / "report.csv"
        generated_file.write_bytes(b"a,b\n1,2\n")

        with app.app.test_client() as client:
            response = client.get(f"/files/generated/{key}/report.csv")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"a,b\n1,2\n")
            response.close()

            escaped = client.get(f"/files/generated/{key}/../other/report.csv")
            self.assertIn(escaped.status_code, {403, 404})
            escaped.close()

    def test_data_only_false_when_schema_says_production_deploy_required(self):
        key = "HEAL-1"
        self._write_artifact(
            key,
            "test_report",
            "Production metadata deploy required: Yes - Gearset\nNo-deploy admin action mentioned only as alternative.",
        )
        self._write_state(
            key,
            {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "support_resolvable", "confidence": "high", "reason": "metadata fix"},
                "deliverable": {
                    "type": "metadata_candidate",
                    "production_deploy_required": "yes",
                    "production_deploy_method": "gearset",
                },
            },
        )

        flags = app._pipeline_file_flags(key, "In Progress")

        self.assertFalse(flags["is_data_only"])

    def test_blocked_false_for_model_prose_without_schema_on_hold(self):
        key = "HEAL-1"
        self._write_artifact(key, "investigation", "I am completely blocked by my previous assumption.")
        self._write_state(
            key,
            {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "support_resolvable", "confidence": "high", "reason": "can proceed"},
                "deliverable": {"type": "metadata_candidate", "production_deploy_required": "yes"},
            },
        )

        flags = app._pipeline_file_flags(key, "In Progress")

        self.assertFalse(flags["is_blocked"])

    def test_jira_status_is_only_actual_escalated_tag_source(self):
        key = "HEAL-1"
        self._write_artifact(key, "eng_handoff", "Engineering handoff prepared.")
        self._write_state(
            key,
            {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "engineering_required", "confidence": "high", "reason": "Apex fix"},
                "deliverable": {"type": "metadata_candidate", "production_deploy_required": "yes"},
            },
        )

        active_flags = app._pipeline_file_flags(key, "In Progress")
        escalated_flags = app._pipeline_file_flags(key, "Escalated to Engineering")

        self.assertFalse(active_flags["is_jira_escalated"])
        self.assertTrue(active_flags["needs_escalation"])
        self.assertTrue(escalated_flags["is_jira_escalated"])
        self.assertFalse(escalated_flags["needs_escalation"])

    def test_schema_version_garbage_falls_back_to_legacy_without_crashing(self):
        key = "HEAL-1"
        self._write_state(key, {"schema_version": "not-a-number"})

        flags = app._pipeline_file_flags(key, "In Progress")

        self.assertIn("pipeline_state", flags)

    def _plan_for_complete_issue(self, key: str) -> None:
        investigation = (
            "## Investigation\n\n"
            "Problem Location confirmed: root cause identified in metadata deployment.\n"
            "Root cause location: metadata validation step.\n"
        )
        step4 = (
            "## Root Cause Hypothesis\n\n"
            "Root cause was likely metadata configuration. Specific artifact: sandbox validation.\n"
        )
        test_report = (
            "## Fixed?\n"
            "- [x] Yes\n"
            "- Validation evidence: production deployment is still required in special case.\n"
            "Production Metadata Deploy Required: **No**\n"
        )
        internal_notes = "Internal notes: detailed actions and evidence summary.\n" * 4
        jira_message = "Jira message draft with guidance and findings.\n" * 4
        summary_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        self._write_artifact(key, "jira_summary", f"Jira Summary for {key}\n")
        self._write_artifact(key, "investigation", investigation)
        self._write_artifact(key, "hypothesis", step4)
        self._write_artifact(key, "test_report", test_report)
        self._write_artifact(key, "internal_notes", internal_notes)
        self._write_artifact(key, "jira_message", jira_message)
        raw_path = app.OUTPUTS / "jira" / "raw" / f"{key}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps({"key": key}), encoding="utf-8")
        self._write_metadata_workspace(
            key,
            manifest_text='{"files":[{"path":"classes/Test.cls","hash":"abc"}]}',
        )

        summary_root = app._summary_root_dir()
        summary_path = summary_root / summary_date / f"issue-summary-{summary_date}.md"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(f"Issue summary for {summary_date}\n", encoding="utf-8")

        # Make summary appear newer than all issue artifacts so Step 11 can short-circuit cleanly.
        tracked_paths = [
            app.OUTPUTS / rel.format(key=key)
            for rel in (
                app.FILE_LOCATIONS["jira_summary"],
                app.FILE_LOCATIONS["investigation"],
                app.FILE_LOCATIONS["hypothesis"],
                app.FILE_LOCATIONS["test_report"],
                app.FILE_LOCATIONS["internal_notes"],
                app.FILE_LOCATIONS["jira_message"],
            )
        ]
        latest_artifact = max(path.stat().st_mtime for path in tracked_paths)
        now = latest_artifact + 10
        os.utime(summary_path, (now, now))

        self._write_state(
            key,
            {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {"path": "support_resolvable", "confidence": "high", "reason": "support-resolvable fix"},
                "deliverable": {
                    "type": "metadata_candidate",
                    "production_deploy_required": "yes",
                    "production_deploy_method": "none",
                },
                "signatures": {
                    "jira_source": app._build_jira_signature(key, app._issue_source_mtime(key)),
                    "investigation": app._file_signature(app.OUTPUTS / app.FILE_LOCATIONS["investigation"].format(key=key)),
                    "hypothesis": app._file_signature(app.OUTPUTS / app.FILE_LOCATIONS["hypothesis"].format(key=key)),
                    "test_report": app._file_signature(app.OUTPUTS / app.FILE_LOCATIONS["test_report"].format(key=key)),
                    "metadata_workspace": app._file_signature(app._metadata_workspace_dirs()["sandbox_work"] / key / "metadata-workspace.json"),
                },
            },
        )

    def test_complete_issue_skips_steps_3_to_10_resume(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)

        plan = app._build_pipeline_resume_plan(key, "In Progress")
        by_step = {step["step"]: step["status"] for step in plan.get("steps", [])}

        for step_no in range(3, 11):
            self.assertIn(step_no, by_step)
            self.assertEqual(
                by_step[step_no],
                "complete",
                f"Step {step_no} should be complete when inputs/signatures are unchanged: {by_step[step_no]}",
            )
        self.assertEqual(plan["next_step"]["step"], 12)

    def test_jira_source_signature_change_invalidates_step3_and_downstream(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)
        state = json.loads((app.OUTPUTS / "pipeline-state" / f"{key}.json").read_text(encoding="utf-8"))

        summary_path = app.OUTPUTS / app.FILE_LOCATIONS["jira_summary"].format(key=key)
        summary_path.write_text("Updated Jira summary for signature churn.\n", encoding="utf-8")

        # Keep valid JSON in state so no fallback happens.
        (app.OUTPUTS / "pipeline-state" / f"{key}.json").write_text(json.dumps(state), encoding="utf-8")
        plan = app._build_pipeline_resume_plan(key, "In Progress")
        by_step = {step["step"]: step["status"] for step in plan.get("steps", [])}

        self.assertNotEqual(by_step[3], "complete")
        self.assertNotEqual(by_step[4], "complete")
        self.assertIn(by_step[3], {"pending", "stale"})
        self.assertIn(by_step[4], {"pending", "stale"})

    def test_summary_touch_does_not_invalidate_completed_issue_steps(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)
        summary_path = app._latest_issue_summary_path()
        self.assertIsNotNone(summary_path)
        assert summary_path is not None
        summary_path.write_text("Refreshed summary touched for no-op update.\n", encoding="utf-8")

        plan = app._build_pipeline_resume_plan(key, "In Progress")
        by_step = {step["step"]: step["status"] for step in plan.get("steps", [])}

        self.assertEqual(by_step[3], "complete")
        self.assertEqual(by_step[4], "complete")
        self.assertEqual(by_step[5], "complete")

    def test_candidate_workspace_signature_change_invalidates_only_step_9_and_10(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)
        state_path = app.OUTPUTS / "pipeline-state" / f"{key}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))

        # Simulate candidate workspace drift after a completed run.
        manifest_path = app._metadata_workspace_dirs()["sandbox_work"] / key / "metadata-workspace.json"
        manifest_path.write_text('{"files":[{"path":"classes/Test.cls","hash":"zzz"}]}', encoding="utf-8")
        state_path.write_text(json.dumps(state), encoding="utf-8")

        plan = app._build_pipeline_resume_plan(key, "In Progress")
        by_step = {step["step"]: step for step in plan.get("steps", [])}

        self.assertEqual(by_step[3]["status"], "complete")
        self.assertEqual(by_step[4]["status"], "complete")
        self.assertIn(by_step[9]["status"], {"stale", "pending", "blocked"})
        self.assertNotEqual(by_step[9]["status"], "complete")
        self.assertIn(by_step[10]["status"], {"stale", "pending", "blocked"})
        self.assertNotEqual(by_step[10]["status"], "complete")

    def test_loop_state_hold_stalls_metadata_steps(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)
        state_path = app.OUTPUTS / "pipeline-state" / f"{key}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["loop_state"] = {
            "metadata_rounds": app.PIPELINE_LOOP_LIMITS["metadata_rounds"],
            "deploy_rounds": 0,
            "no_candidate_delta_count": 0,
            "last_stoppoint_code": "",
            "last_reason": "",
            "last_seen": "",
            "latest_stop_code": "",
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")

        plan = app._build_pipeline_resume_plan(key, "In Progress")
        by_step = {step["step"]: step["status"] for step in plan.get("steps", [])}

        self.assertEqual(plan["loop_reason"], "repeat_metadata")
        self.assertEqual(plan.get("routing", {}).get("path"), "on_hold")
        self.assertIn(by_step[5], {"blocked", "complete"})
        self.assertIn(by_step[6], {"blocked", "complete"})
        self.assertIn(by_step[8], {"blocked", "complete"})

    def _write_pipeline_log(self, run_key: str, records: list[dict[str, str]]) -> None:
        path = app.OUTPUTS_PIPELINE_LOGS / f"{run_key}.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")

    def _collect_preflight_with_fake_cli(self, parallel_enabled: bool, run_soql: bool = False) -> tuple[dict[str, Any], int]:
        settings = {
            "CASEOPS_PRODUCTION_READ_ORG": "PROD",
            "CASEOPS_SANDBOX_TARGET_ORG": "SANDBOX",
            "SF_PROD_ACCESS_TOKEN": "prod-token",
            "SF_SANDBOX_ACCESS_TOKEN": "sandbox-token",
            "SF_PROD_INSTANCE_URL": "https://login.salesforce.com",
            "SF_SANDBOX_INSTANCE_URL": "https://test.salesforce.com",
        }
        original_env = os.environ.get("CASEOPS_ENABLE_PARALLEL_PRECHECKS")
        if parallel_enabled:
            os.environ["CASEOPS_ENABLE_PARALLEL_PRECHECKS"] = "1"
        else:
            os.environ.pop("CASEOPS_ENABLE_PARALLEL_PRECHECKS", None)

        original_llm_mode = app.caseops_llm_auth_uses_anthropic_api_key
        original_which = app.shutil.which
        original_run_cli = app._run_cli_command
        original_read_env = app._read_env_file

        lock = threading.Lock()
        active = set[str]()
        max_active = 0

        def run_cli(cmd: list[str], env: dict[str, str], timeout: int, retries: int = 0):
            nonlocal max_active
            command = " ".join(cmd)
            if cmd[1] == "--version":
                return subprocess.CompletedProcess(cmd, 0, stdout="sf 2.0")
            if "org" in cmd and "display" in cmd:
                try:
                    alias_index = cmd.index("--target-org") + 1
                    alias = cmd[alias_index]
                except ValueError:
                    alias = "unknown"
                with lock:
                    active.add(alias)
                    max_active = max(max_active, len(active))
                time.sleep(0.05)
                with lock:
                    active.discard(alias)
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=json.dumps({"result": {"connectedStatus": "Connected", "username": f"{alias}-user", "id": "00D1", "instanceUrl": "https://example.com"}}),
                )
            if "data" in cmd and "query" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": {"records": []}}))
            return subprocess.CompletedProcess(cmd, 0, stdout="{}")

        try:
            app._read_env_file = lambda *_args, **_kwargs: settings
            app.caseops_llm_auth_uses_anthropic_api_key = lambda: False
            app.shutil.which = lambda *_args, **_kwargs: "/usr/bin/sf"
            app._run_cli_command = run_cli
            result = app._collect_runtime_preflight(run_soql=run_soql)
            return result, max_active
        finally:
            os.environ.pop("CASEOPS_ENABLE_PARALLEL_PRECHECKS", None if original_env is None else original_env)
            app.caseops_llm_auth_uses_anthropic_api_key = original_llm_mode
            app.shutil.which = original_which
            app._run_cli_command = original_run_cli
            app._read_env_file = original_read_env

            if original_env is not None:
                os.environ["CASEOPS_ENABLE_PARALLEL_PRECHECKS"] = original_env

    def test_context_packet_includes_context_metadata(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)
        plan = app._build_pipeline_resume_plan(key, "In Progress")
        packet = plan.get("context_packet") or {}
        self.assertEqual(packet.get("version"), app.PIPELINE_CONTEXT_POLICY_VERSION)
        self.assertIn("org_knowledge", packet)
        self.assertIn("artifacts", packet)
        self.assertGreater(packet.get("artifact_count", 0), 0)
        self.assertGreater(plan.get("context_packet_chars", 0), 0)

        plan_path = app.OUTPUTS / "pipeline-state" / f"{key}.json"
        text = app._format_resume_plan_for_prompt(plan, plan_path)
        self.assertIn("## Context Packet", text)
        self.assertIn("selected org files", text)
        for gate in ("step_6_problem_location", "step_9_test_report", "step_10_message_separation", "loop_limit"):
            self.assertIn(gate, (plan.get("quality_gates") or {}))

    def test_evidence_prechecks_disable_gate_off_by_default(self):
        key = "HEAL-1"
        previous = os.environ.get("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES")
        if previous is not None:
            del os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"]
        try:
            self._write_metadata_workspace(key, manifest_text='{"files":[{"path":"classes/Test.cls","hash":"abc"}]}')
            summary = app._run_issue_evidence_branches(key, run_soql=False)

            self.assertFalse(summary["enabled"])
            self.assertEqual(summary["branches"], {})
            self.assertEqual(summary["evidence_files"], [])
            self.assertTrue(summary["all_ok"])
        finally:
            if previous is None:
                os.environ.pop("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES", None)
            else:
                os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"] = previous

    def test_evidence_branches_run_parallel_when_enabled_and_record_summary(self):
        key = "HEAL-1"
        previous = os.environ.get("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES")
        try:
            self._write_metadata_workspace(key, manifest_text='{"files":[{"path":"classes/Test.cls","hash":"abc"}]}')
            os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"] = "1"

            lock = threading.Lock()
            active = 0
            max_active = 0

            def _record_active_delta(delta: int) -> None:
                nonlocal active, max_active
                with lock:
                    active += delta
                    if delta > 0:
                        max_active = max(max_active, active)

            def slow_access(run_soql: bool = False) -> dict[str, Any]:
                _record_active_delta(1)
                try:
                    time.sleep(0.08)
                    return {
                        "branch": "org_accessibility",
                        "status": "pass",
                        "blocking": True,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "summary": {"prod_authenticated": True},
                    }
                finally:
                    _record_active_delta(-1)

            def slow_knowledge(key_param: str, row: dict[str, Any]) -> dict[str, Any]:
                _record_active_delta(1)
                try:
                    time.sleep(0.08)
                    return {
                        "branch": "org_knowledge_validation",
                        "status": "pass",
                        "blocking": False,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "summary": {"selected_count": 1},
                        "advisory": True,
                    }
                finally:
                    _record_active_delta(-1)

            def slow_object_check(key_param: str, manifest_text: str) -> dict[str, Any]:
                _record_active_delta(1)
                try:
                    time.sleep(0.08)
                    return {
                        "branch": "object_component_precheck",
                        "status": "pass",
                        "blocking": False,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "summary": {"candidate_count": 0},
                    }
                finally:
                    _record_active_delta(-1)

            state_path = app.OUTPUTS / "pipeline-state" / f"{key}.json"
            if state_path.exists():
                state_path.unlink()

            with patch.object(app, "_collect_org_access_branch_evidence", side_effect=slow_access), \
                    patch.object(app, "_collect_org_knowledge_branch_evidence", side_effect=slow_knowledge), \
                    patch.object(app, "_collect_object_component_branch_evidence", side_effect=slow_object_check):
                summary = app._run_issue_evidence_branches(key, run_soql=False)

            self.assertTrue(summary["enabled"])
            self.assertEqual(set(summary["branches"].keys()), {"org_accessibility", "org_knowledge_validation", "object_component_precheck"})
            self.assertTrue(summary["all_ok"])
            self.assertEqual(summary["blocking_branches"], ["org_accessibility"])
            self.assertEqual(summary["failed_branches"], [])
            self.assertGreaterEqual(max_active, 2)
            self.assertGreaterEqual(len(summary["evidence_files"]), 3)
            plan = app._build_pipeline_resume_plan(key, "In Progress")
            self.assertIn("evidence_prechecks", plan)
        finally:
            if previous is None:
                os.environ.pop("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES", None)
            else:
                os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"] = previous

    def test_evidence_precheck_summary_surfaces_blocking_and_advisory_outcomes(self):
        key = "HEAL-1"
        previous = os.environ.get("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES")
        try:
            self._write_metadata_workspace(key, manifest_text='{"files":[{"path":"classes/Test.cls","hash":"abc"}]}')
            os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"] = "1"

            with patch.object(
                app,
                "_collect_org_access_branch_evidence",
                return_value={
                    "branch": "org_accessibility",
                    "status": "pass",
                    "blocking": True,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "summary": {},
                    "preflight": {"ok": True},
                },
            ), patch.object(
                app,
                "_collect_org_knowledge_branch_evidence",
                return_value={
                    "branch": "org_knowledge_validation",
                    "status": "fail",
                    "blocking": False,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "summary": {"selected_count": 0},
                    "advisory": True,
                },
            ), patch.object(
                app,
                "_collect_object_component_branch_evidence",
                return_value={
                    "branch": "object_component_precheck",
                    "status": "fail",
                    "blocking": False,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "summary": {"missing_file_candidates": ["Foo.cls"]},
                },
            ):
                summary = app._run_issue_evidence_branches(key, run_soql=False)

            self.assertTrue(summary["all_ok"])
            self.assertIn("org_knowledge_validation", summary["failed_branches"])
            self.assertIn("object_component_precheck", summary["failed_branches"])
            self.assertEqual(summary["blocking_branches"], ["org_accessibility"])
            state = app._read_pipeline_state(key)
            self.assertTrue(state.get("evidence_prechecks", {}).get("all_ok"))
            evidence_files = state.get("evidence_prechecks", {}).get("evidence_files", [])
            self.assertGreaterEqual(len(evidence_files), 2)
            prompt = app._format_resume_plan_for_prompt(
                app._build_pipeline_resume_plan(key, "In Progress"),
                app.OUTPUTS / "pipeline-state" / f"{key}.json",
            )
            self.assertIn("## Evidence Prechecks", prompt)
            self.assertIn("org_knowledge_validation", prompt)
            self.assertIn("object_component_precheck", prompt)
        finally:
            if previous is None:
                os.environ.pop("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES", None)
            else:
                os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"] = previous

    def test_issue_readiness_blocks_when_org_accessibility_precheck_fails(self):
        key = "HEAL-1"
        self._write_metadata_workspace(key, manifest_text='{"files":[{"path":"classes/Test.cls","hash":"abc"}]}')
        self._write_artifact(key, "investigation", "Investigating issue.")
        previous = os.environ.get("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES")
        previous_sandbox = os.environ.get("CASEOPS_SANDBOX_TARGET_ORG")
        os.environ["CASEOPS_SANDBOX_TARGET_ORG"] = "SANDBOX"
        os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"] = "1"

        def _preflight_gate(run_key: str, run_soql: bool = True, preflight: dict[str, object] | None = None) -> bool:
            return bool(preflight and preflight.get("ok") is True)

        try:
            with patch.object(
                app,
                "_collect_org_access_branch_evidence",
                return_value={
                    "branch": "org_accessibility",
                    "status": "fail",
                    "blocking": True,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "summary": {"issues": ["bad creds"]},
                    "preflight": {"ok": False},
                },
            ), patch.object(app, "_collect_org_knowledge_branch_evidence", return_value={
                "branch": "org_knowledge_validation",
                "status": "pass",
                "blocking": False,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"selected_count": 1},
            }), patch.object(app, "_collect_object_component_branch_evidence", return_value={
                "branch": "object_component_precheck",
                "status": "pass",
                "blocking": False,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"candidate_count": 0},
            }), patch.object(app, "_emit_runtime_preflight_or_stop", side_effect=_preflight_gate):
                # `_issue_pipeline_runtime_ready` should surface branch blockers and fail preflight.
                ready = app._issue_pipeline_runtime_ready(key)
                self.assertFalse(ready)

                summary = app._run_issue_evidence_branches(key, run_soql=False)
                self.assertFalse(summary["all_ok"])
                self.assertEqual(summary["blocking_branches"], ["org_accessibility"])
                self.assertIn("org_accessibility", summary["failed_branches"])
        finally:
            if previous is None:
                os.environ.pop("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES", None)
            else:
                os.environ["CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES"] = previous
            if previous_sandbox is None:
                os.environ.pop("CASEOPS_SANDBOX_TARGET_ORG", None)
            else:
                os.environ["CASEOPS_SANDBOX_TARGET_ORG"] = previous_sandbox

    def test_log_governance_suppresses_duplicate_noncritical_output(self):
        run_key = "HEAL-1"
        app.PIPELINE_CONTEXT_LIMITS["repeated_output_lines"] = 2
        app._init_pipeline_log_governance(run_key)
        try:
            self.assertEqual(app._governed_log_line(run_key, "non-critical note"), "non-critical note")
            self.assertEqual(app._governed_log_line(run_key, "non-critical note"), "non-critical note")
            suppression = app._governed_log_line(run_key, "non-critical note")
            self.assertIsNotNone(suppression)
            self.assertIn("duplicate output suppressed", suppression)
            self.assertIsNone(app._governed_log_line(run_key, "non-critical note"))
        finally:
            app._finalize_pipeline_log_governance(run_key)
            app.PIPELINE_CONTEXT_LIMITS["repeated_output_lines"] = 3000

    def test_log_governance_enforces_output_char_cap(self):
        run_key = "HEAL-1"
        app.PIPELINE_CONTEXT_LIMITS["output_chars_per_run"] = 10
        app._init_pipeline_log_governance(run_key)
        try:
            first = app._governed_log_line(run_key, "first-line-is-long-enough")
            self.assertIn("run output cap reached", first)
            self.assertIsNone(app._governed_log_line(run_key, "another-line"))
        finally:
            app._finalize_pipeline_log_governance(run_key)
            app.PIPELINE_CONTEXT_LIMITS["output_chars_per_run"] = 40_000

    def test_runtime_preflight_parallel_prechecks_toggle_controls_concurrency(self):
        sequential, max_active_seq = self._collect_preflight_with_fake_cli(parallel_enabled=False, run_soql=False)
        parallel, max_active_par = self._collect_preflight_with_fake_cli(parallel_enabled=True, run_soql=False)

        self.assertTrue(sequential.get("ok"))
        self.assertTrue(parallel.get("ok"))
        self.assertEqual(max_active_seq, 1, f"Sequential mode unexpectedly ran org checks concurrently: max_active={max_active_seq}")
        self.assertGreaterEqual(max_active_par, 2, f"Parallel mode did not run org checks concurrently: max_active={max_active_par}")

    def test_update_pipeline_run_metrics_persists_token_and_loop_data(self):
        key = "HEAL-1"
        run_key = f"{key}-run"
        self._plan_for_complete_issue(key)
        state_path = app.OUTPUTS / "pipeline-state" / f"{key}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["run_metrics"] = {}
        state_path.write_text(json.dumps(state), encoding="utf-8")

        base = datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc)
        self._write_pipeline_log(
            run_key,
            [
                {"ts": (base + timedelta(seconds=1)).isoformat(), "text": "STEP_3 resume-skip"},
                {"ts": (base + timedelta(seconds=2)).isoformat(), "text": "Token usage: total=15, input=5, output=4, cache_create=3, cache_read=3"},
                {"ts": (base + timedelta(seconds=2)).isoformat(), "text": "[agent] Step 3 helper"},
                {"ts": (base + timedelta(seconds=3)).isoformat(), "text": "STEP_9 deploy"},
                {"ts": (base + timedelta(seconds=3)).isoformat(), "text": "[agent] Step 9 helper"},
                {"ts": (base + timedelta(seconds=4)).isoformat(), "text": "repeat_metadata"},
                {"ts": (base + timedelta(seconds=5)).isoformat(), "text": "deploy_fail"},
                {"ts": (base + timedelta(seconds=6)).isoformat(), "text": "no_candidate_delta"},
                {"ts": (base + timedelta(seconds=7)).isoformat(), "text": "safe_stoppoint_hit"},
                {"ts": (base + timedelta(seconds=7)).isoformat(), "text": "[bash] sf command"},
            ],
        )

        run_started = base + timedelta(seconds=1)
        run_ended = base + timedelta(seconds=8)
        latest = app._update_pipeline_run_metrics(key, run_key, run_started, run_ended, status="completed")

        updated = app._read_pipeline_state(key)
        self.assertEqual(updated["run_metrics"]["latest"]["status"], "completed")
        self.assertIn("step_timings", latest)
        self.assertEqual(latest["step_timings"]["3"]["start"], (base + timedelta(seconds=1)).isoformat())
        self.assertEqual(latest["step_timings"]["9"]["start"], (base + timedelta(seconds=3)).isoformat())
        self.assertEqual(latest["step_timings"]["3"]["subagent_calls"], 1)
        self.assertEqual(latest["step_timings"]["9"]["subagent_calls"], 1)
        self.assertEqual(latest["loop_events"]["repeat_metadata"], 1)
        self.assertEqual(latest["loop_events"]["deploy_fail"], 1)
        self.assertEqual(latest["loop_events"]["no_candidate_delta"], 1)
        self.assertEqual(latest["loop_events"]["safe_stoppoint_hit"], 1)
        self.assertEqual(latest["subagent_calls"], 2)
        self.assertEqual(latest["subagent_calls_by_step"]["3"], 1)
        self.assertEqual(latest["subagent_calls_by_step"]["9"], 1)
        self.assertEqual(latest["tool_calls"], 3)
        self.assertEqual(latest["tool_calls_by_step"]["3"], 1)
        self.assertEqual(latest["tool_calls_by_step"]["9"], 2)
        self.assertEqual(updated["loop_state"]["metadata_rounds"], 1)
        self.assertEqual(updated["loop_state"]["deploy_rounds"], 1)
        self.assertEqual(updated["loop_state"]["no_candidate_delta_count"], 1)

    def test_full_issue_marks_metrics_failed_when_claude_stream_fails(self):
        key = "HEAL-1"
        plan = {
            "key": key,
            "next_step": {"step": 3, "name": "Analyze issue", "status": "pending"},
            "steps": [{"step": 3, "name": "Analyze issue", "status": "pending"}],
        }
        seen_statuses: list[str] = []

        def fake_update(_key, _run_key, _started, _ended, *, status):
            seen_statuses.append(status)
            return {"status": status, "duration_seconds": 1, "step_timings": {}}

        with patch.object(app, "_issue_pipeline_runtime_ready", return_value=True), \
                patch.object(app, "_prepare_resume_plan", return_value=(plan, app.OUTPUTS / "pipeline-state" / f"{key}.json", "resume")), \
                patch.object(app, "_resume_plan_short_circuit", return_value=False), \
                patch.object(app, "_build_claude_prompt", return_value="prompt"), \
                patch.object(app, "_do_stream_claude", return_value=False), \
                patch.object(app, "_update_pipeline_run_metrics", side_effect=fake_update):
            app._stream_full_issue(key, key)

        self.assertEqual(seen_statuses, ["failed"])

    def test_build_claude_prompt_handles_outputs_outside_root(self):
        key = "HEAL-1"
        self._write_artifact(key, "jira_summary", "Jira summary")
        plan_path = app.OUTPUTS / "pipeline-state" / f"{key}.json"

        with patch.object(
            app,
            "_read_manifest",
            return_value=[{"Key": key, "Summary": "SUP issue", "Status": "In Progress", "Updated": ""}],
        ), patch.object(
            app,
            "_prepare_resume_plan",
            return_value=({}, plan_path, "resume"),
        ), patch.object(app, "_build_org_knowledge_context_block", return_value=""):
            prompt = app._build_claude_prompt(key, "Continue the pipeline.")

        summary_path = app.OUTPUTS / app.FILE_LOCATIONS["jira_summary"].format(key=key)
        self.assertIn(summary_path.as_posix(), prompt)

    def test_transition_contract_failures_mark_contract_step_for_rework(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)
        investigation_path = app.OUTPUTS / app.FILE_LOCATIONS["investigation"].format(key=key)
        investigation_path.write_text("Need help reproducing.", encoding="utf-8")
        state = json.loads((app.OUTPUTS / "pipeline-state" / f"{key}.json").read_text(encoding="utf-8"))
        # Keep signatures stable so the step-completeness logic stays enabled while contracts can still fail.
        state["signatures"]["investigation"] = app._file_signature(investigation_path)
        (app.OUTPUTS / "pipeline-state" / f"{key}.json").write_text(json.dumps(state), encoding="utf-8")

        plan = app._build_pipeline_resume_plan(key, "In Progress")
        step6 = app._build_step(plan, 6)
        self.assertIsNotNone(step6)
        assert step6 is not None
        self.assertEqual(step6["status"], "stale")
        self.assertIn("needs_rework", plan.get("quality_gates", {}).get("step_5_to_6_transition", ""))

    def test_transition_contracts_mark_step_9_as_stale_on_manifest_failure(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)
        manifest_path = app._metadata_workspace_dirs()["sandbox_work"] / key / "metadata-workspace.json"
        manifest_path.write_text("{}", encoding="utf-8")
        state = json.loads((app.OUTPUTS / "pipeline-state" / f"{key}.json").read_text(encoding="utf-8"))
        state["signatures"]["metadata_workspace"] = app._file_signature(manifest_path)
        (app.OUTPUTS / "pipeline-state" / f"{key}.json").write_text(json.dumps(state), encoding="utf-8")

        plan = app._build_pipeline_resume_plan(key, "In Progress")
        step9 = app._build_step(plan, 9)
        self.assertIsNotNone(step9)
        assert step9 is not None
        self.assertEqual(step9["status"], "stale")
        self.assertIn("needs_rework", plan.get("quality_gates", {}).get("step_8_to_9_transition", ""))

    def test_tool_permissions_are_in_resume_plan_and_prompt(self):
        key = "HEAL-1"
        self._plan_for_complete_issue(key)

        plan, _, prompt = app._prepare_resume_plan(key, "In Progress")
        permissions = plan.get("tool_permissions") or {}
        self.assertEqual(permissions.get("version"), app.PIPELINE_TOOL_PERMISSION_VERSION)
        self.assertIn("steps", permissions)
        self.assertTrue(isinstance(permissions.get("active_step"), int) or permissions.get("active_step", "").isdigit() or permissions.get("active_step") in {None, ""})
        self.assertIn("active_step_tools", permissions)
        self.assertIn("## Tool Permissions", prompt)

    def test_pipeline_allowlist_includes_artifact_write_tools(self):
        expected = {
            3: {"write", "edit"},
            5: {"write", "edit"},
            6: {"write", "edit"},
            8: {"write", "edit"},
            9: {"write", "edit"},
            10: {"write", "edit"},
            11: {"write", "edit"},
        }
        for step_no, tools in expected.items():
            with self.subTest(step=step_no):
                allowed = {
                    app._normalize_tool_name(tool)
                    for tool in app.PIPELINE_STEP_TOOL_ALLOWLIST[step_no]["tools"]
                }
                self.assertTrue(tools.issubset(allowed))
                for tool in tools:
                    self.assertTrue(app._is_tool_allowlisted(step_no, tool))

    def test_pipeline_suppresses_unavailable_internal_tool_output(self):
        self.assertTrue(app._is_pipeline_internal_unavailable_tool("ToolSearch"))
        self.assertFalse(app._is_tool_allowlisted(6, "ToolSearch"))
        self.assertTrue(app._is_suppressed_tool_result("ToolSearch", ""))

    def test_salesforce_auth_token_json_is_normalized_for_cli_login(self):
        payload = {
            "status": 0,
            "result": {
                "orgId": "00D000000000001AAA",
                "accessToken": "access-token-value",
            },
        }
        self.assertEqual(
            app._normalize_salesforce_access_token(json.dumps(payload)),
            "00D000000000001AAA!access-token-value",
        )
        self.assertEqual(
            app._normalize_salesforce_access_token("00D000000000001AAA!already-formatted"),
            "00D000000000001AAA!already-formatted",
        )
        self.assertEqual(
            app._normalize_salesforce_access_token(json.dumps({"status": 0, "result": "00D000000000001AAA!result-string-token"})),
            "00D000000000001AAA!result-string-token",
        )

    def test_salesforce_refresh_token_json_accepts_sfdx_auth_url(self):
        payload = {
            "status": 0,
            "result": {
                "sfdxAuthUrl": "force://PlatformCLI::refresh-token-value@example.my.salesforce.com",
            },
        }
        self.assertEqual(
            app._extract_salesforce_refresh_token(json.dumps(payload)),
            "refresh-token-value",
        )
        self.assertEqual(
            app._extract_salesforce_sfdx_auth_url(json.dumps(payload)),
            "force://PlatformCLI::refresh-token-value@example.my.salesforce.com",
        )

    def test_settings_status_exposes_caseops_version(self):
        status = app._settings_status_skeleton()
        self.assertEqual(status["caseops"]["version"], app.CASEOPS_VERSION)

    def test_docker_image_includes_minimal_sfdx_project_workspace(self):
        dockerfile = (app.ROOT / "Dockerfile").read_text(encoding="utf-8")
        sfdx_project = app.ROOT / "docker" / "sfdx-project.json"
        self.assertTrue(sfdx_project.is_file())
        self.assertIn("COPY --chown=1027:100 docker/sfdx-project.json /app/sfdx-project.json", dockerfile)
        self.assertIn("/app/force-app/main/default", dockerfile)
        self.assertIn("ENV CASEOPS_VERSION=0.1.4", dockerfile)

        payload = json.loads(sfdx_project.read_text(encoding="utf-8"))
        self.assertEqual(payload["packageDirectories"][0]["path"], "force-app")
        self.assertTrue(payload["packageDirectories"][0]["default"])


if __name__ == "__main__":
    unittest.main()
