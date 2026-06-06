# CaseOps Deep Review - 2026-06-06

Scope: review the current `main` tree after the recent org-reference cleanup and env-file consolidation.

## Remediation Status

Implemented in the current working tree:

- Runtime prompts now use generic/operator-configurable wording instead of a maintainer-specific name.
- Flask debug mode now defaults off and is controlled by `CASEOPS_FLASK_DEBUG`.
- Startup now gives an explicit one-file env migration hint when the active `.env` file is missing and the legacy Jira-specific env file is present.
- `.env.example` no longer suggests setting `CASEOPS_ENV_FILE` inside the file it is trying to locate.
- Shareable docs now use generic localhost, Docker, and org-alias examples.
- Default `unittest` discovery now finds the test package.
- The hardcoded-reference regression guard now checks private host/path/operator examples in addition to org aliases and legacy env filenames.
- Entrypoint startup logging now loads selected runtime values from the configured env file without sourcing the whole file.
- `CASEOPS_JIRA_ENV_FILE` remains as a dated compatibility alias while deployments move to `CASEOPS_ENV_FILE`.

Post-remediation validation:

- `python -m py_compile app.py jira_sync.py run_pipeline.py skill_registry.py caseops_paths.py`
- `python -m unittest discover -q`
- `python -m unittest tests.test_no_hardcoded_org_refs tests.test_pipeline_state_tags -q`
- `git diff --check`
- `docker build -t caseops-audit:post-review .`
- Docker smoke test with mounted `/data/.env`; `/health` returned `{"ok": true}` and required output directories were created.

Deferred:

- Version bump, image rebuild, and GHCR push. Per maintainer direction, publish after the remaining changes are complete.

Starting state:

- `git status --short` was clean.
- There were no uncommitted source changes to review.
- Most relevant recent commits:
  - `967a170 Consolidate CaseOps env file naming`
  - `b4f28e4 Prevent hardcoded private org references`
  - `2e1a320 Parameterize skill org and env references`

## Original Validation Performed

Passed:

- `python -m unittest tests.test_no_hardcoded_org_refs tests.test_pipeline_state_tags -q`
- `python -m unittest discover -s tests -p "test*.py" -q`
- `python -m py_compile app.py jira_sync.py run_pipeline.py skill_registry.py caseops_paths.py`
- `python app.py --help`
- `python jira_sync.py --help`
- `python run_pipeline.py --help`
- `docker build -t caseops-audit:env-review .`
- Docker smoke test with mounted `/data/.env`; `/health` returned `{"ok": true}`.

Failed or misleading:

- `python -m unittest discover -q` ran zero tests from the repo root.

## Findings

### High - Published Image Drift Risk

The repo now contains the `.env` consolidation, but `Dockerfile` and `docker-compose.example.yml` still advertise `0.1.8`.

Evidence:

- `Dockerfile` sets `CASEOPS_VERSION=0.1.8`.
- `docker-compose.example.yml` defaults to `ghcr.io/sdbingham/caseops:0.1.8`.
- The audit built a local image successfully, but did not publish it.

Impact:

- Unless `0.1.8` was rebuilt and pushed after commit `967a170`, `docker pull ghcr.io/sdbingham/caseops:0.1.8` will not contain the env-file changes.
- A tester may be reading docs from the repo while running an older image.

Recommendation:

- Bump to the next version, rebuild, push the numbered tag and `latest`, then update docs/compose references.

### High - Runtime Prompt Still Hardcodes Maintainer-Specific Language

`app.py` still contains user-specific runtime language. This file is copied into the Docker image, so this is not only a maintainer-doc issue.

Evidence:

- `app.py` included a maintainer-specific owner sentence.
- `app.py` included maintainer-specific voice guidance.
- `app.py` included a maintainer-specific next-action label.

Impact:

- CaseOps is not fully reusable by another operator.
- Generated drafts can inherit a maintainer-specific voice and action model.

Recommendation:

- Replace maintainer-specific runtime language with operator-configurable values from `.env`, such as `CASEOPS_DEFAULT_ACTOR` and `CASEOPS_EXAMPLE_ASSIGNEE_NAME`, or generic "operator" wording.

### High - Flask Debug Server Is Enabled In The Docker Runtime

The container smoke test showed Flask running with debug mode enabled.

Evidence:

- `app.py` ends with `app.run(debug=True, threaded=True, host="0.0.0.0", ...)`.
- Smoke-test logs showed Flask's debug-mode warning.

Impact:

- Debug mode is inappropriate for a shareable container.
- It can expose extra diagnostics and changes runtime behavior.

Recommendation:

- Default debug off in Docker, controlled by an explicit `CASEOPS_FLASK_DEBUG=true` only for local development.

### Medium - `.env` Migration Is A Breaking Local-Dev Change

The repo now uses `.env` by default. Existing local workspaces that only have the old Jira-specific env filename will fail unless they set `CASEOPS_JIRA_ENV_FILE` or rename/copy the file.

Evidence:

- Local default path is now `ROOT / ".env"`.
- Startup validation now raises `.env file does not exist`.
- The working tree still had a local ignored legacy Jira-specific env file but no local `.env` during review.

Impact:

- Local developers upgrading from older CaseOps can hit immediate startup failure.

