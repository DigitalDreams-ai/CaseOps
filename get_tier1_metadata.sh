#!/bin/bash

# Get access token from sf CLI
TOKEN=$(sf org display --target-org 10xhealth --json | jq -r '.result.accessToken')
INSTANCE="https://10xhealth.my.salesforce.com"

# Retrieve PermissionSet metadata for Tier_1
curl -s -H "Authorization: Bearer $TOKEN" \
  "$INSTANCE/services/data/v66.0/metadata/query?type=PermissionSet" | jq . > tier1_ps_list.json

# Now retrieve the specific metadata
curl -s -H "Authorization: Bearer $TOKEN" \
  "$INSTANCE/services/data/v66.0/metadata/read/PermissionSet/Tier_1" | jq . > tier1_ps_metadata.json

cat tier1_ps_metadata.json
