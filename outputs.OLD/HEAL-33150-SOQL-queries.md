# HEAL-33150: SOQL Queries for Email Investigation

## Objective

Document read-only Production queries used to investigate why internal approval replies are missing from Customer Experience Case activity.

Target org: `10xhealth`  
Production writes performed: none

## Query 1: Case Record Types

```soql
SELECT Id, DeveloperName, Name
FROM RecordType
WHERE SobjectType = 'Case'
ORDER BY Name
```

Finding: `Customer_Experience` exists and is the Cx Case record type.

## Query 2: Email Service Addresses

```soql
SELECT Id, LocalPart, EmailDomainName, IsActive, AuthorizedSenders, FunctionId, RunAsUserId
FROM EmailServicesAddress
ORDER BY LocalPart
```

Finding: The org has many active `EmailServicesAddress` records, but they are not all Email-to-Case routing addresses. Most are per-user Email-to-Salesforce addresses using `emailtosalesforce` / `*.le.salesforce.com`. The relevant Case routing service includes routed local parts such as `patientdocs`, `support`, and `tech-dataopps`.

## Query 3: Org-Wide Email Addresses

```soql
SELECT Id, Address, DisplayName, IsAllowAllProfiles
FROM OrgWideEmailAddress
ORDER BY Address
```

Finding: `support@10xhealthsystem.com` and `info@10xhealthsystem.com` are configured org-wide addresses and are visible in successful routed Case email examples.

## Query 4: Customer Experience Refund EmailMessages Around Reported Date

```soql
SELECT Id, ParentId, Parent.CaseNumber, Parent.Subject, Subject, Incoming,
       FromAddress, ToAddress, CcAddress, BccAddress, CreatedDate,
       MessageIdentifier, ThreadIdentifier
FROM EmailMessage
WHERE Parent.RecordType.DeveloperName = 'Customer_Experience'
  AND CreatedDate >= 2026-04-15T00:00:00Z
  AND CreatedDate <= 2026-04-16T23:59:59Z
  AND Subject LIKE '%Refund%'
ORDER BY CreatedDate ASC
LIMIT 50
```

Finding:

- The affected sample Case `00565984` has the outbound internal approval email logged.
- That outbound email was from an agent mailbox to an internal approver mailbox, with the agent Bcc'd.
- A later outbound customer email exists on the same Case.
- No incoming internal approval reply exists on that Case.
- Other Customer Experience refund cases in the same window have incoming replies when addressed to Salesforce-routed mailboxes such as `support@10xhealthsystem.com` or `info@10xhealthsystem.com`.

## Query 5: Affected Case EmailMessages

```soql
SELECT Id, Subject, Incoming, FromAddress, ToAddress, CcAddress, BccAddress,
       CreatedDate, MessageIdentifier, ThreadIdentifier, Status
FROM EmailMessage
WHERE ParentId = '500Ql00000ujeSTIAY'
ORDER BY CreatedDate ASC
```

Finding:

- `02sQl00000t0TfnIAE`: outbound internal approval email, `Incoming = false`.
- `02sQl00000t602WIAQ`: outbound customer email, `Incoming = false`.
- No `Incoming = true` internal approval reply exists on the Case.

## Query 6: EmailMessage Fields

```powershell
$json = sf sobject describe --target-org 10xhealth --sobject EmailMessage --json | ConvertFrom-Json
$json.result.fields |
  Where-Object { $_.name -match 'Reply|Header|From|To|Bcc|Cc|Thread|Message' } |
  Select-Object name,label,type
```

Finding: `Headers`, `MessageIdentifier`, `ThreadIdentifier`, and `ReplyToEmailMessageId` exist, but the affected outbound sample had `Headers = null`, so Salesforce did not store a header-level Reply-To value for that message.

## Query 7: Affected EmailMessage Sender/Template/Route Fields

```soql
SELECT Id, Subject, Source, AutomationType, IsClientManaged,
       EmailTemplateId, EmailRoutingAddressId, FromId, FromAddress,
       FromName, ValidatedFromAddress, ToAddress, BccAddress, Headers
FROM EmailMessage
WHERE Id = '02sQl00000t0TfnIAE'
```

Finding:

- `EmailTemplateId = null`
- `EmailRoutingAddressId = null`
- `FromAddress = ntorres@10xhealthsystem.com`
- `ValidatedFromAddress = ntorres@10xhealthsystem.com`
- `ToAddress = tjones@10xhealthsystem.com`
- `BccAddress = ntorres@10xhealthsystem.com`
- `Headers = null`

## Metadata Retrieve: Customer Experience Case Email Action

Retrieved metadata:

- Layout: `Layout:Case-Customer Experience`
- Quick action: `QuickAction:Case.SendEmail`

Finding:

- `Case-Customer Experience` exposes `Case.SendEmail` in the record action list and publisher action list.
- `Case.SendEmail` has `targetObject = EmailMessage`.
- `Case.SendEmail` has `targetParentField = Parent`.
- `Case.SendEmail` exposes editable `ValidatedFromAddress`.
- `Case.SendEmail` has no predefined `ValidatedFromAddress` override and no Reply-To field.
- Only predefined field override is `ToIds = Case.ContactId`.

## Root Finding

The supported root issue is reply delivery into Salesforce, not broad Cx thread-token matching. Thread tokens are present, and Cx replies attach successfully when routed to Salesforce.

The smoking gun is the `Case.SendEmail` action on the Customer Experience layout. It permits an agent personal `ValidatedFromAddress` and does not enforce a Salesforce-routed reply path. The affected approval email was sent as `ntorres@10xhealthsystem.com`, not as `support@10xhealthsystem.com`, `info@10xhealthsystem.com`, or a routed refund mailbox.
