#!/usr/bin/env python3
"""Fast packaging smoke test for the CaseOps Docker image.

This checks files that are easy to omit from Docker COPY rules and validates
that the knowledge guardrail fails closed for unsafe Salesforce CLI patterns.
Run inside an image with:

  docker run --rm --entrypoint python3 <image> /app/scripts/docker_image_smoke.py
"""

from __future__ import annotations

import importlib
import json
import os
import py_compile
import sys
import tempfile
from pathlib import Path


APP_ROOT = Path(os.environ.get("CASEOPS_IMAGE_SMOKE_ROOT", "/app"))

REQUIRED_FILES = [
    "app.py",
    "knowledge_service.py",
    "issue_clusters.py",
    "jira_sync.py",
    "skill_registry.py",
    "caseops_paths.py",
    "scripts/knowledge_auditor.py",
    "scripts/sf_caseops_helper.py",
    "skills/caseops-pipeline/knowledge/core/manifest.json",
    "skills/caseops-pipeline/knowledge/core/index.json",
]

PYTHON_FILES = [path for path in REQUIRED_FILES if path.endswith(".py")]
IMPORT_MODULES = [
    "knowledge_service",
    "issue_clusters",
    "skill_registry",
    "caseops_paths",
]


def fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not (APP_ROOT / path).exists()]
    if missing:
        return fail("Missing required packaged files: " + ", ".join(missing))

    compile_root = Path(tempfile.mkdtemp(prefix="caseops-image-smoke-pycache-"))
    for relative_path in PYTHON_FILES:
        cfile = compile_root / (relative_path.replace("/", "__").replace("\\", "__") + "c")
        try:
            py_compile.compile(str(APP_ROOT / relative_path), cfile=str(cfile), doraise=True)
        except py_compile.PyCompileError as exc:
            return fail(f"Python compile failed for {relative_path}: {exc}")

    sys.path.insert(0, str(APP_ROOT))
    for module_name in IMPORT_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            return fail(f"Import failed for {module_name}: {exc}")

    knowledge_service = importlib.import_module("knowledge_service")
    result = knowledge_service.classify_guardrail_command(
        "sfdx force:source:deploy -p force-app"
    )
    if result.get("ok") is not False:
        return fail("Guardrail did not block legacy sfdx force deploy command")
    if not any(item.get("rule") == "legacy_sfdx_force" for item in result.get("findings", [])):
        return fail("Guardrail result did not include legacy_sfdx_force finding")

    manifest_path = APP_ROOT / "skills/caseops-pipeline/knowledge/core/manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return fail(f"Knowledge manifest is not readable JSON: {exc}")
    if not manifest.get("items"):
        return fail("Knowledge manifest has no items")

    print("[OK] CaseOps Docker image smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
