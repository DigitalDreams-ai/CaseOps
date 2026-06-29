import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import caseops_paths


class GlobalQueueTests(unittest.TestCase):
    def tearDown(self):
        with app._state_lock:
            app._active_keys.clear()
            app._active_run_actions.clear()
            app._active_run_controls.clear()

    def test_jira_sync_does_not_block_manual_send_request(self):
        class FakeThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                pass

        with app._state_lock:
            app._mark_run_active_locked(app._GLOBAL_KEY, "sync")

        with (
            patch.object(app, "_build_claude_prompt", return_value="prompt"),
            patch.object(app.threading, "Thread", FakeThread),
        ):
            client = app.app.test_client()
            allowed = client.post(
                "/api/run",
                json={"action": "claude_instruction", "key": "OPEN-1", "instruction": "check this"},
            )
            blocked = client.post(
                "/api/run",
                json={"action": "full_issue", "key": "OPEN-2"},
            )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.get_json()["run_key"], "OPEN-1")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("global run", blocked.get_json()["error"].lower())

    def test_production_approval_token_is_stripped_and_scoped(self):
        with patch.dict(os.environ, {"CASEOPS_PRODUCTION_WRITE_APPROVAL_SECRET": "approve-prod"}, clear=False):
            sanitized, approval, error = app._extract_production_write_approval(
                "Update the Production record. PRODUCTION_APPROVAL=approve-prod",
                "OPEN-1",
            )

        self.assertIsNone(error)
        self.assertEqual(sanitized, "Update the Production record.")
        self.assertIsNotNone(approval)
        self.assertEqual(approval["CASEOPS_PRODUCTION_WRITE_APPROVED"], "1")
        self.assertEqual(approval["CASEOPS_PRODUCTION_WRITE_ISSUE_KEY"], "OPEN-1")
        self.assertNotIn("approve-prod", approval["CASEOPS_PRODUCTION_WRITE_REQUEST"])

    def test_production_approval_rejects_invalid_token(self):
        with patch.dict(os.environ, {"CASEOPS_PRODUCTION_WRITE_APPROVAL_SECRET": "approve-prod"}, clear=False):
            sanitized, approval, error = app._extract_production_write_approval(
                "Update Production. PRODUCTION_APPROVAL=wrong",
                "OPEN-1",
            )

        self.assertEqual(sanitized, "Update Production.")
        self.assertIsNone(approval)
        self.assertIn("Invalid", error)

    def test_production_approval_accepts_configured_phrase(self):
        with patch.dict(os.environ, {"CASEOPS_PRODUCTION_WRITE_APPROVAL_PHRASE": "@prod_approval"}, clear=False):
            sanitized, approval, error = app._extract_production_write_approval(
                "Deploy this permission set to Production. @prod_approval",
                "OPEN-1",
            )

        self.assertIsNone(error)
        self.assertEqual(sanitized, "Deploy this permission set to Production.")
        self.assertIsNotNone(approval)
        self.assertEqual(approval["CASEOPS_PRODUCTION_WRITE_APPROVED"], "1")
        self.assertEqual(approval["CASEOPS_PRODUCTION_WRITE_ISSUE_KEY"], "OPEN-1")
        self.assertNotIn("@prod_approval", approval["CASEOPS_PRODUCTION_WRITE_REQUEST"])

    def test_production_approval_marker_is_issue_scoped_and_auditable(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp) / "outputs"
            outputs.mkdir()
            approval = {
                "CASEOPS_PRODUCTION_WRITE_APPROVED": "1",
                "CASEOPS_PRODUCTION_WRITE_ISSUE_KEY": "OPEN-1",
                "CASEOPS_PRODUCTION_WRITE_EXPIRES_AT": "4102444800",
                "CASEOPS_PRODUCTION_WRITE_REQUEST": "Deploy a specific permission set.",
                "CASEOPS_PRODUCTION_WRITE_REQUEST_HASH": "abc123",
            }

            with patch.object(app, "OUTPUTS", outputs):
                updated = app._write_production_write_approval_marker("OPEN-1", approval)

            marker_path = Path(updated["CASEOPS_PRODUCTION_WRITE_APPROVAL_FILE"])
            audit_path = Path(updated["CASEOPS_PRODUCTION_WRITE_AUDIT_LOG"])
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker_path_text = str(marker_path)
            audit_exists = audit_path.exists()

        self.assertEqual(marker["issue_key"], "OPEN-1")
        self.assertEqual(marker["status"], "active")
        self.assertEqual(marker["request_hash"], "abc123")
        self.assertTrue(marker_path_text.endswith("production-approvals\\OPEN-1.json") or marker_path_text.endswith("production-approvals/OPEN-1.json"))
        self.assertTrue(audit_exists)

    def test_default_production_approval_phrase_requires_env_configuration(self):
        with patch.dict(os.environ, {"CASEOPS_PRODUCTION_WRITE_APPROVAL_PHRASE": ""}, clear=False):
            sanitized, approval, error = app._extract_production_write_approval(
                "Deploy this permission set to Production. @prod_approval",
                "OPEN-1",
            )

        self.assertEqual(sanitized, "Deploy this permission set to Production.")
        self.assertIsNone(approval)
        self.assertIn("CASEOPS_PRODUCTION_WRITE_APPROVAL_PHRASE", error)

    def test_manual_instruction_passes_valid_production_approval_to_runner_without_secret(self):
        captured = {}

        class FakeThread:
            def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                captured["target"] = target
                captured["args"] = args

            def start(self):
                pass

        def fake_prompt(key, instruction, resume_block=None, production_approval=None):
            captured["key"] = key
            captured["instruction"] = instruction
            captured["production_approval"] = production_approval
            return "prompt"

        def fake_marker(key, approval):
            updated = dict(approval)
            updated["CASEOPS_PRODUCTION_WRITE_APPROVAL_FILE"] = f"/tmp/{key}.json"
            updated["CASEOPS_PRODUCTION_WRITE_AUDIT_LOG"] = f"/tmp/{key}.audit.log"
            return updated

        with (
            patch.dict(os.environ, {"CASEOPS_PRODUCTION_WRITE_APPROVAL_SECRET": "approve-prod"}, clear=False),
            patch.object(app, "_build_claude_prompt", side_effect=fake_prompt),
            patch.object(app, "_write_production_write_approval_marker", side_effect=fake_marker),
            patch.object(app.threading, "Thread", FakeThread),
        ):
            response = app.app.test_client().post(
                "/api/run",
                json={
                    "action": "claude_instruction",
                    "key": "OPEN-1",
                    "instruction": "Assign the existing permission set in Production. PRODUCTION_APPROVAL=approve-prod",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["instruction"], "Assign the existing permission set in Production.")
        self.assertNotIn("approve-prod", captured["instruction"])
        self.assertEqual(captured["production_approval"]["CASEOPS_PRODUCTION_WRITE_ISSUE_KEY"], "OPEN-1")
        self.assertEqual(captured["args"][3]["CASEOPS_PRODUCTION_WRITE_APPROVED"], "1")

    def test_lightning_hosts_are_derived_from_salesforce_alias_fields(self):
        with patch.dict(
            os.environ,
            {
                "CASEOPS_PRODUCTION_READ_ORG": "10xhealth",
                "CASEOPS_SANDBOX_TARGET_ORG": "10xhealth--sean",
                "CASEOPS_PRODUCTION_INSTANCE_URL": "https://login.salesforce.com",
                "CASEOPS_SANDBOX_INSTANCE_URL": "https://test.salesforce.com",
            },
            clear=False,
        ):
            payload = app.app.test_client().get("/api/orgs").get_json()

        self.assertEqual(payload["prod_lightning_host"], "10xhealth.lightning.force.com")
        self.assertEqual(payload["sandbox_lightning_host"], "10xhealth--sean.sandbox.lightning.force.com")

    def test_sandbox_lightning_host_alias_fallback_keeps_sandbox_segment(self):
        self.assertEqual(
            app._lightning_host_from_alias("10xhealth--sean", sandbox=True),
            "10xhealth--sean.sandbox.lightning.force.com",
        )

    def test_single_line_markdown_table_is_repaired_before_rendering(self):
        html = app.render_md("| Issue | Status | | --- | --- | | HEAL-1 | Ready |")

        self.assertIn("<table>", html)
        self.assertIn("<th>Issue</th>", html)
        self.assertIn("<td>HEAL-1</td>", html)

    def test_markdown_table_cells_escape_raw_pipes_when_repaired(self):
        repaired = app._fix_single_line_tables(
            "| Field | Notes | | --- | --- | | Status | Use A | B carefully |"
        )

        self.assertIn(r"Use A \| B carefully", repaired)

    def test_global_queue_skips_escalated_to_engineering(self):
        rows = [
            {"Key": "OPEN-1", "Status": "Open"},
            {"Key": "ENG-1", "Status": "Escalated to Engineering"},
            {"Key": "CLOSED-1", "Status": "Resolved"},
            {"Key": "DONE-1", "Status": "Open"},
        ]

        def snapshot_for(row):
            key = row["Key"]
            if key == "DONE-1":
                return True, "complete", f"fp-{key}", {"key": key, "mode": "active", "next_step": {"step": 12}}
            if key == "ENG-1":
                return False, "incomplete; next STEP_2 (Triage pre-escalated issue, pending)", f"fp-{key}", {
                    "key": key,
                    "mode": "escalated",
                    "status": "Escalated to Engineering",
                    "next_step": {"step": 2, "name": "Triage pre-escalated issue", "status": "pending"},
                    "steps": [{"step": 2, "name": "Triage pre-escalated issue", "status": "pending"}],
                }
            if key == "CLOSED-1":
                return False, "incomplete; next STEP_2 (Triage closed/resolved issue, pending)", f"fp-{key}", {
                    "key": key,
                    "mode": "closed",
                    "status": "Resolved",
                    "next_step": {"step": 2, "name": "Triage closed/resolved issue", "status": "pending"},
                    "steps": [{"step": 2, "name": "Triage closed/resolved issue", "status": "pending"}],
                }
            return False, "incomplete; next STEP_5 (Retrieve relevant Production metadata, pending)", f"fp-{key}", {
                "key": key,
                "mode": "active",
                "next_step": {"step": 5, "name": "Retrieve relevant Production metadata", "status": "pending"},
                "steps": [{"step": 5, "name": "Retrieve relevant Production metadata", "status": "pending"}],
            }

        messages = []
        dispositions = []
        with (
            patch.object(app, "_read_manifest", return_value=rows),
            patch.object(app, "_global_issue_queue_snapshot_from_row", side_effect=snapshot_for),
            patch.object(app, "_write_queue_disposition", side_effect=lambda key, payload: dispositions.append((key, payload["disposition"]))),
            patch.object(app, "_log_emit_line", side_effect=lambda _run_key, msg: messages.append(msg)),
        ):
            queued = app._select_global_issue_queue("__global__")

        self.assertEqual(queued, ["OPEN-1"])
        self.assertIn(("ENG-1", "skip_escalated_to_engineering"), dispositions)
        self.assertIn(("CLOSED-1", "skip_closed_or_resolved"), dispositions)
        self.assertIn(("DONE-1", "skip_unchanged_success"), dispositions)
        self.assertTrue(any("Queue skip: 1 issue — escalated to engineering;" in msg for msg in messages))
        self.assertTrue(any("Queue skip: 1 issue — closed/resolved;" in msg for msg in messages))
        self.assertFalse(any("Queue skip: ENG-1" in msg for msg in messages))
        self.assertFalse(any("Queue skip: CLOSED-1" in msg for msg in messages))
        self.assertTrue(any("already current=1" in msg for msg in messages))

    def test_dated_summary_prompt_includes_authoritative_queue_outcomes(self):
        captured = {}

        def fake_stream(prompt, run_key, key):
            captured["prompt"] = prompt
            captured["run_key"] = run_key
            captured["key"] = key
            return True

        with (
            patch.object(app, "_today_issue_summary_path", return_value=Path("outputs/summaries/2026-06-29/issue-summary-2026-06-29.md")),
            patch.object(app, "_do_stream_claude", side_effect=fake_stream),
            patch.object(app, "_log_emit_line"),
        ):
            ok = app._stream_global_dated_summary(
                ["OPEN-1", "BLOCKED-1"],
                "__global__",
                {
                    "OPEN-1": "complete",
                    "BLOCKED-1": "stalled/no progress in pass 3; incomplete; next STEP_9 (Deploy and test in Sandbox, blocked)",
                },
            )

        self.assertTrue(ok)
        self.assertEqual(captured["run_key"], "__global__")
        self.assertEqual(captured["key"], "__global__")
        self.assertIn("Authoritative queue outcome facts", captured["prompt"])
        self.assertIn("BLOCKED-1: stalled/no progress in pass 3", captured["prompt"])
        self.assertIn("do not summarize it as complete", captured["prompt"])
        self.assertIn("Validation Status: passed", captured["prompt"])
        self.assertIn("Fixed?: yes", captured["prompt"])
        self.assertIn("Partial Pass", captured["prompt"])
        self.assertIn("routing.path is unknown", captured["prompt"])
        self.assertIn("Do not run `ls`, `find`, `rg`, or broad directory scans under the CaseOps output directory.", captured["prompt"])
        self.assertIn("outputs/pipeline-state/OPEN-1.json", captured["prompt"])
        self.assertIn("outputs/investigations/BLOCKED-1.md", captured["prompt"])
        self.assertNotIn("outputs/pipeline-state/<KEY>.json", captured["prompt"])

    def test_dated_summary_prompt_uses_instance_routed_output_paths(self):
        captured = {}

        with (
            patch.object(app, "OUTPUTS", Path("/data/outputs")),
            patch.object(app, "_today_issue_summary_path", return_value=Path("/data/outputs/summaries/2026-06-29/issue-summary-2026-06-29.md")),
            patch.object(app, "_do_stream_claude", side_effect=lambda prompt, _run_key, _key: captured.setdefault("prompt", prompt) or True),
            patch.object(app, "_log_emit_line"),
        ):
            ok = app._stream_global_dated_summary(
                ["OPEN-1"],
                "__global__",
                {"OPEN-1": "incomplete; next STEP_5 (Retrieve relevant Production metadata, stale)"},
            )

        self.assertTrue(ok)
        self.assertIn("/data/outputs/pipeline-state/OPEN-1.json", captured["prompt"])
        self.assertIn("/data/outputs/investigations/OPEN-1.md", captured["prompt"])
        self.assertNotIn("\n- outputs/pipeline-state/OPEN-1.json", captured["prompt"])

    def test_outputs_dir_resolver_uses_docker_runtime_env(self):
        with patch.dict(os.environ, {"CASEOPS_OUTPUTS_DIR": "/data/outputs"}, clear=False):
            self.assertEqual(app._resolve_outputs_dir(), Path("/data/outputs"))

        with patch.dict(os.environ, {"CASEOPS_OUTPUTS_DIR": "", "CASEOPS_DATA_DIR": "/data"}, clear=False):
            self.assertEqual(app._resolve_outputs_dir(), Path("/data/outputs"))

    def test_global_queue_stall_counts_only_active_requeued_issue(self):
        rows = [
            {"Key": "ISSUE-A", "Status": "Open"},
            {"Key": "ISSUE-B", "Status": "Open"},
        ]
        snapshot_calls = {"ISSUE-A": 0, "ISSUE-B": 0}

        def snapshot_for_key(key):
            snapshot_calls[key] += 1
            if key == "ISSUE-A":
                if snapshot_calls[key] == 1:
                    return False, "incomplete; next STEP_5 (Retrieve relevant Production metadata, pending)", "a0"
                return False, "incomplete; next STEP_5 (Retrieve relevant Production metadata, stale)", "a1"
            return False, "incomplete; next STEP_9 (Deploy and test in Sandbox, pending)", "b0"

        def snapshot_from_row(row):
            key = row["Key"]
            _complete, detail, fingerprint = snapshot_for_key(key)
            status = "stale" if "stale" in detail else "pending"
            step_no = 5 if key == "ISSUE-A" else 9
            plan = {
                "key": key,
                "mode": "active",
                "next_step": {"step": step_no, "name": "Step", "status": status},
                "steps": [{"step": step_no, "name": "Step", "status": status}],
            }
            return False, detail, fingerprint, plan

        worker_results = [
            ("ISSUE-A", False, "incomplete"),
            ("ISSUE-B", False, "incomplete"),
            ("ISSUE-A", False, "incomplete"),
        ]
        messages = []
        summary = {}

        with (
            patch.object(app, "_issue_pipeline_runtime_ready", return_value=True),
            patch.object(app, "_select_global_issue_queue", return_value=["ISSUE-A", "ISSUE-B"]),
            patch.object(app, "_global_issue_queue_snapshot", side_effect=snapshot_for_key),
            patch.object(app, "_global_issue_queue_snapshot_from_row", side_effect=snapshot_from_row),
            patch.object(app, "_run_global_issue_worker", side_effect=worker_results),
            patch.object(app, "_read_manifest", return_value=rows),
            patch.object(app, "_global_max_parallel", return_value=1),
            patch.object(app, "_global_max_queue_passes", return_value=12),
            patch.object(app, "_run_stop_requested", return_value=False),
            patch.object(app, "_stream_global_dated_summary", side_effect=lambda keys, _run_key, outcomes: summary.update({"keys": keys, "outcomes": outcomes}) or True),
            patch.object(app, "_write_queue_disposition"),
            patch.object(app, "manifest_changed"),
            patch.object(app, "_log_emit_line", side_effect=lambda _run_key, msg: messages.append(msg)),
            patch.object(app, "_log_emit_done"),
            patch.object(app, "_finish_run_control"),
        ):
            app._stream_global_skill("reprocess all active issues without re-syncing from Jira", "__global__")

        self.assertTrue(any("Queue: requeueing 1 issue(s)" in msg for msg in messages))
        self.assertTrue(any("Queue stalled: 1 active issue(s) still incomplete" in msg for msg in messages))
        self.assertTrue(any("Queue: finished. complete=0, incomplete=2, reason=stalled" in msg for msg in messages))
        self.assertEqual(summary["keys"], ["ISSUE-A", "ISSUE-B"])
        self.assertIn("stalled/no progress in pass 1", summary["outcomes"]["ISSUE-B"])
        self.assertIn("stalled/no progress in pass 2", summary["outcomes"]["ISSUE-A"])

    def test_global_queue_does_not_requeue_same_blocked_step_for_artifact_churn(self):
        rows = [{"Key": "BLOCKED-1", "Status": "Waiting for customer"}]
        detail = "incomplete; next STEP_9 (Deploy and test in Sandbox, blocked)"
        snapshot_calls = {"BLOCKED-1": 0}

        def snapshot_for_key(key):
            snapshot_calls[key] += 1
            fingerprint = "fp-before" if snapshot_calls[key] == 1 else "fp-after-test-report-write"
            return False, detail, fingerprint

        def snapshot_from_row(row):
            return False, detail, "fp-after-test-report-write", {
                "key": row["Key"],
                "mode": "active",
                "status": row.get("Status", ""),
                "next_step": {"step": 9, "name": "Deploy and test in Sandbox", "status": "blocked"},
                "steps": [{"step": 9, "name": "Deploy and test in Sandbox", "status": "blocked"}],
            }

        messages = []
        summary = {}
        worker_calls = []

        def worker(key, index, total, *, reprocess):
            worker_calls.append(key)
            return key, False, detail

        with (
            patch.object(app, "_issue_pipeline_runtime_ready", return_value=True),
            patch.object(app, "_select_global_issue_queue", return_value=["BLOCKED-1"]),
            patch.object(app, "_global_issue_queue_snapshot", side_effect=snapshot_for_key),
            patch.object(app, "_global_issue_queue_snapshot_from_row", side_effect=snapshot_from_row),
            patch.object(app, "_run_global_issue_worker", side_effect=worker),
            patch.object(app, "_read_manifest", return_value=rows),
            patch.object(app, "_global_max_parallel", return_value=1),
            patch.object(app, "_global_max_queue_passes", return_value=12),
            patch.object(app, "_run_stop_requested", return_value=False),
            patch.object(app, "_stream_global_dated_summary", side_effect=lambda keys, _run_key, outcomes: summary.update({"keys": keys, "outcomes": outcomes}) or True),
            patch.object(app, "_write_queue_disposition"),
            patch.object(app, "manifest_changed"),
            patch.object(app, "_log_emit_line", side_effect=lambda _run_key, msg: messages.append(msg)),
            patch.object(app, "_log_emit_done"),
            patch.object(app, "_finish_run_control"),
        ):
            app._stream_global_skill("reprocess all active issues without re-syncing from Jira", "__global__")

        self.assertEqual(worker_calls, ["BLOCKED-1"])
        self.assertFalse(any("Queue: requeueing" in msg for msg in messages))
        self.assertTrue(any("Queue stalled: 1 active issue(s) still incomplete" in msg for msg in messages))
        self.assertEqual(summary["keys"], ["BLOCKED-1"])
        self.assertIn("artifact updated without planner advancement", summary["outcomes"]["BLOCKED-1"])

    def test_queue_disposition_skips_prior_unchanged_failure(self):
        row = {"Key": "FAIL-1", "Status": "Open", "Updated": "2026-06-08T00:00:00.000+0000"}
        signatures = {
            "jira_source": "same",
            "investigation": "same",
            "hypothesis": "same",
            "test_report": "same",
            "metadata_workspace": "same",
        }
        plan = {
            "key": "FAIL-1",
            "mode": "active",
            "signatures": signatures,
            "next_step": {"step": 9, "name": "Deploy and test in Sandbox", "status": "stale"},
            "steps": [{"step": 9, "name": "Deploy and test in Sandbox", "status": "stale"}],
        }
        state = {
            "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
            "signatures": signatures,
            "run_metrics": {"latest": {"status": "failed"}},
        }

        with patch.object(app, "_read_pipeline_state", return_value=state):
            disposition = app._queue_disposition_for_plan(
                row,
                plan,
                "incomplete; next STEP_9 (Deploy and test in Sandbox, stale)",
                "fp-current",
            )

        self.assertEqual(disposition["disposition"], "skip_unchanged_failure")
        self.assertIn("unchanged", disposition["reason"])

    def test_queue_disposition_prior_stale_state_skip_requires_same_fingerprint(self):
        row = {"Key": "STALE-1", "Status": "Open"}
        plan = {
            "key": "STALE-1",
            "mode": "active",
            "next_step": {"step": 3, "name": "Analyze issue", "status": "stale"},
            "steps": [{"step": 3, "name": "Analyze issue", "status": "stale"}],
        }
        state = {
            "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
            "queue_disposition": {
                "disposition": "stale_state_needs_repair",
                "fingerprint": "fp-same",
                "reason": "stalled/no progress",
            },
        }

        with patch.object(app, "_read_pipeline_state", return_value=state):
            same = app._queue_disposition_for_plan(
                row,
                plan,
                "incomplete; next STEP_3 (Analyze issue, stale)",
                "fp-same",
            )
            changed = app._queue_disposition_for_plan(
                row,
                plan,
                "incomplete; next STEP_3 (Analyze issue, stale)",
                "fp-changed",
            )

        self.assertEqual(same["disposition"], "stale_state_needs_repair")
        self.assertEqual(changed["disposition"], "ready_to_process")

    def test_queue_disposition_prior_reason_is_not_recursively_wrapped(self):
        row = {"Key": "STALE-1", "Status": "Open"}
        plan = {
            "key": "STALE-1",
            "mode": "active",
            "next_step": {"step": 9, "name": "Deploy and test in Sandbox", "status": "stale"},
            "steps": [{"step": 9, "name": "Deploy and test in Sandbox", "status": "stale"}],
        }
        state = {
            "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
            "queue_disposition": {
                "disposition": "stale_state_needs_repair",
                "fingerprint": "fp-same",
                "reason": "Previous queue result is unchanged: stalled/no progress in pass 4",
            },
        }

        with patch.object(app, "_read_pipeline_state", return_value=state):
            disposition = app._queue_disposition_for_plan(
                row,
                plan,
                "incomplete; next STEP_9 (Deploy and test in Sandbox, stale)",
                "fp-same",
            )

        self.assertEqual(
            disposition["reason"],
            "Previous queue result is unchanged: stalled/no progress in pass 4",
        )

    def test_completed_run_metrics_clear_queue_disposition(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            state_dir = outputs / "pipeline-state"
            state_dir.mkdir(parents=True)
            (state_dir / "DONE-1.json").write_text(
                json.dumps({
                    "key": "DONE-1",
                    "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                    "signatures": {},
                    "queue_disposition": {
                        "disposition": "stale_state_needs_repair",
                        "fingerprint": "old",
                        "reason": "stalled/no progress",
                    },
                }),
                encoding="utf-8",
            )
            now = app.datetime.now(app.timezone.utc)
            metrics = {
                "start": now.isoformat(),
                "end": now.isoformat(),
                "duration_seconds": 0.1,
                "status": "completed",
                "loop_events": {},
            }

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "_parse_run_metrics_from_logs", return_value=metrics),
            ):
                app._update_pipeline_run_metrics("DONE-1", "DONE-1", now, now, status="completed")

            stored = json.loads((state_dir / "DONE-1.json").read_text(encoding="utf-8"))

        self.assertNotIn("queue_disposition", stored)
        self.assertEqual(stored["run_metrics"]["latest"]["status"], "completed")

    def test_completed_reprocess_refreshes_state_from_artifacts_before_metrics(self):
        plan = {
            "key": "DONE-1",
            "next_step": {"step": 5, "name": "Retrieve relevant Production metadata", "status": "pending"},
            "steps": [{"step": 5, "name": "Retrieve relevant Production metadata", "status": "pending"}],
        }
        events = []

        def record_repair(*args, **kwargs):
            events.append(("repair", kwargs.get("reason"), kwargs.get("ignore_previous_state")))

        def record_metrics(*args, **kwargs):
            events.append(("metrics", kwargs.get("status")))
            return {"status": kwargs.get("status"), "step_timings": {}, "duration_seconds": 0.1}

        with (
            patch.object(app, "_log_emit_run_start"),
            patch.object(app, "_log_emit_line"),
            patch.object(app, "_issue_pipeline_runtime_ready", return_value=True),
            patch.object(app, "_read_manifest", return_value=[{"Key": "DONE-1", "Status": "Open", "Updated": "2026-06-29T00:00:00.000+0000"}]),
            patch.object(app, "_prepare_resume_plan", return_value=(plan, Path("pipeline-state/DONE-1.json"), "resume")),
            patch.object(app, "_log_resume_plan_summary"),
            patch.object(app, "_resume_plan_short_circuit", return_value=False),
            patch.object(app, "_build_claude_prompt", return_value="prompt"),
            patch.object(app, "_do_stream_claude", return_value=True),
            patch.object(app, "_repair_pipeline_state_from_artifacts_after_run", side_effect=record_repair),
            patch.object(app, "_update_pipeline_run_metrics", side_effect=record_metrics),
            patch.object(app, "_finish_run_control"),
            patch.object(app, "_invalidate_jira_summary_cache"),
            patch.object(app, "_invalidate_issues_api_cache"),
            patch.object(app, "_log_emit_done"),
        ):
            app._stream_reprocess_issue("DONE-1", "DONE-1", run_preflight=True)

        self.assertEqual(events[:2], [("repair", "completed", False), ("metrics", "completed")])

    def test_pipeline_failure_artifact_records_timeout_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            log_dir = outputs / "pipeline-logs"
            log_dir.mkdir(parents=True)
            log_path = log_dir / "ISSUE-1.jsonl"
            log_path.write_text(
                "\n".join([
                    json.dumps({"ts": "2026-06-26T12:00:00+00:00", "text": "STEP_8 ISSUE-1"}),
                    json.dumps({"ts": "2026-06-26T12:01:00+00:00", "text": "STEP_9 ISSUE-1"}),
                    json.dumps({"ts": "2026-06-26T12:02:00+00:00", "text": "[Bash] sf project deploy start --source-dir candidate --target-org sandbox --json"}),
                    json.dumps({"ts": "2026-06-26T12:03:00+00:00", "text": "ERROR: Claude process exceeded total timeout of 1200s — killing subprocess"}),
                ])
                + "\n",
                encoding="utf-8",
            )
            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "OUTPUTS_PIPELINE_LOGS", log_dir),
                patch.object(app, "_log_emit_line"),
            ):
                artifact = app._write_pipeline_failure_artifact(
                    "ISSUE-1",
                    "ISSUE-1",
                    failure_class="timeout_total",
                    reason="total timeout",
                    retryable=False,
                    next_action="repair then rerun",
                    run_started=app._parse_iso_ts("2026-06-26T12:00:00+00:00"),
                    run_ended=app._parse_iso_ts("2026-06-26T12:03:10+00:00"),
                )

            path = outputs / "pipeline-failures" / "ISSUE-1.json"
            state_path = outputs / "pipeline-state" / "ISSUE-1.json"
            saved = json.loads(path.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(artifact["failure_class"], "timeout_total")
        self.assertEqual(saved["failed_step"], 9)
        self.assertEqual(saved["last_successful_checkpoint"], 8)
        self.assertEqual(saved["last_command_family"], "sf-project-deploy")
        self.assertFalse(saved["retry_safe"])
        self.assertEqual(state["latest_failure"]["failure_class"], "timeout_total")

    def test_resume_plan_blocks_step9_after_timeout_failure_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            jira_summary = outputs / "jira" / "summary" / "ISSUE-1.md"
            investigation = outputs / "investigations" / "ISSUE-1.md"
            hypothesis = outputs / "hypothesis" / "ISSUE-1.md"
            workspace_manifest = outputs / "metadata-workspaces" / "ISSUE-1" / "metadata-workspace.json"
            failure_path = outputs / "pipeline-failures" / "ISSUE-1.json"
            for path, text in (
                (jira_summary, "summary"),
                (investigation, "## Problem Location\nRoot cause and failure point are known."),
                (hypothesis, "## Hypothesis\nCandidate solution exists."),
                (workspace_manifest, json.dumps({"candidate": "ready"})),
                (failure_path, json.dumps({
                    "key": "ISSUE-1",
                    "run_key": "ISSUE-1",
                    "failure_class": "timeout_total",
                    "failed_step": 9,
                    "last_successful_checkpoint": 8,
                    "retry_safe": False,
                    "next_action": "Inspect timeout artifact before rerun.",
                })),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            with patch.object(app, "OUTPUTS", outputs):
                plan = app._build_pipeline_resume_plan("ISSUE-1", "Open", "2026-06-26T00:00:00.000+0000")

        step9 = next(step for step in plan["steps"] if step["step"] == 9)
        self.assertEqual(step9["status"], "blocked")
        self.assertIn("timeout_total", step9["reason"])
        self.assertEqual(plan["latest_failure"]["failure_class"], "timeout_total")

    def test_resume_plan_ignores_old_failure_after_completed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            failure = {
                "key": "ISSUE-1",
                "run_key": "ISSUE-1",
                "failure_class": "timeout_total",
                "failed_step": 9,
                "last_successful_checkpoint": 8,
                "retry_safe": False,
                "next_action": "Inspect timeout artifact before rerun.",
            }
            state = {
                "key": "ISSUE-1",
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "latest_failure": failure,
                "run_metrics": {"latest": {"status": "completed"}},
            }
            for path, text in (
                (outputs / "jira" / "summary" / "ISSUE-1.md", "summary"),
                (outputs / "investigations" / "ISSUE-1.md", "## Problem Location\nRoot cause and failure point are known."),
                (outputs / "hypothesis" / "ISSUE-1.md", "## Hypothesis\nCandidate solution exists."),
                (outputs / "metadata-workspaces" / "ISSUE-1" / "metadata-workspace.json", json.dumps({"candidate": "ready"})),
                (outputs / "pipeline-failures" / "ISSUE-1.json", json.dumps(failure)),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            with patch.object(app, "OUTPUTS", outputs), patch.object(app, "_read_pipeline_state", return_value=state):
                plan = app._build_pipeline_resume_plan("ISSUE-1", "Open", "2026-06-26T00:00:00.000+0000")

        step9 = next(step for step in plan["steps"] if step["step"] == 9)
        self.assertEqual(plan["latest_failure"], {})
        self.assertNotEqual(step9["status"], "blocked")

    def test_queue_incomplete_summary_bucket_groups_next_steps(self):
        detail = "stalled/no progress in pass 3; incomplete; next STEP_9 (Deploy and test in Sandbox, stale)"
        self.assertEqual(
            app._queue_incomplete_summary_bucket(detail),
            "STEP_9 Deploy and test in Sandbox (stale)",
        )

    def test_step4_transition_contract_accepts_problem_hypothesis_heading(self):
        contract = app._evaluate_transition_contract_step4_to_step5(
            "## Problem Hypothesis (Active)\n\n"
            "**Problem focus:** No Case Auto-Response Rule exists in Production.\n\n"
            "The candidate solution is an operator Setup action."
        )

        self.assertEqual(contract["status"], "pass")
        self.assertEqual(contract["missing"], [])
        self.assertTrue(contract["observed"]["hypothesis_h2"])
        self.assertTrue(contract["observed"]["problem_focus"])

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
                "has_partial_pipeline_run": True,
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

    def test_partial_run_requires_mixed_issue_step_state(self):
        self.assertFalse(app._pipeline_state_has_partial_issue_run({}))
        self.assertFalse(app._pipeline_state_has_partial_issue_run({"steps": [{"step": 12, "status": "pending"}]}))
        self.assertFalse(app._pipeline_state_has_partial_issue_run({"steps": [{"step": 3, "status": "complete"}]}))
        self.assertTrue(
            app._pipeline_state_has_partial_issue_run(
                {
                    "steps": [
                        {"step": 3, "status": "complete"},
                        {"step": 4, "status": "pending"},
                        {"step": 12, "status": "pending"},
                    ]
                }
            )
        )

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
            "has_partial_pipeline_run": True,
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
            self.assertEqual(contract["condition_tags"], ["failed validation"])

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
                "issue_brief",
                "test_report",
                "eng_handoff",
                "closed_resolved",
            ],
        )

    def test_issue_brief_contract_requires_problem_first_and_five_sections(self):
        valid = "\n".join(
            [
                "Problem",
                "",
                "- Failure point.",
                "",
                "Reproduce",
                "",
                "1. Step.",
                "",
                "Expected behavior",
                "",
                "- Expected result.",
                "",
                "Affected record IDs",
                "",
                "- None confirmed.",
                "",
                "Proposed Solution",
                "",
                "- Fix it.",
            ]
        )
        invalid = "# Issue Brief\n\nProblem\n\nReproduce\n\nExpected behavior\n\nAffected record IDs\n\nProposed Solution\n"
        noisy = valid.replace(
            "Fix it.",
            "Fix it in [Flow: Example](sf://300000000000000AAA). Deploy ID: 0AfEa00000aMT53KAG SB.",
        )

        self.assertTrue(app._issue_brief_has_required_sections(valid))
        self.assertTrue(app._engineering_handoff_has_required_sections(valid))
        self.assertFalse(app._issue_brief_has_required_sections(invalid))
        self.assertFalse(app._issue_brief_has_required_sections(noisy))
        self.assertFalse(app._engineering_handoff_has_required_sections(noisy))

    def test_api_issues_includes_jira_summary_search_text_for_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            summary_path = outputs / app.FILE_LOCATIONS["jira_summary"].format(key="OPEN-1")
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                "# Jira Summary\n\nHidden filter keyword: practitioner billing address mismatch.\n",
                encoding="utf-8",
            )

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(
                    app,
                    "_read_manifest",
                    return_value=[
                        {
                            "Key": "OPEN-1",
                            "Status": "Open",
                            "Summary": "Visible issue summary",
                            "Assignee": "CaseOps User",
                        }
                    ],
                ),
            ):
                payload = app.app.test_client().get("/api/issues").get_json()

        self.assertEqual(len(payload), 1)
        self.assertIn("practitioner billing address mismatch", payload[0]["jira_summary_search_text"])

    def test_api_issues_row_cache_tracks_manifest_and_artifact_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            summary_path = outputs / app.FILE_LOCATIONS["jira_summary"].format(key="OPEN-1")
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text("first hidden keyword", encoding="utf-8")

            manifest_row = {
                "Key": "OPEN-1",
                "Status": "Open",
                "Summary": "Original summary",
                "Assignee": "CaseOps User",
                "Updated": "2026-06-01T00:00:00.000+0000",
            }

            def expire_payload_cache() -> None:
                with app._ISSUES_API_CACHE_LOCK:
                    app._issues_api_cache["created"] = 0.0

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "_read_manifest", side_effect=lambda: [dict(manifest_row)]),
            ):
                app._invalidate_issues_api_cache()
                client = app.app.test_client()

                first = client.get("/api/issues").get_json()[0]
                expire_payload_cache()
                second = client.get("/api/issues").get_json()[0]

                manifest_row["Summary"] = "Updated summary"
                expire_payload_cache()
                third = client.get("/api/issues").get_json()[0]

                summary_path.write_text("second hidden keyword", encoding="utf-8")
                os.utime(summary_path, None)
                expire_payload_cache()
                fourth = client.get("/api/issues").get_json()[0]

        self.assertEqual(first["summary"], "Original summary")
        self.assertEqual(second["summary"], "Original summary")
        self.assertEqual(third["summary"], "Updated summary")
        self.assertIn("first hidden keyword", third["jira_summary_search_text"])
        self.assertIn("second hidden keyword", fourth["jira_summary_search_text"])

    def test_available_tabs_includes_similar_issues_for_candidate_only_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            cluster_root = outputs / app.CLUSTER_DIR_NAME
            cluster_root.mkdir(parents=True, exist_ok=True)
            row = {
                "key": "OPEN-1",
                "status": "Open",
                "cluster_id": "",
                "cluster_type": "same_problem_needs_record_validation",
                "candidate_matches": [
                    {
                        "key": "OPEN-2",
                        "status": "Open",
                        "classification": "same_problem_needs_record_validation",
                        "score": 0.64,
                        "reasons": ["shared_error_term"],
                        "evidence_terms": ["permission"],
                        "rejection_reasons": ["below_confirmed_cluster_threshold"],
                    }
                ],
            }
            (cluster_root / app.ISSUE_INDEX_FILE).write_text(json.dumps(row) + "\n", encoding="utf-8")

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
            ):
                tabs = app._available_tabs("OPEN-1")

        self.assertEqual(tabs[0], {"id": "similar_issues", "label": "Similar Issues"})

    def test_similarity_health_reports_candidate_and_cluster_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            cluster_root = outputs / app.CLUSTER_DIR_NAME
            cluster_root.mkdir(parents=True, exist_ok=True)
            (cluster_root / app.CLUSTER_INDEX_FILE).write_text(
                json.dumps(
                    {
                        "generated_at": "2026-06-09T00:00:00+00:00",
                        "clusters": [{"cluster_id": "cluster-open-1"}],
                        "candidate_summary": {
                            "candidate_links": 4,
                            "promoted_links": 1,
                            "rejected_links": 3,
                            "top_rejection_reasons": [
                                {"reason": "below_confirmed_cluster_threshold", "count": 3}
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            rows = [
                {"key": "OPEN-1", "candidate_matches": [{"key": "OPEN-2"}]},
                {"key": "OPEN-2", "candidate_matches": []},
            ]
            (cluster_root / app.ISSUE_INDEX_FILE).write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            with patch.object(app, "OUTPUTS", outputs):
                health = app._similarity_health_summary(
                    {
                        "CASEOPS_SIMILAR_ISSUES_ENABLED": "true",
                        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER_ONLY": "true",
                        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER": "CaseOps User",
                        "CASEOPS_SIMILAR_ISSUES_PIPELINE_CONTEXT": "false",
                    }
                )

        self.assertTrue(health["enabled"])
        self.assertFalse(health["pipeline_context"])
        self.assertEqual(health["fingerprints_indexed"], 2)
        self.assertEqual(health["issues_with_candidates"], 1)
        self.assertEqual(health["candidate_links"], 4)
        self.assertEqual(health["confirmed_clusters"], 1)

    def test_candidate_only_issue_api_has_tab_without_confirmed_similar_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            cluster_root = outputs / app.CLUSTER_DIR_NAME
            cluster_root.mkdir(parents=True, exist_ok=True)
            row = {
                "key": "OPEN-1",
                "status": "Open",
                "cluster_id": "",
                "candidate_matches": [
                    {
                        "key": "OPEN-2",
                        "status": "Open",
                        "classification": "same_problem_needs_record_validation",
                        "score": 0.64,
                        "reasons": ["shared_error_term"],
                        "rejection_reasons": ["below_confirmed_cluster_threshold"],
                    }
                ],
            }
            (cluster_root / app.ISSUE_INDEX_FILE).write_text(json.dumps(row) + "\n", encoding="utf-8")

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(
                    app,
                    "_read_manifest",
                    return_value=[
                        {
                            "Key": "OPEN-1",
                            "Status": "Open",
                            "Summary": "Visible issue summary",
                            "Assignee": "CaseOps User",
                        }
                    ],
                ),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
                patch.object(app, "_read_pipeline_state", return_value={}),
            ):
                payload = app.app.test_client().get("/api/issue/OPEN-1").get_json()

        self.assertIn("similar_issues", [tab["id"] for tab in payload["tabs"]])
        self.assertTrue(payload["similar_issue_cluster"]["candidate_matches"])
        self.assertFalse(payload["has_similar_issues"])
        self.assertNotIn("similar issues", payload["tags"])

    def test_similarity_health_uses_default_assignee_as_current_user_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            (outputs / app.CLUSTER_DIR_NAME).mkdir(parents=True, exist_ok=True)
            with patch.object(app, "OUTPUTS", outputs):
                health = app._similarity_health_summary(
                    {
                        "CASEOPS_SIMILAR_ISSUES_ENABLED": "true",
                        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER_ONLY": "true",
                        "CASEOPS_DEFAULT_ASSIGNEE": "Fallback User",
                        "JIRA_EMAIL": "fallback@example.com",
                    }
                )

        self.assertTrue(health["current_user_present"])
        self.assertEqual(health["current_user"], "Fallback User")
        self.assertEqual(health["current_user_source"], "CASEOPS_DEFAULT_ASSIGNEE")

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
        self.assertNotIn("partial run", contract["condition_tags"])

    def test_no_deploy_operator_report_recovers_from_unknown_durable_deliverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            files = {
                "jira/summary/OPEN-1.md": "# Jira Summary\n",
                "investigations/OPEN-1.md": (
                    "## Problem Location\n"
                    "Specific artifact: Case Auto-Response Rule.\n"
                    "Failure point: missing Production Setup admin action.\n"
                    "Root cause: no active rule exists.\n"
                    "Support-resolvable classification complete.\n"
                ),
                "hypothesis/OPEN-1.md": (
                    "## Hypothesis\n"
                    "Problem focus: missing Production Setup admin action.\n"
                    "Root cause hypothesis: no active auto-response rule exists.\n"
                ),
                "test-reports/OPEN-1.md": "\n".join(
                    [
                        "## Validation Verdict",
                        "- Validation Status: not-run",
                        "- Fixed?: unknown",
                        "- Production deploy required: n/a",
                        "- Evidence: Operator action has not been executed by CaseOps.",
                        "",
                        "## Next Step",
                        "Configure the rule in Production Setup, then run the final email receipt check.",
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
            degraded_state = {
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "routing": {
                    "path": "support_resolvable",
                    "confidence": "low",
                    "reason": "Routing not yet persisted.",
                },
                "deliverable": {
                    "type": "unknown",
                    "production_deploy_required": "unknown",
                    "no_deploy_reason": "",
                },
                "signatures": {},
            }

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "_read_pipeline_state", return_value=degraded_state),
                patch.object(app, "_latest_issue_summary_path", return_value=None),
                patch.object(app, "_issue_has_similar_issue_context", return_value=False),
                patch.object(app, "_generated_files_for_issue", return_value=[]),
            ):
                plan = app._build_pipeline_resume_plan("OPEN-1", status="Open")

        step9 = next(step for step in plan["steps"] if step["step"] == 9)
        step10 = next(step for step in plan["steps"] if step["step"] == 10)
        self.assertEqual(step9["status"], "complete")
        self.assertEqual(step10["status"], "pending")
        self.assertEqual(plan["quality_gates"]["step_9_test_report"], "operator_action_pending")
        self.assertEqual(plan["deliverable"]["type"], "admin_action")
        self.assertEqual(plan["deliverable"]["production_deploy_required"], "n/a")

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
                    "next_step": {"step": 10, "name": "Draft issue brief, internal notes, and Jira message"},
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

    def test_pipeline_state_repair_clears_queue_disposition(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            plan = {
                "key": "STALE-1",
                "schema_version": app.PIPELINE_STATE_SCHEMA_VERSION,
                "queue_disposition": {
                    "disposition": "stale_state_needs_repair",
                    "fingerprint": "old",
                    "reason": "stalled/no progress",
                },
                "next_step": {"step": 9, "name": "Deploy and test in Sandbox", "status": "stale"},
                "quality_gates": {},
                "steps": [{"step": 9, "name": "Deploy and test in Sandbox", "status": "stale"}],
            }

            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.object(app, "_find_manifest_row", return_value={"Key": "STALE-1", "Status": "Open", "Updated": ""}),
                patch.object(app, "_build_pipeline_resume_plan", return_value=dict(plan)),
                patch.object(app, "_invalidate_jira_summary_cache"),
                patch.object(app, "manifest_changed"),
            ):
                result = app._repair_pipeline_state_key("STALE-1")

            stored = json.loads((outputs / "pipeline-state" / "STALE-1.json").read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertNotIn("queue_disposition", stored)
        self.assertTrue(stored["repair"]["queue_disposition_cleared"])

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
