# Salesforce Gotchas: Automation Order

Use these checks before blaming the first automation artifact found.

- Salesforce save behavior can involve validation rules, before-save flows, Apex before triggers, duplicate rules, assignment rules, after-save flows, Apex after triggers, workflow/process leftovers, rollups, sharing recalculation, and async jobs.
- A field value can be set correctly, then overwritten later by automation. Compare before/after behavior and inspect downstream flows/triggers before declaring root cause.
- Record-triggered flows can have multiple entry conditions, order values, and active versions. Verify `FlowDefinition.ActiveVersionId` and the active version metadata.
- Flow labels and API names can differ. Use Tooling queries to resolve active versions before retrieving or referencing a flow.
- Apex triggers may delegate to handler classes. Query triggers first, then inspect only implicated classes instead of reading all Apex.
- Validation rules can block automation updates even when UI updates work, or vice versa, depending on user context and bypass logic.
- Assignment rules, auto-response rules, escalation rules, and email alerts can change Case behavior without changing the record fields the customer mentions.
- Scheduled paths, queueable Apex, platform events, and integrations can make failures appear delayed. Check timing evidence before narrowing scope.
- If the fix requires Apex, flow modification, validation rule change, approval process change, or business-critical automation ownership, route to Engineering with evidence and a Sandbox-validated proposal when possible.
