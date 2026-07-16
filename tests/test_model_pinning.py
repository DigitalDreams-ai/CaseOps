import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app


class ModelPinningTests(unittest.TestCase):
    def tearDown(self):
        with app._state_lock:
            app._active_keys.clear()
            app._active_run_actions.clear()
            app._active_run_controls.clear()

    def test_missing_model_rejects_pipeline_request(self):
        with patch.dict(os.environ, {"CASEOPS_ANTHROPIC_MODEL": ""}, clear=False):
            response = app.app.test_client().post("/api/run", json={"action": "full_issue", "key": "OPEN-1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "model_not_pinned")

    def test_alias_is_rejected_and_versioned_id_is_accepted(self):
        with patch.dict(os.environ, {"CASEOPS_ANTHROPIC_MODEL": "claude-sonnet"}, clear=False):
            with self.assertRaises(ValueError):
                app._pinned_model()
        with patch.dict(os.environ, {"CASEOPS_ANTHROPIC_MODEL": "claude-sonnet-4-6"}, clear=False):
            self.assertEqual(app._pinned_model(), "claude-sonnet-4-6")

    def test_settings_rejects_alias_before_writing_env_file(self):
        writer = Mock()
        with patch.object(app, "_write_env_file", writer):
            response = app.app.test_client().post(
                "/api/settings",
                json={"CASEOPS_ANTHROPIC_MODEL": "claude-sonnet"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "model_not_pinned")
        writer.assert_not_called()

    def test_settings_accepts_versioned_model(self):
        writer = Mock()
        with patch.object(app, "_write_env_file", writer):
            response = app.app.test_client().post(
                "/api/settings",
                json={"CASEOPS_ANTHROPIC_MODEL": "claude-sonnet-4-6"},
            )
        self.assertEqual(response.status_code, 200)
        writer.assert_called_once()
        self.assertEqual(writer.call_args.args[0]["CASEOPS_ANTHROPIC_MODEL"], "claude-sonnet-4-6")

    def test_model_change_logs_and_triggers_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            marker = outputs / "settings" / "last-model.json"
            marker.parent.mkdir(parents=True)
            marker.write_text(json.dumps({"model_id": "claude-sonnet-4-5"}), encoding="utf-8")
            logger = Mock()
            evaluator = Mock(return_value={})
            with (
                patch.object(app, "OUTPUTS", outputs),
                patch.dict(os.environ, {"CASEOPS_ANTHROPIC_MODEL": "claude-sonnet-4-6"}, clear=False),
                patch.object(app, "_output_evals_settings", return_value={"enabled": True}),
                patch.object(app, "_run_output_evals_once", evaluator),
                patch.object(app, "_log_emit_line", logger),
            ):
                result = app._detect_model_change(run_key="__global__")

            stored = json.loads(marker.read_text(encoding="utf-8"))
        self.assertTrue(result["changed"])
        self.assertEqual(stored["model_id"], "claude-sonnet-4-6")
        logger.assert_called_once_with("__global__", "MODEL CHANGE: claude-sonnet-4-5 -> claude-sonnet-4-6")
        evaluator.assert_called_once_with(reason="model_change")


if __name__ == "__main__":
    unittest.main()
