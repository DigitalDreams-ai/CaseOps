import subprocess
import unittest
from pathlib import Path


class NoHardcodedOrgReferenceTests(unittest.TestCase):
    ORG_PREFIX = "10" + "x"
    BLOCKED_PATTERNS = (
        ORG_PREFIX + "health",
        ORG_PREFIX + "-healthsystem",
        ORG_PREFIX + "health-sean",
        ORG_PREFIX + "health--sean",
    )

    def test_tracked_files_do_not_hardcode_private_org_references(self):
        repo_root = Path(__file__).resolve().parents[1]
        files = subprocess.check_output(
            ["git", "ls-files"],
            cwd=repo_root,
            text=True,
        ).splitlines()

        offenders = []
        for rel_path in files:
            path = repo_root / rel_path
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            lowered = text.lower()
            for pattern in self.BLOCKED_PATTERNS:
                if pattern in lowered:
                    offenders.append(f"{rel_path}: {pattern}")

        self.assertEqual([], offenders)
