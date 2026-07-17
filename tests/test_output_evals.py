import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import app
import knowledge_service
import output_evals


HYPOTHESIS = """# Problem Hypothesis

## Problem Hypothesis

**Root cause hypothesis:** The Account validation rule rejects supported updates because Region__c is absent from its accepted-value condition.

## Smallest Viable Fix

- **Artifact:** Account.Region_Required
- Add the supported Region value while preserving all other conditions.

## Sandbox Validation Plan

- Reproduce the Account update in Sandbox.
- Confirm supported values save and unsupported values remain blocked.

## Rollback Plan

- Restore the prior condition if validation fails.
"""

HANDOFF = """Problem

- Flow: Account_Update_Region sends an unsupported Account.Region__c value.
- The save fails before downstream automation starts.

Reproduce

1. Log in as the affected user.
2. Open the Account and update Region.
3. Save and observe the validation error.

Expected behavior

- The supported Region value saves successfully.

Affected record IDs

- Example Account 001000000000001AAA.

Proposed Solution

- Update Flow Account_Update_Region to pass a supported Region__c value.
- Run the Account update regression scenario in Sandbox.
"""


class OutputEvalTests(unittest.TestCase):
    def _write(self, outputs: Path, dirname: str, key: str, text: str) -> Path:
        path = outputs / dirname / f"{key}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_deterministic_checks_cover_clean_and_bad_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            clean_jira = self._write(outputs, "jira-messages", "GOOD-1", "Hi Sam,\n\nThe field rule blocked the update. I can help verify the corrected value after it is applied.")
            bad_jira = self._write(outputs, "jira-messages", "BAD-1", "Hi Sam,\n\n[INTERNAL] We leverage a robust fix — Sam can use record 001000000000001AAA.")
            clean_notes = self._write(outputs, "internal-notes", "GOOD-1", "NOT a missing field. Root cause is the validation rule.\n\nProduction has the rule. No deploy is needed.\n\nAction: update the allowed value.")
            bad_notes = self._write(outputs, "internal-notes", "BAD-1", "Looked at the issue and found some details.")
            self._write(outputs, "hypothesis", "GOOD-1", HYPOTHESIS)
            self._write(outputs, "hypothesis", "BAD-1", "## Problem Hypothesis\nTBD")
            self._write(outputs, "engineering-escalations", "GOOD-1", HANDOFF)
            self._write(outputs, "engineering-escalations", "BAD-1", "Problem\nUnknown")

            self.assertTrue(output_evals.evaluate_artifact(outputs, "jira_message", clean_jira)["deterministic_passed"])
            self.assertFalse(output_evals.evaluate_artifact(outputs, "jira_message", bad_jira)["deterministic_passed"])
            self.assertTrue(output_evals.evaluate_artifact(outputs, "internal_notes", clean_notes)["deterministic_passed"])
            self.assertFalse(output_evals.evaluate_artifact(outputs, "internal_notes", bad_notes)["deterministic_passed"])
            self.assertTrue(output_evals.evaluate_artifact(outputs, "hypothesis", outputs / "hypothesis" / "GOOD-1.md")["deterministic_passed"])
            self.assertFalse(output_evals.evaluate_artifact(outputs, "hypothesis", outputs / "hypothesis" / "BAD-1.md")["deterministic_passed"])
            self.assertTrue(output_evals.evaluate_artifact(outputs, "engineering_escalation", outputs / "engineering-escalations" / "GOOD-1.md")["deterministic_passed"])
            self.assertFalse(output_evals.evaluate_artifact(outputs, "engineering_escalation", outputs / "engineering-escalations" / "BAD-1.md")["deterministic_passed"])

    def test_history_appends_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "jira-messages", "GOOD-1", "The field rule blocked the update. I can help verify the corrected value.")
            fixed_now = datetime.now(timezone.utc)
            for reason in ("first", "second"):
                output_evals.run_output_evals(
                    outputs,
                    model_id="claude-sonnet-4-6",
                    reason=reason,
                    now=fixed_now,
                )
            lines = (outputs / "eval-reports" / "history.jsonl").read_text(encoding="utf-8").splitlines()
            reports = list((outputs / "eval-reports").glob("*.json"))
            self.assertEqual(len(lines), 2)
            self.assertEqual(len(reports), 2)
            self.assertEqual(json.loads(lines[0])["reason"], "first")
            self.assertEqual(json.loads(lines[1])["reason"], "second")

    def test_persistent_regression_resignals_on_cooldown(self):
        # New regressions signal immediately. Persistent ones stay quiet
        # inside the cooldown window (no signal-file spam, no recurrence
        # inflation) but re-signal once the cooldown elapses, so a
        # still-degraded pipeline keeps reappearing in the review queue.
        from datetime import datetime, timedelta, timezone

        start = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "jira-messages", "BAD-1", "[INTERNAL] We leverage a robust solution — now.")
            writer = Mock()

            first = output_evals.run_output_evals(
                outputs, model_id="claude-sonnet-4-6", alert_threshold=0.9, lookback_days=30,
                signal_writer=writer, now=start,
            )
            self.assertTrue(first["regressions"])
            writer.assert_called_once()
            self.assertEqual(writer.call_args.kwargs["signal_type"], "output_quality_regression")

            # Next day, same persistent regression: inside cooldown, no signal.
            second = output_evals.run_output_evals(
                outputs, model_id="claude-sonnet-4-6", alert_threshold=0.9, lookback_days=30,
                signal_writer=writer, now=start + timedelta(days=1),
            )
            self.assertEqual(writer.call_count, 1)
            self.assertTrue(second["regressions"])
            self.assertEqual(second["new_regressions"], {})

            # Cooldown elapsed: persistent regression re-signals.
            third = output_evals.run_output_evals(
                outputs, model_id="claude-sonnet-4-6", alert_threshold=0.9, lookback_days=30,
                signal_writer=writer, now=start + timedelta(days=output_evals.RESIGNAL_AFTER_DAYS + 1),
            )
            self.assertEqual(writer.call_count, 2)
            self.assertTrue(third["regressions"])

    def test_generic_greeting_is_not_treated_as_reporter_name(self):
        message = (
            "Hi team,\n\nThe report filter was excluding the team's records. "
            "I fixed it in our test environment and confirmed the team can see them now.\n"
        )
        checks = output_evals._jira_message_checks(message)
        self.assertTrue(checks["reporter_name_once"]["passed"])

    def test_named_reporter_repetition_still_fails(self):
        message = (
            "Hi Ashlee,\n\nAshlee, the filter was wrong. I fixed it, Ashlee.\n"
        )
        checks = output_evals._jira_message_checks(message)
        self.assertFalse(checks["reporter_name_once"]["passed"])

    def test_regression_signal_is_accepted_by_knowledge_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "jira-messages", "BAD-2", "[INTERNAL] We leverage a robust solution — now.")
            report = output_evals.run_output_evals(
                outputs,
                model_id="claude-sonnet-4-6",
                alert_threshold=0.9,
                signal_writer=knowledge_service.write_signal,
            )
            signals = list((outputs / "org-knowledge" / "signals").glob("*.json"))
        self.assertTrue(report["new_regressions"])
        self.assertEqual(len(signals), 1)
        self.assertNotIn("signal_error", report)

    def test_plain_fifteen_character_word_is_not_treated_as_salesforce_id(self):
        checks = output_evals._jira_message_checks("The recommendations are ready for review.")
        self.assertTrue(checks["no_salesforce_ids"]["passed"])

    def test_llm_grade_parses_and_malformed_json_does_not_stop_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "jira-messages", "GOOD-1", "The field rule blocked the update. I can help verify the corrected value.")
            good = output_evals.run_output_evals(
                outputs,
                model_id="claude-sonnet-4-6",
                llm_enabled=True,
                llm_grader=lambda _prompt: '{"scores":{"voice":5,"clarity":4,"next_step_clear":5},"worst_problem":""}',
            )
            self.assertEqual(good["results"][0]["llm_grade"]["scores"]["voice"], 5)

            bad = output_evals.run_output_evals(
                outputs,
                model_id="claude-sonnet-4-6",
                llm_enabled=True,
                llm_grader=lambda _prompt: "not json",
            )
            self.assertIn("JSONDecodeError", bad["results"][0]["llm_grade"]["llm_error"])

    def test_claude_grader_rejects_model_alias(self):
        with self.assertRaises(ValueError):
            output_evals.claude_cli_grader("claude-sonnet")

    def test_manual_and_latest_eval_apis(self):
        report = {
            "artifact_count": 2,
            "pass_rates": {"jira_message.no_em_dash": 1.0},
            "regressions": {},
            "latest_path": "eval-reports/latest.md",
        }
        client = app.app.test_client()
        with patch.object(app, "_run_output_evals_once", return_value=report) as runner:
            response = client.post("/api/evals/run")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["artifact_count"], 2)
        runner.assert_called_once_with(reason="manual")

        latest = {"summary_markdown": "# Report", "headline": {"artifact_count": 2}}
        with patch.object(output_evals, "read_latest_report", return_value=latest):
            response = client.get("/api/evals/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["summary_markdown"], "# Report")

    def test_eval_scheduler_settings_and_thread_registration(self):
        settings = app._output_evals_settings({
            "CASEOPS_OUTPUT_EVALS_ENABLED": "true",
            "CASEOPS_OUTPUT_EVALS_INTERVAL_MINUTES": "1440",
            "CASEOPS_EVAL_LOOKBACK_DAYS": "7",
            "CASEOPS_EVAL_MAX_ARTIFACTS": "25",
            "CASEOPS_EVAL_LLM_ENABLED": "false",
            "CASEOPS_EVAL_ALERT_THRESHOLD": "0.9",
        })
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["interval_minutes"], 1440)

        thread = Mock()
        try:
            with patch.object(app.threading, "Thread", return_value=thread) as factory:
                app._OUTPUT_EVALS_THREAD_STARTED = False
                app._start_output_evals_scheduler_if_needed()
            factory.assert_called_once()
            self.assertIs(factory.call_args.kwargs["target"], app._output_evals_scheduler_loop)
            thread.start.assert_called_once()
        finally:
            app._OUTPUT_EVALS_THREAD_STARTED = False

    def test_settings_template_exposes_eval_controls(self):
        template = (Path(__file__).resolve().parents[1] / "templates" / "settings.html").read_text(encoding="utf-8")
        for expected in (
            'id="output-evals-section"',
            'name="CASEOPS_OUTPUT_EVALS_ENABLED"',
            'name="CASEOPS_EVAL_LLM_ENABLED"',
            'id="run-output-evals-btn"',
            "async function runOutputEvals()",
        ):
            self.assertIn(expected, template)


if __name__ == "__main__":
    unittest.main()
