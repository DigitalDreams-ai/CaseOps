"""
Azure DevOps escalation integration for CaseOps.

Creates ADO work items (Bug or User Story) from Jira tickets and links them back.
Reads Jira data from local sync outputs.
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional
import requests


class ADOClient:
    """Azure DevOps REST API client."""

    def __init__(self, org: str, project: str, pat: str):
        self.org = org
        self.project = project
        self.pat = pat
        self.base_url = f"https://dev.azure.com/{org}/{project}/_apis"
        self.auth = self._make_auth_header(pat)

    def _make_auth_header(self, pat: str) -> dict:
        """Create Basic auth header from PAT."""
        encoded = base64.b64encode(f":{pat}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def create_work_item(
        self,
        work_item_type: str,
        title: str,
        description: str,
        fields: Optional[dict] = None,
    ) -> dict:
        """Create a work item (Bug or User Story)."""
        url = f"{self.base_url}/wit/workitems/${work_item_type}?api-version=7.0"
        headers = {
            **self.auth,
            "Content-Type": "application/json-patch+json",
        }

        # Build patch operations for work item creation
        ops = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": description},
        ]

        if fields:
            for field_path, value in fields.items():
                ops.append({"op": "add", "path": field_path, "value": value})

        resp = requests.patch(url, json=ops, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def get_work_item(self, work_item_id: int) -> dict:
        """Fetch work item details."""
        url = f"{self.base_url}/wit/workitems/{work_item_id}?api-version=7.0"
        resp = requests.get(url, headers=self.auth)
        resp.raise_for_status()
        return resp.json()


class JiraClient:
    """Jira REST API client (for updating ticket after ADO creation)."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.auth = (email, api_token)

    def update_issue_status(self, key: str, status: str) -> None:
        """Update issue status."""
        url = f"{self.base_url}/rest/api/3/issue/{key}/transitions"
        # Get available transitions
        resp = requests.get(url, auth=self.auth)
        resp.raise_for_status()
        transitions = resp.json().get("transitions", [])

        # Find transition ID by target status
        target_transition = None
        for t in transitions:
            if t["to"]["name"].lower() == status.lower():
                target_transition = t["id"]
                break

        if not target_transition:
            raise ValueError(
                f"No transition to '{status}' found. Available: {[t['to']['name'] for t in transitions]}"
            )

        # Apply transition
        resp = requests.post(
            url,
            json={"transition": {"id": target_transition}},
            auth=self.auth,
        )
        resp.raise_for_status()

    def add_link(self, key: str, link_text: str, link_url: str) -> None:
        """Add a link (external) to the issue."""
        url = f"{self.base_url}/rest/api/3/issue/{key}/remotelink"
        payload = {
            "object": {
                "title": link_text,
                "url": link_url,
            }
        }
        resp = requests.post(url, json=payload, auth=self.auth)
        resp.raise_for_status()

    def add_comment(self, key: str, comment: str) -> None:
        """Add a comment to the issue."""
        url = f"{self.base_url}/rest/api/3/issue/{key}/comments"
        payload = {"body": {"content": [{"type": "text", "text": comment}]}}
        resp = requests.post(url, json=payload, auth=self.auth)
        resp.raise_for_status()


def load_jira_data(jira_dir: Path, key: str) -> dict:
    """Load Jira issue data from local sync output."""
    raw_path = jira_dir / "raw" / f"{key}.json"
    summary_path = jira_dir / "summary" / f"{key}.md"

    if not raw_path.exists():
        raise FileNotFoundError(f"Jira raw data not found: {raw_path}")

    with raw_path.open(encoding="utf-8") as f:
        raw_data = json.load(f)

    summary_text = ""
    if summary_path.exists():
        with summary_path.open(encoding="utf-8") as f:
            summary_text = f.read()

    return {"raw": raw_data, "summary_text": summary_text}


