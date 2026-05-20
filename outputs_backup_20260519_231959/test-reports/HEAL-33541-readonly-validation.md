# HEAL-33541 Read-Only Validation

Production validation only. No production data was changed.

Validated:

- Opportunity `006Ql00000d7V5RIAU` exists and is a Medication Opportunity.
- Patient account billing and shipping state are both CA.
- Latest failed Wellvi order is `00890991`.
- Latest failed Order Item is `802Ql00000dErsQIAS`.
- Product is `Tesamorelin 2mg/mL 10mL (Injectable) (per mL)`.
- Latest vendor error is `PHARMACY_STATE_RESTRICTED`.
- Previous failed Wellvi order for the same product/state had `STATE_RESTRICTED` / alternative pharmacy routing not authorized.

Result:

- No metadata deployment recommended.
- Issue should be resolved through pharmacy/vendor routing confirmation or vendor escalation.

