import subprocess
import unittest
from pathlib import Path


class NoHardcodedOrgReferenceTests(unittest.TestCase):
    ORG_PREFIX = "10" + "x"
    ENV_PREFIX = ".env"
    BLOCKED_PATTERNS = (
        ORG_PREFIX + "health",
        ORG_PREFIX + "-healthsystem",
        ORG_PREFIX + "health-sean",
        ORG_PREFIX + "health--sean",
    )
    BLOCKED_ENV_FILE_PATTERNS = (
        ENV_PREFIX + ".jira",
        ENV_PREFIX + ".nas",
        ENV_PREFIX + ".{workspace}",
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
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            lowered = text.lower()
            for pattern in self.BLOCKED_PATTERNS:
                if pattern in lowered:
                    offenders.append(f"{rel_path}: {pattern}")

        self.assertEqual([], offenders)

    def test_tracked_files_use_single_env_filename(self):
        repo_root = Path(__file__).resolve().parents[1]
        files = subprocess.check_output(
            ["git", "ls-files"],
            cwd=repo_root,
            text=True,
        ).splitlines()

        offenders = []
        for rel_path in files:
            path = repo_root / rel_path
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            lowered = text.lower()
            for pattern in self.BLOCKED_ENV_FILE_PATTERNS:
                if pattern in lowered:
                    offenders.append(f"{rel_path}: {pattern}")

        self.assertEqual([], offenders)
