#!/usr/bin/env python3
"""Run CaseOps output evaluations from the command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import knowledge_service
import output_evals
from model_config import validate_pinned_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate recent CaseOps output artifacts")
    parser.add_argument("--outputs", required=True, type=Path)
    parser.add_argument("--lookback-days", type=int, default=int(os.environ.get("CASEOPS_EVAL_LOOKBACK_DAYS", "7")))
    parser.add_argument("--max-artifacts", type=int, default=int(os.environ.get("CASEOPS_EVAL_MAX_ARTIFACTS", "25")))
    parser.add_argument("--alert-threshold", type=float, default=float(os.environ.get("CASEOPS_EVAL_ALERT_THRESHOLD", "0.9")))
    parser.add_argument("--llm", action="store_true", default=False)
    parser.add_argument("--reason", default="manual_cli")
    args = parser.parse_args()

    try:
        model_id = validate_pinned_model(os.environ.get("CASEOPS_ANTHROPIC_MODEL") or "")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    grader = output_evals.claude_cli_grader(model_id) if args.llm else None
    report = output_evals.run_output_evals(
        args.outputs,
        model_id=model_id,
        lookback_days=max(0, args.lookback_days),
        max_artifacts=max(1, args.max_artifacts),
        llm_enabled=args.llm,
        llm_grader=grader,
        alert_threshold=max(0.0, min(1.0, args.alert_threshold)),
        signal_writer=knowledge_service.write_signal,
        reason=args.reason,
    )
    print(json.dumps({
        "artifact_count": report["artifact_count"],
        "pass_rates": report["pass_rates"],
        "regressions": report["regressions"],
        "report_path": report["report_path"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
