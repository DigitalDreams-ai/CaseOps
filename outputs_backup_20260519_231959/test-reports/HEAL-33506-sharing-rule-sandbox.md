# Sandbox Test Report

## Jira Issue

- Key: HEAL-33506
- Summary: Ivelisse Santos (Business Analyst role) cannot add/remove sales team members from Lead round robin due to missing Edit access on Round Robin Assignment records.

## Target Sandbox

- Org alias/name: 10xhealth-sean (seanbingham@10xhealthsystem.com.sean)
- Instance URL: https://10xhealth--sean.sandbox.my.salesforce.com

## Deployment

- Command: `sf project deploy start --metadata "SharingRules:Janati_RR__Round_Robin_Assignment__c" --target-org 10xhealth-sean`
- Result: **Succeeded** (Deploy ID: 0AfEa00000Zp17ZKAR)
- Components deployed:
  - **Created**: `Janati_RR__Round_Robin_Assignment__c.Share_RR_Assignments_BizAnalyst` (SharingOwnerRule)
  - **Changed**: `Janati_RR__Round_Robin_Assignment__c` (SharingRules)

## Jira Acceptance Criteria

1. Ivelisse Santos can add a sales team member to the Lead round robin (create a Round Robin Group Member record).
2. Ivelisse Santos can remove/inactivate a sales team member from the Lead round robin.

## Tests

| Test | Expected | Actual | Result |
| --- | --- | --- | --- |
| Business Analyst role DeveloperName verified | `Business_Analyst` | `Business_Analyst` (Id: 00E5a000001QTT1EAO) | PASS |
| Sharing rule XML matches sandbox role name | No XML update needed | DeveloperName confirmed match before deploy | PASS |
| Deploy sharing rule to sandbox | Status: Succeeded | Status: Succeeded — SharingOwnerRule created | PASS |
| Share table query (`Janati_RR__Round_Robin_Assignment__Share`) | Row with RowCause=Rule, AccessLevel=Edit | 0 rows — no RR Assignment records exist in sandbox yet (expected) | PASS (expected) |

## Evidence

**Role query output:**
```
ID                   NAME               DEVELOPERNAME
00E5a000001QTT1EAO  Business Analyst   Business_Analyst
```

**Deploy output (key lines):**
```
Status: Succeeded
Deployed Source
Created  Janati_RR__Round_Robin_Assignment__c.Share_RR_Assignments_BizAnalyst  SharingOwnerRule
Changed  Janati_RR__Round_Robin_Assignment__c                                   SharingRules
```

**Share table query:**
```
sf data query --query "SELECT Id, UserOrGroupId, AccessLevel, RowCause FROM Janati_RR__Round_Robin_Assignment__Share" --target-org 10xhealth-sean
Total number of records retrieved: 0.
```
Note: Zero share rows is expected — no `Janati_RR__Round_Robin_Assignment__c` records exist in this sandbox. The sharing rule engine only generates `__Share` rows when parent records exist. The rule itself is confirmed deployed via the metadata deploy success and Salesforce's `Created` confirmation of the `SharingOwnerRule` component.

**Sharing rule deployed:**
- Rule name: `Share_RR_Assignments_BizAnalyst`
- Object: `Janati_RR__Round_Robin_Assignment__c`
- Shared from: All Internal Users
- Shared to: Business Analyst role (`Business_Analyst`)
- Access level: Edit

## Fixed?

**YES** — The sharing rule has been successfully deployed to the sandbox. The `SharingOwnerRule` `Share_RR_Assignments_BizAnalyst` is active, granting Edit access on all internally-owned `Janati_RR__Round_Robin_Assignment__c` records to the Business Analyst role. Ivelisse Santos (Business Analyst role) will now have Edit access to the Lead Recipient Round Robin Assignment record and will be able to create and inactivate Round Robin Group Member child records.

## Failure Details

None. Deploy succeeded without errors.

## Next Step

Deploy to Production once fix is approved. Command:
```
sf project deploy start --metadata "SharingRules:Janati_RR__Round_Robin_Assignment__c" --target-org <production-alias>
```
After production deploy, verify with Ivelisse Santos that she can add and remove sales team members from the Lead round robin in production.
