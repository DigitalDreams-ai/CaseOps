"""Update Opportunity Field History reports using Salesforce REST API."""
import json
import subprocess
import sys
import os
import urllib.parse
import base64

def run_cmd(cmd):
    """Run shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=os.getcwd())
    return result.stdout.strip(), result.returncode

def get_org_info(org):
    """Get organization instance URL and access token."""
    cmd = f'sf org display --target-org {org} --json'
    output, code = run_cmd(cmd)
    if code == 0:
        try:
            data = json.loads(output)
            result = data.get('result', {})
            return result.get('instanceUrl'), result.get('accessToken')
        except json.JSONDecodeError:
            pass
    return None, None

def get_rest_token(org):
    """Get REST API access token from sf CLI."""
    # Use sf CLI to execute authenticated HTTP request
    cmd = f'sf org display --target-org {org} --json'
    output, code = run_cmd(cmd)
    try:
        data = json.loads(output)
        auth_fields = data.get('result', {})
        return auth_fields
    except:
        return {}

# Target org
org = "10xhealth-sean"

print("Attempting to retrieve org info...")
auth_info = get_rest_token(org)
print(f"Auth info available: {bool(auth_info)}")

# Since direct API calls are complex, we need to use a workaround
# Salesforce Report Builder requires UI interaction for column modifications
# Best approach: Use sf CLI with sfdx JSON response parsing and direct Report API

reports = [
    {
        "id": "00OEa000007vWiIMAU",
        "name": "Avg Days to Scheduled - Lab Review",
        "dev_name": "Avg_Days_to_Scheduled_NEW"
    },
    {
        "id": "00OEa000007vWiHMAU",
        "name": "Avg Days to Scheduled - Clarity Calls",
        "dev_name": "Avg_Days_to_Scheduled_Clarity_Calls"
    },
    {
        "id": "00OEa000007vWiJMAU",
        "name": "Avg Days to Scheduled - PepEx",
        "dev_name": "Avg_Days_to_Scheduled_PepEx"
    }
]

print("\nReports to be updated:")
for r in reports:
    print(f"  {r['name']} ({r['id']})")

print("\nNote: Direct REST API updates to reports are complex.")
print("Recommended: Use interactive Report Builder in Salesforce UI.")
print("URL pattern: https://sandbox.my.salesforce.com/lightning/r/Report/[ID]/view")
