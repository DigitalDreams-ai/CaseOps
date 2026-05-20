# Sandbox Deployment Report

## Jira Issue

- Key: HEAL-32413
- Summary: Need privilege change on SF so I can update lab vendor on lab draw opps after approved

## Target Sandbox

- Sandbox alias: `10xhealth-sean`
- Verified `IsSandbox`: true
- Deployment date: 2026-05-11

## Deployment

### Dry Run

Command:

```text
sf project deploy start --target-org 10xhealth-sean --source-dir force-app/main/default/approvalProcesses --test-level NoTestRun --dry-run --wait 10 --json
```

Result:

- Status: Succeeded
- Deploy ID: `0AfEa00000Zn5QbKAJ`
- Components validated: 3
- Component errors: 0
- Tests run: 0

### Actual Deploy

Initial deploy without conflict override reported source-tracking conflicts for the three approval process metadata files. The dry run had already validated the package against the target Sandbox, so the package was redeployed with conflict override.

Command:

```text
sf project deploy start --target-org 10xhealth-sean --source-dir force-app/main/default/approvalProcesses --test-level NoTestRun --ignore-conflicts --wait 10 --json
```

Result:

- Status: Succeeded
- Deploy ID: `0AfEa00000Zn5aHKAR`
- Components deployed: 3
- Component errors: 0
- Tests run: 0

Deployed components:

- `ApprovalProcess:Opportunity.Opportunity_Approval_Process_Labs`
- `ApprovalProcess:Opportunity.Opportunity_Approval_Process`
- `ApprovalProcess:Opportunity.Genetic_Approval_Process`

## Post-Deploy Verification

Read-only verification confirmed three active Opportunity approval processes in `10xhealth-sean`:

- `Genetic_Approval_Process`
- `Opportunity_Approval_Process`
- `Opportunity_Approval_Process_Labs`

Retrieved post-deploy metadata into:

```text
outputs/sandbox-metadata/HEAL-32413-post-deploy/
```

Verified metadata state:

| Component | Verified State |
| --- | --- |
| `Opportunity_Approval_Process_Labs` | Contains `RecordType = Labs`, `processOrder = 1`, `finalApprovalRecordLock = false`. |
| `Opportunity_Approval_Process` | Does not contain `RecordType = Labs`, `processOrder = 2`, `finalApprovalRecordLock = true`. |
| `Genetic_Approval_Process` | `processOrder = 3`, `finalApprovalRecordLock = true`. |

## Test Status

Deployment is complete. Functional testing has not been performed yet.

Step 8 should test whether a Clinical/nurse user can update `Lab_Provider__c` and, if in scope, `Lab_Name__c` on an approved Labs Opportunity.

Known secondary risk to test:

- `Lab_Ordered_NO_EDIT`
- `Lab_Received_NO_EDIT`

These validation rules may still block the intended edit even though the approval-process final lock has been removed for Labs.
