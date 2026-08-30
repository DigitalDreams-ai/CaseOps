import tempfile
import unittest
from pathlib import Path

from pipeline_gates import validate_hypothesis_artifact


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

if __name__ == "__main__":
    unittest.main()
