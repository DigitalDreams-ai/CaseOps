# Query Pattern: Verify Object Existence First

Use this pattern before querying unfamiliar, optional, managed-package, or org-specific objects.

- Before the first SOQL query against an unfamiliar object, verify the object exists and is queryable:
  `python scripts/sf_caseops_helper.py verify-sobject --org "$ORG" --sobject Object_API_Name --out-dir "$RAW_DIR"`
- If you need to inspect available fields before writing SOQL, run:
  `python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject Object_API_Name --out-dir "$RAW_DIR"`
- If the object does not exist, treat that as evidence about org configuration or package installation. Do not keep retrying broad query variants.
- For custom fields, use `verify-field` or the `custom-field` helper instead of guessing the object/field pair from memory.
- For Flow definitions, use `verify-flow` before retrieve or deploy work that depends on a specific DeveloperName.
