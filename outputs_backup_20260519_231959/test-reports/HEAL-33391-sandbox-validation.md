# HEAL-33391 Sandbox Validation

## Scope

Sandbox validation for order processing lead/manager Order visibility.

## Sandbox

- Alias: `10xhealth-sean`
- Deployment id: `0AfEa00000ZnBhLKAV`

## Components Deployed

- `Group:Order_Processing_Leads_Managers`
- `PermissionSet:Order_Processing_Lead_Manager`
- `ListView:Order.AllOrders`

## Validation

Deployment succeeded with 3 components deployed and 0 errors.

Read-back checks confirmed:

- Public group `Order_Processing_Leads_Managers` exists.
- Permission set `Order_Processing_Lead_Manager` grants:
  - `Order` read = true
  - `Order` view all records = true
  - create/edit/delete/modify all = false
- `Order.AllOrders` list view sharing includes:
  - `group`: `Order_Processing_Leads_Managers`
  - existing `roleAndSubordinates`: `CFO_New`

## Outcome

Pass. Metadata is ready for Production deployment, followed by user assignment to the permission set and public group.