def extract_ado_content(jira_data: dict, key: str) -> tuple[str, str]:
    """Extract title and description for ADO from Jira data."""
    raw = jira_data["raw"]
    summary_text = jira_data["summary_text"]

    # Title: [Issue Summary] (HEAL ####)
    summary = raw.get("fields", {}).get("summary", "No summary")
    title = f"{summary} ({key})"

    # Description: structured content from summary + raw data
    parts = [
        f"# Jira: {key}",
        f"## Summary\n{summary}",
    ]

    # Add reproduction steps if available in summary text
    if "Reproduction Steps" in summary_text:
        idx = summary_text.find("Reproduction Steps")
        end_idx = summary_text.find("##", idx + 1)
        if end_idx == -1:
            repro = summary_text[idx:]
        else:
            repro = summary_text[idx:end_idx]
        parts.append(f"## {repro}")

    # Add expected behavior if available
    if "Expected behavior" in summary_text:
        idx = summary_text.find("Expected behavior")
        end_idx = summary_text.find("##", idx + 1)
        if end_idx == -1:
            expected = summary_text[idx:]
        else:
            expected = summary_text[idx:end_idx]
        parts.append(f"## {expected}")

    # Add environment/version if available
    description = raw.get("fields", {}).get("description", "")
    if description:
        parts.append(f"## Environment\n{description}")

    # Add attachments note if any
    attachments = raw.get("fields", {}).get("attachment", [])
    if attachments:
        parts.append(f"## Attachments (see Jira)\n{len(attachments)} file(s) attached")

    description = "\n\n".join(parts)
    return title, description


def escalate_to_ado(
    jira_key: str,
    work_item_type: str,
    jira_dir: Path = None,
    dry_run: bool = False,
) -> dict:
    """
    Escalate a Jira issue to Azure DevOps.

    Args:
        jira_key: Jira issue key (e.g., HEAL-12345)
        work_item_type: "Bug" or "User Story"
        jira_dir: Path to jira outputs directory (default: outputs/jira)
        dry_run: If True, return preview without creating ADO item

    Returns:
        dict with ado_id, ado_url, status
    """
    if jira_dir is None:
        jira_dir = Path.cwd() / "outputs" / "jira"

    # Load environment
    ado_org = os.getenv("AZURE_DEVOPS_ORG")
    ado_project = os.getenv("AZURE_DEVOPS_PROJECT")
    ado_pat = os.getenv("AZURE_DEVOPS_PAT")
    jira_base_url = os.getenv("JIRA_BASE_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_api_token = os.getenv("JIRA_API_TOKEN")

    if not all([ado_org, ado_project, ado_pat]):
        raise ValueError(
            "Missing Azure DevOps config. Set AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_PAT in .env.jira"
        )

    if not all([jira_base_url, jira_email, jira_api_token]):
        raise ValueError(
            "Missing Jira config. Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env.jira"
        )

    # Load Jira data
    jira_data = load_jira_data(jira_dir, jira_key)
    title, description = extract_ado_content(jira_data, jira_key)

    if dry_run:
        return {
            "status": "preview",
            "title": title,
            "description": description,
            "work_item_type": work_item_type,
        }

    # Create ADO work item
    ado_client = ADOClient(ado_org, ado_project, ado_pat)
    extra_fields = {
        "/fields/System.AssignedTo": "Sean Bingham <sbingham@10xhealthsystem.com>"
    }

    work_item = ado_client.create_work_item(
        work_item_type=work_item_type,
        title=title,
        description=description,
        fields=extra_fields,
    )

    ado_id = work_item["id"]
    ado_url = work_item["_links"]["self"]["href"]

    # Link back to Jira and update status
    jira_client = JiraClient(jira_base_url, jira_email, jira_api_token)
    try:
        jira_client.add_link(
            jira_key,
            f"ADO Work Item {ado_id}",
            ado_url,
        )
    except Exception as e:
        print(f"Warning: Failed to add ADO link to Jira: {e}")

    try:
        jira_client.update_issue_status(jira_key, "Escalated")
    except Exception as e:
        print(f"Warning: Failed to update Jira status: {e}")

    try:
        jira_client.add_comment(
            jira_key,
            f"Escalated to Azure DevOps: [Work Item {ado_id}]({ado_url})",
        )
    except Exception as e:
        print(f"Warning: Failed to add comment: {e}")

    return {
        "status": "success",
        "jira_key": jira_key,
        "ado_id": ado_id,
        "ado_url": ado_url,
        "work_item_type": work_item_type,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python ado_integration.py <JIRA_KEY> <Bug|UserStory> [--dry-run]")
        sys.exit(1)

    key = sys.argv[1]
    work_type = sys.argv[2]
    dry_run = "--dry-run" in sys.argv

    result = escalate_to_ado(key, work_type, dry_run=dry_run)
    print(json.dumps(result, indent=2))
