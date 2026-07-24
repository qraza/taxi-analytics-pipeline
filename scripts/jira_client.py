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


def find_refinement_comments(issue: dict) -> list[dict]:
    """Stakeholder comments to layer on top of the description, oldest first.

    This is every comment up to and including the one immediately preceding the
    terminal "Approved" comment, with any "Approved" markers themselves filtered out.
    Falls back to the full comment list if there are comments but none reads exactly
    "Approved" (the workflow is only meant to fire after that comment exists, but a
    manual workflow_dispatch test run may not have one).
    """
    comments = issue["comments"]
    if not comments:
        return []

    for i in range(len(comments) - 1, -1, -1):
        if comments[i]["body"].strip().lower() == APPROVED_MARKER:
            refinements = comments[:i]
            break
    else:
        refinements = comments

    return [c for c in refinements if c["body"].strip().lower() != APPROVED_MARKER]


def build_prompt(issue: dict) -> str:
    """Build the full instructional prompt for the Claude Code agent."""
    refinements = find_refinement_comments(issue)

    thread = (
        "\n".join(
            f"[{comment['created']}] {comment['author']}: {comment['body']}"
            for comment in issue["comments"]
        )
        or "(no comments)"
    )

    refinements_block = (
        "\n".join(f"- {c['body']}" for c in refinements)
        if refinements
        else "(none — implement the ticket description as-is)"
    )

    branch = f"jira/{issue['key']}"

    return f"""You are implementing a change requested via Jira ticket {issue["key"]}.

Ticket summary: {issue["summary"]}

Ticket description (the base requirement):
{issue["description"] or "(no description)"}

Full comment thread, oldest first:
{thread}

Stakeholder refinements to incorporate on top of the base requirement, oldest first
(every comment up to and including the most recent one before "Approved"):
{refinements_block}

Implement the ticket description above as the base requirement, then apply each of the
refinements listed on top of it. Where a later refinement conflicts with the
description or an earlier refinement, the most recent one wins.

Instructions:
- Follow the conventions in CLAUDE.md.
- Work on a branch named {branch}, created from main.
- If this change adds or alters a dbt model, a dashboard tab, an interface, a test count, or
  anything else README.md describes, update README.md and CLAUDE.md in the same change — don't
  leave the docs to drift out of sync with the code.
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