Recommendation:

- Add an explicit migration note to docs and/or startup error text: rename the old Jira-specific env file to `.env`.
- Do not silently accept the old filename if the one-file policy is intentional.

### Medium - `.env.example` Contains A Misleading `CASEOPS_ENV_FILE` Example

`.env.example` suggests setting `CASEOPS_ENV_FILE` inside `.env`.

Evidence:

- `.env.example` has `# CASEOPS_ENV_FILE=/absolute/path/.env`.

Impact:

- For local startup, CaseOps must know the env-file path before it reads the env file.
- Setting this value inside `.env` cannot change which env file is selected.

Recommendation:

- Remove that line from `.env.example`, or clarify that `CASEOPS_ENV_FILE` is a shell/Compose variable and not useful inside the active `.env` itself.

### Medium - Tracked Docs Still Contain Private Or Stale Deployment Details

Several tracked docs still contain internal/private or stale examples.

Evidence:

- `docs/API.md` used a private LAN host example.
- `docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md` used NAS-specific output and stack paths.
- `docs/TECHNICAL_OVERVIEW.md` used a stale production-org alias example.
- `docs/TECHNICAL_OVERVIEW.md` says tokens are stored at `/app/.env`; Docker uses `/data/.env`.

Impact:

- Not all tracked docs are shareable.
- Maintainer docs can contradict the Docker model.

Recommendation:

- Sanitize or archive old planning docs.
- Change `docs/API.md` to localhost/generic examples.
- Change `docs/TECHNICAL_OVERVIEW.md` token path to `/data/.env`.

### Medium - Root Test Discovery Gives False Confidence

Direct module tests pass, but default discovery from repo root does not.

Evidence:

- `python -m unittest discover -q` ran zero tests.
- `python -m unittest discover -s tests -p "test*.py" -q` ran 38 tests successfully.

Impact:

- A maintainer or CI job using the conventional root discovery command can report no failures while not running any tests.

Recommendation:

- Add `tests/__init__.py`, add CI with the explicit `-s tests` command, or document the exact supported command.

### Medium - Hardcoded-Reference Regression Test Is Too Narrow

The new guard prevents the old org strings and old env filenames, but it does not catch other private/operator-specific references.

Evidence still found in tracked files:

- Maintainer-specific personal names.
- Private LAN host examples.
- NAS-specific deployment paths.
- Stale org-alias examples.

Impact:

- The repo can regress on shareability without failing tests.

Recommendation:

- Extend the guard or add a separate "shareable package hygiene" test with allowlists for maintainer-only archived docs.

### Low - Entrypoint Readiness Log Can Be Misleading Outside Compose

When the container is run with `/data/.env` mounted but without Docker Compose `env_file`, the entrypoint prints `CASEOPS_LLM_AUTH=` before `app.py` loads `/data/.env`.

Evidence:

- Smoke test with only mounted `/data/.env` started successfully.
- Logs showed `Environment ready: CASEOPS_LLM_AUTH=` before startup validation.

Impact:

- Docker Desktop/manual container users can see misleading logs even though the app later reads `.env`.

Recommendation:

- Either load selected non-secret config values in the entrypoint from `CASEOPS_ENV_FILE`, or change the log wording so it does not imply the full env has already been loaded.

### Low - `CASEOPS_JIRA_ENV_FILE` Remains As A Compatibility Alias

The code still accepts and exports `CASEOPS_JIRA_ENV_FILE`.

Evidence:

- `caseops_paths.py`, `docker-entrypoint.sh`, and `app.py` still reference `CASEOPS_JIRA_ENV_FILE`.

Impact:

- This does not create a second env file.
- It does preserve old naming in code, which may look inconsistent during future audits.

Recommendation:

- Keep it temporarily if backward compatibility matters.
- Add a dated removal note, or remove it once all deployments use `CASEOPS_ENV_FILE`.

### Low - Shareable Runtime Files Are Not In The Image

The Docker image intentionally does not include docs, `.env.example`, or `docker-compose.example.yml`.

Evidence:

- `Dockerfile` copies app source, templates, static assets, skills, and scripts only.
- `.dockerignore` excludes env files and many docs.

Impact:

- This is acceptable if release packaging provides compose/env/docs beside the image.
- It is a gap if a tester expects the image alone to contain setup files.

Recommendation:

- Keep the image lean, but produce a release bundle or GitHub release assets containing:
  - `docker-compose.yml`
  - `.env.example`
  - `docs/TESTER_GUIDE.md`

## Non-Issues Confirmed

- Docker build succeeds.
- Container startup with `/data/.env` succeeds.
- `/health` succeeds.
- Startup creates required output directories under `/data/outputs`.
- Tracked files no longer contain legacy multi-env filename references.
- Tracked package files no longer contain the old hardcoded private Salesforce org strings.

## Suggested Fix Order

1. Remove maintainer-specific runtime language from `app.py`.
2. Disable Flask debug mode by default in Docker.
3. Fix stale/private docs and the misleading `.env.example` `CASEOPS_ENV_FILE` line.
4. Add/repair CI test discovery.
5. Bump version, rebuild, and push GHCR image.
6. Decide and document when `CASEOPS_JIRA_ENV_FILE` compatibility will be removed.
