"""Update Opportunity Field History reports to include new formula fields."""
import json
import subprocess
import sys
import os
from pathlib import Path
import re

def run_cmd(cmd):
    """Run shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=os.getcwd())
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
    return result.stdout.strip(), result.returncode

def query_reports(org):
    """Query for Avg Days to Scheduled reports."""
    query = "SELECT Id, DeveloperName, Name FROM Report WHERE Name LIKE 'Avg Days%' ORDER BY Name"
    cmd = f'sf data query --query "{query}" --target-org {org} --json'
    output, code = run_cmd(cmd)
    if code == 0:
        try:
            data = json.loads(output)
            return data.get('result', {}).get('records', [])
        except json.JSONDecodeError:
            print("Failed to parse JSON response")
    return []

# Target org
org = "10xhealth-sean"

# Query for reports
print("Querying Sandbox for Avg Days to Scheduled reports...")
reports = query_reports(org)

print("\nReports found in Sandbox:")
report_map = {}
for report in reports:
    report_id = report.get('Id')
    name = report.get('Name')
    dev_name = report.get('DeveloperName')
    print(f"  {name}")
    print(f"    ID: {report_id}")
    print(f"    DeveloperName: {dev_name}")
    report_map[dev_name] = {
        'id': report_id,
        'name': name
    }

print("\nNote: Salesforce reports are typically NOT modifiable via metadata API.")
print("The Report Builder requires UI-based column additions.")
print("Recommendation: Use selenium-based automation or direct Salesforce REST API.")
