import csv
import json
import tempfile
import unittest
from pathlib import Path

from issue_clusters import (
    build_candidate_adjudication_packet,
    build_delta_validation_plan,
    parse_similarity_adjudication_output,
    read_issue_cluster_context,
    rebuild_issue_clusters,
    similarity_adjudication_json_schema,
    write_cluster_safety_validation,
    write_similarity_adjudication,
    write_similarity_correction,
)
from issue_clusters import _sanitize_public_summary


class IssueClusterFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outputs = Path(self.tmp.name)
        for rel in [
            "jira/raw",
            "jira/summary",
            "investigations",
            "hypothesis",
            "test-reports",
            "internal-notes",
        ]:
            (self.outputs / rel).mkdir(parents=True, exist_ok=True)
        self.rows = []

    def tearDown(self):
        self.tmp.cleanup()

    def add_issue(
        self,
        key,
        summary,
        description,
        *,
        status="Open",
        component="Automation",
        assignee="Frodo Operator",
        email="frodo@example.com",
        reporter="Fixture Reporter",
        request_type="Support Request",
        created="2026-06-01T00:00:00Z",
        updated="2026-06-01T00:00:00Z",
    ):
        self.rows.append(
            {
                "Key": key,
                "Summary": summary,
                "Status": status,
                "Created": created,
                "Updated": updated,
                "Assignee": assignee,
            }
        )
        raw = {
            "issue": {
                "fields": {
                    "status": {"name": status},
                    "summary": summary,
                    "description": description,
                    "components": [{"name": component}] if component else [],
                    "labels": [component.lower()] if component else [],
                    "customfield_10010": request_type,
                    "assignee": {"displayName": assignee, "emailAddress": email},
                    "reporter": {"displayName": reporter},
                    "created": created,
                    "updated": updated,
                }
            }
        }
        (self.outputs / "jira" / "raw" / f"{key}.json").write_text(json.dumps(raw), encoding="utf-8")
        for rel in ["jira/summary", "investigations", "hypothesis", "test-reports", "internal-notes"]:
            (self.outputs / rel / f"{key}.md").write_text(
                f"{key} {summary}\n{description}\n",
                encoding="utf-8",
            )

    def write_manifest(self):
        path = self.outputs / "jira" / "manifest.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Key", "Summary", "Status", "Created", "Updated", "Assignee"])
            writer.writeheader()
            writer.writerows(self.rows)

    def build_matrix(self):
        for group in range(5):
            for idx in range(2):
                self.add_issue(
                    f"ROOT-{group}-{idx}",
                    f"Same flow failure group {group} Account.Shared_Field_{group}__c exception",
                    f"Flow Shared_Flow_{group} failed with invalid exception on Account.Shared_Field_{group}__c.",
                    component=f"SharedFlow{group}",
                    status="Closed" if group == 0 and idx == 0 else "Open",
                    updated=f"2026-06-0{group + 1}T0{idx}:00:00Z",
                )
        for group in range(5):
            self.add_issue(
                f"SYM-{group}-A",
                "Notification failed with permission exception",
                f"Same symptom text but Account.Field_A_{group}__c is involved.",
                component=f"SymptomA{group}",
            )
            self.add_issue(
                f"SYM-{group}-B",
                "Notification failed with permission exception",
                f"Same symptom text but Contact.Field_B_{group}__c is involved.",
                component=f"SymptomB{group}",
            )
        for group in range(5):
            self.add_issue(
                f"TITLE-{group}-A",
                "User cannot save request",
                f"Opportunity.Title_A_{group}__c has a separate validation rule.",
                component=f"TitleA{group}",
            )
            self.add_issue(
                f"TITLE-{group}-B",
                "User cannot save request",
                f"Case.Title_B_{group}__c has unrelated entitlement config.",
                component=f"TitleB{group}",
            )
        self.write_manifest()

    def rebuild(self, **kwargs):
        options = {
            "include_closed": True,
            "current_user_only": True,
            "current_user": "Frodo Operator;frodo@example.com",
            "auto_cluster": True,
            "candidate_limit": 15,
            "lookback_days": 180,
            "log": lambda _msg: None,
        }
        options.update(kwargs)
        return rebuild_issue_clusters(
            outputs_dir=self.outputs,
            **options,
        )

    def test_fixture_matrix_clusters_same_root_and_blocks_false_positives(self):
        self.build_matrix()
        result = self.rebuild()
        self.assertGreaterEqual(result["clusters"], 5)
        self.assertGreater(result["candidate_links"], result["clusters"])

        same_root = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-1-1")
        self.assertTrue(same_root["cluster_id"])
        self.assertTrue(same_root["open_matches"])
        self.assertNotIn("ROOT-1-1", [item["key"] for item in same_root["open_matches"]])
        first_match = same_root["open_matches"][0]
        self.assertTrue(first_match["reasons"])
        self.assertTrue(first_match["evidence_terms"])

        symptom_only = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="SYM-1-A")
        self.assertFalse(symptom_only.get("cluster_id"))
        self.assertTrue(symptom_only.get("candidate_matches"))
        self.assertTrue(symptom_only.get("candidate_open_matches"))
        self.assertFalse(any(item.get("promoted_to_cluster") for item in symptom_only["candidate_matches"]))
        title_only = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="TITLE-1-A")
        self.assertFalse(title_only.get("cluster_id"))

        closed_context = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-0-1")
        self.assertTrue(closed_context["closed_matches"])

    def test_current_user_filter_and_closed_context_do_not_change_active_manifest_rows(self):
        self.add_issue(
            "OWNED-1",
            "Flow owned Account.Owned__c exception",
            "Flow Owned failed Account.Owned__c invalid exception.",
            component="OwnedFlow",
            assignee="Frodo Operator",
            email="frodo@example.com",
        )
        self.add_issue(
            "OTHER-1",
            "Flow owned Account.Owned__c exception",
            "Flow Owned failed Account.Owned__c invalid exception.",
            component="OwnedFlow",
            assignee="Other Person",
            email="other@example.com",
        )
        self.write_manifest()
        result = self.rebuild()
        self.assertEqual(result["issues"], 1)
        rows = (self.outputs / "jira" / "manifest.csv").read_text(encoding="utf-8")
        self.assertIn("OTHER-1", rows)

    def test_template_request_family_scores_as_candidate_without_auto_cluster(self):
        request_type = {"requestType": {"name": "Suggest a new feature"}}
        common_kwargs = {
            "component": "",
            "assignee": "Frodo Operator",
            "email": "frodo@example.com",
            "reporter": "Salesforce Integration",
            "request_type": request_type,
        }
        self.add_issue(
            "SUP-54",
            "Letter Enclosing Payment for Mediation Template Request",
            "Reporter Angie Archer asked for a new letter template for enclosing payment for mediation.",
            created="2026-06-01T09:00:00Z",
            updated="2026-06-01T09:10:00Z",
            **common_kwargs,
        )
        self.add_issue(
            "SUP-55",
            "Letter Defendant enclosing Plaintiff Transcript and Errata sheet",
            "Reporter Angie Archer asked for a new letter template for enclosing transcript and errata sheet.",
            created="2026-06-01T09:12:00Z",
            updated="2026-06-01T09:22:00Z",
            **common_kwargs,
        )
        self.add_issue(
            "SUP-58",
            "Letter Requesting Union Records Template Request",
            "Reporter Angie Archer asked for a new letter template for requesting union records.",
            created="2026-06-01T09:24:00Z",
            updated="2026-06-01T09:34:00Z",
            **common_kwargs,
        )
        self.write_manifest()

        result = self.rebuild()

        self.assertEqual(result["clusters"], 0)
        ctx = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="SUP-54")
        candidate_scores = {item["key"]: item["score"] for item in ctx["candidate_matches"]}
        self.assertGreaterEqual(candidate_scores["SUP-55"], 0.45)
        self.assertGreaterEqual(candidate_scores["SUP-58"], 0.45)
        self.assertFalse(any(item.get("promoted_to_cluster") for item in ctx["candidate_matches"]))
        reasons = {reason for item in ctx["candidate_matches"] for reason in item.get("reasons", [])}
        self.assertIn("same_service_request_family", reasons)
        self.assertIn("same_request_creation_burst", reasons)

    def test_auto_cluster_disabled_keeps_candidate_matches_unpromoted(self):
        self.add_issue(
            "ROOT-A",
            "Same flow failure Account.Shared_Field__c exception",
            "Flow Shared_Flow failed with invalid exception on Account.Shared_Field__c.",
            component="SharedFlow",
        )
        self.add_issue(
            "ROOT-B",
            "Same flow failure Account.Shared_Field__c exception",
            "Flow Shared_Flow failed with invalid exception on Account.Shared_Field__c.",
            component="SharedFlow",
        )
        self.write_manifest()
        result = self.rebuild(auto_cluster=False)

        self.assertEqual(result["clusters"], 0)
        self.assertEqual(result["promoted_links"], 0)
        ctx = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-A")
        self.assertFalse(ctx["cluster_id"])
        self.assertTrue(ctx["candidate_matches"])
        self.assertFalse(any(item.get("promoted_to_cluster") for item in ctx["candidate_matches"]))
        self.assertNotIn("confirmed_cluster_member", {item.get("relationship") for item in ctx["candidate_matches"]})

    def test_malformed_candidate_score_does_not_break_context_read(self):
        root = self.outputs / "issue-clusters"
        root.mkdir(parents=True, exist_ok=True)
        row = {
            "key": "OPEN-1",
            "status": "Open",
            "cluster_id": "",
            "candidate_matches": [
                {
                    "key": "OPEN-2",
                    "status": "Open",
                    "classification": "related_context_only",
                    "score": "not-a-number",
                    "reasons": ["shared_feature_terms"],
                }
            ],
        }
        (root / "issue-index.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

        ctx = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="OPEN-1")

        self.assertFalse(ctx["cluster_id"])
        self.assertEqual(ctx["candidate_matches"][0]["score"], 0.0)

    def test_operator_corrections_and_artifact_drift(self):
        self.build_matrix()
        self.rebuild()
        ctx = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-2-1")
        target = next(item for item in ctx["open_matches"] if item["key"] == "ROOT-2-0")
        self.assertFalse(target["is_stale"])

        (self.outputs / "test-reports" / "ROOT-2-0.md").write_text("changed report", encoding="utf-8")
        drifted = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-2-1")
        target = next(item for item in drifted["open_matches"] if item["key"] == "ROOT-2-0")
        self.assertTrue(target["is_stale"])

        write_similarity_correction(
            self.outputs,
            "ROOT-2-1",
            "mark_not_related",
            cluster_id=ctx["cluster_id"],
            reference_issue="ROOT-2-0",
        )
        corrected = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-2-1")
        self.assertNotIn("ROOT-2-0", [item["key"] for item in corrected["members"]])

        write_similarity_correction(
            self.outputs,
            "ROOT-2-1",
            "make_canonical",
            cluster_id=ctx["cluster_id"],
            canonical_issue="ROOT-2-1",
        )
        canonical = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-2-1")
        self.assertEqual(canonical["cluster"]["canonical_issue"], "ROOT-2-1")

        write_similarity_correction(
            self.outputs,
            "ROOT-2-1",
            "detach_from_cluster",
            cluster_id=ctx["cluster_id"],
        )
        detached = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-2-1")
        self.assertEqual(detached["cluster_state"], "detached")
        self.assertTrue(detached["summary_url"].startswith("/files/issue-clusters/"))

    def test_adjudication_schema_parser_prompt_and_delta_gate(self):
        self.build_matrix()
        self.rebuild()
        ctx = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-3-1")
        packet = build_candidate_adjudication_packet(ctx, issue_key="ROOT-3-1")
        self.assertIn("prompt", packet)
        self.assertIn("ROOT-3-0", packet["candidate_keys"])
        self.assertNotIn("full corpus", packet["prompt"].lower())
        self.assertEqual(similarity_adjudication_json_schema()["schema_version"], 1)

        valid = {
            "schema_version": 1,
            "current_issue": "ROOT-3-1",
            "cluster_id": ctx["cluster_id"],
            "adjudicator": "fixture",
            "candidates": [
                {
                    "key": "ROOT-3-0",
                    "classification": "same_problem_same_fix",
                    "confidence": 0.91,
                    "evidence_for": ["same flow", "same field", "same exception"],
                    "evidence_against": ["record/user specifics still unknown"],
                    "required_validation": ["confirm affected record", "run sandbox validation"],
                    "recommended_pipeline_mode": "delta_validation",
                    "rationale": "Fixture same root cause.",
                }
            ],
            "selected_canonical_issue": "ROOT-3-0",
            "selected_pipeline_mode": "delta_validation",
            "safety_gate": {
                "reuse_allowed": True,
                "requires_salesforce_validation": True,
                "requires_delta_validation": True,
                "stale_artifact_block": False,
                "reason": "Fixture validated.",
            },
        }
        parsed = parse_similarity_adjudication_output(
            json.dumps(valid),
            issue_key="ROOT-3-1",
            cluster_id=ctx["cluster_id"],
            candidate_keys=packet["candidate_keys"],
        )
        self.assertTrue(parsed["valid"])

        malformed = parse_similarity_adjudication_output(
            "{not-json",
            issue_key="ROOT-3-1",
            cluster_id=ctx["cluster_id"],
            candidate_keys=packet["candidate_keys"],
        )
        self.assertFalse(malformed["valid"])
        self.assertEqual(malformed["selected_pipeline_mode"], "full_investigation")

        persisted = write_similarity_adjudication(
            self.outputs,
            issue_key="ROOT-3-1",
            cluster_id=ctx["cluster_id"],
            model_output=json.dumps(valid),
            candidate_keys=packet["candidate_keys"],
        )
        self.assertTrue(persisted["valid"])
        refreshed = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-3-1")
        adjudicated = next(item for item in refreshed["open_matches"] if item["key"] == "ROOT-3-0")
        self.assertEqual(adjudicated["confidence"], 0.91)

        write_cluster_safety_validation(
            self.outputs,
            issue_key="ROOT-3-1",
            cluster_id=ctx["cluster_id"],
            validation_status="pass",
            salesforce_checks=["confirmed affected record", "ran sandbox validation"],
            reuse_reason="Fixture delta validation passed.",
        )
        safety_context = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-3-1")
        lookup = {
            "cluster_id": ctx["cluster_id"],
            "classification": "same_problem_same_fix",
            "issue_is_stale": False,
            "open_matches": safety_context["open_matches"],
            "closed_matches": safety_context["closed_matches"],
            "adjudication": persisted,
            "safety": safety_context["cluster"]["safety"],
        }
        allowed = build_delta_validation_plan(lookup, delta_mode_enabled=True)
        self.assertTrue(allowed["allowed"])

        (self.outputs / "test-reports" / "ROOT-3-1.md").write_text("drift after validation", encoding="utf-8")
        stale_safety_context = read_issue_cluster_context(outputs_dir=self.outputs, issue_key="ROOT-3-1")
        self.assertFalse(stale_safety_context["cluster"]["safety"]["reuse_allowed"])
        self.assertTrue(stale_safety_context["cluster"]["safety"]["validation_stale"])

        blocked = build_delta_validation_plan({**lookup, "adjudication": None}, delta_mode_enabled=True)
        self.assertFalse(blocked["allowed"])
        self.assertIn("no valid model adjudication", blocked["reason"])

    def test_public_summary_redaction(self):
        unsafe = (
            "force://client:secret@example C:\\Users\\operator\\secret\\file.txt "
            "https://example.invalid/secur/frontdoor.jsp?sid=SESSION_TOKEN "
            "003000000000000AAA frodo@example.com prod-alias"
        )
        safe = _sanitize_public_summary(unsafe, {"prod-alias"})
        self.assertNotIn("force://", safe)
        self.assertNotIn("C:\\Users", safe)
        self.assertNotIn("token", safe)
        self.assertNotIn("frodo@example.com", safe)
        self.assertNotIn("prod-alias", safe)


if __name__ == "__main__":
    unittest.main()
