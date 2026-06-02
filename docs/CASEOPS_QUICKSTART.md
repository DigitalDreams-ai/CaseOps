# CaseOps Quickstart

Use [User Guide](USER_GUIDE.md) for the full walkthrough.

## NAS Pilot

1. Open:

   ```text
   http://10.0.1.10:5350
   ```

2. Confirm Settings status is healthy.

3. Select an issue.

4. Click the issue pipeline action.

5. Watch the pipeline log and step indicator.

6. Review generated artifacts:

   - investigation
   - test report
   - internal notes
   - Jira message
   - engineering handoff, if present

## Auth Refresh

Salesforce:

```bash
sf org auth show-access-token -o 10xhealth --json
sf org auth show-access-token -o 10xhealth-sean --json
sf org auth show-sfdx-auth-url -o 10xhealth --json
sf org auth show-sfdx-auth-url -o 10xhealth-sean --json
```

Paste values at:

```text
/setup/refresh-salesforce-tokens
```

Claude:

```bash
claude setup-token
```

Paste the token at:

```text
/setup/claude-login
```

## Safety

- Production is read-only.
- Sandbox writes only target `CASEOPS_SANDBOX_TARGET_ORG`.
- Retrieve/deploy uses modern `sf` CLI only.
- Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest`.
