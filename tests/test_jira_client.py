import pytest

from scripts.jira_client import (
    adf_to_text,
    build_prompt,
    find_refinement_comments,
    get_issue,
    post_comment,
    text_to_adf,
)


@pytest.fixture(autouse=True)
def jira_config(monkeypatch):
    """All tests get a fake, valid config unless a test overrides it."""
    monkeypatch.setattr("scripts.jira_client.JIRA_BASE_URL", "https://fake.atlassian.net")
    monkeypatch.setattr("scripts.jira_client.JIRA_EMAIL", "fake@example.com")
    monkeypatch.setattr("scripts.jira_client.JIRA_API_TOKEN", "fake-token")


# --- ADF flattening -----------------------------------------------------------------


def test_adf_to_text_none_returns_empty_string():
    assert adf_to_text(None) == ""


def test_adf_to_text_flattens_simple_paragraph():
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}
        ],
    }
    assert adf_to_text(doc).strip() == "Hello world"


def test_adf_to_text_joins_multiple_paragraphs_with_newlines():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
        ],
    }
    assert adf_to_text(doc).strip() == "First\nSecond"


def test_adf_to_text_handles_hard_break():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Line one"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "Line two"},
                ],
            }
        ],
    }
    assert adf_to_text(doc).strip() == "Line one\nLine two"


def test_adf_to_text_handles_bullet_list_items():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "First item"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Second item"}],
                            }
                        ],
                    },
                ],
            }
        ],
    }
    text = adf_to_text(doc)
    assert "- First item" in text
    assert "- Second item" in text


def test_adf_to_text_handles_mention():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"text": "@Jane Doe"}},
                    {"type": "text", "text": " please review"},
                ],
            }
        ],
    }
    assert adf_to_text(doc).strip() == "@Jane Doe please review"


def test_text_to_adf_builds_one_paragraph_per_line():
    adf = text_to_adf("First line\nSecond line")
    assert adf["type"] == "doc"
    assert len(adf["content"]) == 2
    assert adf["content"][0]["content"][0]["text"] == "First line"
    assert adf["content"][1]["content"][0]["text"] == "Second line"


def test_text_to_adf_handles_blank_lines():
    adf = text_to_adf("First\n\nThird")
    assert adf["content"][1]["content"] == []


# --- get_issue / post_comment (Jira API mocked) --------------------------------------


def test_get_issue_requires_config(monkeypatch):
    monkeypatch.setattr("scripts.jira_client.JIRA_BASE_URL", None)

    with pytest.raises(ValueError, match="JIRA_BASE_URL"):
        get_issue("PROJ-1")


def test_get_issue_parses_summary_description_and_comments(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "fields": {
                    "summary": "Fix the thing",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Do the thing"}],
                            }
                        ],
                    },
                    "comment": {
                        "comments": [
                            {
                                "author": {"displayName": "Alice"},
                                "body": {
                                    "type": "doc",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Please add X"}
                                            ],
                                        }
                                    ],
                                },
                                "created": "2026-07-01T10:00:00.000+0000",
                            },
                            {
                                "author": {"displayName": "Bob"},
                                "body": {
                                    "type": "doc",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Approved"}
                                            ],
                                        }
                                    ],
                                },
                                "created": "2026-07-02T10:00:00.000+0000",
                            },
                        ]
                    },
                }
            }

    captured = {}

    def fake_get(url, params, auth, timeout):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr("scripts.jira_client.httpx.get", fake_get)

    issue = get_issue("PROJ-1")

    assert issue["key"] == "PROJ-1"
    assert issue["summary"] == "Fix the thing"
    assert issue["description"] == "Do the thing"
    assert [c["author"] for c in issue["comments"]] == ["Alice", "Bob"]
    assert issue["comments"][0]["body"] == "Please add X"
    assert captured["url"].endswith("/rest/api/3/issue/PROJ-1")
    assert captured["params"] == {"fields": "summary,description,comment"}


