# Salesforce Gotchas: Layouts And Record Types

Use these checks before concluding a page layout or field placement is wrong.

- A field being present on one layout does not mean it appears for every profile, app, record type, or Lightning page.
- Page layout assignment depends on profile and record type. Lightning App Builder visibility rules can further hide or show components.
- A Lightning record page can display Dynamic Forms fields that are not visible in the classic page layout metadata shape.
- A section label can be confused with a nearby field label. Confirm the field's actual `layoutSections[].layoutColumns[].layoutItems[].field` placement.
- Record type picklist settings can make values unavailable even when the field and layout are correct.
- Compact layouts, highlights panels, related lists, and Lightning components are separate surfaces. Do not treat one as evidence for the others.
- Field-level security overrides layout visibility. If a user cannot see a field, check FLS and page layout/Lightning visibility.
- Profiles are not valid Support-owned targets for CaseOps edits. Prefer permission sets or document admin steps.
- For visual-only uncertainty, browser/frontdoor inspection is allowed, but API/SOQL/retrieve/deploy work must use `sf` CLI.
