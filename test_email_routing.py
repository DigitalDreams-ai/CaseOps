#!/usr/bin/env python3
import json
import subprocess

# Get org details
result = subprocess.run(
    ["sf", "org", "display", "--target-org", "10xhealth-sean", "--json"],
    capture_output=True,
    text=True
)
org_details = json.loads(result.stdout)
instance_url = org_details.get("result", {}).get("instanceUrl", "")
print(f"Instance URL: {instance_url}")

# Query Email Routing Addresses
query = "SELECT Id, FunctionId, Priority, ParentDeveloperName FROM EmailServicesAddress LIMIT 20"
result = subprocess.run(
    ["sf", "data", "query", "--target-org", "10xhealth-sean", "--query", query, "--json"],
    capture_output=True,
    text=True
)
if result.returncode == 0:
    addresses_data = json.loads(result.stdout)
    print("\n=== Email Routing Addresses ===")
    for addr in addresses_data.get("result", {}).get("records", []):
        print(json.dumps(addr, indent=2))
else:
    print("Error querying addresses:", result.stderr)

