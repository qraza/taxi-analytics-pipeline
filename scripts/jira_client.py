"""Jira REST API v3 client for the jira-agent workflow.

Workflow-only: no CLI, dashboard, or reporting code imports this module.
"""

import os

import httpx

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

APPROVED_MARKER = "approved"


def _require_config() -> None:
    missing = [
        name
        for name, value in [
            ("JIRA_BASE_URL", JIRA_BASE_URL),
            ("JIRA_EMAIL", JIRA_EMAIL),
            ("JIRA_API_TOKEN", JIRA_API_TOKEN),
        ]
        if not value
    ]
    if missing:
        raise ValueError(
            "Missing required Jira config: " + ", ".join(missing) + " (set in the "
            "environment or a .env file — see .env.example)."
        )


def adf_to_text(node) -> str:
    """Flatten an Atlassian Document Format node (or None) to plain text."""
    if not node:
        return ""

    node_type = node.get("type")

    if node_type == "text":
        return node.get("text", "")
    if node_type == "hardBreak":
        return "\n"
    if node_type in ("mention", "emoji"):
        attrs = node.get("attrs", {})
        return attrs.get("text") or attrs.get("shortName", "")

    children = "".join(adf_to_text(child) for child in node.get("content", []))

    if node_type == "listItem":
        return f"- {children}\n"
    if node_type in ("paragraph", "heading", "codeBlock", "blockquote"):
        return f"{children}\n"
    return children


def text_to_adf(text: str) -> dict:
    """Build a minimal ADF doc (one paragraph per line) for posting a comment."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}] if line else [],
            }
            for line in text.split("\n")
        ],
    }


def get_issue(issue_key: str) -> dict:
    """Fetch summary, description, and the full ordered comment list for an issue."""
    _require_config()

    response = httpx.get(
        f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/issue/{issue_key}",
        params={"fields": "summary,description,comment"},
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        timeout=30.0,
    )
    response.raise_for_status()
    fields = response.json()["fields"]

    comments = [
        {
            "author": comment.get("author", {}).get("displayName", "Unknown"),
            "body": adf_to_text(comment.get("body")).strip(),
            "created": comment.get("created", ""),
        }
        for comment in fields.get("comment", {}).get("comments", [])
    ]

    return {
        "key": issue_key,
        "summary": fields.get("summary", ""),
        "description": adf_to_text(fields.get("description")).strip(),
        "comments": comments,
    }


def post_comment(issue_key: str, body: str) -> dict:
    """Post a plain-text comment back to a Jira issue."""
    _require_config()

    response = httpx.post(
        f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/issue/{issue_key}/comment",
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        json={"body": text_to_adf(body)},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def find_request_to_implement(issue: dict) -> str:
    """The comment immediately preceding the 'Approved' comment, or the description.

    Falls back to the most recent comment if there are comments but none reads
    exactly "Approved" (the workflow is only meant to fire after that comment
    exists, but a manual workflow_dispatch test run may not have one).
    """
    comments = issue["comments"]
    if not comments:
        return issue["description"]

    for i in range(len(comments) - 1, -1, -1):
        if comments[i]["body"].strip().lower() == APPROVED_MARKER:
            return comments[i - 1]["body"] if i > 0 else issue["description"]

    return comments[-1]["body"]


def build_prompt(issue: dict) -> str:
    """Build the full instructional prompt for the Claude Code agent."""
    request = find_request_to_implement(issue)

    thread = (
        "\n".join(
            f"[{comment['created']}] {comment['author']}: {comment['body']}"
            for comment in issue["comments"]
        )
        or "(no comments)"
    )

    branch = f"jira/{issue['key']}"

    return f"""You are implementing a change requested via Jira ticket {issue["key"]}.

Ticket summary: {issue["summary"]}

Ticket description:
{issue["description"] or "(no description)"}

Full comment thread, oldest first:
{thread}

Implement the following request (the stakeholder comment immediately preceding the
"Approved" comment, or the ticket description if there are no comments):

{request}

Instructions:
- Follow the conventions in CLAUDE.md.
- Work on a branch named {branch}, created from main.
- Before considering the work done, run: `ruff check cli/ scripts/ reporting/`, then
  `pytest tests/ -v --ignore=tests/fixtures`, then (loading the CI fixture first if the
  database doesn't have it yet: `python scripts/load_raw.py --source ci`)
  `dbt build --project-dir dbt_project --profiles-dir .ci`.
- If any of those checks fail, stop and explain the failure instead of proceeding —
  do not open a pull request.
- Only once all checks pass: commit your changes on {branch}, push it, and open a pull
  request against main (e.g. via `gh pr create`) describing the change and confirming
  the checks passed.
"""
