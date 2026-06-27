#!/usr/bin/env python3
"""Manual CaseOps knowledge auditor.

Reads inactive knowledge signals from appdata and creates pending lesson/helper
candidates. This command never writes to Jira, Salesforce, or Production.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import knowledge_service


def _default_outputs_dir() -> Path:
    if os.environ.get("CASEOPS_OUTPUTS_DIR"):
        return Path(os.environ["CASEOPS_OUTPUTS_DIR"])
    data_dir = os.environ.get("CASEOPS_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "outputs"
    return ROOT / "outputs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the manual CaseOps knowledge auditor")
    parser.add_argument("--outputs-dir", default=str(_default_outputs_dir()), help="CaseOps outputs directory")
    parser.add_argument("--min-recurrence", type=int, default=2, help="Minimum repeated signals before creating a pending lesson")
    args = parser.parse_args(argv)

    summary = knowledge_service.run_manual_audit(
        Path(args.outputs_dir),
        min_recurrence=max(1, args.min_recurrence),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
