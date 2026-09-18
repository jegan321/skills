#!/usr/bin/env python3
"""Perform supported Jira operations and emit their results."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


TIMEOUT_SECONDS = 30
USER_AGENT = "jira-util/1"
ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]+$")
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIRECTORY = PROJECT_ROOT / "data" / "jira" / "issues"
CUSTOM_FIELDS = {
    "Acceptance criteria": (("acceptance criteria",), "customfield_10076"),
    "Location of change": (("location of change",), "customfield_10077"),
    "Notes for QA": (("notes for qa", "qa notes"), "customfield_10068"),
    "Technical notes": (("technical notes",), "customfield_10083"),
    "Required permissions": (
        ("required permissions", "required permission", "permissions required"),
        None,
    ),
}


class JiraError(Exception):
    """An error that can be shown safely to the user."""


def issue_key(value: str) -> str:
    """Validate and normalize a Jira issue key supplied on the command line."""
    normalized = value.upper()
    if not ISSUE_KEY_PATTERN.fullmatch(normalized):
        raise argparse.ArgumentTypeError(
            "issue key must look like WTF-123 (letters, digits, or underscores "
            "before the hyphen; digits after it)"
        )
    return normalized


def environment_value(name: str) -> str:
    """Return a required, non-empty environment variable."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise JiraError(f"required environment variable {name} is not set")
    return value


