import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import scripts.sf_caseops_helper as helper


class SalesforceHelperTests(unittest.TestCase):
    def test_classify_failure_detects_invalid_type(self):
        failure_class, retryable, next_action = helper._classify_failure('{"name":"INVALID_TYPE","message":"sObject type not supported."}', returncode=1)

        self.assertEqual(failure_class, "invalid_query_type")
        self.assertFalse(retryable)
        self.assertIn("verify-sobject", next_action)

    def test_retrieve_metadata_rejects_mixed_selectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                rc = helper.retrieve_metadata(Namespace(
                    org="prod",
                    metadata=["Flow:Example"],
                    source_dir=["force-app/main/default/flows/Example.flow-meta.xml"],
                    out_dir=tmp,
                    timeout=10,
                ))
            summary = json.loads((Path(tmp) / "retrieve-metadata-summary.json").read_text(encoding="utf-8"))

        self.assertEqual(rc, 1)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["failure_class"], "bad_cli_flag_combo")
        self.assertFalse(summary["retryable"])

    def test_retrieve_metadata_classifies_invalid_project_workspace(self):
        proc = subprocess.CompletedProcess(
            args=["sf"],
            returncode=1,
            stdout="",
            stderr="Error (InvalidProjectWorkspaceError): /app does not contain a valid Salesforce DX project.",
        )
        with tempfile.TemporaryDirectory() as tmp, patch.object(helper, "_run", return_value=proc) as run_mock:
            with redirect_stdout(StringIO()):
                rc = helper.retrieve_metadata(Namespace(
                    org="prod",
                    metadata=["WorkflowAlert:Example.Alert"],
                    source_dir=None,
                    out_dir=tmp,
                    timeout=10,
                ))
            summary = json.loads((Path(tmp) / "retrieve-metadata-summary.json").read_text(encoding="utf-8"))
            expected_project = Path(tmp) / "_caseops-sfdx-project"
            project_file_exists = (expected_project / "sfdx-project.json").exists()
            project_cwd = Path(run_mock.call_args.kwargs["cwd"])

        self.assertEqual(rc, 1)
        self.assertEqual(summary["failure_class"], "invalid_project_workspace")
        self.assertFalse(summary["retryable"])
        self.assertIn("workspace-init", summary["next_action"])
        self.assertTrue(project_file_exists)
        self.assertEqual(project_cwd, expected_project)

    def test_deploy_source_uses_source_dir_without_metadata_selector(self):
        proc = subprocess.CompletedProcess(
            args=["sf"],
            returncode=0,
            stdout=json.dumps({"status": 0, "result": {"id": "0Af123", "status": "Succeeded"}}),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp, patch.object(helper, "_run", return_value=proc) as run_mock:
            source_dir = Path(tmp) / "candidate" / "force-app"
            source_dir.mkdir(parents=True)
            with redirect_stdout(StringIO()):
                rc = helper.deploy_source(Namespace(
                    sandbox_org="sandbox",
                    source_dir=str(source_dir),
                    attempt=tmp,
                    test_level=None,
                    tests=None,
                    timeout=10,
                ))
            summary = json.loads((Path(tmp) / "deploy-source-summary.json").read_text(encoding="utf-8"))
            expected_project = source_dir.parent
            project_file_exists = (source_dir.parent / "sfdx-project.json").exists()
            project_cwd = Path(run_mock.call_args.kwargs["cwd"])

        self.assertEqual(rc, 0)
        self.assertTrue(summary["ok"])
        command = run_mock.call_args.args[0]
        self.assertIn("--source-dir", command)
        self.assertNotIn("--metadata", command)
        self.assertEqual(command[command.index("--target-org") + 1], "sandbox")
        self.assertEqual(project_cwd, expected_project)
        self.assertTrue(project_file_exists)

    def test_deploy_report_without_out_dir_uses_caseops_temp_project(self):
        proc = subprocess.CompletedProcess(
            args=["sf"],
            returncode=0,
            stdout=json.dumps({"status": 0, "result": {"id": "0Af123", "status": "Succeeded"}}),
            stderr="",
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict("os.environ", {"CASEOPS_TEMP_DIR": tmp}),
            patch.object(helper, "_run", return_value=proc) as run_mock,
        ):
            with redirect_stdout(StringIO()):
                rc = helper.deploy_report(Namespace(
                    org="sandbox",
                    deploy_id="0Af123",
                    out_dir=None,
                    timeout=10,
                ))

            project_root = Path(tmp) / "deploy-report-sfdx-project"
            project_file_exists = (project_root / "sfdx-project.json").exists()
            project_cwd = Path(run_mock.call_args.kwargs["cwd"])

        self.assertEqual(rc, 0)
        self.assertEqual(project_cwd, project_root)
        self.assertTrue(project_file_exists)

    def test_command_result_preserves_non_json_stdout(self):
        proc = subprocess.CompletedProcess(
            args=["sf"],
            returncode=0,
            stdout="not json at all",
            stderr="",
        )

        result = helper._command_result(kind="unit", proc=proc, command=["sf", "example", "--json"])

        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_class"], "json_parse_failed")
        self.assertIn("not json at all", result["stdoutTail"])
        self.assertIn("non-JSON", result["next_action"])

    def test_workspace_init_writes_issue_scoped_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                rc = helper.workspace_init(Namespace(issue_key="HEAL-1", attempt="attempt-002", root=tmp))
            manifest_path = Path(tmp) / "HEAL-1" / "metadata-workspace.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(manifest["issueKey"], "HEAL-1")
        self.assertEqual(manifest["activeAttempt"], "attempt-002")
        self.assertTrue(manifest["paths"]["candidate"].endswith("attempt-002\\candidate") or manifest["paths"]["candidate"].endswith("attempt-002/candidate"))

    def test_query_data_prechecks_primary_object_existence(self):
        describe = {
            "ok": False,
            "failure_class": "invalid_query_type",
            "retryable": False,
            "next_action": "Verify the object exists before retrying the query.",
        }
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(helper, "_describe_sobject", return_value=describe) as describe_mock,
            patch.object(helper, "_query") as query_mock,
        ):
            with redirect_stdout(StringIO()):
                rc = helper.query_data(Namespace(
                    org="prod",
                    soql="SELECT Id FROM Missing_Object__c LIMIT 1",
                    name=None,
                    out_dir=tmp,
                    timeout=10,
                    skip_existence_check=False,
                ))
            summary = json.loads((Path(tmp) / "query-data.json").read_text(encoding="utf-8"))

        self.assertEqual(rc, 1)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["failure_class"], "invalid_query_type")
        self.assertEqual(summary["precheck"]["sobject"], "Missing_Object__c")
        describe_mock.assert_called_once()
        query_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
