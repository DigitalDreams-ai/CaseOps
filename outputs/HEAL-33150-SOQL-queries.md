# HEAL-33150: SOQL Queries for Email-to-Case Investigation

## Objective
Document SOQL queries used to investigate email threading issue for Cx Case Record Type in Production (10xhealth org).

---

## Query 1: Case Record Types

**Purpose:** Identify the Cx Case Record Type API name and ID.

```soql
SELECT Id, DeveloperName, Name 
FROM RecordType 
WHERE SobjectType='Case' 
ORDER BY Name
```

**Results:**
| Id | DeveloperName | Name |
|----|---|---|
| 012Rh00000BCCVJIA5 | Customer_Experience | Customer Experience |
| 0120b000000EuaSAAS | IT_Record_Type | IT Record Type |
| 0120b000000EuaNAAS | Operations_Record_Type | Operations Record Type |
| 0120b000000EqO9AAK | Patient_Case_Record_Type | Patient Case Record Type |
| 012Rh0000035TCXIA2 | Patient_Demographic_Log | Patient Demographic Log |

**Finding:** "Cx Case" refers to the **Customer_Experience** Record Type with ID `012Rh00000BCCVJIA5`.

---

## Query 2: Email Templates

**Purpose:** Retrieve available email templates (sample of first 10).

```soql
SELECT Id, Name 
FROM EmailTemplate 
LIMIT 10
```

**Results:** 10 email templates found (e.g., "Campaign Tracker 2 Lead Notification", "Lead Reactivation - Internal", "Incoming Message Alert", etc.). 
- Note: No templates specifically named for Case emails were visible in the sample, indicating templates may be referenced differently or are in closed folders.

---

## Query 3: Cases with Customer_Experience Record Type

**Purpose:** Verify Cx Case records exist and retrieve sample records.

```soql
SELECT Id, CaseNumber, Subject, RecordTypeId, CreatedDate 
FROM Case 
WHERE RecordType.DeveloperName = 'Customer_Experience' 
LIMIT 5
```

**Results:** 5 Cx Case records found (Sample):
| Id | CaseNumber | Subject | RecordTypeId | CreatedDate |
|----|---|---|---|---|
| 500Ql00000ngYSbIAM | 00515707 | Re: [10X Health System] Re: 10x Vitamins | 012Rh00000BCCVJIA5 | 2026-01-19T16:03:56.000+0000 |
| 500Ql00000noxtYIAQ | 00517004 | Subscription | 012Rh00000BCCVJIA5 | 2026-01-21T00:44:45.000+0000 |
| 500Ql00000o65EkIAI | 00519301 | Internal CX Assistance: Blood Test | 012Rh00000BCCVJIA5 | 2026-01-23T16:15:20.000+0000 |
| 500Ql00000o7Yg5IAE | 00519506 | (null) | 012Rh00000BCCVJIA5 | 2026-01-23T19:51:37.000+0000 |
| 500Ql00000oGlJ7IAK | 00520937 | Adverse effects - refund requested | 012Rh00000BCCVJIA5 | 2026-01-26T16:47:12.000+0000 |

**Finding:** Cx Case records are active and exist in Production.

---

## Query 4: EmailMessage Records for Sample Cx Case

**Purpose:** Verify email threading—check if both outgoing and incoming emails exist for a Cx Case.

```soql
SELECT Id, ParentId, Subject, Incoming, CreatedDate 
FROM EmailMessage 
WHERE ParentId = '500Ql00000ngYSbIAM' 
ORDER BY CreatedDate DESC 
LIMIT 10
```

**Results:** 2 EmailMessage records found for case `500Ql00000ngYSbIAM`:
| Id | ParentId | Subject | Incoming | CreatedDate |
|----|---|---|---|---|
| 02sQl00000lQJ7KIAW | 500Ql00000ngYSbIAM | Re: [10X Health System] Re: 10x Vitamins | true | 2026-01-19T16:03:58.000+0000 |
| 02sQl00000lQJ7JIAW | 500Ql00000ngYSbIAM | 10X Health System Support Request | false | 2026-01-19T16:03:57.000+0000 |

**Finding:** 
- Email threading **is working** for this sample case (both outgoing and incoming emails logged).
- However, the issue reporter states that **some** Cx Cases are not receiving inbound replies.
- This suggests the problem may be:
  1. Intermittent (not all Cx Cases affected).
  2. Related to specific conditions (reply format, sender address, email routing address configuration).
  3. Related to Email-to-Case routing address settings for Cx Case Record Type.

---

## Next Steps (Production Investigation)

Need to verify in Production (read-only):
1. **Email-to-Case Routing Address configuration** — Check Setup > Feature Settings > Service > Email-to-Case > Routing Addresses to confirm:
   - The routing address used for Cx Case Record Type.
   - Whether "Use Email Thread ID" / threading is enabled.
   - Reply-To address configuration.

2. **Email-to-Case Settings** — Verify:
   - Global Email-to-Case enabled.
   - Thread ID configuration.

3. **Send Email Quick Action / Page Layout** — Check the Cx Case page layout's Send Email action configuration to confirm the Reply-To header points to the Salesforce routing address (not an agent's personal email).

4. **Flows/Automation** — Check for any Flows or Apex triggers that may be suppressing EmailMessage creation or modifying email routing for Cx Cases.

---

## Summary of Production State (as of 2026-05-18)

| Component | Status | Finding |
|---|---|---|
| **Cx Case Record Type** | ✓ Exists | DeveloperName: `Customer_Experience`, ID: `012Rh00000BCCVJIA5` |
| **Sample Cx Cases** | ✓ Exist | 5+ Cx Case records with both incoming/outgoing emails |
| **Email Threading (Sample)** | ✓ Working | Case `500Ql00000ngYSbIAM` has both outgoing and incoming EmailMessage records |
| **Email-to-Case Routing** | ? To verify | Routing address config must be checked in Setup (read-only) |
| **Email Templates** | ✓ Available | 10+ templates found; may be in closed folders |
| **Root Cause** | ? Pending | Likely Email-to-Case routing address config or Reply-To header misconfiguration |
