#!/usr/bin/env python3
"""List open GitLab merge requests and render them as Markdown."""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


TIMEOUT_SECONDS = 30
USER_AGENT = "gitlab-util/1"
PAGE_SIZE = 100


class GitLabError(Exception):
    """An error that can be shown safely to the user."""


def environment_value(name: str) -> str:
    """Return a required, non-empty environment variable."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise GitLabError(f"required environment variable {name} is not set")
    return value


def normalize_gitlab_url(value: str) -> str:
    """Validate and normalize a GitLab instance root URL."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise GitLabError(f"invalid GITLAB_URL: {error}") from error

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise GitLabError(
            "GITLAB_URL must be an HTTPS GitLab instance root such as "
            "https://gitlab.com"
        )

    return urlunsplit(("https", parsed.hostname, parsed.path.rstrip("/"), "", ""))


def project_name(value: str) -> str:
    """Validate a GitLab project name supplied on the command line."""
    normalized = value.strip()
    if not normalized or "/" in normalized or normalized in (".", ".."):
        raise argparse.ArgumentTypeError(
            "project must be a name only, such as my-project"
        )
    return normalized


def group_path(value: str) -> str:
    """Validate and normalize a GitLab group path from the environment."""
    normalized = value.strip().strip("/")
    if not normalized or any(part in (".", "..") for part in normalized.split("/")):
        raise GitLabError(
            "GITLAB_GROUP must be a GitLab group path such as my-group"
        )
    return normalized


def http_error_detail(error: HTTPError) -> str:
    """Return a concise response detail without exposing credentials."""
    try:
        body = error.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not body:
        return ""
    return body[:500]


def read_json(request: Request) -> tuple[Any, Any]:
    """Send one request and decode its JSON response and headers."""
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            import json

            return json.load(response), response.headers
    except HTTPError as error:
        detail = http_error_detail(error)
        message = f"GitLab returned HTTP {error.code} {error.reason}"
        if detail:
            message += f": {detail}"
        raise GitLabError(message) from error
    except URLError as error:
        raise GitLabError(f"could not reach GitLab: {error.reason}") from error
    except TimeoutError as error:
        raise GitLabError(
            f"GitLab did not respond within {TIMEOUT_SECONDS} seconds"
        ) from error
    except (ValueError, UnicodeDecodeError) as error:
        raise GitLabError("GitLab returned a response that was not valid JSON") from error


def fetch_open_merge_requests(
    gitlab_url: str, token: str, repository: str
) -> list[dict[str, Any]]:
    """Fetch every open merge request for a project."""
    encoded_project = quote(repository, safe="")
    merge_requests: list[dict[str, Any]] = []
    page = "1"

    while page:
        query = urlencode(
            {
                "state": "opened",
                "order_by": "updated_at",
                "sort": "desc",
                "per_page": PAGE_SIZE,
                "page": page,
            }
        )
        request = Request(
            f"{gitlab_url}/api/v4/projects/{encoded_project}/merge_requests?{query}",
            headers={
                "Accept": "application/json",
                "PRIVATE-TOKEN": token,
                "User-Agent": USER_AGENT,
            },
        )
        payload, headers = read_json(request)
        if not isinstance(payload, list) or any(
            not isinstance(item, dict) for item in payload
        ):
            raise GitLabError("GitLab returned an unexpected merge request response")
        merge_requests.extend(payload)
        page = headers.get("X-Next-Page", "").strip()

    return merge_requests


def heading_text(value: str) -> str:
    """Escape Markdown heading syntax while preserving the visible title."""
    return re.sub(r"^(\s*)(#+)(\s+)", r"\1\\\2\3", value.strip())


def humanize_state(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.replace("_", " ").capitalize()


def author_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("name", "username"):
        name = value.get(key)
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def local_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    localized = timestamp.astimezone()
    timezone = localized.tzname() or ""
    formatted = localized.strftime("%B %-d, %Y at %-I:%M %p")
    return f"{formatted} {timezone}".rstrip()


def pipeline_markdown(pipeline: Any) -> str:
    """Render the status and link for the merge request's head pipeline."""
    if not isinstance(pipeline, dict):
        return "Not run"

    status = pipeline.get("status")
    if not isinstance(status, str) or not status.strip():
        status_text = "Unknown"
    else:
        normalized_status = status.strip().lower()
        status_text = {
            "created": "Building",
            "waiting_for_resource": "Waiting for resource",
            "preparing": "Preparing",
            "pending": "Pending",
            "running": "Running",
            "success": "Passed",
            "failed": "Failed",
            "canceled": "Canceled",
            "skipped": "Skipped",
            "manual": "Manual action required",
            "scheduled": "Scheduled",
        }.get(normalized_status, humanize_state(normalized_status) or "Unknown")

    url = pipeline.get("web_url")
    if isinstance(url, str) and url.strip():
        return f"[{status_text}](<{url.strip()}>)"
    return status_text


def merge_request_markdown(merge_request: dict[str, Any]) -> str:
    """Render one merge request as Markdown."""
    title = merge_request.get("title")
    if not isinstance(title, str) or not title.strip():
        title = "Untitled merge request"

    url = merge_request.get("web_url")
    lines = [f"## {heading_text(title)}"]
    if isinstance(url, str) and url.strip():
        lines.append(f"[View](<{url.strip()}>)")

    fields = (
        ("State", humanize_state(merge_request.get("state"))),
        ("Pipeline", pipeline_markdown(merge_request.get("head_pipeline"))),
        ("Author", author_name(merge_request.get("author"))),
        ("Last updated", local_timestamp(merge_request.get("updated_at"))),
    )
    lines.extend(f"**{label}:** {value}" for label, value in fields if value is not None)
    return "  \n".join(lines)


def list_markdown(repository: str, merge_requests: list[dict[str, Any]]) -> str:
    """Render a repository's merge requests as Markdown."""
    canonical_repository = repository
    for merge_request in merge_requests:
        project = merge_request.get("project")
        if isinstance(project, dict):
            path = project.get("path_with_namespace")
            if isinstance(path, str) and path.strip():
                canonical_repository = path.strip()
                break

    sections = [f"# {heading_text(canonical_repository)}"]
    if merge_requests:
        sections.extend(merge_request_markdown(item) for item in merge_requests)
    else:
        sections.append("_No open merge requests._")
    return "\n\n".join(sections) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Perform GitLab operations.")
    operations = parser.add_subparsers(dest="operation", required=True)

    list_parser = operations.add_parser(
        "list", help="List open merge requests as Markdown."
    )
    list_parser.add_argument(
        "project",
        nargs="?",
        type=project_name,
        help="GitLab project name only, e.g. my-project",
    )
    args = parser.parse_args(argv)
    if args.operation == "list" and args.project is None:
        list_parser.error("project is required")
    return args


def list_merge_requests_markdown(project: str) -> str:
    """Fetch and render a project's open merge requests."""
    gitlab_url = normalize_gitlab_url(
        os.environ.get("GITLAB_URL", "https://gitlab.com")
    )
    token = environment_value("GITLAB_TOKEN")
    group = group_path(environment_value("GITLAB_GROUP"))
    repository = f"{group}/{project}"
    merge_requests = fetch_open_merge_requests(gitlab_url, token, repository)
    return list_markdown(repository, merge_requests)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.operation == "list":
            sys.stdout.write(list_merge_requests_markdown(args.project))
    except GitLabError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
