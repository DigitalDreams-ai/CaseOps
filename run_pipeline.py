#!/usr/bin/env python3
"""CaseOps pipeline entry point.

Runs the deterministic stages of the Jira-to-Salesforce fix pipeline:

  1. Sync issues from Jira via jira_sync.py (skippable with --no-sync).
  2. Read manifest.csv and triage every issue by status.
  3. Archive Closed/Resolved/Canceled issues to outputs/closed-resolved/.
  4. Archive pre-escalated issues to outputs/engineering-escalations/.
  5. Scaffold investigation records for active issues.
  6. Scaffold or update the dated issue summary.
  7. Print a handoff report for the AI reasoning steps.

The reasoning steps (diagnosis, escalation gate, implementation, deploy/test,
notes drafting) are handled by the jira-salesforce-fix-pipeline skill in
Claude Code or another capable AI agent pointed at the skill docs.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from caseops_paths import PROJECT_ROOT, default_jira_dir, default_jira_env_file
from jira_sync import MANIFEST_FIELDNAMES

CLOSED_STATUSES = {"closed", "resolved", "canceled", "cancelled"}
ESCALATED_STATUS = "escalated to engineering"

SKILLS_DIR = PROJECT_ROOT / "skills" / "jira-salesforce-fix-pipeline" / "assets"
INVESTIGATION_TEMPLATE = SKILLS_DIR / "investigation-record-template.md"
CLOSED_RESOLVED_TEMPLATE = SKILLS_DIR / "closed-resolved-log-template.md"
ISSUE_SUMMARY_TEMPLATE = SKILLS_DIR / "issue-summary-template.md"


def main() -> int:
    args = parse_args()
    jira_dir = Path(args.jira_dir)
    out_dir = PROJECT_ROOT / "outputs"

    closed_dir = out_dir / "closed-resolved"
    escalations_dir = out_dir / "engineering-escalations"
    investigations_dir = out_dir / "investigations"
    closed_dir.mkdir(parents=True, exist_ok=True)
    escalations_dir.mkdir(parents=True, exist_ok=True)
    investigations_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_sync:
        print("-- Step 1: Syncing from Jira ------------------------------")
        result = run_sync(args)
        if result != 0:
            print(
                "\nSync failed. Fix credentials or network and retry.\n"
                "To skip sync and use the existing manifest, add --no-sync.",
                file=sys.stderr,
            )
            return result
        print()

    manifest_path = jira_dir / "manifest.csv"
    if not manifest_path.exists():
        print(
            f"manifest.csv not found at {manifest_path}.\n"
            "Run without --no-sync to pull issues from Jira first.",
            file=sys.stderr,
        )
        return 1

    print("-- Step 2: Triaging issues --------------------------------")
    issues = read_manifest(manifest_path)

    # When targeting a single issue, triage only that row
    if args.issue:
        issues = [r for r in issues if r["Key"] == args.issue]
        if not issues:
            print(f"  {args.issue} not found in manifest after sync.", file=sys.stderr)
            return 1

    closed, escalated, active = [], [], []
    for issue in issues:
        status_lower = issue["Status"].lower()
        if status_lower in CLOSED_STATUSES:
            closed.append(issue)
        elif status_lower == ESCALATED_STATUS:
            escalated.append(issue)
        else:
            active.append(issue)

    print(f"  Total synced:             {len(issues)}")
    print(f"  Closed / Resolved / Canceled: {len(closed)}")
    print(f"  Escalated to Engineering: {len(escalated)}")
    print(f"  Active (needs processing): {len(active)}")
    print()

    if not args.dry_run:
        print("-- Step 3: Archiving Closed / Resolved / Canceled --------")
        for issue in closed:
            path = archive_closed(issue, jira_dir, closed_dir)
            print(f"  {issue['Key']}  ->  {path.relative_to(PROJECT_ROOT)}")
        if not closed:
            print("  (none)")
        print()

        print("-- Step 4: Archiving pre-escalated issues ------------------")
        for issue in escalated:
            path = archive_escalated(issue, jira_dir, escalations_dir)
            print(f"  {issue['Key']}  ->  {path.relative_to(PROJECT_ROOT)}")
        if not escalated:
            print("  (none)")
        print()

        print("-- Step 5: Scaffolding investigation records ---------------")
        for issue in active:
            path = scaffold_investigation(issue, investigations_dir)
            status = "created" if path[1] else "exists "
            print(f"  [{status}] {issue['Key']}  ->  {path[0].relative_to(PROJECT_ROOT)}")
        if not active:
            print("  (none)")
        print()

        print("-- Step 6: Updating dated summary --------------------------")
        summary_path = scaffold_summary(issues, closed, escalated, active, out_dir)
        print(f"  {summary_path.relative_to(PROJECT_ROOT)}")
        print()

    print("-- Step 7: Handoff to AI reasoning ------------------------")
    if active:
        print(f"\n  {len(active)} active issue(s) ready for processing:\n")
        for issue in active:
            print(f"    {issue['Key']}  {issue['Status']}")
            print(f"      {issue['Summary'][:72]}")
        print()

        if not args.dry_run and not args.no_agents:
            print("-- Step 8: Processing active issues in parallel -----------")
            process_active_issues_parallel(active)
        else:
            print(
                "\n  Ask your AI agent:\n"
                '  "Process my active Jira issues through the fix pipeline."\n'
                "\n  The jira-salesforce-fix-pipeline skill will handle diagnosis,\n"
                "  escalation gate, implementation, deploy/test, and response drafting."
            )
    else:
        print("\n  No active issues to process.")

    return 0


def run_sync(args: argparse.Namespace) -> int:
    jira_dir = Path(args.jira_dir)
    manifest_path = jira_dir / "manifest.csv"

    # For single-issue sync, preserve all other rows in the manifest
    existing_rows: dict[str, dict[str, str]] = {}
    if args.issue and manifest_path.exists():
        for row in read_manifest(manifest_path):
            existing_rows[row["Key"]] = row

    cmd = [sys.executable, str(PROJECT_ROOT / "jira_sync.py"), "--env-file", args.env_file]
    if args.incremental:
        cmd.append("--incremental")
    if args.issue:
        cmd += ["--issue", args.issue]
    if args.jira_dir != str(default_jira_dir()):
        cmd += ["--out-dir", args.jira_dir]

    result = subprocess.call(cmd)

    # Merge single-issue result back into the full manifest
    if args.issue and result == 0 and manifest_path.exists() and existing_rows:
        new_rows = read_manifest(manifest_path)
        for row in new_rows:
            existing_rows[row["Key"]] = row  # update or add the synced key
        fieldnames = MANIFEST_FIELDNAMES
        merged = {k: {fn: row.get(fn, "") for fn in fieldnames} for k, row in existing_rows.items()}
        with manifest_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(merged.values())
        print(f"Manifest merged: {len(existing_rows)} total issue(s).", flush=True)

    return result


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def archive_closed(issue: dict[str, str], jira_dir: Path, dest_dir: Path) -> Path:
    dest = dest_dir / f"{issue['Key']}.md"
    if dest.exists():
        return dest
    summary_md = _read_jira_summary(issue, jira_dir)
    template = _read_template(CLOSED_RESOLVED_TEMPLATE)
    content = (
        template
        .replace("[KEY]", issue["Key"])
        .replace("[JIRA_STATUS]", issue["Status"])
        .replace("- Summary:", f"- Summary: {issue['Summary']}")
        .replace("- Last updated (Jira):", f"- Last updated (Jira): {issue.get('Updated', '')}")
        .replace("[Paste or copy content from outputs/jira/summary/<KEY>.md]", summary_md)
    )
    dest.write_text(content, encoding="utf-8")
    return dest


def archive_escalated(issue: dict[str, str], jira_dir: Path, dest_dir: Path) -> Path:
    dest = dest_dir / f"{issue['Key']}.md"
    if dest.exists():
        return dest
    summary_md = _read_jira_summary(issue, jira_dir)
    content = (
        f"# Engineering Escalation — {issue['Key']}\n\n"
        f"> Pre-escalated: this issue had Jira status \"{issue['Status']}\" at sync time.\n"
        f"> No pipeline processing was performed. Full handoff details to be added by the AI agent.\n\n"
        f"## Jira Summary\n\n{summary_md}"
    )
    dest.write_text(content, encoding="utf-8")
    return dest


def scaffold_investigation(issue: dict[str, str], dest_dir: Path) -> tuple[Path, bool]:
    dest = dest_dir / f"{issue['Key']}.md"
    if dest.exists():
        return dest, False
    template = _read_template(INVESTIGATION_TEMPLATE)
    content = (
        template
        .replace("- Key:", f"- Key: {issue['Key']}")
        .replace("- Summary:", f"- Summary: {issue['Summary']}")
        .replace("- Status:", f"- Status: {issue['Status']}")
        .replace("- Link:", f"- Link: {issue.get('SummaryPath', '')}")
    )
    dest.write_text(content, encoding="utf-8")
    return dest, True


def scaffold_summary(
    all_issues: list[dict[str, str]],
    closed: list[dict[str, str]],
    escalated: list[dict[str, str]],
    active: list[dict[str, str]],
    out_dir: Path,
) -> Path:
    today = date.today().isoformat()
    dest = out_dir / f"issue-summary-{today}.md"

    closed_rows = "\n".join(
        f"| {i['Key']} | {i['Status']} | {i['Summary']} |" for i in closed
    ) or "| — | — | — |"
    active_rows = "\n".join(
        f"| {i['Key']} | {i['Status']} | {i['Summary']} | Pending | — |" for i in active
    ) or "| — | — | — | — | — |"
    escalated_rows = "\n".join(
        f"| {i['Key']} | {i['Status']} | — | outputs/engineering-escalations/{i['Key']}.md | — | — |"
        for i in escalated
    ) or "| — | — | — | — | — | — |"

    if dest.exists():
        return dest

    template = _read_template(ISSUE_SUMMARY_TEMPLATE)
    content = (
        template
        .replace("# CaseOps Issue Summary - YYYY-MM-DD", f"# CaseOps Issue Summary - {today}")
        .replace("Generated: YYYY-MM-DD", f"Generated: {today}")
        .replace("Last updated: YYYY-MM-DD", f"Last updated: {today}")
        .replace(
            "- Total issues synced:",
            f"- Total issues synced: {len(all_issues)}",
        )
        .replace(
            "- Closed / Resolved / Canceled (skipped, not processed):",
            f"- Closed / Resolved / Canceled (skipped, not processed): {len(closed)}",
        )
        .replace(
            "- Pre-escalated in Jira (skipped, not processed):",
            f"- Pre-escalated in Jira (skipped, not processed): {len(escalated)}",
        )
        .replace(
            "- Active issues processed:",
            f"- Active issues processed: {len(active)}",
        )
        .replace(
            "| — | — | — |",
            closed_rows,
            1,
        )
        .replace(
            "| — | — | — | — | — |",
            active_rows,
            1,
        )
        .replace(
            "| — | — | — | — | — | — |",
            escalated_rows,
            1,
        )
    )
    dest.write_text(content, encoding="utf-8")
    return dest


def _read_jira_summary(issue: dict[str, str], jira_dir: Path) -> str:
    summary_path = Path(issue.get("SummaryPath", ""))
    if summary_path.exists():
        return summary_path.read_text(encoding="utf-8")
    fallback = jira_dir / "summary" / f"{issue['Key']}.md"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    return f"Summary not found for {issue['Key']}."


def _read_template(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[Template not found: {path}]\n"


def process_active_issues_parallel(active: list[dict[str, str]], batch_size: int = 5) -> None:
    """Spawn parallel agents to process active issues through the fix pipeline."""
    if not active:
        return

    results_dir = PROJECT_ROOT / "outputs" / "step-8-results"
    results_dir.mkdir(parents=True, exist_ok=True)

    total = len(active)
    completed = 0
    failed = 0

    for i in range(0, total, batch_size):
        batch = active[i:i + batch_size]
        print(f"\n  Batch {i // batch_size + 1}: Processing {len(batch)} issue(s)...")

        processes = []
        for issue in batch:
            key = issue["Key"]
            cmd = [
                sys.executable,
                "-m", "claude",
                "run", "jira-salesforce-fix-pipeline",
                key,
            ]
            print(f"    → {key}", flush=True)
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append((key, p))
            except Exception as e:
                print(f"    ✗ {key} failed to start: {str(e)[:80]}", flush=True)
                failed += 1

        for key, p in processes:
            try:
                stdout, stderr = p.communicate(timeout=600)
                if p.returncode == 0:
                    print(f"    ✓ {key} completed", flush=True)
                    completed += 1
                else:
                    print(f"    ✗ {key} failed (exit {p.returncode})", flush=True)
                    failed += 1
            except subprocess.TimeoutExpired:
                p.kill()
                print(f"    ✗ {key} timeout", flush=True)
                failed += 1
            except Exception as e:
                print(f"    ✗ {key} error: {str(e)[:80]}", flush=True)
                failed += 1

    print(f"\n  Step 8 complete: {completed} succeeded, {failed} failed out of {total} issues")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CaseOps pipeline: sync, triage, scaffold, and hand off to AI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python run_pipeline.py                     # full run: sync + triage + scaffold
  python run_pipeline.py --incremental       # only pull recently updated issues
  python run_pipeline.py --no-sync           # triage from existing manifest
  python run_pipeline.py --dry-run           # show triage counts, write nothing
        """,
    )
    parser.add_argument(
        "--env-file",
        default=default_jira_env_file(),
        help="Jira credentials env file (default: .env.jira)",
    )
    parser.add_argument(
        "--jira-dir",
        default=str(default_jira_dir()),
        help="Directory containing manifest.csv and jira outputs (default: outputs/jira)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Pass --incremental to jira_sync.py (only pull updated issues)",
    )
    parser.add_argument(
        "--issue",
        help="Sync and triage a single issue key, merging it into the existing manifest",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip jira_sync.py and triage from the existing manifest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print triage counts but do not write any files",
    )
    parser.add_argument(
        "--no-agents",
        action="store_true",
        help="Skip Step 8 (parallel agent processing) and print handoff message instead",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
