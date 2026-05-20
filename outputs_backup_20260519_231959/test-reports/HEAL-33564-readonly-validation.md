# HEAL-33564 Read-Only Validation

## Scope

Read-only validation for the duplicate/follow-up Informed Consent send issue.

## Commands Run

Synced Jira:

```text
python jira_sync.py --env-file .env.jira --issue HEAL-33564
```

Retrieved Production flow metadata:

```text
sf project retrieve start -o 10xhealth --metadata Flow:Autolaunch_Send_Patient_Agreements_to_Patient --target-metadata-dir outputs\production-metadata\HEAL-33564 --unzip --json
```

Retrieved sandbox flow metadata:

```text
sf project retrieve start -o 10xhealth-sean --metadata Flow:Autolaunch_Send_Patient_Agreements_to_Patient --target-metadata-dir outputs\sandbox-metadata\HEAL-33564 --unzip --json
```

Queried related Production account from prior debug-log test:

```text
sf data query -o 10xhealth -q "SELECT Id, Name, Biocanic_External_Id__c, Do_Not_Sync_to_Biocanic__c, LastModifiedDate FROM Account WHERE Id = '0010b00002dC2y2AAC'" --json
```

Queried related Production Informed Consent Patient Agreements:

```text
sf data query -o 10xhealth -q "SELECT Id, Name, Status__c, Date_Sent__c, Expiration_Date__c, Dispatch_Platform__c, CreatedDate, LastModifiedDate FROM Patient_Agreement__c WHERE Patient__c = '0010b00002dC2y2AAC' AND Name LIKE '%Informed Consent%' ORDER BY CreatedDate DESC LIMIT 10" --json
```

## Results

- Production active flow version: 14.
- Production `Collection_Informed_Consents` condition: `1 OR (1 AND 2) AND NOT(3)`.
- Sandbox active flow version: 16.
- Sandbox `Collection_Informed_Consents` condition: `1 AND NOT(2) AND NOT(3)`.
- No new sandbox deploy was required because the `HEAL-33418` fix is already present in `10xhealth-sean`.
- No functional retest was possible from `HEAL-33564` alone because the ticket contains no patient/account or new send attempt timestamp.

