#!/usr/bin/env python3
import json
import subprocess
import sys

# Query for the Tier_1 Permission Set
ps_query = "SELECT Id, Name, Label FROM PermissionSet WHERE Name = 'Tier_1'"

result = subprocess.run(
    [
        "sf", "data", "query",
        "--query", ps_query,
        "--target-org", "10xhealth",
        "--json"
    ],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    data = json.loads(result.stdout)
    if data.get("result", {}).get("records"):
        ps_id = data["result"]["records"][0]["Id"]
        print(json.dumps(data["result"]["records"][0], indent=2))
    else:
        print("No Tier_1 Permission Set found")
        sys.exit(1)
else:
    print(f"Error querying Permission Set: {result.stderr}")
    sys.exit(1)
