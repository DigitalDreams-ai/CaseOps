# HEAL-33418 Sandbox Deploy And Test Report

## Target

- Sandbox: `10xhealth-sean`
- Metadata: `Flow:Autolaunch_Send_Patient_Agreements_to_Patient`

## Deployment

Dry-run:

```text
sf project deploy start --target-org 10xhealth-sean --source-dir force-app\main\default\flows\Autolaunch_Send_Patient_Agreements_to_Patient.flow-meta.xml --test-level NoTestRun --dry-run --wait 10 --json
```

- Result: succeeded
- ID: `0AfEa00000Zn8MrKAJ`

Deploy:

```text
sf project deploy start --target-org 10xhealth-sean --source-dir force-app\main\default\flows\Autolaunch_Send_Patient_Agreements_to_Patient.flow-meta.xml --test-level NoTestRun --ignore-conflicts --wait 10 --json
```

- Result: succeeded
- ID: `0AfEa00000Zn8WXKAZ`

## Metadata Verification

Retrieved sandbox metadata after deploy into:

- `outputs/sandbox-metadata/HEAL-33418-post-deploy/`

Confirmed deployed condition:

```text
<conditionLogic>1 AND NOT(2) AND NOT(3)</conditionLogic>
```

## Functional Testing

Attempted exact expired-Informed-Consent test:

- Script: `outputs/test-reports/HEAL-33418-flow-test.apex`
- Result: blocked.
- Blocker: Apex in `10xhealth-sean` rejects `Patient_Agreement__c.Expiration_Date__c` as invalid, despite Tooling metadata and the deployed flow referencing the field.

Attempted synthetic smoke test:

- Script: `outputs/test-reports/HEAL-33418-flow-smoke-test.apex`
- Result: failed with a generic unhandled flow fault during `Autolaunch_Send_Patient_Agreements_to_Patient`.
- Likely cause: sandbox lacks representative Patient Agreement Configuration data/setup. Querying the sandbox returned zero `Patient_Agreement_Configuration__c` records.

## Conclusion

The metadata fix is deployed and verified in sandbox. Full business validation is not complete because the sandbox does not currently support a representative functional test for this flow path.