def normalize_site_url(value: str) -> str:
    """Validate and normalize a Jira Cloud site root URL."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise JiraError(f"invalid JIRA_SITE_URL: {error}") from error

    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".atlassian.net")
        or hostname == ".atlassian.net"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise JiraError(
            "JIRA_SITE_URL must be an HTTPS Atlassian site root such as "
            "https://example.atlassian.net"
        )

    return urlunsplit(("https", hostname, "", "", ""))


def read_json(request: Request) -> Any:
    """Send one request and decode its JSON response."""
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except HTTPError as error:
        detail = http_error_detail(error)
        message = f"Jira returned HTTP {error.code} {error.reason}"
        if detail:
            message += f": {detail}"
        raise JiraError(message) from error
    except URLError as error:
        raise JiraError(f"could not reach Jira: {error.reason}") from error
    except TimeoutError as error:
        raise JiraError(
            f"Jira did not respond within {TIMEOUT_SECONDS} seconds"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise JiraError("Jira returned a response that was not valid JSON") from error


def http_error_detail(error: HTTPError) -> str:
    """Extract a concise Jira error without exposing request credentials."""
    try:
        payload = json.load(error)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return ""

    if not isinstance(payload, dict):
        return ""

    messages: list[str] = []
    error_messages = payload.get("errorMessages")
    if isinstance(error_messages, list):
        messages.extend(str(message) for message in error_messages)

    errors = payload.get("errors")
    if isinstance(errors, dict):
        messages.extend(f"{field}: {message}" for field, message in errors.items())

    return "; ".join(messages)


def discover_cloud_id(site_url: str) -> str:
    """Discover the Atlassian cloud ID associated with a Jira site."""
    request = Request(
        f"{site_url}/_edge/tenant_info",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    payload = read_json(request)
    cloud_id = payload.get("cloudId") if isinstance(payload, dict) else None
    if not isinstance(cloud_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", cloud_id):
        raise JiraError("Jira tenant information did not contain a valid cloudId")
    return cloud_id


def fetch_issue(cloud_id: str, email: str, token: str, key: str) -> dict[str, Any]:
    """Fetch every field available for one Jira issue."""
    credentials = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
    query = urlencode({"fields": "*all", "expand": "names"})
    url = (
        f"https://api.atlassian.com/ex/jira/{quote(cloud_id, safe='')}"
        f"/rest/api/3/issue/{quote(key, safe='')}?{query}"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Basic {credentials}",
            "User-Agent": USER_AGENT,
        },
    )
    payload = read_json(request)
    if not isinstance(payload, dict):
        raise JiraError("Jira returned an unexpected issue response")
    return payload


def fetch_comments(
    cloud_id: str, email: str, token: str, key: str
) -> dict[str, Any]:
    """Fetch every comment for one Jira issue, following pagination."""
    credentials = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
    comments: list[dict[str, Any]] = []
    start_at = 0

    while True:
        query = urlencode(
            {"startAt": start_at, "maxResults": 100, "orderBy": "created"}
        )
        url = (
            f"https://api.atlassian.com/ex/jira/{quote(cloud_id, safe='')}"
            f"/rest/api/3/issue/{quote(key, safe='')}/comment?{query}"
        )
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {credentials}",
                "User-Agent": USER_AGENT,
            },
        )
        payload = read_json(request)
        if not isinstance(payload, dict) or not isinstance(
            payload.get("comments"), list
        ):
            raise JiraError("Jira returned an unexpected comments response")

        page = [
            comment
            for comment in payload["comments"]
            if isinstance(comment, dict)
        ]
        comments.extend(page)
        total = payload.get("total")
        if not page or (isinstance(total, int) and len(comments) >= total):
            break
        start_at += len(payload["comments"])

    return {"comments": comments, "total": len(comments)}


def inline_markdown(node: Any) -> str:
    """Convert an inline Atlassian Document Format node to Markdown."""
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    if node_type == "hardBreak":
        return "  \n"
    if node_type == "mention":
        return str(node.get("attrs", {}).get("text", ""))
    if node_type == "emoji":
        attrs = node.get("attrs", {})
        return str(attrs.get("text") or attrs.get("shortName") or "")
    if node_type == "inlineCard":
        url = str(node.get("attrs", {}).get("url", ""))
        return f"[{url}]({url})" if url else ""

    text = str(node.get("text", ""))
    if node_type != "text":
        text += "".join(inline_markdown(child) for child in node.get("content", []))
        return text

    text = text.replace("\n", "  \n")
    for mark in node.get("marks", []):
        mark_type = mark.get("type")
        if mark_type == "code":
            delimiter = "``" if "`" in text else "`"
            text = f"{delimiter}{text}{delimiter}"
        elif mark_type == "strong":
            text = f"**{text}**"
        elif mark_type == "em":
            text = f"*{text}*"
        elif mark_type == "strike":
            text = f"~~{text}~~"
        elif mark_type == "link":
            href = str(mark.get("attrs", {}).get("href", ""))
            if href:
                text = f"[{text}]({href})"
    return text


def list_markdown(node: dict[str, Any], indent: int) -> str:
    """Convert an ADF bullet or ordered list, including nested lists."""
    ordered = node.get("type") == "orderedList"
    number = node.get("attrs", {}).get("order", 1)
    if not isinstance(number, int):
        number = 1
    lines: list[str] = []

    for offset, item in enumerate(node.get("content", [])):
        if not isinstance(item, dict):
            continue
        children = item.get("content", [])
        first_block = children[0] if children else {}
        first_text = block_markdown(first_block, indent + 1).strip()
        marker = f"{number + offset}." if ordered else "-"
        prefix = "    " * indent + marker + " "
        first_lines = first_text.splitlines() or [""]
        lines.append(prefix + first_lines[0])
        continuation = "    " * (indent + 1)
        lines.extend(continuation + line for line in first_lines[1:])
        for child in children[1:]:
            rendered = block_markdown(child, indent + 1)
            if rendered:
                lines.append(rendered)
    return "\n".join(lines)


def block_markdown(node: Any, indent: int = 0) -> str:
    """Convert a block Atlassian Document Format node to Markdown."""
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    if node_type in ("doc", "panel"):
        return "\n\n".join(
            rendered
            for child in node.get("content", [])
            if (rendered := block_markdown(child, indent))
        )
    if node_type == "paragraph":
        return "".join(inline_markdown(child) for child in node.get("content", []))
    if node_type == "heading":
        level = node.get("attrs", {}).get("level", 1)
        if not isinstance(level, int) or not 1 <= level <= 6:
            level = 1
        content = "".join(
            inline_markdown(child) for child in node.get("content", [])
        )
        return f"{'#' * level} {content}"
    if node_type in ("bulletList", "orderedList"):
        return list_markdown(node, indent)
    if node_type == "blockquote":
        content = "\n\n".join(
            block_markdown(child, indent) for child in node.get("content", [])
        )
        return "\n".join(f"> {line}" for line in content.splitlines())
    if node_type == "codeBlock":
        language = str(node.get("attrs", {}).get("language", ""))
        content = "".join(
            str(child.get("text", ""))
            for child in node.get("content", [])
            if isinstance(child, dict)
        )
        return f"```{language}\n{content}\n```"
    if node_type == "rule":
        return "---"
    return "".join(inline_markdown(child) for child in node.get("content", []))


def value_markdown(value: Any) -> str:
    """Convert a Jira field value to displayable Markdown."""
    if value in (None, "", [], {}):
        return "_Not provided._"
    if isinstance(value, dict) and value.get("type") == "doc":
        return block_markdown(value).strip() or "_Not provided._"
    if isinstance(value, dict):
        for key in ("value", "name", "displayName"):
            if value.get(key):
                return str(value[key])
    if isinstance(value, list):
        values = [value_markdown(item) for item in value]
        present_values = [item for item in values if item != "_Not provided._"]
        return ", ".join(present_values) or "_Not provided._"
    return str(value)


def custom_field_value(
    issue: dict[str, Any], aliases: tuple[str, ...], fallback: str | None
) -> Any:
    """Find a custom field by its Jira name, with a site-specific fallback ID."""
    fields = issue.get("fields", {})
    names = issue.get("names", {})
    if isinstance(fields, dict) and isinstance(names, dict):
        aliases_casefolded = {alias.casefold() for alias in aliases}
        for field_id, name in names.items():
            if isinstance(name, str) and name.casefold() in aliases_casefolded:
                return fields.get(field_id)
    if isinstance(fields, dict) and fallback:
        return fields.get(fallback)
    return None


def comments_markdown(value: Any) -> str:
    """Render a Jira comment collection as Markdown."""
    if isinstance(value, dict):
        comments = value.get("comments", [])
    elif isinstance(value, list):
        comments = value
    else:
        comments = []

    rendered_comments: list[str] = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        author = value_markdown(comment.get("author"))
        created = value_markdown(comment.get("created"))
        body = value_markdown(comment.get("body"))
        rendered_comments.append(
            f"### {author}\n\n**Created:** {created}\n\n{body}"
        )

    return "\n\n".join(rendered_comments) or "_No comments._"


def issue_markdown(issue: dict[str, Any]) -> str:
    """Render only the requested Jira fields as Markdown."""
    fields = issue.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}

    key = value_markdown(issue.get("key"))
    issue_type = value_markdown(fields.get("issuetype"))
    summary = value_markdown(fields.get("summary"))
    labels = value_markdown(fields.get("labels"))

    sections = [
        f"# {key}",
        f"**Issue key:** {key}",
        f"**Issue type:** {issue_type}",
        f"**Summary:** {summary}",
        f"## Description\n\n{value_markdown(fields.get('description'))}",
        f"## Labels\n\n{labels}",
    ]
    for heading, (aliases, fallback) in CUSTOM_FIELDS.items():
        value = custom_field_value(issue, aliases, fallback)
        sections.append(f"## {heading}\n\n{value_markdown(value)}")
    sections.append(f"## Comments\n\n{comments_markdown(fields.get('comment'))}")
    return "\n\n".join(sections) + "\n"


def write_text_atomically(destination: Path, content: str) -> None:
    """Replace a text file only after its complete contents have been written."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Perform Jira Cloud operations.")
    operations = parser.add_subparsers(dest="operation", required=True)

    fetch_parser = operations.add_parser(
        "fetch", help="Fetch selected issue fields as Markdown."
    )
    fetch_parser.add_argument(
        "issue_key", type=issue_key, help="Jira issue key, e.g. WTF-123"
    )
    fetch_parser.add_argument(
        "--output",
        choices=("stdout", "file"),
        default="stdout",
        help="Output destination (default: stdout).",
    )
    return parser.parse_args(argv)


def fetch_issue_markdown(key: str) -> str:
    """Fetch one Jira issue and render its selected fields as Markdown."""
    site_url = normalize_site_url(environment_value("JIRA_SITE_URL"))
    email = environment_value("JIRA_EMAIL")
    token = environment_value("JIRA_API_TOKEN")
    cloud_id = discover_cloud_id(site_url)
    issue = fetch_issue(cloud_id, email, token, key)
    fields = issue.get("fields")
    if not isinstance(fields, dict):
        fields = {}
        issue["fields"] = fields
    fields["comment"] = fetch_comments(cloud_id, email, token, key)
    return issue_markdown(issue)


def main() -> int:
    args = parse_args()
    try:
        if args.operation == "fetch":
            content = fetch_issue_markdown(args.issue_key)
            if args.output == "file":
                destination = OUTPUT_DIRECTORY / f"{args.issue_key}.md"
                write_text_atomically(destination, content)
                print(destination)
            else:
                sys.stdout.write(content)
    except JiraError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: could not write Jira output: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
