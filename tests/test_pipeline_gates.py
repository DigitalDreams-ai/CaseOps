import tempfile
import unittest
from pathlib import Path

from pipeline_gates import validate_escalation_handoff, validate_hypothesis_artifact


FILLED_HYPOTHESIS = """# Problem Hypothesis and Solution

## Problem Hypothesis

**Confirmed facts:**
- The issue consistently occurs for the affected profile in Production.

**Root cause hypothesis:**
The Account validation configuration rejects the update because Region__c is omitted from the allowed-value condition.

## Smallest Viable Fix

- **Artifact:** Account.Region_Required
- **Change scope:** Add the missing allowed value.
- **Why it solves the problem:** The update will satisfy the existing rule.

## Sandbox Validation Plan

- Reproduce the update in Sandbox and confirm that it succeeds.
- Confirm unrelated values are still rejected by the validation rule.

## Rollback Plan

- Restore the prior validation rule condition if testing fails.
"""

FILLED_HANDOFF = """Problem

- Flow: Account_Update_Region updates Account.Region__c with an unsupported value.
- The validation failure stops the save before downstream automation runs.

Reproduce

1. Log in as the affected user.
2. Edit the Account Region field.
3. Save and observe the validation error.

Expected behavior

- The supported Region value saves successfully.

Affected record IDs

- Example Account 001000000000001AAA.

Proposed Solution

- Update Flow Account_Update_Region to pass the supported Region__c value.
- Re-run the account update regression scenario in Sandbox.
"""


class PipelineGateTests(unittest.TestCase):
    def _write(self, outputs: Path, subdir: str, key: str, text: str) -> None:
        path = outputs / subdir / f"{key}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_hypothesis_passes_when_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "hypothesis", "ISSUE-1", FILLED_HYPOTHESIS)
            self.assertTrue(validate_hypothesis_artifact(outputs, "ISSUE-1").passed)

    def test_hypothesis_fails_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_hypothesis_artifact(Path(tmp), "ISSUE-1")
            self.assertFalse(result.passed)
            self.assertIn("missing", result.reason.lower())

    def test_hypothesis_fails_when_too_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "hypothesis", "ISSUE-1", "## Problem Hypothesis\nShort")
            self.assertFalse(validate_hypothesis_artifact(outputs, "ISSUE-1").passed)

    def test_hypothesis_fails_when_heading_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "hypothesis", "ISSUE-1", FILLED_HYPOTHESIS.replace("## Sandbox Validation Plan", "## Testing"))
            self.assertFalse(validate_hypothesis_artifact(outputs, "ISSUE-1").passed)

    def test_hypothesis_fails_when_placeholder_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "hypothesis", "ISSUE-1", FILLED_HYPOTHESIS + "\n[Fact 1: replace me]\n")
            result = validate_hypothesis_artifact(outputs, "ISSUE-1")
            self.assertFalse(result.passed)
            self.assertIn("placeholder", result.reason.lower())

    def test_hypothesis_fails_when_root_cause_is_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            text = FILLED_HYPOTHESIS.replace(
                "The Account validation configuration rejects the update because Region__c is omitted from the allowed-value condition.",
                "Unknown.",
            )
            self._write(outputs, "hypothesis", "ISSUE-1", text)
            self.assertFalse(validate_hypothesis_artifact(outputs, "ISSUE-1").passed)

    def test_hypothesis_fails_when_artifact_is_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "hypothesis", "ISSUE-1", FILLED_HYPOTHESIS.replace("Account.Region_Required", "[component]"))
            result = validate_hypothesis_artifact(outputs, "ISSUE-1")
            self.assertFalse(result.passed)
            self.assertIn("artifact", result.reason.lower())

    def test_escalation_passes_with_flow_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "engineering-escalations", "ISSUE-1", FILLED_HANDOFF)
            self.assertTrue(validate_escalation_handoff(outputs, "ISSUE-1").passed)

    def test_escalation_passes_when_only_artifact_is_a_case_or_custom_object_id(self):
        # Case (500) and custom-object (aXX) key prefixes must count as
        # concrete artifacts.
        for record_id in ("500Ql00000ujeSTIAY", "a0X8d000001AbCdEAV"):
            handoff = FILLED_HANDOFF.replace(
                "- Flow: Account_Update_Region updates Account.Region__c with an unsupported value.",
                f"- Record {record_id} is stuck in the broken state.",
            ).replace("Account.Region__c value.", "record value.")
            handoff = handoff.replace("Flow Account_Update_Region", "the automation")
            with tempfile.TemporaryDirectory() as tmp:
                outputs = Path(tmp)
                self._write(outputs, "engineering-escalations", "ISSUE-1", handoff)
                result = validate_escalation_handoff(outputs, "ISSUE-1")
                self.assertTrue(result.passed, f"{record_id}: {result.reason}")

    def test_escalation_fails_when_section_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "engineering-escalations", "ISSUE-1", FILLED_HANDOFF.replace("Expected behavior", "Desired result"))
            self.assertFalse(validate_escalation_handoff(outputs, "ISSUE-1").passed)

    def test_escalation_fails_ask_to_discover_outside_open_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "engineering-escalations", "ISSUE-1", FILLED_HANDOFF + "\n- Which specific class should change?\n")
            result = validate_escalation_handoff(outputs, "ISSUE-1")
            self.assertFalse(result.passed)
            self.assertIn("ask-to-discover", result.reason.lower())

    def test_escalation_allows_ask_to_discover_inside_open_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "engineering-escalations", "ISSUE-1", FILLED_HANDOFF + "\n## Open Questions\n\n- Which specific release owns deployment?\n")
            self.assertTrue(validate_escalation_handoff(outputs, "ISSUE-1").passed)

    def test_escalation_exemption_short_circuits(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = Path(tmp)
            self._write(outputs, "engineering-escalations", "ISSUE-1", "Pre-escalated at sync\n")
            result = validate_escalation_handoff(outputs, "ISSUE-1")
            self.assertTrue(result.passed)
            self.assertTrue(result.details["exempt"])


if __name__ == "__main__":
    unittest.main()