def test_post_comment_sends_adf_body(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "123"}

    captured = {}

    def fake_post(url, auth, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("scripts.jira_client.httpx.post", fake_post)

    result = post_comment("PROJ-1", "PR opened: https://example.com/pr/1")

    assert result == {"id": "123"}
    assert captured["url"].endswith("/rest/api/3/issue/PROJ-1/comment")
    assert captured["json"]["body"]["type"] == "doc"
    assert captured["json"]["body"]["content"][0]["content"][0]["text"] == (
        "PR opened: https://example.com/pr/1"
    )


# --- prompt-building logic ------------------------------------------------------------


def test_find_refinements_empty_when_no_comments():
    issue = {"key": "PROJ-1", "summary": "s", "description": "the description", "comments": []}
    assert find_refinement_comments(issue) == []


def test_find_refinements_uses_comment_before_approved():
    issue = {
        "key": "PROJ-1",
        "summary": "s",
        "description": "d",
        "comments": [
            {"author": "Alice", "body": "Please add X", "created": "t1"},
            {"author": "Manager", "body": "Approved", "created": "t2"},
        ],
    }
    bodies = [c["body"] for c in find_refinement_comments(issue)]
    assert bodies == ["Please add X"]


def test_find_refinements_is_case_insensitive_on_approved_marker():
    issue = {
        "key": "PROJ-1",
        "summary": "s",
        "description": "d",
        "comments": [
            {"author": "Alice", "body": "Please add X", "created": "t1"},
            {"author": "Manager", "body": "  approved  ", "created": "t2"},
        ],
    }
    bodies = [c["body"] for c in find_refinement_comments(issue)]
    assert bodies == ["Please add X"]


def test_find_refinements_are_cumulative_when_multiple_approved_present():
    issue = {
        "key": "PROJ-1",
        "summary": "s",
        "description": "d",
        "comments": [
            {"author": "Alice", "body": "Please add X", "created": "t1"},
            {"author": "Manager", "body": "Approved", "created": "t2"},
            {"author": "Alice", "body": "Please add Y instead", "created": "t3"},
            {"author": "Manager", "body": "Approved", "created": "t4"},
        ],
    }
    bodies = [c["body"] for c in find_refinement_comments(issue)]
    assert bodies == ["Please add X", "Please add Y instead"]


def test_find_refinements_empty_when_approved_is_first_comment():
    issue = {
        "key": "PROJ-1",
        "summary": "s",
        "description": "the description",
        "comments": [{"author": "Manager", "body": "Approved", "created": "t1"}],
    }
    assert find_refinement_comments(issue) == []


def test_find_refinements_uses_all_comments_when_no_approved_present():
    issue = {
        "key": "PROJ-1",
        "summary": "s",
        "description": "d",
        "comments": [
            {"author": "Alice", "body": "Please add X", "created": "t1"},
            {"author": "Bob", "body": "Actually add Y", "created": "t2"},
        ],
    }
    bodies = [c["body"] for c in find_refinement_comments(issue)]
    assert bodies == ["Please add X", "Actually add Y"]


def test_build_prompt_includes_key_summary_description_and_refinements():
    issue = {
        "key": "PROJ-42",
        "summary": "Add a widget",
        "description": "We need a widget",
        "comments": [
            {"author": "Alice", "body": "Add a blue widget", "created": "t1"},
            {"author": "Manager", "body": "Approved", "created": "t2"},
        ],
    }
    prompt = build_prompt(issue)

    assert "PROJ-42" in prompt
    assert "Add a widget" in prompt
    assert "We need a widget" in prompt
    assert "jira/PROJ-42" in prompt
    assert "- Add a blue widget" in prompt
    assert "[t1] Alice: Add a blue widget" in prompt
    assert "ruff check cli/ scripts/ reporting/" in prompt
    assert "dbt build" in prompt
    assert "update README.md and CLAUDE.md" in prompt


def test_build_prompt_with_no_comments_uses_description_with_no_refinements():
    issue = {"key": "PROJ-7", "summary": "s", "description": "the description", "comments": []}
    prompt = build_prompt(issue)

    assert "the description" in prompt
    assert "(no comments)" in prompt
    assert "implement the ticket description as-is" in prompt
