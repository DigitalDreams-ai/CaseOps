import subprocess
import json
import xml.etree.ElementTree as ET

# Get access token for sandbox
result = subprocess.run(
    ["sf", "org", "display", "-u", "10xhealth-sean", "--json"],
    capture_output=True,
    text=True
)
org_info = json.loads(result.stdout)
instance_url = org_info["result"]["instanceUrl"]
access_token = org_info["result"]["accessToken"]

# Get the permission set details
import urllib.request
import urllib.error

# Query for the full permission set details
url = f"{instance_url}/services/data/v67.0/sobjects/PermissionSet/0PSRh0000002o0jOAA"
req = urllib.request.Request(url)
req.add_header("Authorization", f"Bearer {access_token}")

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print(json.dumps(data, indent=2))
except urllib.error.URLError as e:
    print(f"Error: {e}")
