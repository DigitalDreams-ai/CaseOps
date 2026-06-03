# CaseOps Tester Guide

This guide is safe to share with a tester. It intentionally avoids private hostnames, internal paths, Jira issue keys, Salesforce org aliases, customer data, and credentials.

## Purpose

CaseOps helps support operators review synced Jira issues, run a guided Salesforce investigation pipeline, validate candidate fixes in an allowed Sandbox, and draft internal notes or customer-facing Jira messages.

CaseOps must not write to Salesforce Production. Production access is read-only. The only writable Salesforce org should be the explicitly configured Sandbox.

## What To Test

1. Open the CaseOps web app URL provided by the operator.
2. Confirm the issue list loads.
3. Use the issue filter to search by:
   - issue key,
   - summary text,
   - visible tags such as `not triaged`, `blocked`, `data only`, `validated`, or `needs escalation`.
4. Select an issue and confirm the detail view loads.
5. Confirm available tabs render without browser errors.
6. Confirm the pipeline log panel loads and can be copied.
7. Open Settings and confirm status panels load.
8. Use the Restart button only if the operator asks you to verify restart behavior.

## Pipeline Test Rules

Run pipeline actions only on issues approved by the operator.

Before starting any run, confirm:

- Salesforce Production is read-only.
- The Sandbox target is the only writable Salesforce org.
- Jira writes are disabled unless the operator explicitly asks for a Jira post or transition.
- No credentials are pasted into logs, chat, tickets, screenshots, or shared documents.

During a run, watch for:

- app crashes,
- browser console errors,
- stale or incorrect tags,
- incorrect progress step indicators,
- repeated loops without a new reason,
- broad or unbounded Salesforce metadata retrieves,
- any attempted Production write.

If CaseOps appears to attempt a forbidden action, stop testing and report the exact visible command or log line.

## Expected Results

The app should:

- keep the issue list responsive,
- show mutually consistent tags,
- keep pipeline logs readable and bounded,
- preserve existing issue artifacts unless a rerun is requested,
- mark failed pipeline streams as failed rather than complete,
- reconnect after restart without showing a misleading network error.

## What Not To Share

Do not include these in bug reports unless the operator explicitly asks:

- Jira issue keys,
- customer names or summaries,
- Salesforce org aliases,
- Salesforce record IDs,
- access tokens or refresh tokens,
- internal hostnames, IP addresses, or filesystem paths,
- full pipeline logs.

Use screenshots with sensitive content cropped or blurred when possible.
